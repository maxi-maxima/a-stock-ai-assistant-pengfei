import json
import os

PARAM_PATH = "config/strategy_params.json"
_CACHE = None
_CACHE_MTIME = None


def _load_params():
    global _CACHE, _CACHE_MTIME
    try:
        mtime = os.path.getmtime(PARAM_PATH)
    except Exception:
        mtime = None
    if _CACHE is not None and _CACHE_MTIME == mtime:
        return _CACHE
    data = {}
    if mtime is None:
        _CACHE = {}
        _CACHE_MTIME = mtime
        return _CACHE
    try:
        with open(PARAM_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data = raw
    except Exception:
        data = {}
    _CACHE = data
    _CACHE_MTIME = mtime
    return _CACHE


def get_params(name, defaults=None):
    params = {}
    data = _load_params()
    if isinstance(data, dict):
        entry = data.get(name, {})
        if isinstance(entry, dict):
            params.update(entry)
    if isinstance(defaults, dict):
        merged = dict(defaults)
        merged.update(params)
        return merged
    return params


def as_int(value, default=0, min_value=None):
    try:
        value = int(value)
    except Exception:
        value = int(default)
    if min_value is not None and value < min_value:
        value = int(min_value)
    return value


def as_float(value, default=0.0, min_value=None):
    try:
        value = float(value)
    except Exception:
        value = float(default)
    if min_value is not None and value < min_value:
        value = float(min_value)
    return value


def as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(default)
