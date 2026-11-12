"""集中保存可编辑的学习提示词模板。"""


TEMPLATES = {
    "知识点讲解": (
        "请面向初学者讲解以下知识点。\n"
        "先解释概念，再给出具体例子，最后总结常见误区并提供一道练习题。\n"
        "不要假设我掌握了尚未说明的前置知识。\n\n"
        "知识点：\n{content}"
    ),
    "学习计划": (
        "请根据以下信息制定可执行的学习计划。\n"
        "按阶段列出学习内容、练习任务和检查方法，合理安排复习。\n"
        "如果目标、基础或可用时间不明确，请先询问缺失信息。\n\n"
        "我的目标、当前基础、可用时间：\n{content}"
    ),
    "错题分析": (
        "请分析以下题目和我的解答。\n"
        "指出出错位置和原因，解释涉及的知识点，给出正确思路及一道类似练习。\n"
        "如果题目或解答信息不足，请先询问，不要编造缺失条件。\n\n"
        "题目、我的解答及疑问：\n{content}"
    ),
}


def build_prompt(name, content):
    """将用户输入嵌入指定模板，不发送网络请求。"""
    if name not in TEMPLATES:
        raise ValueError("请选择有效的学习模板。")
    if not content.strip():
        raise ValueError("请先在输入框填写学习内容。")
    return TEMPLATES[name].format(content=content.strip())
