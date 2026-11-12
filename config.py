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
    collection = load_profiles()
    return collection["profiles"][collection["active_profile"]].copy()


def load_profiles():
    """读取配置集合，旧版单套配置只在内存中转换。"""
    if not CONFIG_FILE.exists():
        return {"active_profile": "默认配置", "profiles": {"默认配置": DEFAULT_CONFIG.copy()}}

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            settings = json.load(file)
    except (OSError, ValueError) as error:
        raise ValueError("无法读取 config.json，请检查文件和 JSON 格式。") from error

    if isinstance(settings, dict) and "profiles" not in settings:
        settings = {"active_profile": "默认配置", "profiles": {"默认配置": settings}}
    return validate_profiles(settings)


def validate_profiles(settings):
    """检查配置名称、当前选择以及每套接口参数。"""
    if not isinstance(settings, dict) or not isinstance(settings.get("profiles"), dict):
        raise ValueError("配置集合必须包含 profiles 对象。")
    profiles = settings["profiles"]
    if not profiles:
        raise ValueError("至少需要保留一套配置。")
    for name in profiles:
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise ValueError("配置名称不能为空，且首尾不能有空格。")
    active = settings.get("active_profile")
    if not isinstance(active, str) or active not in profiles:
        raise ValueError("当前配置名称不存在。")
    return {"active_profile": active, "profiles": {
        name: validate_config(config) for name, config in profiles.items()
    }}


def validate_config(settings):
    """校验并返回配置副本，供文件读取和配置窗口共用。"""
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


def save_config(settings):
    """先校验再写入本地配置，成功后返回规范化配置。"""
    config = validate_config(settings)
    collection = load_profiles()
    collection["profiles"][collection["active_profile"]] = config
    save_profiles(collection)
    return config


def save_profiles(settings):
    """原子替换整个配置集合；失败时不应用到主窗口。"""
    collection = validate_profiles(settings)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(collection, file, ensure_ascii=False, indent=2)
    temporary.replace(CONFIG_FILE)
    return collection
