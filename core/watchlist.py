import datetime
import json
import os

from core.stock_name import resolve_name
from skills.data_factory import DataSkillFactory


WATCHLIST_PATH = "data/watchlist.json"

_PRICE_CACHE = {}
_PRICE_CACHE_TS = {}
_PRICE_TTL = 300  # seconds


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def normalize_code(code):
    if not code:
        return None
    code = str(code).strip().upper()
    if not code:
        return None
    if code.endswith(".SH") or code.endswith(".SZ"):
        return code
    if code.isdigit() and len(code) == 6:
        return code + (".SH" if code.startswith("6") else ".SZ")
    return code


def _is_name_placeholder(name, code):
    if not name:
        return True
    if code and str(name).strip() == str(code).strip():
        return True
    return False


def _coerce_price(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except Exception:
        return None


def _load_raw():
    if not os.path.exists(WATCHLIST_PATH):
        return []
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if isinstance(data, dict) and "codes" in data:
        data = data.get("codes", [])
    return data if isinstance(data, list) else []


def load_entries():
    data = _load_raw()
    out = []
    for item in data:
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
            name = item.get("name") or item.get("stock_name")
            init_price = item.get("init_price")
            if init_price is None:
                init_price = item.get("price") or item.get("entry_price")
            source = item.get("source")
            source_detail = item.get("source_detail") or item.get("source_scope")
            added_at = item.get("added_at") or item.get("created_at")
        else:
            code = item
            name = None
            init_price = None
            source = None
            source_detail = None
            added_at = None
        code = normalize_code(code)
        if not code:
            continue
        entry = {
            "code": code,
            "name": name or code,
            "init_price": _coerce_price(init_price),
            "source": source,
            "source_detail": source_detail,
            "added_at": added_at
        }
        out.append(entry)
    return _dedup_merge(out)


def load_codes():
    return [e.get("code") for e in load_entries() if e.get("code")]


def save_entries(entries):
    os.makedirs(os.path.dirname(WATCHLIST_PATH), exist_ok=True)
    clean = _dedup_merge(entries)
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump({"codes": clean}, f, ensure_ascii=False, indent=2)
    return clean


def build_entry(code, name=None, init_price=None, source=None, source_detail=None, added_at=None):
    code = normalize_code(code)
    if not code:
        return None
    return {
        "code": code,
        "name": name or code,
        "init_price": _coerce_price(init_price),
        "source": source,
        "source_detail": source_detail,
        "added_at": added_at
    }


def _dedup_merge(entries):
    by_code = {}
    for item in entries or []:
        if not isinstance(item, dict):
            item = build_entry(item)
        if not item:
            continue
        code = normalize_code(item.get("code"))
        if not code:
            continue
        existing = by_code.get(code)
        if not existing:
            base = {
                "code": code,
                "name": item.get("name") or code,
                "init_price": _coerce_price(item.get("init_price")),
                "source": item.get("source"),
                "source_detail": item.get("source_detail"),
                "added_at": item.get("added_at")
            }
            by_code[code] = base
            continue
        # merge missing fields only
        name = item.get("name")
        if (_is_name_placeholder(existing.get("name"), code) and name) or not existing.get("name"):
            existing["name"] = name
        if existing.get("init_price") is None and item.get("init_price") is not None:
            existing["init_price"] = _coerce_price(item.get("init_price"))
        if not existing.get("source") and item.get("source"):
            existing["source"] = item.get("source")
        if not existing.get("source_detail") and item.get("source_detail"):
            existing["source_detail"] = item.get("source_detail")
        if not existing.get("added_at") and item.get("added_at"):
            existing["added_at"] = item.get("added_at")
        by_code[code] = existing
    return list(by_code.values())


def _get_latest_price(code):
    code = normalize_code(code)
    if not code:
        return None
    now_ts = datetime.datetime.now().timestamp()
    if code in _PRICE_CACHE and (now_ts - _PRICE_CACHE_TS.get(code, 0) < _PRICE_TTL):
        return _PRICE_CACHE.get(code)
    try:
        skill = DataSkillFactory.get_skill("tushare")
        df = skill.get_history(code, days=30)
        if df is not None and not df.empty:
            price = float(df.iloc[-1]["close"])
        else:
            price = None
    except Exception:
        price = None
    _PRICE_CACHE[code] = price
    _PRICE_CACHE_TS[code] = now_ts
    return price


def _fill_entry_defaults(entry, fill_name=True, fill_price=True):
    if not entry or not entry.get("code"):
        return entry
    code = entry["code"]
    if fill_name and _is_name_placeholder(entry.get("name"), code):
        try:
            entry["name"] = resolve_name(code) or code
        except Exception:
            entry["name"] = entry.get("name") or code
    if fill_price and entry.get("init_price") is None:
        entry["init_price"] = _coerce_price(_get_latest_price(code))
    if not entry.get("added_at"):
        entry["added_at"] = _now()
    return entry


def append_entries(new_entries, source=None, source_detail=None, fill_name=True, fill_price=True):
    existing = load_entries()
    prepared = []
    for item in new_entries or []:
        entry = item if isinstance(item, dict) else build_entry(item)
        if not entry:
            continue
        entry["code"] = normalize_code(entry.get("code"))
        if not entry.get("code"):
            continue
        if source and not entry.get("source"):
            entry["source"] = source
        if source_detail and not entry.get("source_detail"):
            entry["source_detail"] = source_detail
        entry = _fill_entry_defaults(entry, fill_name=fill_name, fill_price=fill_price)
        prepared.append(entry)
    merged = _dedup_merge(existing + prepared)
    save_entries(merged)
    return merged
