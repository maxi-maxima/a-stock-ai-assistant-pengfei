import datetime
import json
import os

from core.env_loader import load_env, is_placeholder_value
from core.logger import exception, warn


CONFIG_PATH = "config/letta.json"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


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


def _default_config():
    return {
        "enabled": False,
        "base_url": "https://api.letta.com",
        "project_id": "",
        "agent_id": "",
        "agent_name": "kimi_stock_semantic",
        "model": "openai/gpt-4o-mini",
        "embedding": "openai/text-embedding-3-small",
        "semantic_block_label": "semantic",
        "max_chars": 6000,
        "max_read_chars": 1200,
        "append_mode": "prepend"
    }


def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        return _default_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_config()
        merged = _default_config()
        merged.update(data)
        return merged
    except Exception:
        return _default_config()


def save_config(cfg, path=CONFIG_PATH):
    cfg = cfg if isinstance(cfg, dict) else _default_config()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        exception("letta.config_save_failed", exc, {"path": path})
        return False


def _resolve_api_key(explicit=None):
    load_env()
    secure = _load_secure_settings()
    return _pick_value(
        explicit,
        os.getenv("LETTA_API_KEY"),
        secure.get("letta_api_key"),
        secure.get("LETTA_API_KEY")
    )


def _resolve_base_url(cfg):
    load_env()
    return _pick_value(
        os.getenv("LETTA_BASE_URL"),
        cfg.get("base_url"),
        "https://api.letta.com"
    )


def _resolve_project_id(cfg):
    load_env()
    return _pick_value(
        os.getenv("LETTA_PROJECT_ID"),
        cfg.get("project_id")
    )


def apply_overrides(cfg, env_prefix="LETTA_"):
    cfg = cfg if isinstance(cfg, dict) else _default_config()
    overrides = {
        "project_id": os.getenv("LETTA_PROJECT_ID"),
        "base_url": os.getenv("LETTA_BASE_URL"),
        "agent_id": os.getenv("LETTA_AGENT_ID"),
        "agent_name": os.getenv("LETTA_AGENT_NAME"),
        "model": os.getenv("LETTA_MODEL"),
        "embedding": os.getenv("LETTA_EMBEDDING"),
        "append_mode": os.getenv("LETTA_APPEND_MODE")
    }
    for k, v in overrides.items():
        if v is not None and str(v).strip() and not is_placeholder_value(v):
            cfg[k] = v
    return cfg


def _get_client(api_key=None, base_url=None, project_id=None):
    try:
        from letta_client import Letta
    except Exception as exc:
        return None, f"letta_import_failed:{exc}"
    key = _resolve_api_key(api_key)
    if not key:
        return None, "missing_letta_api_key"
    kwargs = {"api_key": key}
    if base_url:
        kwargs["base_url"] = base_url
    if project_id:
        kwargs["project_id"] = project_id
    try:
        client = Letta(**kwargs)
        return client, ""
    except Exception as exc:
        return None, f"letta_init_failed:{exc}"


def _ensure_agent(client, cfg):
    agent_id = str(cfg.get("agent_id") or "").strip()
    if agent_id:
        return agent_id

    agent_name = str(cfg.get("agent_name") or "kimi_stock_semantic").strip()
    # Try to find by name if list is available
    try:
        if hasattr(client.agents, "list"):
            agents = client.agents.list(name=agent_name)
            # SyncArrayPage is iterable
            for ag in agents or []:
                name = getattr(ag, "name", None)
                if name == agent_name:
                    agent_id = getattr(ag, "id", None) or getattr(ag, "agent_id", None)
                    if agent_id:
                        cfg["agent_id"] = agent_id
                        save_config(cfg)
                        return agent_id
    except Exception:
        pass

    # Create agent with minimal semantic block
    try:
        mem_blocks = [
            {
                "label": str(cfg.get("semantic_block_label") or "semantic"),
                "value": "",
                "limit": int(cfg.get("max_chars", 6000) or 6000)
            }
        ]
        res = client.agents.create(
            name=agent_name,
            model=cfg.get("model"),
            embedding=cfg.get("embedding"),
            memory_blocks=mem_blocks
        )
        agent_id = getattr(res, "id", None) or getattr(res, "agent_id", None)
        if agent_id:
            cfg["agent_id"] = agent_id
            save_config(cfg)
            return agent_id
    except Exception as exc:
        exception("letta.agent_create_failed", exc)
    return ""


