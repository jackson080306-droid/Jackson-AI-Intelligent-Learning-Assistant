"""将单个会话导出为便于阅读的文本文件。"""

from pathlib import Path


def export_session(session, path):
    """导出会话名称和已保存消息，不包含配置或输入草稿。"""
    path = Path(path)
    if path.suffix.lower() not in (".txt", ".md"):
        raise ValueError("请选择 .txt 或 .md 文件。")
    markdown = path.suffix.lower() == ".md"
    name = session["name"].replace("\r", " ").replace("\n", " ")
    sections = [f"# {name}" if markdown else f"会话：{name}"]
    for message in session["messages"]:
        speaker = "你" if message["role"] == "user" else "AI"
        heading = f"## {speaker}" if markdown else f"{speaker}："
        sections.append(f"{heading}\n\n{message['content']}")
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
