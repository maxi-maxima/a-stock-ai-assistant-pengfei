import datetime
import json
import os
import uuid

from core.event_bus import EventBus
from core.agent_hub import run_daily_agents
from core.metrics import compute_loop_health
from core.learning_engine_v2 import refresh_learning_views
from core.experiment_tracker_v1 import refresh_experiment_tracking
from skills.data_factory import DataSkillFactory


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


def _make_loose_key(event, decision_id, code, payload=None):
    if event == "decision":
        return ("decision", str(decision_id))
    if event == "outcome":
        payload = payload if isinstance(payload, dict) else {}
        eval_type = str(payload.get("eval_type") or payload.get("outcome_type") or payload.get("action") or "").strip().lower()
        eval_date = str(payload.get("eval_date") or "")[:10]
        return ("outcome", str(decision_id), str(code or ""), eval_type, eval_date)
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
        payload = rec.get("payload", {}) if isinstance(rec.get("payload"), dict) else {}
        if not did:
            continue
        key = _make_loose_key(ev, did, rec.get("code", ""), payload=payload)
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
        key = _make_loose_key(ev, decision_id, code, payload=payload)
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
        key = _make_loose_key("outcome", decision_id, code, payload={"eval_type": "sell_realized"})
        if key in existing_keys:
            continue
        payload = {
            "action": "SELL",
            "eval_type": "sell_realized",
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


def _safe_float(val):
    try:
        return float(val)
    except Exception:
        return None


def _extract_entry_price(payload):
    payload = payload if isinstance(payload, dict) else {}
    market = payload.get("market_data", {}) if isinstance(payload.get("market_data"), dict) else {}
    candidates = [
        market.get("latest_price"),
        payload.get("price"),
        payload.get("entry_price"),
    ]
    for c in candidates:
        v = _safe_float(c)
        if v is not None and v > 0:
            return v
    return None


def _build_existing_outcome_keys(events):
    keys = set()
    for rec in events:
        if not isinstance(rec, dict) or rec.get("event") != "outcome":
            continue
        payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
        did = rec.get("decision_id") or payload.get("origin_decision_id") or payload.get("decision_id")
        if not did:
            continue
        code = str(rec.get("code") or payload.get("code") or "").strip().upper()
        eval_type = str(payload.get("eval_type") or payload.get("outcome_type") or "legacy").strip().lower()
        eval_date = str(payload.get("eval_date") or str(rec.get("ts") or "")[:10] or "").strip()
        keys.add((str(did), code, eval_type, eval_date))
    return keys


def backfill_outcomes_from_mark_to_market(days=60, limit=None, apply=True):
    """
    Generate daily mark-to-market outcomes for decisions without waiting for SELL.
    This improves decision->outcome linkage for learning loops.
    """
    events = _load_jsonl(EVENT_BUS_PATH, limit=limit)
    events = _filter_days(events, days)
    decisions = [e for e in events if isinstance(e, dict) and e.get("event") == "decision"]
    existing_keys = _build_existing_outcome_keys(events)
    bus = EventBus()

    try:
        max_decisions = int(os.getenv("MTM_MAX_DECISIONS", "1200") or 1200)
    except Exception:
        max_decisions = 1200
    if max_decisions > 0 and len(decisions) > max_decisions:
        decisions = decisions[-max_decisions:]

    # preload latest prices once per code
    codes = []
    for d in decisions:
        payload = d.get("payload", {}) if isinstance(d.get("payload", {}), dict) else {}
        code = str(d.get("code") or payload.get("code") or "").strip().upper()
        if code:
            codes.append(code)
    codes = list(dict.fromkeys(codes))

    data_skill = None
    try:
        data_skill = DataSkillFactory.get_skill("tushare")
    except Exception:
        data_skill = None

    price_map = {}
    date_map = {}
    for code in codes:
        if not data_skill:
            continue
        try:
            df = data_skill.get_history(code, days=120)
            if df is None or df.empty:
                continue
            latest = df.iloc[-1]
            mark_price = _safe_float(latest.get("close"))
            mark_date = str(latest.get("date") or "")[:10]
            if mark_price is None or mark_price <= 0:
                continue
            price_map[code] = mark_price
            if mark_date:
                date_map[code] = mark_date
        except Exception:
            continue

    today = datetime.datetime.now().date().isoformat()
    added = 0
    skipped_existing = 0
    skipped_invalid = 0

    for d in decisions:
        if not isinstance(d, dict):
            continue
        payload = d.get("payload", {}) if isinstance(d.get("payload", {}), dict) else {}
        did = d.get("decision_id") or payload.get("decision_id")
        code = str(d.get("code") or payload.get("code") or "").strip().upper()
        action = str(payload.get("action") or "").strip().upper()
        if not did or not code:
            skipped_invalid += 1
            continue
        if action not in ("BUY", "SELL", "HOLD"):
            skipped_invalid += 1
            continue

        mark_price = _safe_float(price_map.get(code))
        if mark_price is None or mark_price <= 0:
            skipped_invalid += 1
            continue
        mark_date = date_map.get(code) or today
        key = (str(did), code, "mark_to_market", mark_date)
        if key in existing_keys:
            skipped_existing += 1
            continue

        entry_price = _extract_entry_price(payload)
        if entry_price is None or entry_price <= 0:
            skipped_invalid += 1
            continue

        if action == "BUY":
            pnl_pct = (mark_price - entry_price) / entry_price
        elif action == "SELL":
            pnl_pct = (entry_price - mark_price) / entry_price
        else:
            pnl_pct = 0.0

        ts = _parse_ts(d.get("ts"))
        eval_days = None
        if ts is not None:
            try:
                eval_days = max(0, (datetime.datetime.now().date() - ts.date()).days)
            except Exception:
                eval_days = None

        out_payload = {
            "action": action,
            "origin_decision_id": did,
            "signal_source": payload.get("signal_source"),
            "eval_type": "mark_to_market",
            "eval_date": mark_date,
            "eval_days": eval_days,
            "price_entry": entry_price,
            "price_mark": mark_price,
            "pnl": 0.0,
            "pnl_pct": pnl_pct,
            "synthetic": True,
            "reason": "daily_mark_to_market",
        }

        if apply:
            try:
                bus.log(
                    "outcome",
                    payload=out_payload,
                    code=code,
                    decision_id=did,
                    source="mtm_backfill",
                )
            except Exception:
                skipped_invalid += 1
                continue
        added += 1
        existing_keys.add(key)

    return {
        "scanned_decisions": len(decisions),
        "added": added,
        "skipped_existing": skipped_existing,
        "skipped_invalid": skipped_invalid,
        "codes": len(codes),
    }


def audit_decision_id_integrity(days=60, limit=None):
    events = _load_jsonl(EVENT_BUS_PATH, limit=limit)
    events = _filter_days(events, days)
    decisions = [e for e in events if isinstance(e, dict) and e.get("event") == "decision"]
    executions = [e for e in events if isinstance(e, dict) and e.get("event") == "execution"]
    outcomes = [e for e in events if isinstance(e, dict) and e.get("event") == "outcome"]

    missing_decision = sum(1 for e in decisions if not e.get("decision_id"))
    missing_execution = sum(1 for e in executions if not e.get("decision_id"))
    missing_outcome = 0
    for e in outcomes:
        payload = e.get("payload", {}) if isinstance(e.get("payload", {}), dict) else {}
        did = e.get("decision_id") or payload.get("origin_decision_id") or payload.get("decision_id")
        if not did:
            missing_outcome += 1

    return {
        "decisions": len(decisions),
        "executions": len(executions),
        "outcomes": len(outcomes),
        "decision_missing_id": missing_decision,
        "execution_missing_id": missing_execution,
        "outcome_missing_id": missing_outcome,
        "ok": (missing_decision == 0 and missing_execution == 0 and missing_outcome == 0),
    }


def run_daily(days=60):
    result = {}
    try:
        result["decision_id_audit"] = audit_decision_id_integrity(days=days)
    except Exception:
        result["decision_id_audit"] = {}
    try:
        result["backfill_experience"] = backfill_event_bus_from_experience(days=days, apply=True)
    except Exception:
        result["backfill_experience"] = {}
    try:
        result["backfill_trades"] = backfill_outcomes_from_trades(days=days, apply=True)
    except Exception:
        result["backfill_trades"] = {}
    try:
        result["backfill_mark_to_market"] = backfill_outcomes_from_mark_to_market(days=days, apply=True)
    except Exception:
        result["backfill_mark_to_market"] = {}
    try:
        result["learning_views"] = refresh_learning_views(days=max(30, int(days or 60)), apply=True)
    except Exception:
        result["learning_views"] = {}
    try:
        result["experiment_tracking"] = refresh_experiment_tracking(apply=True)
    except Exception:
        result["experiment_tracking"] = {}
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
        windows = sorted(set([7, 30, int(days)]))
    except Exception:
        windows = [7, 30, 60]
    try:
        window_reports = {}
        for w in windows:
            if w == int(days) and isinstance(result.get("loop_health"), dict) and result.get("loop_health"):
                wr = dict(result.get("loop_health"))
            else:
                wr = compute_loop_health(days=w)
            if isinstance(wr, dict):
                window_reports[str(w)] = wr
        result["loop_health_windows"] = window_reports
    except Exception:
        result["loop_health_windows"] = {}
    try:
        context = {}
        if isinstance(result.get("loop_health"), dict):
            context["loop_health"] = result.get("loop_health")
        if isinstance(result.get("loop_health_windows"), dict):
            context["loop_health_windows"] = result.get("loop_health_windows")
        result["agent_reports"] = run_daily_agents(days=days, context=context)
    except Exception:
        result["agent_reports"] = {}
    return result


if __name__ == "__main__":
    print(run_daily())
