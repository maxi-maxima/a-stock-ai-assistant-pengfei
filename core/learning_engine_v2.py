import datetime
import json
import math
import os

from core.decision_sample import ensure_decision_sample


EVENT_BUS_PATH = "data/event_bus.jsonl"
SAMPLES_PATH = "data/learning_samples.jsonl"
PROFILES_PATH = "data/strategy_profiles.json"


REALIZED_TYPES = {"sell_realized", "realized", "final"}
MTM_TYPES = {"mark_to_market", "mtm", "unrealized"}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


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


def _safe_float(val):
    try:
        return float(val)
    except Exception:
        return None


def _days_ago(ts, now=None):
    dt = _parse_ts(ts)
    if dt is None:
        return 0
    now_dt = now if isinstance(now, datetime.datetime) else datetime.datetime.now()
    try:
        return max(0, (now_dt.date() - dt.date()).days)
    except Exception:
        return 0


def _load_jsonl(path):
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
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception:
        return []
    return out


def _write_jsonl(path, rows):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                if isinstance(row, dict):
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _outcome_priority(payload):
    payload = payload if isinstance(payload, dict) else {}
    eval_type = str(payload.get("eval_type") or payload.get("outcome_type") or "").strip().lower()
    if eval_type in REALIZED_TYPES:
        return 2
    if eval_type in MTM_TYPES:
        return 1
    return 0


def _outcome_eval_date(rec):
    if not isinstance(rec, dict):
        return ""
    payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
    dt = str(payload.get("eval_date") or "")[:10]
    if dt:
        return dt
    ts = str(rec.get("ts") or "")
    return ts[:10]


def _choose_best_outcome(records):
    best = None
    best_key = None
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
        pnl_pct = _safe_float(payload.get("pnl_pct"))
        if pnl_pct is None:
            continue
        key = (
            _outcome_priority(payload),
            _outcome_eval_date(rec),
            str(rec.get("ts") or ""),
        )
        if best is None or key > best_key:
            best = rec
            best_key = key
    return best


def _sample_quality(sample):
    score = 0
    reasons = []
    if sample.get("thesis"):
        score += 25
    else:
        reasons.append("missing_thesis")
    if isinstance(sample.get("risk_points"), list) and sample.get("risk_points"):
        score += 20
    else:
        reasons.append("missing_risk_points")
    conf = _safe_float(sample.get("confidence"))
    if conf is not None and 0 <= conf <= 1:
        score += 15
    else:
        reasons.append("invalid_confidence")
    tags = sample.get("strategy_tags") if isinstance(sample.get("strategy_tags"), list) else []
    if tags:
        score += 15
    else:
        reasons.append("missing_strategy_tags")
    if sample.get("outcome_pnl_pct") is not None:
        score += 15
    else:
        reasons.append("missing_outcome")
    if str(sample.get("outcome_eval_type") or "").lower() in REALIZED_TYPES:
        score += 10
    score = max(0, min(100, int(score)))
    return score, reasons


def _build_sample(decision, outcome=None):
    decision = decision if isinstance(decision, dict) else {}
    payload = decision.get("payload", {}) if isinstance(decision.get("payload", {}), dict) else {}
    payload = ensure_decision_sample(payload)
    ds = payload.get("decision_sample", {}) if isinstance(payload.get("decision_sample", {}), dict) else {}

    rec = {
        "decision_id": decision.get("decision_id"),
        "ts": decision.get("ts"),
        "code": decision.get("code") or payload.get("code"),
        "action": payload.get("action"),
        "suggested_action": payload.get("suggested_action"),
        "thesis": ds.get("thesis"),
        "risk_points": ds.get("risk_points", []),
        "confidence": ds.get("confidence"),
        "strategy_tags": ds.get("strategy_tags", []),
        "timeframe": ds.get("timeframe"),
        "decision_sample_version": ds.get("version", "v2"),
    }

    out_payload = outcome.get("payload", {}) if isinstance(outcome, dict) and isinstance(outcome.get("payload", {}), dict) else {}
    pnl_pct = _safe_float(out_payload.get("pnl_pct"))
    rec["outcome_pnl_pct"] = pnl_pct
    rec["outcome_eval_type"] = str(out_payload.get("eval_type") or out_payload.get("outcome_type") or "").strip().lower()
    rec["outcome_eval_date"] = _outcome_eval_date(outcome) if isinstance(outcome, dict) else ""
    rec["label"] = "win" if pnl_pct is not None and pnl_pct > 0 else ("loss" if pnl_pct is not None and pnl_pct < 0 else ("flat" if pnl_pct == 0 else "unknown"))

    quality_score, quality_issues = _sample_quality(rec)
    rec["quality_score"] = quality_score
    rec["quality_issues"] = quality_issues
    rec["sample_valid"] = quality_score >= 60
    return rec