def _retrieve_block(client, agent_id, label):
    try:
        block = client.agents.blocks.retrieve(agent_id=agent_id, block_label=label)
        if hasattr(block, "value"):
            return str(block.value or "")
        if isinstance(block, dict):
            return str(block.get("value") or "")
    except Exception:
        return ""
    return ""


def _update_block(client, agent_id, label, value):
    try:
        client.agents.blocks.update(agent_id=agent_id, block_label=label, value=value)
        return True
    except Exception as exc:
        exception("letta.block_update_failed", exc)
        return False


def append_semantic(entry, cfg=None):
    cfg = cfg or load_config()
    cfg = apply_overrides(cfg)
    if not cfg.get("enabled"):
        return False, "letta_disabled"
    if str(cfg.get("shadow_mode") or "").lower() == "read":
        return False, "shadow_read_only"
    client, err = _get_client(base_url=_resolve_base_url(cfg), project_id=_resolve_project_id(cfg))
    if not client:
        return False, err
    agent_id = _ensure_agent(client, cfg)
    if not agent_id:
        return False, "missing_agent_id"

    label = str(cfg.get("semantic_block_label") or "semantic")
    existing = _retrieve_block(client, agent_id, label)
    entry = str(entry or "").strip()
    if not entry:
        return False, "empty_entry"

    mode = str(cfg.get("append_mode") or "prepend").lower()
    if mode == "append":
        new_val = (existing + "\n" + entry).strip()
    else:
        new_val = (entry + "\n" + existing).strip()

    max_chars = int(cfg.get("max_chars", 6000) or 6000)
    if max_chars and len(new_val) > max_chars:
        new_val = new_val[:max_chars]

    ok = _update_block(client, agent_id, label, new_val)
    return ok, "" if ok else "update_failed"


def read_semantic(cfg=None):
    cfg = cfg or load_config()
    cfg = apply_overrides(cfg)
    if not cfg.get("enabled"):
        return ""
    if str(cfg.get("shadow_mode") or "").lower() == "write":
        return ""
    client, err = _get_client(base_url=_resolve_base_url(cfg), project_id=_resolve_project_id(cfg))
    if not client:
        return ""
    agent_id = _ensure_agent(client, cfg)
    if not agent_id:
        return ""
    label = str(cfg.get("semantic_block_label") or "semantic")
    text = _retrieve_block(client, agent_id, label)
    if not text:
        return ""
    max_read = int(cfg.get("max_read_chars", 1200) or 1200)
    if max_read and len(text) > max_read:
        return text[:max_read]
    return text


def build_semantic_entry(state, debate=None):
    state = state if isinstance(state, dict) else {}
    debate = debate if isinstance(debate, dict) else {}
    code = str(state.get("stock_code") or "").strip()
    action = str(debate.get("policy_action") or debate.get("action") or "").strip().upper()
    core_view = str(debate.get("core_view") or debate.get("final_verdict") or "").strip()
    risk = str((debate.get("risk") or {}).get("risk_warning") or "").strip()
    tags = state.get("context_tags") or []
    if not isinstance(tags, list):
        tags = []
    profile = str(state.get("profile_name") or "").strip()
    hint = str(state.get("autogen_review") or "").strip()
    parts = [
        f"[{_now()}]",
        f"code={code}",
        f"action={action}" if action else "action=HOLD",
    ]
    if profile:
        parts.append(f"profile={profile}")
    if tags:
        parts.append(f"tags={','.join(tags[:6])}")
    if core_view:
        parts.append(f"view={core_view}")
    if risk:
        parts.append(f"risk={risk}")
    if hint:
        parts.append(f"review={hint[:200]}")
    return " | ".join(parts).strip()


def write_semantic_from_state(state, debate=None):
    entry = build_semantic_entry(state, debate=debate)
    if not entry:
        return False, "empty_entry"
    ok, err = append_semantic(entry)
    if not ok and err:
        warn("letta.append_failed", {"error": err})
    return ok, err
