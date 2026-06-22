import datetime
import json
import os

from core.backtest_smoke import run_backtest_smoke
from core.experiment_tracker_v1 import refresh_experiment_tracking
from core.learning_engine_v2 import refresh_learning_views
from core.strategy_trainer import run_training


LATEST_PATH = "data/upgrade_pipeline_latest.json"
HISTORY_PATH = "data/upgrade_pipeline_report.jsonl"


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


def _light_training_config(days):
    try:
        max_codes = int(os.getenv("UPGRADE_TRAIN_MAX_CODES", "8") or 8)
    except Exception:
        max_codes = 8
    try:
        max_strategies = int(os.getenv("UPGRADE_TRAIN_MAX_STRATEGIES", "6") or 6)
    except Exception:
        max_strategies = 6
    return {
        "enabled": True,
        "pool": "watchlist",
        "mode": "walk_forward",
        "days": max(120, min(int(days or 365), 365)),
        "max_codes": max(2, max_codes),
        "max_strategies": max(1, max_strategies),
        "min_trades": 1,
        "train_ratio": 0.7,
        "window_count": 3,
        "use_saved_params": True,
        "auto_update_pool": True,
        "use_strategy_pool": True,
        "pool_min_samples": 3,
        "pool_min_avg_score": 0,
        "pool_top_k": 4,
        "pool_fallback_to_top": True,
        "auto_update_watchlist": False,
        "auto_update_strategy_pools": False,
        "default_params": {
            "tp": 0.1,
            "sl": 0.05,
            "days": 20,
            "position_pct": 1.0,
            "execution": "next_open",
        },
        "include_strategies": [],
        "exclude_strategies": [],
        "custom_codes": [],
    }


def _step_ok(payload):
    if not isinstance(payload, dict):
        return False
    if "ok" in payload:
        return bool(payload.get("ok"))
    if "error" in payload and payload.get("error"):
        return False
    return True


def _run_step(step_name, fn, **kwargs):
    try:
        out = fn(**kwargs)
        if not isinstance(out, dict):
            out = {"ok": False, "error": "invalid_output", "value": str(out)}
    except Exception as exc:
        out = {"ok": False, "error": f"{step_name}_failed: {exc}"}
    return out


def run_upgrade_pipeline(
    days=365,
    apply=True,
    training_enabled=True,
    training_mode="light",
    latest_path=LATEST_PATH,
    history_path=HISTORY_PATH,
    learning_runner=None,
    tracking_runner=None,
    training_runner=None,
    smoke_runner=None,
):
    learning_runner = learning_runner or refresh_learning_views
    tracking_runner = tracking_runner or refresh_experiment_tracking
    training_runner = training_runner or run_training
    smoke_runner = smoke_runner or run_backtest_smoke

    learning = _run_step(
        "learning",
        learning_runner,
        days=max(30, int(days or 365)),
        apply=apply,
    )
    tracking = _run_step("tracking", tracking_runner, apply=apply)

    training = {"ok": True, "skipped": True}
    if training_enabled:
        if str(training_mode).strip().lower() == "light":
            training_cfg = _light_training_config(days=days)
            training = _run_step("training", training_runner, config=training_cfg)
        else:
            training = _run_step("training", training_runner, config=None)

    smoke = _run_step(
        "smoke",
        smoke_runner,
        days=max(120, min(int(days or 365), 365)),
        apply=apply,
    )

    ok = _step_ok(learning) and _step_ok(tracking) and _step_ok(training) and _step_ok(smoke)
    report = {
        "ts": _now(),
        "ok": bool(ok),
        "status": "pass" if ok else "fail",
        "days": int(days or 0),
        "training_enabled": bool(training_enabled),
        "training_mode": str(training_mode),
        "learning": learning,
        "tracking": tracking,
        "training": training,
        "smoke": smoke,
    }

    if apply:
        _save_json(latest_path, report)
        _append_jsonl(history_path, report)
    return report


def run_upgrade_with_retries(
    days=365,
    max_attempts=3,
    training_enabled=True,
    training_mode="light",
    apply=True,
    pipeline_runner=None,
):
    pipeline_runner = pipeline_runner or run_upgrade_pipeline
    attempts = []
    final_report = None
    max_attempts = max(1, int(max_attempts or 1))

    for i in range(max_attempts):
        attempt_no = i + 1
        report = pipeline_runner(
            days=days,
            apply=apply,
            training_enabled=training_enabled,
            training_mode=training_mode,
        )
        if not isinstance(report, dict):
            report = {"ok": False, "status": "fail", "error": "invalid_report"}
        final_report = report
        attempts.append(
            {
                "attempt": attempt_no,
                "ok": bool(report.get("ok")),
                "status": report.get("status"),
                "smoke_passed": (report.get("smoke", {}) or {}).get("passed_cases"),
                "smoke_errors": (report.get("smoke", {}) or {}).get("error_cases"),
            }
        )
        if report.get("ok"):
            break

    return {
        "ok": bool(final_report.get("ok")) if isinstance(final_report, dict) else False,
        "attempts_used": len(attempts),
        "max_attempts": max_attempts,
        "attempts": attempts,
        "final_report": final_report if isinstance(final_report, dict) else {},
    }
