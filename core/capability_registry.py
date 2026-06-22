import datetime
import json
import os

from core.logger import exception


DEFAULT_PATH = "config/capabilities.json"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _default_registry():
    return {
        "version": "1.0",
        "updated_at": _now(),
        "capabilities": {
            "tools": {},
            "agents": {},
            "orchestrators": {},
            "memory": {},
            "optimizers": {},
            "browsers": {},
            "data": {}
        }
    }


def _ensure_registry(path=DEFAULT_PATH):
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_default_registry(), f, ensure_ascii=False, indent=2)
    except Exception as exc:
        exception("capability_registry.init_failed", exc, {"path": path})


def load_registry(path=DEFAULT_PATH):
    _ensure_registry(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_registry()
        if "capabilities" not in data or not isinstance(data.get("capabilities"), dict):
            data["capabilities"] = _default_registry().get("capabilities")
        return data
    except Exception as exc:
        exception("capability_registry.load_failed", exc, {"path": path})
        return _default_registry()


def save_registry(data, path=DEFAULT_PATH):
    data = data if isinstance(data, dict) else _default_registry()
    data["updated_at"] = _now()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        exception("capability_registry.save_failed", exc, {"path": path})
        return False


def list_capabilities(kind=None, enabled_only=False, path=DEFAULT_PATH):
    reg = load_registry(path)
    caps = reg.get("capabilities", {})
    if kind:
        items = caps.get(kind, {})
    else:
        items = {}
        for k, v in caps.items():
            if isinstance(v, dict):
                for name, cfg in v.items():
                    items[f"{k}:{name}"] = cfg
    out = []
    for name, cfg in items.items():
        if not isinstance(cfg, dict):
            continue
        if enabled_only and not cfg.get("enabled", False):
            continue
        out.append({"name": name, **cfg})
    return out


def get_capability(kind, name, path=DEFAULT_PATH):
    reg = load_registry(path)
    caps = reg.get("capabilities", {})
    if not kind or not name:
        return None
    cfg = caps.get(kind, {}).get(name)
    return cfg if isinstance(cfg, dict) else None


def set_capability(kind, name, config, path=DEFAULT_PATH):
    if not kind or not name:
        return False
    reg = load_registry(path)
    caps = reg.setdefault("capabilities", {})
    bucket = caps.setdefault(kind, {})
    bucket[str(name).strip()] = config if isinstance(config, dict) else {}
    return save_registry(reg, path)
