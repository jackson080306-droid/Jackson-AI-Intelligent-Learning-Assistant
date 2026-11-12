"""保存多个独立会话，并兼容旧版聊天历史。"""

import json
from pathlib import Path
from uuid import uuid4


DATA_FILE = Path(__file__).resolve().parent / "sessions.json"
LEGACY_FILE = Path(__file__).resolve().parent / "chat_history.json"


def validate_messages(messages):
    """拒绝格式损坏的消息，避免覆盖原始数据。"""
    if not isinstance(messages, list):
        raise ValueError("消息必须是列表。")
    for message in messages:
        if (
            not isinstance(message, dict)
            or message.get("role") not in ("user", "assistant")
            or not isinstance(message.get("content"), str)
        ):
            raise ValueError("消息格式不正确。")


class SessionManager:
    """管理会话身份、当前会话和本地文件。"""

    def __init__(self, path=DATA_FILE, legacy_path=LEGACY_FILE):
        self.path = Path(path)
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as file:
                self.data = json.load(file)
            self.validate()
        else:
            messages = []
            legacy_path = Path(legacy_path)
            if legacy_path.exists():
                with legacy_path.open("r", encoding="utf-8") as file:
                    messages = json.load(file)
                validate_messages(messages)
            session_id = uuid4().hex
            self.data = {
                "version": 1,
                "current_session_id": session_id,
                "sessions": [{"id": session_id, "name": "默认会话", "messages": messages}],
            }
            self.save()

    def validate(self):
        """检查文件结构、唯一 ID 和当前会话是否有效。"""
        if not isinstance(self.data, dict) or self.data.get("version") != 1:
            raise ValueError("会话文件版本或结构不正确。")
        sessions = self.data.get("sessions")
        if not isinstance(sessions, list) or not sessions:
            raise ValueError("至少需要一个会话。")
        identifiers = set()
        for session in sessions:
            if not isinstance(session, dict):
                raise ValueError("会话必须是对象。")
            identifier = session.get("id")
            name = session.get("name")
            if not isinstance(identifier, str) or not identifier or identifier in identifiers:
                raise ValueError("会话 ID 无效或重复。")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("会话名称不能为空。")
            identifiers.add(identifier)
            validate_messages(session.get("messages"))
        if self.data.get("current_session_id") not in identifiers:
            raise ValueError("当前会话不存在。")

    def current_session(self):
        """取得当前会话，调用方可修改其中的消息列表。"""
        for session in self.data["sessions"]:
            if session["id"] == self.data["current_session_id"]:
                return session
        raise ValueError("当前会话不存在。")

    def save(self):
        """检查数据后写临时文件，再替换正式文件。"""
        self.validate()
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
        temporary.replace(self.path)

    def create_session(self, name):
        """建立空会话并选中；由调用方负责保存。"""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("会话名称不能为空。")
        session = {"id": uuid4().hex, "name": name.strip(), "messages": []}
        self.data["sessions"].append(session)
        self.data["current_session_id"] = session["id"]
        return session

    def select_session(self, session_id):
        """根据稳定的 ID 切换会话。"""
        if not any(item["id"] == session_id for item in self.data["sessions"]):
            raise ValueError("会话不存在。")
        self.data["current_session_id"] = session_id
