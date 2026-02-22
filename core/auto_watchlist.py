import datetime
import json
import os

from core.strategy_pool import get_pool_names, pool_enabled
from core.watchlist import load_entries, save_entries, append_entries, normalize_code
from core.stock_name import resolve_name
from skills.scanner import MarketScanner


CONFIG_PATH = "config/strategy_training.json"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_pool_entries(entries):
    out = []
    seen = set()
    for item in entries or []:
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
            name = item.get("name") or code
            price = item.get("price") or item.get("init_price")
            reason = item.get("reason")
        else:
            code = item
            name = code
            price = None
            reason = None
        code = normalize_code(code)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name": name or code, "price": price, "reason": reason})
    return out


def update_watchlist_from_pool(cfg=None, pool_names=None):
    cfg = cfg if isinstance(cfg, dict) else _load_config()
    if not cfg.get("auto_update_watchlist", False):
        return {"updated": False, "reason": "disabled"}
    if not pool_enabled():
        return {"updated": False, "reason": "pool_disabled"}

    pool_names = pool_names or get_pool_names()
    if not pool_names:
        return {"updated": False, "reason": "pool_empty"}

    source_scope = str(cfg.get("watchlist_source", "watchlist") or "watchlist").strip().lower()
    scan_limit = int(cfg.get("watchlist_scan_limit", 800) or 800)
    top_k = int(cfg.get("watchlist_top_k", 80) or 80)
    replace_old = bool(cfg.get("watchlist_replace_source", True))
    custom_codes = cfg.get("watchlist_custom_codes", []) if isinstance(cfg.get("watchlist_custom_codes", []), list) else []

    scanner = MarketScanner()
    if source_scope == "custom":
        pool = _normalize_pool_entries(custom_codes)
    else:
        pool = scanner.get_candidate_pool(mode=source_scope, limit=scan_limit)

    pool = _normalize_pool_entries(pool)
    if not pool:
        return {"updated": False, "reason": "no_pool_data"}

    candidates, _ = scanner.fusion_scan(pool, top_k=len(pool_names), strategies=pool_names)
    if not candidates:
        return {"updated": False, "reason": "no_candidates"}

    candidates = _normalize_pool_entries(candidates)
    if top_k > 0:
        candidates = candidates[:top_k]

    source = "strategy_pool_auto"
    detail = f"auto_pool:{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if replace_old:
        existing = load_entries()
        existing = [e for e in existing if e.get("source") != source]
        save_entries(existing)

    new_entries = []
    for c in candidates:
        code = c.get("code")
        if not code:
            continue
        name = c.get("name") or resolve_name(code) or code
        entry = {
            "code": code,
            "name": name,
            "init_price": c.get("price")
        }
        new_entries.append(entry)

    append_entries(new_entries, source=source, source_detail=detail, fill_name=True, fill_price=True)

    return {
        "updated": True,
        "count": len(new_entries),
        "source_scope": source_scope,
        "top_k": top_k,
        "strategies": pool_names,
        "detail": detail
    }


if __name__ == "__main__":
    print(update_watchlist_from_pool())
