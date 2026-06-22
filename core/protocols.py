import json
import os

from core.logger import warn


PROTOCOL_PATH = "config/protocols.json"


def _default_protocol():
    return {
        "version": "1.1",
        "agent_report": {
            "required": ["agent_id", "agent_type", "status", "summary"],
            "allowed_statuses": ["ok", "warn", "fail", "idle"]
        },
        "decision": {
            "required": ["action", "suggested_action", "scores", "feature_weights", "decision_sample"],
            "required_sample": ["thesis", "risk_points", "confidence", "strategy_tags", "timeframe"],
            "allowed_actions": ["BUY", "SELL", "HOLD"],
            "allowed_timeframes": ["intraday", "swing_1_5d", "swing_3_10d", "position_10_30d", "watchlist"]
        },
        "tool_task": {
            "required_any": ["tool", "kind"],
            "required_when_kind": {"composio": ["tool"]},
            "fields": ["tool", "args", "kind", "map_to", "timeout_s", "tags", "purpose"]
        },
        "tool_result": {
            "required": ["tool", "ok"],
            "fields": ["tool", "ok", "data", "error", "latency_ms"]
        }
    }


def load_protocol(path=PROTOCOL_PATH):
    if not os.path.exists(path):
        return _default_protocol()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _default_protocol()


def get_protocol_version(path=PROTOCOL_PATH):
    proto = load_protocol(path)
    return str(proto.get("version") or "1.0")


def normalize_action(action):
    if action is None:
        return ""
    return str(action).strip().upper()


def validate_agent_report(report, path=PROTOCOL_PATH):
    proto = load_protocol(path)
    spec = proto.get("agent_report", {}) if isinstance(proto.get("agent_report"), dict) else {}
    required = spec.get("required", [])
    allowed = spec.get("allowed_statuses", [])
    errors = []
    if not isinstance(report, dict):
        return False, ["report_not_dict"]
    for key in required:
        if not report.get(key):
            errors.append(f"agent_missing_{key}")
    status = str(report.get("status") or "").lower()
    if allowed and status and status not in allowed:
        errors.append("agent_invalid_status")
    return len(errors) == 0, errors


def validate_decision_payload(payload, path=PROTOCOL_PATH):
    proto = load_protocol(path)
    spec = proto.get("decision", {}) if isinstance(proto.get("decision"), dict) else {}
    required = spec.get("required", [])
    required_sample = spec.get("required_sample", [])
    allowed = spec.get("allowed_actions", [])
    allowed_timeframes = spec.get("allowed_timeframes", [])
    errors = []
    if not isinstance(payload, dict):
        return False, ["decision_payload_not_dict"]
    for key in required:
        if payload.get(key) is None:
            errors.append(f"decision_missing_{key}")
    action = normalize_action(payload.get("action"))
    if allowed and action and action not in allowed:
        errors.append("decision_invalid_action")

    sample = payload.get("decision_sample")
    if sample is not None and not isinstance(sample, dict):
        errors.append("decision_sample_not_dict")
        sample = None
    if "decision_sample" in required and not isinstance(sample, dict):
        errors.append("decision_missing_decision_sample")
    if isinstance(sample, dict):
        for key in required_sample:
            if sample.get(key) is None:
                errors.append(f"decision_sample_missing_{key}")
        confidence = sample.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
                if confidence < 0 or confidence > 1:
                    errors.append("decision_sample_confidence_out_of_range")
            except Exception:
                errors.append("decision_sample_invalid_confidence")
        risk_points = sample.get("risk_points")
        if risk_points is not None and not isinstance(risk_points, list):
            errors.append("decision_sample_risk_points_not_list")
        strategy_tags = sample.get("strategy_tags")
        if strategy_tags is not None and not isinstance(strategy_tags, list):
            errors.append("decision_sample_strategy_tags_not_list")
        timeframe = str(sample.get("timeframe") or "").strip()
        if allowed_timeframes and timeframe and timeframe not in allowed_timeframes:
            errors.append("decision_sample_invalid_timeframe")
    return len(errors) == 0, errors


def sanitize_tool_tasks(tasks, path=PROTOCOL_PATH):
    proto = load_protocol(path)
    spec = proto.get("tool_task", {}) if isinstance(proto.get("tool_task"), dict) else {}
    required_any = spec.get("required_any", ["tool", "kind"])
    required_when_kind = spec.get("required_when_kind", {})
    valid = []
    errors = []

    if not isinstance(tasks, list):
        return [], ["tool_tasks_not_list"]

    for idx, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tool_task_{idx}_not_dict")
            continue
        tool = str(task.get("tool") or task.get("tool_name") or "").strip()
        kind = str(task.get("kind") or task.get("type") or "").strip().lower()
        if not tool and not kind:
            errors.append(f"tool_task_{idx}_missing_tool_or_kind")
            continue
        missing = []
        for k in required_any:
            if k == "tool" and tool:
                continue
            if k == "kind" and kind:
                continue
        if kind and kind in required_when_kind:
            for k in required_when_kind.get(kind, []):
                if k == "tool" and not tool:
                    missing.append(k)
        if missing:
            errors.append(f"tool_task_{idx}_missing_{'_'.join(missing)}")
            continue
        if tool:
            task["tool"] = tool
        if "args" in task and not isinstance(task.get("args"), dict):
            task["args"] = {}
        valid.append(task)

    if errors:
        warn("protocol.tool_task_errors", {"errors": errors})
    return valid, errors
