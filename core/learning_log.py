import datetime
import json
import os

from core.knowledge_base import KnowledgeBase
from core.event_bus import EventBus
from core.logger import exception


LOG_PATH = "data/learning_log.jsonl"


def _ensure_dir():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


def log_event(event_type, payload=None, meta=None, emit_bus=True):
    """
    Append a learning event in JSONL format.
    event_type: str
    payload/meta: dict
    """
    _ensure_dir()
    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "event": event_type,
        "payload": payload or {},
        "meta": meta or {}
    }
    try:
        if event_type == "paper_trade":
            p = payload if isinstance(payload, dict) else {}
            if p.get("action") == "SELL":
                try:
                    auto_update_knowledge_for_trade(p, record.get("ts"))
                except Exception as e:
                    exception("learning_log.knowledge_update_failed", e)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        exception("learning_log.write_failed", e, {"event": event_type})

    # optional event bus emission for non-trade learning events
    if emit_bus and event_type not in ("paper_trade",):
        try:
            payload = payload if isinstance(payload, dict) else {}
            code = payload.get("code") if isinstance(payload, dict) else None
            decision_id = payload.get("decision_id") if isinstance(payload, dict) else None
            EventBus().log(event_type, payload=payload, code=code, decision_id=decision_id, source="learning_log")
        except Exception as e:
            exception("learning_log.event_bus_emit_failed", e, {"event": event_type})


def load_events(limit=1000):
    if not os.path.exists(LOG_PATH):
        return []
    events = []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    if limit and len(events) > limit:
        return events[-limit:]
    return events


def summarize_behavior(events=None):
    events = events if events is not None else load_events()
    summary = {
        "total_events": len(events),
        "by_type": {},
        "risk_appetite": "平衡",
        "holding_preference": "中性",
        "activity_level": "低"
    }

    if not events:
        return summary

    # counts
    for e in events:
        et = e.get("event", "unknown")
        summary["by_type"][et] = summary["by_type"].get(et, 0) + 1

    # activity
    if len(events) >= 100:
        summary["activity_level"] = "高"
    elif len(events) >= 30:
        summary["activity_level"] = "中"

    # infer risk appetite from backtest params if available
    tps, sls, days = [], [], []
    for e in events:
        if e.get("event") == "backtest_run":
            p = e.get("payload", {})
            if isinstance(p.get("take_profit"), (int, float)):
                tps.append(float(p["take_profit"]))
            if isinstance(p.get("stop_loss"), (int, float)):
                sls.append(float(p["stop_loss"]))
            if isinstance(p.get("max_days"), (int, float)):
                days.append(float(p["max_days"]))

    if tps or sls:
        avg_tp = sum(tps) / len(tps) if tps else 0
        avg_sl = sum(sls) / len(sls) if sls else 0
        if avg_tp >= 0.20 or avg_sl >= 0.10:
            summary["risk_appetite"] = "激进"
        elif avg_tp <= 0.08 and avg_sl <= 0.04:
            summary["risk_appetite"] = "保守"
        else:
            summary["risk_appetite"] = "平衡"

    if days:
        avg_days = sum(days) / len(days)
        if avg_days >= 30:
            summary["holding_preference"] = "偏中长"
        elif avg_days <= 10:
            summary["holding_preference"] = "偏短线"

    return summary


def record_feature_weights(weights):
    if not isinstance(weights, dict):
        return
    log_event("feature_weights", {"weights": weights})


def get_last_feature_weights():
    events = load_events(2000)
    for ev in reversed(events):
        if ev.get("event") == "feature_weights":
            payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
            w = payload.get("weights")
            if isinstance(w, dict) and w:
                return w
    return {}


def extract_trade_outcomes(events=None):
    events = events if events is not None else load_events()
    trades = [e for e in events if e.get("event") == "paper_trade"]
    outcomes = []
    for e in trades:
        payload = e.get("payload", {}) if isinstance(e.get("payload"), dict) else {}
        if payload.get("action") != "SELL":
            continue
        outcomes.append({
            "ts": e.get("ts"),
            "code": payload.get("code"),
            "pnl": payload.get("pnl", 0),
            "reason": payload.get("reason")
        })
    return outcomes


def _parse_ts(ts):
    if isinstance(ts, datetime.datetime):
        return ts
    if isinstance(ts, datetime.date):
        return datetime.datetime.combine(ts, datetime.time.min)
    if isinstance(ts, str):
        try:
            return datetime.datetime.fromisoformat(ts)
        except Exception:
            try:
                return datetime.datetime.fromisoformat(ts[:19])
            except Exception:
                return None
    return None


def _norm_code(code):
    return str(code or "").strip().upper()


def _norm_titles(val):
    if not val:
        return []
    if isinstance(val, (list, tuple, set)):
        return [str(v).strip() for v in val if str(v).strip()]
    text = str(val)
    for sep in ["，", ";", "；", "|", "/", " "]:
        text = text.replace(sep, ",")
    return [t.strip() for t in text.split(",") if t.strip()]


