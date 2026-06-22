#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.upgrade_pipeline import run_upgrade_pipeline
from core.upgrade_pipeline import run_upgrade_with_retries


def main():
    parser = argparse.ArgumentParser(description="Run full upgrade pipeline and backtest smoke with retries.")
    parser.add_argument("--days", type=int, default=365, help="lookback window for learning/training/smoke")
    parser.add_argument("--max-attempts", type=int, default=3, help="max retry attempts")
    parser.add_argument("--skip-training", action="store_true", help="skip strategy training stage")
    parser.add_argument("--full-training", action="store_true", help="use full training mode instead of light mode")
    args = parser.parse_args()

    max_attempts = max(1, int(args.max_attempts or 1))
    training_enabled = not bool(args.skip_training)
    training_mode = "full" if bool(args.full_training) else "light"

    out = run_upgrade_with_retries(
        days=int(args.days or 365),
        max_attempts=max_attempts,
        training_enabled=training_enabled,
        training_mode=training_mode,
        apply=True,
        pipeline_runner=run_upgrade_pipeline,
    )
    for item in out.get("attempts", []):
        print(
            json.dumps(
                {
                    "attempt": item.get("attempt"),
                    "ok": item.get("ok"),
                    "status": item.get("status"),
                    "smoke_passed": item.get("smoke_passed"),
                    "smoke_errors": item.get("smoke_errors"),
                },
                ensure_ascii=False,
            )
        )

    final_report = out.get("final_report", {}) if isinstance(out.get("final_report", {}), dict) else {}
    if out.get("ok"):
        print("[upgrade] pipeline passed")
        print(
            json.dumps(
                {
                    "champion": final_report.get("tracking", {}).get("champion_strategy"),
                    "attempts_used": out.get("attempts_used"),
                },
                ensure_ascii=False,
            )
        )
        return 0
    print("[upgrade] pipeline did not pass after retries")
    print(json.dumps(final_report, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
