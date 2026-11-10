"""提供模拟回答，以及真实 API 的普通和流式回答。"""

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class APIError(Exception):
    """可以安全显示给用户的接口调用错误。"""


class NoRedirectHandler(HTTPRedirectHandler):
    """拒绝重定向，避免将认证信息发送到其他地址。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_reply(messages, config):
    """根据配置选择模拟回答或兼容 Chat Completions 的真实接口。"""
    if config["mode"] == "mock":
        return get_mock_reply(messages)
    return get_api_reply(messages, config)


def get_api_reply(messages, config):
    """发送完整历史并读取一次性回答；不输出密钥或服务端原始错误。"""
    return "".join(request_reply(messages, config, stream=False))


def stream_reply(messages, config):
    """逐个产生回答片段，供控制台或后续图形界面显示。"""
    if config["mode"] == "mock":
        reply = get_mock_reply(messages)
        for index in range(0, len(reply), 5):
            yield reply[index:index + 5]
    else:
        yield from request_reply(messages, config, stream=True)


def read_stream(response):
    """解析 SSE 事件，忽略心跳和思考片段，检查结束标记。"""
    data_lines = []
    has_content = False
    for raw_line in response:
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if line:
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip(" "))
            continue
        if not data_lines:
            continue
        data = "\n".join(data_lines)
        data_lines = []
        if data == "[DONE]":
            if not has_content:
                raise APIError("接口没有返回回答正文。")
            return
        event = json.loads(data)
        if "error" in event:
            raise APIError("服务商在输出过程中返回错误，请稍后重试。")
        choices = event.get("choices", [])
        if not choices:
            continue
        choice = choices[0]
        content = choice.get("delta", {}).get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("回答片段必须是文本")
        if content:
            has_content = True
            yield content
        reason = choice.get("finish_reason")
        if reason == "length":
            raise APIError("回答达到长度上限，已输出内容不完整。")
        if reason not in (None, "stop"):
            raise APIError("回答未正常完成，可能受到内容限制或需要工具调用。")
    raise APIError("连接提前结束，没有收到完整结束标记。")


def request_reply(messages, config, stream):
    """统一发送请求并处理错误；按模式返回完整文本或流式片段。"""
    url = config["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": config["model"],
        "messages": messages,
        "stream": stream,
    }
    try:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        opener = build_opener(NoRedirectHandler())
        with opener.open(request, timeout=config["timeout"]) as response:
            if stream:
                yield from read_stream(response)
                return
            result = json.loads(response.read().decode("utf-8"))
        reply = result["choices"][0]["message"]["content"]
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("回答为空或不是文本")
        yield reply
    except HTTPError as error:
        hints = {
            401: "认证失败，请检查 API Key。",
            402: "余额不足，请检查服务商账户。",
            403: "没有访问权限，请检查账户和模型权限。",
            404: "接口或模型不存在，请检查地址和模型名称。",
            429: "请求受限，请检查额度或稍后重试。",
        }
        raise APIError(hints.get(error.code, f"请求失败，HTTP 状态码：{error.code}。")) from None
    except (TimeoutError, socket.timeout):
        raise APIError("请求超时，请稍后重试或增加 timeout。") from None
    except URLError:
        raise APIError("网络连接失败，请检查网络、接口地址和证书。") from None
    except (ValueError, KeyError, IndexError, TypeError, UnicodeError, AttributeError):
        raise APIError("请求或响应格式异常，请检查接口是否兼容 Chat Completions。") from None
    except OSError:
        raise APIError("网络读写失败，请稍后重试。") from None


def get_mock_reply(messages):
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