def summarize_knowledge_effects(events=None, lookback_days=7, start_date=None, end_date=None):
    events = events if events is not None else load_events(5000)
    analysis_by_code = {}

    for e in events:
        if e.get("event") != "analysis_run":
            continue
        payload = e.get("payload", {}) if isinstance(e.get("payload"), dict) else {}
        titles = _norm_titles(payload.get("knowledge_titles") or payload.get("k_titles") or payload.get("knowledge"))
        if not titles:
            continue
        ts = _parse_ts(e.get("ts"))
        code = _norm_code(payload.get("code"))
        if not ts or not code:
            continue
        analysis_by_code.setdefault(code, []).append({"ts": ts, "titles": titles})

    for code, arr in analysis_by_code.items():
        arr.sort(key=lambda x: x["ts"])

    effects = {}
    links = []

    for e in events:
        if e.get("event") != "paper_trade":
            continue
        payload = e.get("payload", {}) if isinstance(e.get("payload"), dict) else {}
        if payload.get("action") != "SELL":
            continue
        ts = _parse_ts(e.get("ts"))
        if not ts:
            continue
        if start_date and ts.date() < start_date:
            continue
        if end_date and ts.date() > end_date:
            continue
        code = _norm_code(payload.get("code"))
        if not code:
            continue
        try:
            pnl = float(payload.get("pnl", 0) or 0)
        except Exception:
            pnl = 0.0

        candidates = analysis_by_code.get(code, [])
        match = None
        for a in reversed(candidates):
            if a["ts"] <= ts:
                if (ts - a["ts"]).days <= int(lookback_days):
                    match = a
                break
        if not match:
            continue

        links.append({
            "ts": ts.isoformat(timespec="seconds"),
            "code": code,
            "pnl": pnl,
            "titles": match.get("titles", [])
        })

        for title in match.get("titles", []):
            stats = effects.setdefault(title, {
                "title": title,
                "hits": 0,
                "wins": 0,
                "losses": 0,
                "pnl_sum": 0.0,
                "pnl_count": 0,
                "last_ts": ""
            })
            stats["hits"] += 1
            stats["pnl_sum"] += pnl
            stats["pnl_count"] += 1
            if pnl > 0:
                stats["wins"] += 1
            elif pnl < 0:
                stats["losses"] += 1
            if not stats["last_ts"] or ts.isoformat(timespec="seconds") > stats["last_ts"]:
                stats["last_ts"] = ts.isoformat(timespec="seconds")

    by_title = []
    for title, stats in effects.items():
        pnl_count = stats.get("pnl_count", 0) or 0
        avg_pnl = stats["pnl_sum"] / pnl_count if pnl_count else 0.0
        win_rate = stats["wins"] / pnl_count if pnl_count else 0.0
        stats["avg_pnl"] = avg_pnl
        stats["win_rate"] = win_rate
        stats["win_rate_str"] = f"{win_rate * 100:.1f}%" if pnl_count else "—"
        by_title.append(stats)

    by_title.sort(key=lambda x: (x.get("pnl_sum", 0), x.get("hits", 0)), reverse=True)
    return {
        "by_title": by_title,
        "links": links,
        "total_links": len(links)
    }


def _find_latest_analysis_titles(code, ts, events, lookback_days=7):
    if not events:
        return []
    code = _norm_code(code)
    for e in reversed(events):
        if e.get("event") != "analysis_run":
            continue
        payload = e.get("payload", {}) if isinstance(e.get("payload"), dict) else {}
        if _norm_code(payload.get("code")) != code:
            continue
        ts_a = _parse_ts(e.get("ts"))
        if not ts_a or ts_a > ts:
            continue
        if (ts - ts_a).days > int(lookback_days):
            continue
        titles = _norm_titles(payload.get("knowledge_titles") or payload.get("k_titles") or payload.get("knowledge"))
        if titles:
            return titles
    return []


def auto_update_knowledge_for_trade(trade_payload, ts=None, lookback_days=7):
    if not isinstance(trade_payload, dict):
        return False
    if trade_payload.get("action") != "SELL":
        return False
    code = _norm_code(trade_payload.get("code"))
    if not code:
        return False
    try:
        pnl = float(trade_payload.get("pnl", 0) or 0)
    except Exception:
        pnl = 0.0
    trade_ts = _parse_ts(ts) if ts else _parse_ts(trade_payload.get("ts"))
    if not trade_ts:
        return False

    events = load_events(5000)
    titles = _find_latest_analysis_titles(code, trade_ts, events, lookback_days=lookback_days)
    if not titles:
        return False

    kb = KnowledgeBase()
    updated = False
    for title in titles:
        if kb.record_trade_effect(title, pnl, ts=trade_ts):
            updated = True
    return updated
