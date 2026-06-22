#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys
import time

import schedule

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.upgrade_scheduler import load_scheduler_config, run_scheduled_upgrade_once


def _print_result(row):
    payload = {
        "ts": row.get("ts"),
        "ok": row.get("ok"),
        "skipped": row.get("skipped"),
        "reason": row.get("reason"),
        "attempts_used": row.get("attempts_used"),
        "status": row.get("status"),
    }
    print(json.dumps(payload, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Daily upgrade scheduler daemon.")
    parser.add_argument("--config", default="config/upgrade_scheduler.json", help="scheduler config path")
    parser.add_argument("--once", action="store_true", help="run once immediately and exit")
    parser.add_argument("--run-now", action="store_true", help="run once immediately before daemon loop")
    args = parser.parse_args()

    cfg = load_scheduler_config(path=args.config)

    def _job():
        row = run_scheduled_upgrade_once(config=cfg, apply=True)
        _print_result(row)
        return row

    if args.once:
        row = _job()
        return 0 if (row.get("ok") or row.get("skipped")) else 1

    if args.run_now:
        _job()

    schedule_time = str(cfg.get("schedule_time") or "02:30")
    schedule.every().day.at(schedule_time).do(_job)
    print(f"[scheduler] started, schedule_time={schedule_time}")

    while True:
        schedule.run_pending()
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
