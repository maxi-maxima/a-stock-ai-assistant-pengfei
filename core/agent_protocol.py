import datetime
import uuid

from core.event_bus import EventBus
from core.protocols import get_protocol_version


AGENT_REPORT_EVENT = "agent_report"
ALLOWED_STATUSES = {"ok", "warn", "fail", "idle"}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def new_run_id():
    return uuid.uuid4().hex


def _normalize_status(status):
    status = str(status or "").strip().lower()
    if status not in ALLOWED_STATUSES:
        return "idle"
    return status


def _normalize_list(val):
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        return [str(x).strip() for x in val if str(x).strip()]
    text = str(val).strip()
    return [text] if text else []


def build_agent_report(
    agent_id,
    agent_type,
    status,
    summary="",
    details=None,
    metrics=None,
    recommendations=None,
    tags=None,
    run_id=None,
    version="1.0",
    ts=None
):
    """
    Build a normalized agent report payload.
    """
    return {
        "agent_id": str(agent_id or "").strip(),
        "agent_type": str(agent_type or agent_id or "").strip(),
        "status": _normalize_status(status),
        "summary": str(summary or "").strip(),
        "details": details if isinstance(details, dict) else {},
        "metrics": metrics if isinstance(metrics, dict) else {},
        "recommendations": _normalize_list(recommendations),
        "tags": _normalize_list(tags),
        "run_id": str(run_id or "").strip(),
        "version": str(version or "").strip() or "1.0",
        "protocol_version": get_protocol_version(),
        "ts": ts or _now()
    }


def emit_agent_report(report, bus=None, source="agent_hub"):
    """
    Emit a normalized agent report into the event bus.
    """
    report = report if isinstance(report, dict) else {}
    if not report.get("agent_id"):
        report["agent_id"] = "unknown"
    if not report.get("agent_type"):
        report["agent_type"] = report.get("agent_id")
    if not report.get("status"):
        report["status"] = "idle"
    if not report.get("ts"):
        report["ts"] = _now()

    bus = bus or EventBus()
    bus.log(
        AGENT_REPORT_EVENT,
        payload=report,
        source=source
    )
    return report
