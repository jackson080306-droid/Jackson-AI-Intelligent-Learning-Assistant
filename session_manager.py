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
            self.data.setdefault("favorites", [])
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
        favorites = self.data.get("favorites", [])
        if not isinstance(favorites, list):
            raise ValueError("收藏夹格式不正确。")
        favorite_ids = set()
        for item in favorites:
            if not isinstance(item, dict):
                raise ValueError("收藏格式不正确。")
            for field in ("id", "source_name", "question", "answer"):
                if not isinstance(item.get(field), str):
                    raise ValueError("收藏字段格式不正确。")
            if not item["id"] or item["id"] in favorite_ids:
                raise ValueError("收藏 ID 无效。")
            favorite_ids.add(item["id"])

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

    def answered_pairs(self):
        """只返回紧邻用户问题的完整回答，跳过失败后未回答的问题。"""
        messages = self.current_session()["messages"]
        return [
            (messages[index - 1]["content"], message["content"])
            for index, message in enumerate(messages)
            if index > 0 and message["role"] == "assistant"
            and messages[index - 1]["role"] == "user"
        ]

    def add_favorite(self, question, answer):
        """保存问答副本；相同内容不重复收藏。"""
        favorites = self.data.setdefault("favorites", [])
        if any(item["question"] == question and item["answer"] == answer for item in favorites):
            return False
        favorites.append({
            "id": uuid4().hex, "source_name": self.current_session()["name"],
            "question": question, "answer": answer,
        })
        return True

    def remove_favorite(self, identifier):
        """移除指定收藏，不影响原会话消息。"""
        self.data["favorites"] = [
            item for item in self.data.get("favorites", []) if item["id"] != identifier
        ]

    def rename_current(self, name):
        """修改名称，保留会话 ID 和消息。"""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("会话名称不能为空。")
        self.current_session()["name"] = name.strip()

    def delete_current(self):
        """删除当前会话，选中相邻会话；最后一个删除后建立默认会话。"""
        sessions = self.data["sessions"]
        index = next(
            index for index, session in enumerate(sessions)
            if session["id"] == self.data["current_session_id"]
        )
        sessions.pop(index)
        if sessions:
            self.data["current_session_id"] = sessions[min(index, len(sessions) - 1)]["id"]
        else:
            self.create_session("默认会话")
