import datetime
import json
import os

from core.upgrade_pipeline import run_upgrade_with_retries


CONFIG_PATH = "config/upgrade_scheduler.json"
LATEST_PATH = "data/upgrade_scheduler_latest.json"
HISTORY_PATH = "data/upgrade_scheduler_report.jsonl"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _save_json(path, payload):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _append_jsonl(path, payload):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def load_scheduler_config(path=CONFIG_PATH):
    defaults = {
        "enabled": True,
        "schedule_time": "02:30",
        "skip_weekends": False,
        "days": 365,
        "max_attempts": 3,
        "training_enabled": True,
        "training_mode": "light",
    }
    if not os.path.exists(path):
        return defaults
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        out = dict(defaults)
        out.update(data)
        return out
    except Exception:
        return defaults


def save_scheduler_config(config, path=CONFIG_PATH):
    if not isinstance(config, dict):
        return False
    current = load_scheduler_config(path=path)
    merged = dict(current)
    merged.update(config)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_scheduler_latest(path=LATEST_PATH):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def run_scheduled_upgrade_once(
    config=None,
    apply=True,
    latest_path=LATEST_PATH,
    history_path=HISTORY_PATH,
    now=None,
    retry_runner=None,
):
    cfg = dict(load_scheduler_config())
    if isinstance(config, dict):
        cfg.update(config)

    now_dt = now if isinstance(now, datetime.datetime) else datetime.datetime.now()
    retry_runner = retry_runner or run_upgrade_with_retries

    if not bool(cfg.get("enabled", True)):
        row = {
            "ts": _now(),
            "ok": True,
            "skipped": True,
            "reason": "disabled",
            "config": cfg,
        }
        if apply:
            _save_json(latest_path, row)
            _append_jsonl(history_path, row)
        return row

    if bool(cfg.get("skip_weekends")) and now_dt.weekday() >= 5:
        row = {
            "ts": _now(),
            "ok": True,
            "skipped": True,
            "reason": "weekend",
            "config": cfg,
        }
        if apply:
            _save_json(latest_path, row)
            _append_jsonl(history_path, row)
        return row

    result = retry_runner(
        days=int(cfg.get("days", 365) or 365),
        max_attempts=int(cfg.get("max_attempts", 3) or 3),
        training_enabled=bool(cfg.get("training_enabled", True)),
        training_mode=str(cfg.get("training_mode", "light")),
        apply=apply,
    )
    row = {
        "ts": _now(),
        "ok": bool(result.get("ok")),
        "skipped": False,
        "reason": "",
        "attempts_used": int(result.get("attempts_used", 0) or 0),
        "max_attempts": int(result.get("max_attempts", 0) or 0),
        "status": ((result.get("final_report", {}) or {}).get("status") if isinstance(result.get("final_report", {}), dict) else ""),
        "config": cfg,
        "result": result,
    }
    if apply:
        _save_json(latest_path, row)
        _append_jsonl(history_path, row)
    return row
