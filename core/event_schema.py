import datetime
import uuid


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _new_id():
    return uuid.uuid4().hex


def _safe_float(val):
    try:
        return float(val)
    except Exception:
        return None


def _upper_action(val):
    if val is None:
        return ""
    return str(val).strip().upper()


def normalize_event(event_type, payload=None, code=None, decision_id=None, source=None, ts=None):
    """
    Create a normalized event record with minimal guarantees.
    """
    payload = payload if isinstance(payload, dict) else {}
    event_type = str(event_type or "").strip()

    # normalize action fields if present
    if "action" in payload:
        payload["action"] = _upper_action(payload.get("action"))
    if "suggested_action" in payload:
        payload["suggested_action"] = _upper_action(payload.get("suggested_action"))

    # link outcome/execution to decision if missing
    if event_type in ("execution", "outcome"):
        if not payload.get("origin_decision_id") and decision_id:
            payload["origin_decision_id"] = decision_id

    record = {
        "event_id": _new_id(),
        "ts": ts or _now(),
        "event": event_type,
        "code": str(code or payload.get("code") or "").strip(),
        "decision_id": decision_id or payload.get("decision_id"),
        "source": str(source or ""),
        "payload": payload
    }
    return record


def validate_event(record):
    """
    Validate a normalized record. Returns (ok, errors list).
    """
    errors = []
    if not isinstance(record, dict):
        return False, ["record_not_dict"]
    event_type = record.get("event")
    payload = record.get("payload", {}) if isinstance(record.get("payload"), dict) else {}

    if not record.get("ts"):
        errors.append("missing_ts")
    if not event_type:
        errors.append("missing_event")

    # required by type
    if event_type == "decision":
        if not payload.get("action"):
            errors.append("decision_missing_action")
        if payload.get("suggested_action") is None and payload.get("action"):
            payload["suggested_action"] = payload.get("action")
    elif event_type == "execution":
        if not payload.get("action"):
            errors.append("execution_missing_action")
        if _safe_float(payload.get("price")) is None:
            errors.append("execution_missing_price")
        if _safe_float(payload.get("shares")) is None:
            errors.append("execution_missing_shares")
    elif event_type == "outcome":
        if not payload.get("action"):
            errors.append("outcome_missing_action")
        if payload.get("origin_decision_id") is None and record.get("decision_id") is None:
            errors.append("outcome_missing_decision_id")
        if _safe_float(payload.get("pnl")) is None and _safe_float(payload.get("pnl_pct")) is None:
            errors.append("outcome_missing_pnl")
    elif event_type == "agent_report":
        if not payload.get("agent_id"):
            errors.append("agent_missing_agent_id")
        if not payload.get("status"):
            errors.append("agent_missing_status")

    # ensure action upper
    if "action" in payload:
        payload["action"] = _upper_action(payload.get("action"))
    if "suggested_action" in payload:
        payload["suggested_action"] = _upper_action(payload.get("suggested_action"))

    # write back normalized payload
    record["payload"] = payload
    return len(errors) == 0, errors
