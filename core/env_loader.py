import os


_PLACEHOLDER_VALUES = {
    "your_key_here",
    "your_api_key_here",
    "your_tushare_token",
    "your_token_here",
    "your_secret_here",
    "your_secret_key",
    "your_key",
}


def is_placeholder_value(val):
    if val is None:
        return False
    try:
        v = str(val).strip()
    except Exception:
        return False
    if not v:
        return False
    return v.lower() in _PLACEHOLDER_VALUES


def _strip_quotes(val):
    if len(val) >= 2 and ((val[0] == val[-1]) and val[0] in ("'", '"')):
        return val[1:-1]
    return val


def load_env(path=".env", override=False):
    """
    Minimal .env loader (no external deps).
    - override=False: do not clobber existing env vars
    """
    if not os.path.exists(path):
        return {}
    loaded = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = _strip_quotes(val.strip())
                if not key:
                    continue
                if is_placeholder_value(val):
                    continue
                if not override and key in os.environ:
                    continue
                os.environ[key] = val
                loaded[key] = val
    except Exception:
        return {}
    return loaded