def _aggregate_profiles(samples, now=None, half_life_days=30):
    now_dt = now if isinstance(now, datetime.datetime) else datetime.datetime.now()
    profiles = {}
    half_life_days = max(1, int(half_life_days or 30))

    for s in samples:
        tags = s.get("strategy_tags") if isinstance(s.get("strategy_tags"), list) else []
        if not tags:
            continue
        age = _days_ago(s.get("ts"), now=now_dt)
        decay = math.exp(-float(age) / float(half_life_days))
        pnl_pct = _safe_float(s.get("outcome_pnl_pct"))
        conf = _safe_float(s.get("confidence"))

        for tag in tags:
            tag = str(tag or "").strip()
            if not tag:
                continue
            row = profiles.setdefault(
                tag,
                {
                    "sample_count": 0,
                    "valid_count": 0,
                    "labeled_count": 0,
                    "win_count": 0,
                    "pnl_sum": 0.0,
                    "conf_sum": 0.0,
                    "conf_count": 0,
                    "decay_weight_sum": 0.0,
                    "decay_pnl_sum": 0.0,
                    "last_ts": "",
                    "recent_7_sum": 0.0,
                    "recent_7_count": 0,
                    "recent_30_sum": 0.0,
                    "recent_30_count": 0,
                },
            )
            row["sample_count"] += 1
            if s.get("sample_valid"):
                row["valid_count"] += 1
            if conf is not None:
                row["conf_sum"] += conf
                row["conf_count"] += 1
            if s.get("ts") and (not row["last_ts"] or str(s.get("ts")) > row["last_ts"]):
                row["last_ts"] = str(s.get("ts"))

            if pnl_pct is not None:
                row["labeled_count"] += 1
                row["pnl_sum"] += pnl_pct
                if pnl_pct > 0:
                    row["win_count"] += 1
                row["decay_weight_sum"] += decay
                row["decay_pnl_sum"] += pnl_pct * decay
                if age <= 7:
                    row["recent_7_sum"] += pnl_pct
                    row["recent_7_count"] += 1
                if age <= 30:
                    row["recent_30_sum"] += pnl_pct
                    row["recent_30_count"] += 1

    out = {}
    champion_tag = ""
    champion_score = None
    drift_warnings = []

    for tag, row in profiles.items():
        labeled = int(row.get("labeled_count", 0) or 0)
        samples = int(row.get("sample_count", 0) or 0)
        valid = int(row.get("valid_count", 0) or 0)
        win_rate = (row.get("win_count", 0) / labeled) if labeled else 0.0
        avg_pnl = (row.get("pnl_sum", 0.0) / labeled) if labeled else 0.0
        avg_conf = (row.get("conf_sum", 0.0) / row.get("conf_count", 1)) if row.get("conf_count", 0) else 0.0
        decayed_pnl = (row.get("decay_pnl_sum", 0.0) / row.get("decay_weight_sum", 1.0)) if row.get("decay_weight_sum", 0) else 0.0
        recent_7 = (row.get("recent_7_sum", 0.0) / row.get("recent_7_count", 1)) if row.get("recent_7_count", 0) else None
        recent_30 = (row.get("recent_30_sum", 0.0) / row.get("recent_30_count", 1)) if row.get("recent_30_count", 0) else None

        drift = None
        if recent_7 is not None and recent_30 is not None:
            drift = recent_7 - recent_30
            if row.get("recent_7_count", 0) >= 2 and drift < -0.015:
                drift_warnings.append(
                    {
                        "strategy": tag,
                        "drift": round(drift, 4),
                        "recent_7_avg": round(recent_7, 4),
                        "recent_30_avg": round(recent_30, 4),
                    }
                )

        out[tag] = {
            "sample_count": samples,
            "valid_count": valid,
            "valid_rate": round(valid / samples, 4) if samples else 0.0,
            "labeled_count": labeled,
            "win_rate": round(win_rate, 4),
            "avg_pnl_pct": round(avg_pnl, 6),
            "avg_confidence": round(avg_conf, 4),
            "decayed_pnl_pct": round(decayed_pnl, 6),
            "recent_7_avg": None if recent_7 is None else round(recent_7, 6),
            "recent_30_avg": None if recent_30 is None else round(recent_30, 6),
            "drift_7_vs_30": None if drift is None else round(drift, 6),
            "last_ts": row.get("last_ts", ""),
        }

        if labeled >= 3:
            score = decayed_pnl
            if champion_score is None or score > champion_score:
                champion_score = score
                champion_tag = tag

    drift_warnings = sorted(drift_warnings, key=lambda x: x.get("drift", 0))
    return out, champion_tag, champion_score, drift_warnings


