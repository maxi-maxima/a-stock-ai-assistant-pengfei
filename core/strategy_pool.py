import json
import os
import datetime


POOL_PATH = "data/strategy_pool.json"
CONFIG_PATH = "config/strategy_training.json"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _load_training_config():
    return _load_json(CONFIG_PATH, {})


def pool_enabled():
    cfg = _load_training_config()
    return bool(cfg.get("use_strategy_pool", False))


def load_pool():
    return _load_json(POOL_PATH, {})


def get_pool_names(limit=None):
    if not pool_enabled():
        return []
    pool = load_pool()
    strategies = pool.get("strategies", []) if isinstance(pool.get("strategies", []), list) else []
    names = []
    for s in strategies:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").strip()
        if name:
            names.append(name)
    if limit and len(names) > int(limit):
        names = names[: int(limit)]
    return names


def update_pool_from_training(report, cfg=None):
    if not isinstance(report, dict):
        return {"updated": False, "reason": "invalid_report"}
    cfg = cfg if isinstance(cfg, dict) else _load_training_config()

    strategies = report.get("strategies", {}) if isinstance(report.get("strategies", {}), dict) else {}
    if not strategies:
        return {"updated": False, "reason": "no_strategies"}

    min_samples = int(cfg.get("pool_min_samples", 5) or 5)
    min_avg_score = float(cfg.get("pool_min_avg_score", 0) or 0)
    top_k = int(cfg.get("pool_top_k", 0) or 0)
    fallback = bool(cfg.get("pool_fallback_to_top", True))

    rows = []
    for name, stats in strategies.items():
        if not isinstance(stats, dict):
            continue
        samples = int(stats.get("samples", 0) or 0)
        avg_score = float(stats.get("avg_score", 0) or 0)
        avg_ret = float(stats.get("avg_return", 0) or 0)
        avg_dd = float(stats.get("avg_drawdown", 0) or 0)
        if samples < min_samples:
            continue
        if avg_score < min_avg_score:
            continue
        rows.append({
            "name": str(stats.get("strategy_code") or name).strip(),
            "avg_score": avg_score,
            "avg_return": avg_ret,
            "avg_drawdown": avg_dd,
            "samples": samples
        })

    if not rows and fallback:
        for name, stats in strategies.items():
            if not isinstance(stats, dict):
                continue
            samples = int(stats.get("samples", 0) or 0)
            avg_score = float(stats.get("avg_score", 0) or 0)
            avg_ret = float(stats.get("avg_return", 0) or 0)
            avg_dd = float(stats.get("avg_drawdown", 0) or 0)
            rows.append({
                "name": str(stats.get("strategy_code") or name).strip(),
                "avg_score": avg_score,
                "avg_return": avg_ret,
                "avg_drawdown": avg_dd,
                "samples": samples
            })

    if not rows:
        return {"updated": False, "reason": "no_candidates"}

    rows = sorted(rows, key=lambda x: (x.get("avg_score", 0), x.get("avg_return", 0)), reverse=True)
    if top_k > 0 and len(rows) > top_k:
        rows = rows[:top_k]

    payload = {
        "updated_at": _now(),
        "source": "training",
        "pool": report.get("pool"),
        "mode": report.get("mode"),
        "days": report.get("days"),
        "min_samples": min_samples,
        "min_avg_score": min_avg_score,
        "top_k": top_k,
        "strategies": rows
    }
    ok = _save_json(POOL_PATH, payload)
    return {"updated": bool(ok), "pool": payload if ok else None}

