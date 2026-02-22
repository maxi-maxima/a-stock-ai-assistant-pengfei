import datetime
import json
import os
import uuid

from core.event_bus import EventBus
from core.agent_hub import run_daily_agents
from core.metrics import compute_loop_health


EVENT_BUS_PATH = "data/event_bus.jsonl"
EXPERIENCE_LOG_PATH = "data/experience_log.jsonl"
TRADES_PATH = "data/trades.jsonl"
LOOP_REPORT_PATH = "data/loop_health_report.jsonl"


def _append_loop_report(record):
    try:
        os.makedirs(os.path.dirname(LOOP_REPORT_PATH), exist_ok=True)
        with open(LOOP_REPORT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


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


def _load_jsonl(path, limit=None):
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    if limit and len(out) > limit:
        out = out[-limit:]
    return out


def _filter_days(records, days):
    if not days:
        return records
    try:
        days = int(days)
    except Exception:
        return records
    if days <= 0:
        return records
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    out = []
    for r in records:
        ts = _parse_ts(r.get("ts")) if isinstance(r, dict) else None
        if ts is None or ts >= cutoff:
            out.append(r)
    return out


def _make_loose_key(event, decision_id, code):
    if event == "decision":
        return ("decision", str(decision_id))
    return (str(event), str(decision_id), str(code or ""))


def _index_event_bus(events):
    existing = set()
    for rec in events:
        if not isinstance(rec, dict):
            continue
        ev = rec.get("event")
        if ev not in ("decision", "execution", "outcome"):
            continue
        did = rec.get("decision_id")
        if not did:
            continue
        key = _make_loose_key(ev, did, rec.get("code", ""))
        existing.add(key)
    return existing


def backfill_event_bus_from_experience(days=30, limit=None, apply=True):
    exp = _load_jsonl(EXPERIENCE_LOG_PATH, limit=limit)
    exp = _filter_days(exp, days)
    existing = _load_jsonl(EVENT_BUS_PATH)
    existing_keys = _index_event_bus(existing)

    to_add = []
    skipped_dup = 0
    skipped_no_id = 0
    added_counts = {"decision": 0, "execution": 0, "outcome": 0}

    for rec in exp:
        if not isinstance(rec, dict):
            continue
        ev = rec.get("event")
        if ev not in ("decision", "execution", "outcome"):
            continue
        payload = rec.get("payload", {}) if isinstance(rec.get("payload"), dict) else {}
        decision_id = payload.get("decision_id") or rec.get("decision_id")
        if not decision_id:
            skipped_no_id += 1
            continue
        code = payload.get("code") or rec.get("code") or ""
        key = _make_loose_key(ev, decision_id, code)
        if key in existing_keys:
            skipped_dup += 1
            continue

        event_payload = dict(payload)
        if ev == "decision" and "action" in event_payload and "suggested_action" not in event_payload:
            event_payload["suggested_action"] = event_payload.get("action")

        out = {
            "event_id": uuid.uuid4().hex,
            "ts": rec.get("ts") or datetime.datetime.now().isoformat(timespec="seconds"),
            "event": ev,
            "code": str(code),
            "decision_id": decision_id,
            "source": "experience_backfill",
            "payload": event_payload
        }
        to_add.append(out)
        existing_keys.add(key)
        added_counts[ev] = added_counts.get(ev, 0) + 1

    if apply and to_add:
        os.makedirs(os.path.dirname(EVENT_BUS_PATH), exist_ok=True)
        try:
            with open(EVENT_BUS_PATH, "a", encoding="utf-8") as f:
                for rec in to_add:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    return {
        "scanned": len(exp),
        "added": added_counts,
        "skipped_duplicate": skipped_dup,
        "skipped_no_id": skipped_no_id
    }


def backfill_outcomes_from_trades(days=60, limit=None, apply=True):
    trades = _load_jsonl(TRADES_PATH, limit=limit)
    trades = _filter_days(trades, days)
    existing = _load_jsonl(EVENT_BUS_PATH)
    existing_keys = _index_event_bus(existing)
    bus = EventBus()

    added = 0
    for t in trades:
        if not isinstance(t, dict):
            continue
        if t.get("action") != "SELL":
            continue
        decision_id = t.get("origin_decision_id") or t.get("decision_id")
        if not decision_id:
            continue
        code = t.get("code") or ""
        key = _make_loose_key("outcome", decision_id, code)
        if key in existing_keys:
            continue
        payload = {
            "action": "SELL",
            "price": t.get("price"),
            "shares": t.get("shares"),
            "pnl": t.get("pnl"),
            "pnl_pct": t.get("pnl_pct"),
            "origin_decision_id": t.get("origin_decision_id"),
            "signal_source": t.get("signal_source"),
            "reason": t.get("reason")
        }
        if apply:
            try:
                bus.log(
                    "outcome",
                    payload=payload,
                    code=code,
                    decision_id=decision_id,
                    source="trade_backfill"
                )
            except Exception:
                pass
        existing_keys.add(key)
        added += 1

    return {"scanned": len(trades), "added": added}


def run_daily(days=60):
    result = {}
    try:
        result["backfill_experience"] = backfill_event_bus_from_experience(days=days, apply=True)
    except Exception:
        result["backfill_experience"] = {}
    try:
        result["backfill_trades"] = backfill_outcomes_from_trades(days=days, apply=True)
    except Exception:
        result["backfill_trades"] = {}
    try:
        enable_env = os.getenv("ENABLE_STRATEGY_TRAINER", "").strip()
        if enable_env == "1":
            from core.strategy_trainer import run_training
            result["strategy_training"] = run_training()
        elif enable_env == "":
            from core.strategy_trainer import run_training, _load_config
            cfg = _load_config()
            if isinstance(cfg, dict) and cfg.get("enabled", True):
                result["strategy_training"] = run_training(cfg)
    except Exception:
        result["strategy_training"] = {}
    try:
        report = compute_loop_health(days=days)
        if isinstance(report, dict):
            report["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
            result["loop_health"] = report
            _append_loop_report(report)
    except Exception:
        result["loop_health"] = {}
    try:
        context = {}
        if isinstance(result.get("loop_health"), dict):
            context["loop_health"] = result.get("loop_health")
        result["agent_reports"] = run_daily_agents(days=days, context=context)
    except Exception:
        result["agent_reports"] = {}
    return result


if __name__ == "__main__":
    print(run_daily())
