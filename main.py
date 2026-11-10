"""AI 智能学习助手：逐步开发的程序入口。"""

import json
from pathlib import Path

from ai_client import APIError, stream_reply
from config import load_config


HISTORY_FILE = Path(__file__).resolve().parent / "chat_history.json"


def load_messages():
    """读取历史消息；首次运行时返回空列表，读取失败时返回 None。"""
    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as file:
            messages = json.load(file)

        if not isinstance(messages, list):
            raise ValueError("聊天记录必须是列表")

        for message in messages:
            if (
                not isinstance(message, dict)
                or message.get("role") not in ("user", "assistant")
                or not isinstance(message.get("content"), str)
            ):
                raise ValueError("消息格式不正确")

        return messages
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as error:
        print(f"无法读取聊天记录：{error}")
        print("请检查历史文件。程序停止，以免覆盖原记录。")
        return None


def save_messages(messages):
    """先写临时文件，再替换历史文件，减少写入中断造成的损坏。"""
    temporary_file = HISTORY_FILE.with_suffix(".tmp")
    try:
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(messages, file, ensure_ascii=False, indent=2)
        temporary_file.replace(HISTORY_FILE)
        return True
    except OSError as error:
        print(f"保存失败：{error}")
        print("本次记录仍在内存中，关闭程序后可能丢失。")
        return False


def show_messages(messages):
    """按角色显示全部聊天记录。"""
    print("\n当前聊天记录：")
    for message in messages:
        if message["role"] == "user":
            speaker = "你"
        else:
            speaker = "AI"

        print(f"{speaker}：{message['content']}")


def main():
    """恢复历史，连续接收问题，并在每次提问后保存。"""
    try:
        config = load_config()
    except ValueError as error:
        print(f"配置错误：{error}")
        return

    messages = load_messages()
    if messages is None:
        return

    if messages:
        show_messages(messages)

    print("输入问题后按回车；输入“退出”结束程序。")
    if config["mode"] == "mock":
        print("当前使用模拟 AI，不发送网络请求。")
    else:
        print("当前使用真实 API，聊天历史会发送到你配置的服务商。")

    while True:
        question = input("\n请输入你的问题：").strip()

        if question == "退出":
            save_messages(messages)
            print("程序已结束。")
            break

        if not question:
            print("问题不能为空。")
            continue

        messages.append({"role": "user", "content": question})
        save_messages(messages)

        pieces = []
        print("AI：", end="", flush=True)
        try:
            for piece in stream_reply(messages, config):
                print(piece, end="", flush=True)
                pieces.append(piece)
        except APIError as error:
            print(f"\nAI 请求失败：{error}")
            if pieces:
                print("上面的回答不完整，未保存为 AI 消息；你的问题已保留。")
            continue
        reply = "".join(pieces)
        print()
        messages.append({"role": "assistant", "content": reply})
        save_messages(messages)


if __name__ == "__main__":
    main()
