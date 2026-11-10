"""读取本地配置；真实密钥只放在被 Git 忽略的 config.json 中。"""

import json
from pathlib import Path
from urllib.parse import urlparse


CONFIG_FILE = Path(__file__).resolve().parent / "config.json"

DEFAULT_CONFIG = {
    "mode": "mock",
    "api_key": "",
    "base_url": "",
    "model": "",
    "timeout": 30,
}


def load_config():
    """读取并检查配置；文件不存在时使用默认模拟模式。"""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            settings = json.load(file)
    except (OSError, ValueError) as error:
        raise ValueError("无法读取 config.json，请检查文件和 JSON 格式。") from error

    if not isinstance(settings, dict):
        raise ValueError("配置内容必须是一个 JSON 对象。")

    config = DEFAULT_CONFIG.copy()
    config.update(settings)

    if config["mode"] not in ("mock", "api"):
        raise ValueError("mode 只能填写 mock 或 api。")

    for field in ("api_key", "base_url", "model"):
        if not isinstance(config[field], str):
            raise ValueError(f"{field} 必须是字符串。")
        config[field] = config[field].strip()

    if type(config["timeout"]) is not int or config["timeout"] <= 0:
        raise ValueError("timeout 必须是正整数，单位为秒。")

    if config["mode"] == "api":
        if not all(config[field] for field in ("api_key", "base_url", "model")):
            raise ValueError("API 模式需要填写 api_key、base_url 和 model。")
        address = urlparse(config["base_url"])
        if (
            address.scheme != "https"
            or not address.hostname
            or address.username
            or address.password
            or address.query
            or address.fragment
        ):
            raise ValueError("base_url 必须是 HTTPS 基础地址，不能包含账号、查询参数或片段。")
        if address.path.rstrip("/").endswith("/chat/completions"):
            raise ValueError("base_url 请填写基础地址，不要包含 /chat/completions。")
        if any(character.isspace() for character in config["api_key"]):
            raise ValueError("api_key 不能包含空白字符。")

    return config
