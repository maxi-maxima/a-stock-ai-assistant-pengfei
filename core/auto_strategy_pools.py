import datetime
import json
import os

from skills.scanner import MarketScanner
from core.strategy_pool import get_pool_names, pool_enabled
from core.stock_name import resolve_name
from core.watchlist import normalize_code


CONFIG_PATH = "config/strategy_training.json"
POOL_PATH = "data/strategy_pools.json"


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


def _load_pools():
    if not os.path.exists(POOL_PATH):
        return {}
    try:
        with open(POOL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_pools(data):
    os.makedirs(os.path.dirname(POOL_PATH), exist_ok=True)
    try:
        with open(POOL_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _normalize_entries(entries):
    out = []
    seen = set()
    for item in entries or []:
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
            name = item.get("name") or code
        else:
            code = item
            name = code
        code = normalize_code(code)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name": name or code})
    return out


def update_strategy_pools(cfg=None, pool_names=None):
    cfg = cfg if isinstance(cfg, dict) else _load_config()
    if not cfg.get("auto_update_strategy_pools", False):
        return {"updated": False, "reason": "disabled"}
    if not pool_enabled():
        return {"updated": False, "reason": "pool_disabled"}

    if pool_names is None:
        pool_names = []
    if not isinstance(pool_names, list):
        try:
            pool_names = list(pool_names)
        except Exception:
            pool_names = []

    if not pool_names and bool(cfg.get("strategy_pools_use_skill_tags", False)):
        try:
            from core.strategy_skill_map import resolve_active_tags, strategies_from_tags
            pool_names = strategies_from_tags(resolve_active_tags())
        except Exception:
            pool_names = []

    if not pool_names:
        pool_names = get_pool_names()

    pool_names = [str(name).strip() for name in pool_names if str(name).strip()]
    if not pool_names:
        return {"updated": False, "reason": "pool_empty"}

    source_scope = str(cfg.get("strategy_pools_source", "watchlist") or "watchlist").strip().lower()
    scan_limit = int(cfg.get("strategy_pools_scan_limit", 800) or 800)
    top_k = int(cfg.get("strategy_pools_top_k", 60) or 60)
    add_prefix = bool(cfg.get("strategy_pools_add_prefix", True))

    scanner = MarketScanner()
    if source_scope == "global":
        pool = scanner.get_candidate_pool(mode="global", limit=scan_limit)
    elif source_scope == "custom":
        pool = _normalize_entries(cfg.get("strategy_pools_custom_codes", []))
    else:
        pool = scanner.get_candidate_pool(mode="watchlist", limit=scan_limit)

    pool = _normalize_entries(pool)
    if not pool:
        return {"updated": False, "reason": "no_pool_data"}

    data = _load_pools()
    updated_keys = []
    for strat in pool_names:
        strat_code = str(strat).strip()
        if not strat_code:
            continue
        candidates, _ = scanner.technical_filter(pool, mode=strat_code)
        if not candidates:
            continue
        candidates = _normalize_entries(candidates)
        if top_k > 0:
            candidates = candidates[:top_k]
        # resolve names
        for c in candidates:
            if not c.get("name") or c.get("name") == c.get("code"):
                try:
                    c["name"] = resolve_name(c.get("code")) or c.get("code")
                except Exception:
                    c["name"] = c.get("code")

        meta = {
            "source": "auto_trainer",
            "strategy": strat_code,
            "pool": source_scope,
            "top_k": top_k,
            "updated_at": _now()
        }

        # only fill direct key if not exists (avoid overwriting manual pools)
        if strat_code not in data:
            data[strat_code] = {
                "updated_at": meta["updated_at"],
                "codes": candidates,
                "meta": meta
            }
            updated_keys.append(strat_code)

        if add_prefix:
            auto_key = f"auto_{strat_code}"
            data[auto_key] = {
                "updated_at": meta["updated_at"],
                "codes": candidates,
                "meta": meta
            }
            updated_keys.append(auto_key)

    ok = _save_pools(data)
    return {
        "updated": bool(ok),
        "keys": updated_keys,
        "count": len(updated_keys),
        "source_scope": source_scope,
        "top_k": top_k
    }


if __name__ == "__main__":
    print(update_strategy_pools())
