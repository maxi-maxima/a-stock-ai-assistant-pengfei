import datetime
import json
import os

from core.threshold_profiles import load_profiles, get_active_profile_name, get_profile


EVENT_BUS_PATH = "data/event_bus.jsonl"
OVERRIDE_PATH = "data/threshold_overrides.json"
STATE_PATH = "data/threshold_adapt_state.json"


def _now():
    return datetime.datetime.now()


def _parse_ts(ts):
    if isinstance(ts, datetime.datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.datetime.fromisoformat(ts)
        except Exception:
            try:
                return datetime.datetime.fromisoformat(ts[:19])
            except Exception:
                return None
    return None


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _load_event_bus(days=30):
    if not os.path.exists(EVENT_BUS_PATH):
        return []
    cutoff = _now() - datetime.timedelta(days=int(days))
    out = []
    try:
        with open(EVENT_BUS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                ts = _parse_ts(rec.get("ts"))
                if ts and ts < cutoff:
                    continue
                out.append(rec)
    except Exception:
        return []
    return out


def _compute_outcome_stats(events):
    pnl_list = []
    for rec in events:
        if not isinstance(rec, dict):
            continue
        if rec.get("event") != "outcome":
            continue
        payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
        pnl_pct = payload.get("pnl_pct")
        if pnl_pct is None:
            continue
        try:
            pnl_pct = float(pnl_pct)
        except Exception:
            continue
        pnl_list.append(pnl_pct)
    if not pnl_list:
        return {"samples": 0, "win_rate": 0.0, "avg_pnl": 0.0}
    wins = sum(1 for v in pnl_list if v > 0)
    return {
        "samples": len(pnl_list),
        "win_rate": wins / len(pnl_list),
        "avg_pnl": sum(pnl_list) / len(pnl_list)
    }


def _build_override(base_constraints, stats):
    """
    Return override constraints dict, or {} if no change.
    """
    if not isinstance(base_constraints, dict):
        base_constraints = {}

    samples = int(stats.get("samples", 0) or 0)
    if samples <= 0:
        return {}

    win_rate = float(stats.get("win_rate", 0) or 0)
    avg_pnl = float(stats.get("avg_pnl", 0) or 0)

    # base values
    max_single = float(base_constraints.get("max_single_position", 0.3) or 0.3)
    max_trades = int(base_constraints.get("max_daily_trades", 6) or 6)
    sl = float(base_constraints.get("stop_loss_pct", 0.06) or 0.06)
    tp = float(base_constraints.get("take_profit_pct", 0.15) or 0.15)
    allow_chase = bool(base_constraints.get("allow_chase", False))

    override = {}

    # tighten when losing
    if win_rate < 0.45 and avg_pnl < 0:
        override["max_single_position"] = _clamp(max_single - 0.05, 0.10, 0.50)
        override["max_daily_trades"] = max(1, max_trades - 1)
        override["stop_loss_pct"] = _clamp(sl - 0.01, 0.02, 0.12)
        override["take_profit_pct"] = _clamp(tp - 0.02, 0.05, 0.30)
        override["allow_chase"] = False

    # loosen when winning
    elif win_rate > 0.60 and avg_pnl > 0:
        override["max_single_position"] = _clamp(max_single + 0.05, 0.10, 0.50)
        override["max_daily_trades"] = min(12, max_trades + 1)
        override["stop_loss_pct"] = _clamp(sl + 0.01, 0.02, 0.12)
        override["take_profit_pct"] = _clamp(tp + 0.02, 0.05, 0.30)
        if win_rate > 0.68 and avg_pnl > 0.02:
            override["allow_chase"] = True
        else:
            override["allow_chase"] = allow_chase

    # mild adjustment when flat
    elif win_rate < 0.50 and avg_pnl <= 0:
        override["max_single_position"] = _clamp(max_single - 0.02, 0.10, 0.50)
        override["stop_loss_pct"] = _clamp(sl - 0.005, 0.02, 0.12)
        override["allow_chase"] = False

    return override


def _load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _save_override(payload):
    os.makedirs(os.path.dirname(OVERRIDE_PATH), exist_ok=True)
    try:
        with open(OVERRIDE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def maybe_update_overrides():
    """
    Compute adaptive constraint overrides from event bus outcomes.
    Only runs when ENABLE_THRESHOLD_ADAPT=1.
    """
    if os.getenv("ENABLE_THRESHOLD_ADAPT", "0") != "1":
        return {}

    try:
        min_hours = float(os.getenv("THRESH_ADAPT_MIN_HOURS", "12"))
    except Exception:
        min_hours = 12.0

    state = _load_state()
    last_ts = state.get("last_update")
    if last_ts:
        try:
            last_dt = datetime.datetime.fromisoformat(last_ts)
            if (_now() - last_dt).total_seconds() < min_hours * 3600:
                return {}
        except Exception:
            pass

    try:
        lookback_days = int(os.getenv("THRESH_ADAPT_DAYS", "30"))
    except Exception:
        lookback_days = 30
    try:
        min_samples = int(os.getenv("THRESH_ADAPT_MIN_SAMPLES", "20"))
    except Exception:
        min_samples = 20

    events = _load_event_bus(days=lookback_days)
    stats = _compute_outcome_stats(events)
    if stats.get("samples", 0) < min_samples:
        return {}

    profiles = load_profiles()
    active = get_active_profile_name(profiles)
    profile = get_profile(active, profiles)
    base_constraints = {}
    if isinstance(profile, dict):
        rules = profile.get("rules", {}) if isinstance(profile.get("rules", {}), dict) else {}
        base_constraints = rules.get("constraints", {}) if isinstance(rules.get("constraints", {}), dict) else {}
        if not base_constraints:
            base_constraints = profile.get("constraints", {}) if isinstance(profile.get("constraints", {}), dict) else {}

    override = _build_override(base_constraints, stats)
    if not override:
        return {}

    payload = {
        "updated_at": _now().isoformat(timespec="seconds"),
        "lookback_days": lookback_days,
        "min_samples": min_samples,
        "metrics": stats,
        "profiles": {
            active: {
                "rules": {
                    "constraints": override
                }
            }
        }
    }
    _save_override(payload)
    _save_state({"last_update": payload["updated_at"]})
    return payload

