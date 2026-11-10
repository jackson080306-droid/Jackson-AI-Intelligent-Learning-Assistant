"""提供模拟回答，供尚未连接真实 API 时验证对话流程。"""


def get_reply(messages):
    """接收完整聊天历史，返回明确标注的模拟回答。"""
    question = messages[-1]["content"]
    question_count = sum(
        1 for message in messages if message["role"] == "user"
    )

    if "列表" in question:
        answer = (
            "列表可以按顺序保存多个元素，也允许修改。"
            "例如 numbers = [1, 2, 3]，"
            "执行 numbers.append(4) 后，列表变成 [1, 2, 3, 4]。"
        )
    elif "循环" in question:
        answer = (
            "循环用于重复执行代码。"
            "for 常用于遍历元素，while 在条件成立时重复执行。"
        )
    else:
        answer = (
            f"已收到你的问题：{question}。"
            "目前只能演示对话流程，接入真实模型后才能回答更多问题。"
        )

    return f"【模拟 AI，第 {question_count} 次提问】{answer}"
