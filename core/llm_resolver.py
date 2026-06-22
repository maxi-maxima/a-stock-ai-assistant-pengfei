import json
import os
from typing import Dict, Iterable, List, Tuple

import yaml

from core.env_loader import is_placeholder_value, load_env


SECURE_SETTINGS_PATH = "data/secure_settings.json"
LLM_CONFIG_PATH = "config/llm_config.yaml"


_BRAIN_META = {
    "blue": {"env": "BLUE_BRAIN", "config": "blue_brain"},
    "red": {"env": "RED_BRAIN", "config": "red_brain"},
    "green": {"env": "GREEN_BRAIN", "config": "green_brain"},
}


SOURCE_LABEL_ZH = {
    "env_brain": "环境变量(本脑)",
    "env_global": "环境变量(通用)",
    "secure_brain": "安全存储(本脑)",
    "secure_global": "安全存储(通用)",
    "config_brain": "配置文件(本脑)",
    "config_global": "配置文件(通用)",
    "input": "当前输入",
    "missing": "未提供",
}


def source_label_zh(source: str) -> str:
    return SOURCE_LABEL_ZH.get(str(source or "").strip(), str(source or "missing"))


def _clean_value(val) -> str:
    if val is None:
        return ""
    try:
        text = str(val).strip()
    except Exception:
        return ""
    if not text:
        return ""
    if is_placeholder_value(text):
        return ""
    return text


def _pick_with_source(candidates: Iterable[Tuple[str, str]]) -> Tuple[str, str]:
    for val, source in candidates:
        clean = _clean_value(val)
        if clean:
            return clean, source
    return "", "missing"


def load_secure_settings(path: str = SECURE_SETTINGS_PATH) -> Dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_llm_config(path: str = LLM_CONFIG_PATH) -> Dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _ensure_dict(val) -> Dict:
    return val if isinstance(val, dict) else {}


def _secure_keys_for_brain(brain: str, field: str) -> List[str]:
    base = str(brain or "").strip().lower()
    if field == "api_key":
        return [f"{base}_brain_api_key", f"{base}_api_key"]
    if field == "base_url":
        return [f"{base}_brain_base_url", f"{base}_base_url"]
    if field == "model":
        return [f"{base}_brain_model", f"{base}_model"]
    return []


def resolve_brain_settings(
    brain: str,
    secure: Dict = None,
    conf: Dict = None,
    load_environment: bool = True,
) -> Dict:
    brain = str(brain or "").strip().lower()
    meta = _BRAIN_META.get(brain)
    if not meta:
        return {
            "api_key": "",
            "base_url": "",
            "model": "",
            "api_key_source": "missing",
            "base_url_source": "missing",
            "model_source": "missing",
        }

    if load_environment:
        load_env()
    secure = _ensure_dict(secure) if secure is not None else load_secure_settings()
    conf = _ensure_dict(conf) if conf is not None else load_llm_config()

    env_prefix = meta["env"]
    brain_conf = _ensure_dict(conf.get(meta["config"]))
    global_conf = _ensure_dict(conf.get("llm"))

    secure_api_keys = _secure_keys_for_brain(brain, "api_key")
    secure_base_keys = _secure_keys_for_brain(brain, "base_url")
    secure_model_keys = _secure_keys_for_brain(brain, "model")

    api_key, api_key_source = _pick_with_source(
        [
            (os.getenv(f"{env_prefix}_API_KEY"), "env_brain"),
            (os.getenv("LLM_API_KEY"), "env_global"),
            (next((secure.get(k) for k in secure_api_keys if secure.get(k)), None), "secure_brain"),
            (secure.get("llm_api_key"), "secure_global"),
            (brain_conf.get("api_key"), "config_brain"),
            (global_conf.get("api_key"), "config_global"),
        ]
    )
    base_url, base_url_source = _pick_with_source(
        [
            (os.getenv(f"{env_prefix}_BASE_URL"), "env_brain"),
            (os.getenv("LLM_BASE_URL"), "env_global"),
            (next((secure.get(k) for k in secure_base_keys if secure.get(k)), None), "secure_brain"),
            (secure.get("llm_base_url"), "secure_global"),
            (brain_conf.get("base_url"), "config_brain"),
            (global_conf.get("base_url"), "config_global"),
        ]
    )
    model, model_source = _pick_with_source(
        [
            (os.getenv(f"{env_prefix}_MODEL"), "env_brain"),
            (os.getenv("LLM_MODEL"), "env_global"),
            (next((secure.get(k) for k in secure_model_keys if secure.get(k)), None), "secure_brain"),
            (secure.get("llm_model"), "secure_global"),
            (brain_conf.get("model"), "config_brain"),
            (global_conf.get("model"), "config_global"),
        ]
    )
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "api_key_source": api_key_source,
        "base_url_source": base_url_source,
        "model_source": model_source,
    }


def resolve_general_settings(
    secure: Dict = None,
    conf: Dict = None,
    load_environment: bool = True,
) -> Dict:
    if load_environment:
        load_env()
    secure = _ensure_dict(secure) if secure is not None else load_secure_settings()
    conf = _ensure_dict(conf) if conf is not None else load_llm_config()
    global_conf = _ensure_dict(conf.get("llm"))

    api_key, api_key_source = _pick_with_source(
        [
            (os.getenv("LLM_API_KEY"), "env_global"),
            (secure.get("llm_api_key"), "secure_global"),
            (global_conf.get("api_key"), "config_global"),
        ]
    )
    base_url, base_url_source = _pick_with_source(
        [
            (os.getenv("LLM_BASE_URL"), "env_global"),
            (secure.get("llm_base_url"), "secure_global"),
            (global_conf.get("base_url"), "config_global"),
        ]
    )
    model, model_source = _pick_with_source(
        [
            (os.getenv("LLM_MODEL"), "env_global"),
            (secure.get("llm_model"), "secure_global"),
            (global_conf.get("model"), "config_global"),
        ]
    )
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "api_key_source": api_key_source,
        "base_url_source": base_url_source,
        "model_source": model_source,
    }


def resolve_preferred_settings(
    preferred: Iterable[str],
    secure: Dict = None,
    conf: Dict = None,
    load_environment: bool = True,
) -> Dict:
    if load_environment:
        load_env()
    secure = _ensure_dict(secure) if secure is not None else load_secure_settings()
    conf = _ensure_dict(conf) if conf is not None else load_llm_config()

    for item in preferred:
        name = str(item or "").strip().lower()
        if name in _BRAIN_META:
            setting = resolve_brain_settings(name, secure=secure, conf=conf, load_environment=False)
        elif name == "general":
            setting = resolve_general_settings(secure=secure, conf=conf, load_environment=False)
        else:
            continue
        if setting.get("api_key") and setting.get("model"):
            setting["resolved_name"] = name
            return setting
    return {
        "api_key": "",
        "base_url": "",
        "model": "",
        "api_key_source": "missing",
        "base_url_source": "missing",
        "model_source": "missing",
        "resolved_name": "",
    }


def apply_input_overrides(
    setting: Dict,
    api_key: str = None,
    base_url: str = None,
    model: str = None,
) -> Dict:
    out = dict(setting or {})
    key_v = _clean_value(api_key)
    base_v = _clean_value(base_url)
    model_v = _clean_value(model)
    if key_v:
        out["api_key"] = key_v
        out["api_key_source"] = "input"
    if base_v:
        out["base_url"] = base_v
        out["base_url_source"] = "input"
    if model_v:
        out["model"] = model_v
        out["model_source"] = "input"
    return out
