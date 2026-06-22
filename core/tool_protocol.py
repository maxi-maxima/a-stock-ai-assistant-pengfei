import datetime
import uuid


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def new_trace_id():
    return uuid.uuid4().hex


def _normalize_tags(val):
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        return [str(v).strip() for v in val if str(v).strip()]
    text = str(val).strip()
    return [text] if text else []


def build_tool_call(
    tool,
    args=None,
    caller=None,
    trace_id=None,
    timeout_s=None,
    dry_run=False,
    tags=None,
    ts=None
):
    return {
        "tool": str(tool or "").strip(),
        "caller": str(caller or "").strip(),
        "trace_id": str(trace_id or "").strip(),
        "args": args if isinstance(args, dict) else {},
        "timeout_s": timeout_s,
        "dry_run": bool(dry_run),
        "tags": _normalize_tags(tags),
        "ts": ts or _now()
    }


def build_tool_result(
    tool,
    ok,
    data=None,
    error=None,
    caller=None,
    trace_id=None,
    latency_ms=None,
    ts=None
):
    return {
        "tool": str(tool or "").strip(),
        "caller": str(caller or "").strip(),
        "trace_id": str(trace_id or "").strip(),
        "ok": bool(ok),
        "data": data if isinstance(data, dict) else {},
        "error": str(error or "").strip(),
        "latency_ms": latency_ms,
        "ts": ts or _now()
    }
