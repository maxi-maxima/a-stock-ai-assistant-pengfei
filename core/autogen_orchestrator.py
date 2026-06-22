import json
import os
import tempfile

import yaml

from core.env_loader import load_env, is_placeholder_value
from core.logger import exception
from core.llm_resolver import resolve_preferred_settings
from core.tool_registry import get_registry


DEFAULT_SYSTEM_PROMPT = (
    "You are a research assistant. Provide concise, structured analysis and clear next steps."
)


def _load_secure_settings():
    path = "data/secure_settings.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _pick_value(*vals):
    for v in vals:
        if v is None:
            continue
        try:
            text = str(v).strip()
        except Exception:
            continue
        if not text:
            continue
        if is_placeholder_value(text):
            continue
        return text
    return ""


def _load_llm_config():
    path = "config/llm_config.yaml"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_llm_settings():
    load_env()
    secure = _load_secure_settings()
    conf = _load_llm_config()
    setting = resolve_preferred_settings(
        preferred=("blue", "general"),
        secure=secure,
        conf=conf,
        load_environment=False,
    )
    api_key = _pick_value(setting.get("api_key"))
    base_url = _pick_value(setting.get("base_url"))
    model = _pick_value(setting.get("model"))

    if not api_key or not model:
        return None
    return {"api_key": api_key, "base_url": base_url, "model": model}


def _build_config_list(settings):
    item = {"model": settings.get("model"), "api_key": settings.get("api_key")}
    if settings.get("base_url"):
        item["base_url"] = settings.get("base_url")
    return [item]


def _extract_text(result):
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    summary = getattr(result, "summary", None)
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    if isinstance(result, dict):
        if isinstance(result.get("summary"), str):
            return result.get("summary").strip()
        if isinstance(result.get("content"), str):
            return result.get("content").strip()
        history = result.get("chat_history")
        if isinstance(history, list) and history:
            last = history[-1]
            if isinstance(last, dict) and isinstance(last.get("content"), str):
                return last.get("content").strip()
    history = getattr(result, "chat_history", None)
    if isinstance(history, list) and history:
        last = history[-1]
        if isinstance(last, dict) and isinstance(last.get("content"), str):
            return last.get("content").strip()
    return str(result)


def _build_llm_config(autogen_mod, config_list):
    llm_config = {"config_list": config_list}
    LLMConfig = getattr(autogen_mod, "LLMConfig", None)
    if not LLMConfig:
        return llm_config
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(config_list, f, ensure_ascii=False, indent=2)
            tmp_path = f.name
        if hasattr(LLMConfig, "from_json"):
            return LLMConfig.from_json(path=tmp_path)
        if hasattr(LLMConfig, "from_dict"):
            return LLMConfig.from_dict({"config_list": config_list})
    except Exception:
        return llm_config
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    return llm_config


def run_autogen_task(prompt, system_prompt=None, max_turns=1, temperature=0.2):
    settings = _resolve_llm_settings()
    if not settings:
        return {"ok": False, "error": "missing_llm_config"}
    try:
        import autogen
    except Exception as exc:
        return {"ok": False, "error": f"autogen_import_failed:{exc}"}

    config_list = _build_config_list(settings)
    llm_config = _build_llm_config(autogen, config_list)
    if isinstance(llm_config, dict):
        llm_config = {**llm_config, "temperature": temperature}

    AssistantAgent = getattr(autogen, "AssistantAgent", None)
    UserProxyAgent = getattr(autogen, "UserProxyAgent", None)
    if AssistantAgent is None or UserProxyAgent is None:
        return {"ok": False, "error": "autogen_agent_classes_missing"}

    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    try:
        assistant = AssistantAgent(
            "autogen_assistant",
            llm_config=llm_config,
            system_message=sys_prompt
        )
    except Exception:
        assistant = AssistantAgent("autogen_assistant", llm_config=llm_config)

    user_proxy = None
    for kwargs in (
        {"human_input_mode": "NEVER", "code_execution_config": {"use_docker": False}},
        {"human_input_mode": "NEVER", "code_execution_config": False},
        {"human_input_mode": "NEVER"},
        {},
    ):
        try:
            user_proxy = UserProxyAgent("autogen_user", **kwargs)
            break
        except Exception:
            continue
    if user_proxy is None:
        return {"ok": False, "error": "autogen_user_proxy_init_failed"}

    result = None
    try:
        if hasattr(user_proxy, "run"):
            try:
                result = user_proxy.run(assistant, message=prompt)
            except TypeError:
                result = user_proxy.run(assistant, message=prompt, max_turns=max_turns)
        elif hasattr(user_proxy, "initiate_chat"):
            try:
                result = user_proxy.initiate_chat(assistant, message=prompt)
            except TypeError:
                result = user_proxy.initiate_chat(assistant, message=prompt, max_turns=max_turns)
    except Exception as exc:
        exception("autogen.run_failed", exc)
        return {"ok": False, "error": str(exc)}

    if hasattr(result, "process"):
        try:
            result = result.process()
        except Exception:
            pass
    output = _extract_text(result)
    return {"ok": True, "output": output}


def autogen_run_tool(args=None):
    args = args if isinstance(args, dict) else {}
    prompt = args.get("prompt") or args.get("message") or ""
    if not prompt:
        return {"ok": False, "error": "missing_prompt"}
    return run_autogen_task(
        prompt=prompt,
        system_prompt=args.get("system_prompt"),
        max_turns=args.get("max_turns", 1),
        temperature=args.get("temperature", 0.2)
    )


def register_autogen_tool(registry=None):
    registry = registry or get_registry()
    registry.register(
        "autogen_run",
        autogen_run_tool,
        meta={
            "kind": "autogen",
            "description": "Run an AutoGen task with a single assistant + user proxy."
        }
    )
    return registry