def build_learning_views_from_events(events, now=None, half_life_days=30):
    events = events if isinstance(events, list) else []

    decisions_by_id = {}
    outcomes_by_id = {}

    for rec in events:
        if not isinstance(rec, dict):
            continue
        ev = rec.get("event")
        payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
        did = rec.get("decision_id") or payload.get("origin_decision_id") or payload.get("decision_id")
        if not did:
            continue

        if ev == "decision":
            old = decisions_by_id.get(str(did))
            if old is None:
                decisions_by_id[str(did)] = rec
            else:
                if str(rec.get("ts") or "") >= str(old.get("ts") or ""):
                    decisions_by_id[str(did)] = rec
        elif ev == "outcome":
            outcomes_by_id.setdefault(str(did), []).append(rec)

    samples = []
    for did, decision in decisions_by_id.items():
        best_out = _choose_best_outcome(outcomes_by_id.get(str(did), []))
        samples.append(_build_sample(decision, best_out))
    samples = sorted(samples, key=lambda x: str(x.get("ts") or ""), reverse=True)

    now_dt = now if isinstance(now, datetime.datetime) else datetime.datetime.now()
    profiles, champion_tag, champion_score, drift_warnings = _aggregate_profiles(samples, now=now_dt, half_life_days=half_life_days)

    valid_count = sum(1 for s in samples if s.get("sample_valid"))
    labeled_count = sum(1 for s in samples if s.get("outcome_pnl_pct") is not None)
    summary = {
        "updated_at": _now(),
        "decision_count": len(decisions_by_id),
        "sample_count": len(samples),
        "valid_count": valid_count,
        "valid_rate": round(valid_count / len(samples), 4) if samples else 0.0,
        "labeled_count": labeled_count,
        "labeled_rate": round(labeled_count / len(samples), 4) if samples else 0.0,
        "profile_count": len(profiles),
        "champion_strategy": champion_tag,
        "champion_decayed_pnl_pct": None if champion_score is None else round(champion_score, 6),
        "drift_warning_count": len(drift_warnings),
        "drift_warnings": drift_warnings[:12],
    }

    return {"summary": summary, "samples": samples, "profiles": profiles}


def refresh_learning_views(days=365, apply=True, event_bus_path=EVENT_BUS_PATH):
    events = _load_jsonl(event_bus_path)
    if days:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=int(days))
        filt = []
        for rec in events:
            ts = _parse_ts(rec.get("ts")) if isinstance(rec, dict) else None
            if ts is None or ts >= cutoff:
                filt.append(rec)
        events = filt

    out = build_learning_views_from_events(events)
    summary = dict(out.get("summary", {}))
    summary["days"] = int(days or 0)
    summary["event_count"] = len(events)

    if apply:
        _write_jsonl(SAMPLES_PATH, out.get("samples", []))
        data = {
            "summary": summary,
            "profiles": out.get("profiles", {}),
            "top_profiles": sorted(
                [
                    {"strategy": k, **v}
                    for k, v in (out.get("profiles", {}) or {}).items()
                    if isinstance(v, dict)
                ],
                key=lambda x: (x.get("decayed_pnl_pct", 0), x.get("labeled_count", 0)),
                reverse=True,
            )[:30],
        }
        _write_json(PROFILES_PATH, data)

    return {
        "ok": True,
        "days": int(days or 0),
        "event_count": len(events),
        "sample_count": summary.get("sample_count", 0),
        "valid_rate": summary.get("valid_rate", 0.0),
        "labeled_rate": summary.get("labeled_rate", 0.0),
        "champion_strategy": summary.get("champion_strategy", ""),
        "drift_warning_count": summary.get("drift_warning_count", 0),
    }
