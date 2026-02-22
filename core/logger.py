import datetime
import json
import os
import traceback


LOG_PATH = "data/system_log.jsonl"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _ensure_dir():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


def _write(level, msg, extra=None):
    _ensure_dir()
    record = {
        "ts": _now(),
        "level": str(level).upper(),
        "msg": str(msg),
        "extra": extra or {}
    }
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return record


def info(msg, extra=None):
    return _write("INFO", msg, extra=extra)


def warn(msg, extra=None):
    return _write("WARN", msg, extra=extra)


def error(msg, extra=None):
    return _write("ERROR", msg, extra=extra)


def exception(msg, err=None, extra=None):
    payload = dict(extra or {})
    if err is not None:
        payload["error"] = str(err)
    try:
        payload["traceback"] = traceback.format_exc(limit=5)
    except Exception:
        pass
    return _write("ERROR", msg, extra=payload)
