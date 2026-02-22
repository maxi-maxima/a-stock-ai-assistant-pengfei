import datetime
import json
import os

from core.skill_registry import SkillRegistry


EVENT_BUS_PATH = "data/event_bus.jsonl"
STATE_PATH = "data/strategy_reward_state.json"
GOVERNOR_PATH = "data/strategy_governor.json"
POLICY_PATH = "config/strategy_governor.json"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_policy():
    default = {
        "min_samples": 5,
        "watch_below": -0.02,
        "disable_below": -0.08,
        "min_win_rate": 0.40,
        "cooldown_days": 3
    }
    policy = _load_json(POLICY_PATH, {})
    if isinstance(policy, dict):
        default.update(policy)
    return default


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


def _load_event_bus():
    if not os.path.exists(EVENT_BUS_PATH):
        return []
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
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception:
        return []
    return out


def _load_state():
    state = _load_json(STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("last_ts", "")
    state.setdefault("last_ids", [])
    return state


def _save_state(state):
    _save_json(STATE_PATH, state)


def _get_strategies_from_signal(signal_source):
    if not isinstance(signal_source, dict):
        return []
    strategies = []
    if signal_source.get("strategy"):
        strategies.append(str(signal_source.get("strategy")).strip())
    if isinstance(signal_source.get("strategies"), list):
        strategies.extend([str(s).strip() for s in signal_source.get("strategies") if str(s).strip()])
    if isinstance(signal_source.get("strategy_votes"), list):
        for v in signal_source.get("strategy_votes"):
            if not isinstance(v, dict):
                continue
            name = v.get("strategy") or v.get("name")
            if name:
                strategies.append(str(name).strip())
    # de-dup
    out = []
    seen = set()
    for s in strategies:
        if not s:
            continue
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out


def update_strategy_rewards():
    """
    Incrementally update strategy rewards from new outcome events.
    """
    events = _load_event_bus()
    if not events:
        return {"updated": 0, "strategies": 0}

    # decision map to recover signal_source
    decision_map = {}
    for e in events:
        if e.get("event") != "decision":
            continue
        did = e.get("decision_id")
        if did:
            decision_map[str(did)] = e.get("payload", {})

    state = _load_state()
    last_ts = state.get("last_ts", "")
    last_ids = set(state.get("last_ids", []) or [])

    updated = 0
    reg = SkillRegistry()
    max_ts = last_ts
    new_ids = []

    for e in events:
        if e.get("event") != "outcome":
            continue
        ts = e.get("ts", "")
        ev_id = e.get("event_id") or e.get("id")
        if last_ts:
            # skip older events (idempotent)
            if ts < last_ts:
                continue
            if ts == last_ts and ev_id in last_ids:
                continue
        payload = e.get("payload", {}) if isinstance(e.get("payload", {}), dict) else {}
        pnl_pct = payload.get("pnl_pct")
        if pnl_pct is None:
            continue
        try:
            pnl_pct = float(pnl_pct)
        except Exception:
            continue

        signal_source = payload.get("signal_source") if isinstance(payload.get("signal_source"), dict) else {}
        if not signal_source:
            did = payload.get("origin_decision_id") or e.get("decision_id")
            d = decision_map.get(str(did)) if did is not None else None
            if isinstance(d, dict):
                signal_source = d.get("signal_source", {}) if isinstance(d.get("signal_source"), dict) else {}

        strategies = _get_strategies_from_signal(signal_source)
        for s in strategies:
            reg.update_reward(s, pnl_pct, source="outcome")
            updated += 1

        if ts and (not max_ts or ts > max_ts):
            max_ts = ts
        if ev_id:
            new_ids.append(ev_id)

    # keep last 50 ids for same-timestamp de-dup
    if max_ts:
        state["last_ts"] = max_ts
        if new_ids:
            state["last_ids"] = (list(last_ids) + new_ids)[-50:]
        _save_state(state)

    return {"updated": updated, "strategies": updated}


def build_governor_report(days=60):
    """
    Build strategy status report based on recent outcomes + registry stats.
    """
    policy = _load_policy()
    min_samples = int(policy.get("min_samples", 5) or 5)
    watch_below = float(policy.get("watch_below", -0.02) or -0.02)
    disable_below = float(policy.get("disable_below", -0.08) or -0.08)
    min_win_rate = float(policy.get("min_win_rate", 0.40) or 0.40)

    events = _load_event_bus()
    cutoff = datetime.datetime.now() - datetime.timedelta(days=int(days))
    stats = {}
    for e in events:
        if e.get("event") != "outcome":
            continue
        ts = _parse_ts(e.get("ts"))
        if ts and ts < cutoff:
            continue
        payload = e.get("payload", {}) if isinstance(e.get("payload", {}), dict) else {}
        pnl_pct = payload.get("pnl_pct")
        if pnl_pct is None:
            continue
        try:
            pnl_pct = float(pnl_pct)
        except Exception:
            continue
        signal_source = payload.get("signal_source") if isinstance(payload.get("signal_source"), dict) else {}
        strategies = _get_strategies_from_signal(signal_source)
        for s in strategies:
            row = stats.setdefault(s, {"samples": 0, "wins": 0, "pnl_sum": 0.0, "last_ts": ""})
            row["samples"] += 1
            row["pnl_sum"] += pnl_pct
            if pnl_pct > 0:
                row["wins"] += 1
            if e.get("ts") and (not row["last_ts"] or e.get("ts") > row["last_ts"]):
                row["last_ts"] = e.get("ts")

    # fallback to registry for empty strategies
    reg_stats = []
    try:
        reg_stats = SkillRegistry().get_leaderboard().to_dict("records")
    except Exception:
        reg_stats = []

    for row in reg_stats:
        name = str(row.get("name", "")).strip()
        if not name or name in stats:
            continue
        try:
            reward_sum = float(row.get("reward_sum", 0) or 0)
        except Exception:
            reward_sum = 0.0
        try:
            reward_count = int(row.get("reward_count", 0) or 0)
        except Exception:
            reward_count = 0
        if reward_count <= 0:
            continue
        stats[name] = {
            "samples": reward_count,
            "wins": int(row.get("hits", 0) or 0),
            "pnl_sum": reward_sum,
            "last_ts": row.get("last_reward_ts") or ""
        }

    report = {
        "updated_at": _now(),
        "policy": policy,
        "strategies": {}
    }
    for name, s in stats.items():
        samples = int(s.get("samples", 0) or 0)
        pnl_sum = float(s.get("pnl_sum", 0) or 0)
        wins = int(s.get("wins", 0) or 0)
        avg_pnl = pnl_sum / samples if samples else 0.0
        win_rate = wins / samples if samples else 0.0

        status = "seed"
        if samples >= min_samples:
            if avg_pnl <= disable_below or win_rate < min_win_rate:
                status = "disabled"
            elif avg_pnl <= watch_below:
                status = "watch"
            else:
                status = "active"

        report["strategies"][name] = {
            "status": status,
            "samples": samples,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "last_ts": s.get("last_ts", "")
        }

    _save_json(GOVERNOR_PATH, report)
    return report


def load_governor_status():
    data = _load_json(GOVERNOR_PATH, {})
    if not isinstance(data, dict):
        return {}
    strategies = data.get("strategies", {})
    if not isinstance(strategies, dict):
        return {}
    return strategies
