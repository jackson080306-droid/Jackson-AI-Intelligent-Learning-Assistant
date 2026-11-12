"""离线回归测试：只使用临时目录、假密钥和模拟网络。"""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import ai_client
import config
from exporter import export_session
from session_manager import SessionManager


class IsolatedFiles(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        override = patch.object(config, "CONFIG_FILE", self.folder / "config.json")
        override.start()
        self.addCleanup(override.stop)

    def manager(self):
        return SessionManager(self.folder / "sessions.json", self.folder / "legacy.json")


class ConfigTests(IsolatedFiles):
    def test_missing_config_uses_mock_without_creating_file(self):
        self.assertEqual(config.load_config(), config.DEFAULT_CONFIG)
        self.assertFalse(config.CONFIG_FILE.exists())

    def test_legacy_config_is_read_without_rewriting(self):
        original = json.dumps(config.DEFAULT_CONFIG).encode()
        config.CONFIG_FILE.write_bytes(original)
        self.assertEqual(config.load_config(), config.DEFAULT_CONFIG)
        self.assertEqual(config.CONFIG_FILE.read_bytes(), original)

    def test_multiple_profiles_survive_reload(self):
        api = dict(config.DEFAULT_CONFIG, mode="api", api_key="fake-key",
                   base_url="https://example.com", model="demo")
        config.save_profiles({"active_profile": "API", "profiles": {
            "模拟": config.DEFAULT_CONFIG, "API": api,
        }})
        self.assertEqual(config.load_config(), api)
        config.save_config(dict(api, timeout=60))
        loaded = config.load_profiles()
        self.assertEqual(loaded["profiles"]["API"]["timeout"], 60)
        self.assertEqual(loaded["profiles"]["模拟"], config.DEFAULT_CONFIG)

    def test_invalid_settings_are_rejected(self):
        cases = [{"timeout": 0}, {"timeout": True}, {"mode": "unknown"},
                 {"mode": "api"}, {"mode": "api", "api_key": "fake",
                  "base_url": "http://example.com", "model": "demo"}]
        for settings in cases:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                config.validate_config(settings)

    def test_corrupt_file_is_not_overwritten(self):
        config.CONFIG_FILE.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            config.load_config()
        self.assertEqual(config.CONFIG_FILE.read_text(), "{broken")

    def test_failed_replace_preserves_previous_config(self):
        config.save_config(config.DEFAULT_CONFIG)
        previous = config.CONFIG_FILE.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("fake")):
            with self.assertRaises(OSError):
                config.save_config(dict(config.DEFAULT_CONFIG, timeout=60))
        self.assertEqual(config.CONFIG_FILE.read_bytes(), previous)


class SessionTests(IsolatedFiles):
    def test_migration_keeps_legacy_file(self):
        messages = [{"role": "user", "content": "旧问题"}]
        legacy = self.folder / "legacy.json"
        legacy.write_text(json.dumps(messages), encoding="utf-8")
        original = legacy.read_bytes()
        self.assertEqual(self.manager().current_session()["messages"], messages)
        self.assertEqual(legacy.read_bytes(), original)

    def test_sessions_are_isolated_and_selection_persists(self):
        manager = self.manager()
        first = manager.current_session()
        first["messages"].append({"role": "user", "content": "问题"})
        second = manager.create_session("第二个")
        manager.save()
        loaded = self.manager()
        self.assertEqual(loaded.current_session()["id"], second["id"])
        self.assertEqual(loaded.current_session()["messages"], [])
        loaded.select_session(first["id"])
        self.assertEqual(len(loaded.current_session()["messages"]), 1)

    def test_favorite_survives_deletion_and_is_not_duplicated(self):
        manager = self.manager()
        self.assertTrue(manager.add_favorite("问题", "回答"))
        self.assertFalse(manager.add_favorite("问题", "回答"))
        manager.delete_current()
        manager.save()
        self.assertEqual(self.manager().data["favorites"][0]["answer"], "回答")
        self.assertEqual(len(manager.data["sessions"]), 1)

    def test_corrupt_history_is_not_overwritten(self):
        path = self.folder / "sessions.json"
        path.write_text('{"version": 1}', encoding="utf-8")
        previous = path.read_bytes()
        with self.assertRaises(ValueError):
            self.manager()
        self.assertEqual(path.read_bytes(), previous)

    def test_failed_session_save_preserves_disk_history(self):
        manager = self.manager()
        previous = manager.path.read_bytes()
        manager.rename_current("新名字")
        with patch.object(Path, "replace", side_effect=PermissionError("fake")):
            with self.assertRaises(OSError):
                manager.save()
        self.assertEqual(manager.path.read_bytes(), previous)

    def test_long_unicode_message_round_trip_and_export(self):
        manager = self.manager()
        content = "中文问题\nPython 🐍\n" * 10000
        manager.current_session()["messages"].append({"role": "user", "content": content})
        manager.save()
        session = self.manager().current_session()
        self.assertEqual(session["messages"][0]["content"], content)
        for extension in ("txt", "md"):
            target = self.folder / ("export." + extension)
            export_session(session, target)
            self.assertIn(content, target.read_text(encoding="utf-8"))


class APITests(unittest.TestCase):
    settings = dict(config.DEFAULT_CONFIG, mode="api", api_key="fake-secret",
                    base_url="https://example.com", model="demo")
    messages = [{"role": "user", "content": "问题"}]

    def request(self, body):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.BytesIO(body)
        with patch.object(ai_client, "build_opener", return_value=opener):
            return list(ai_client.stream_reply(self.messages, self.settings))

    def test_stream_ignores_reasoning_and_preserves_content(self):
        events = [
            {"choices": [{"delta": {"reasoning_content": "不显示"}}]},
            {"choices": [{"delta": {"content": "你好"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ]
        body = ": heartbeat\n\n" + "".join(
            "data: " + json.dumps(event) + "\n\n" for event in events
        ) + "data: [DONE]\n\n"
        self.assertEqual(self.request(body.encode()), ["你好"])

    def test_broken_streams_are_errors(self):
        cases = [b"data: [DONE]\n\n", b"data: not-json\n\n",
                 b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
                 b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n',
                 b'data: {"error":{"message":"fake-secret"}}\n\n']
        for body in cases:
            with self.subTest(body=body), self.assertRaises(ai_client.APIError) as caught:
                self.request(body)
            self.assertNotIn("fake-secret", str(caught.exception))

    def test_network_errors_are_safe_and_actionable(self):
        cases = [(HTTPError("https://example.com", 401, "fake-secret", {}, None), "认证失败"),
                 (HTTPError("https://example.com", 429, "fake-secret", {}, None), "请求受限"),
                 (TimeoutError("fake-secret"), "超时"),
                 (URLError("fake-secret"), "网络连接失败")]
        for error, hint in cases:
            opener = MagicMock()
            opener.open.side_effect = error
            with self.subTest(hint=hint), patch.object(ai_client, "build_opener", return_value=opener):
                with self.assertRaises(ai_client.APIError) as caught:
                    list(ai_client.stream_reply(self.messages, self.settings))
                self.assertIn(hint, str(caught.exception))
                self.assertNotIn("fake-secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
