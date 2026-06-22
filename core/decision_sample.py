import datetime


ALLOWED_TIMEFRAMES = {
    "intraday",
    "swing_1_5d",
    "swing_3_10d",
    "position_10_30d",
    "watchlist",
}


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except Exception:
        return float(default)


def _clip_text(text, limit=280):
    text = str(text or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _normalize_list(items, limit=8):
    if items is None:
        return []
    if isinstance(items, (list, tuple, set)):
        seq = list(items)
    else:
        seq = [items]
    out = []
    seen = set()
    for x in seq:
        v = str(x or "").strip()
        if not v:
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
        if limit and len(out) >= int(limit):
            break
    return out


def _split_risk_points(text, limit=5):
    text = str(text or "").strip()
    if not text:
        return []
    for sep in ("\n", ";", "；", "。", "|", "、", ",", "，"):
        text = text.replace(sep, "|")
    parts = [p.strip(" .:：-") for p in text.split("|")]
    parts = [p for p in parts if p]
    return parts[: int(limit)]


def _extract_strategy_tags(signal_source, context_tags=None, limit=8):
    tags = []
    src = signal_source if isinstance(signal_source, dict) else {}
    strategy = src.get("strategy")
    if strategy:
        tags.append(strategy)
    strategies = src.get("strategies")
    if isinstance(strategies, list):
        tags.extend(strategies)
    elif isinstance(strategies, str):
        tags.append(strategies)
    votes = src.get("strategy_votes") or src.get("votes")
    if isinstance(votes, list):
        for vote in votes:
            if not isinstance(vote, dict):
                continue
            name = vote.get("strategy") or vote.get("name")
            if name:
                tags.append(name)
    if isinstance(context_tags, list):
        tags.extend(context_tags[:4])
    return _normalize_list(tags, limit=limit)


def _infer_timeframe(action, debate):
    action = str(action or "").upper()
    if action == "HOLD":
        return "watchlist"

    note = ""
    if isinstance(debate, dict):
        grid = debate.get("grid_strategy")
        if isinstance(grid, dict):
            note = str(grid.get("note") or "")
    note_low = note.lower()
    if "intraday" in note_low or "daytrade" in note_low:
        return "intraday"
    if "position" in note_low or "中长" in note or "波段" in note:
        return "position_10_30d"
    return "swing_3_10d"


def _compute_confidence(debate, action):
    debate = debate if isinstance(debate, dict) else {}
    scores = debate.get("scores", {}) if isinstance(debate.get("scores", {}), dict) else {}
    total = _safe_float(scores.get("total", 50), default=50)
    base = (total - 40.0) / 60.0
    risk = debate.get("risk", {}) if isinstance(debate.get("risk", {}), dict) else {}
    risk_score = _safe_float(risk.get("score", 0), default=0)
    penalty = max(0.0, min(0.35, risk_score / 300.0))
    conf = base - penalty
    if str(action or "").upper() == "HOLD":
        conf = min(conf, 0.7)
    conf = max(0.0, min(1.0, conf))
    return round(conf, 4)


def build_decision_sample(
    debate,
    action,
    suggested_action=None,
    signal_source=None,
    context_tags=None,
    policy_notes=None,
):
    debate = debate if isinstance(debate, dict) else {}
    action = str(action or "").strip().upper() or "HOLD"
    suggested_action = str(suggested_action or action).strip().upper() or action

    thesis = (
        debate.get("final_verdict")
        or debate.get("core_view")
        or (debate.get("scores", {}) if isinstance(debate.get("scores", {}), dict) else {}).get("reason")
        or "观点信息不足，先观察。"
    )
    thesis = _clip_text(thesis, limit=320)

    risk_points = []
    risk_points.extend(_split_risk_points(debate.get("risk_warning"), limit=4))
    if isinstance(policy_notes, list):
        risk_points.extend([str(x).strip() for x in policy_notes if str(x).strip()])
    risk_points = _normalize_list(risk_points, limit=6)
    if not risk_points:
        risk_points = ["暂无显著风险点，需持续跟踪。"]

    strategy_tags = _extract_strategy_tags(signal_source, context_tags=context_tags, limit=8)
    if not strategy_tags:
        strategy_tags = ["tri_brain_default"]

    timeframe = _infer_timeframe(action, debate)
    if timeframe not in ALLOWED_TIMEFRAMES:
        timeframe = "swing_3_10d"

    sample = {
        "version": "v2",
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "suggested_action": suggested_action,
        "thesis": thesis,
        "risk_points": risk_points,
        "confidence": _compute_confidence(debate, action),
        "strategy_tags": strategy_tags,
        "timeframe": timeframe,
    }
    return sample


def ensure_decision_sample(payload, fallback_sample=None):
    payload = dict(payload or {})
    existing = payload.get("decision_sample")
    if isinstance(existing, dict):
        sample = dict(existing)
    else:
        sample = {}

    if not sample and isinstance(fallback_sample, dict):
        sample = dict(fallback_sample)

    if not sample:
        sample = build_decision_sample(
            debate={
                "core_view": payload.get("core_view"),
                "risk_warning": payload.get("risk_warning"),
                "scores": payload.get("scores"),
                "risk": payload.get("risk"),
                "grid_strategy": payload.get("grid_strategy"),
                "scenarios": payload.get("scenarios"),
            },
            action=payload.get("action"),
            suggested_action=payload.get("suggested_action"),
            signal_source=payload.get("signal_source"),
            context_tags=payload.get("context_tags"),
            policy_notes=payload.get("policy_notes"),
        )

    sample.setdefault("version", "v2")
    sample.setdefault("created_at", datetime.datetime.now().isoformat(timespec="seconds"))
    sample["thesis"] = _clip_text(sample.get("thesis") or "观点信息不足，先观察。", limit=320)
    sample["risk_points"] = _normalize_list(sample.get("risk_points"), limit=6)
    if not sample["risk_points"]:
        sample["risk_points"] = ["暂无显著风险点，需持续跟踪。"]
    sample["confidence"] = max(0.0, min(1.0, _safe_float(sample.get("confidence", 0.5), default=0.5)))
    sample["strategy_tags"] = _normalize_list(sample.get("strategy_tags"), limit=8) or ["tri_brain_default"]
    timeframe = str(sample.get("timeframe") or "").strip()
    sample["timeframe"] = timeframe if timeframe in ALLOWED_TIMEFRAMES else _infer_timeframe(payload.get("action"), {})

    payload["decision_sample"] = sample
    return payload
