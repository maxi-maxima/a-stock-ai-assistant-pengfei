#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import datetime
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.blindbox_datafeed import load_watchlist_codes, prefer_akshare_fallback, resolve_reference_trade_date, resolve_universe
from core.blindbox_engine import run_blindbox_day
from core.blindbox_maintenance import sanitize_future_state
from skills.scanner import MarketScanner


LATEST_PATH = "data/blindbox_runner_latest.json"
HISTORY_PATH = "data/blindbox_runner_history.jsonl"


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return default if default is not None else {}


def _save_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _append_jsonl(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _build_blindbox_scanner():
    scanner = MarketScanner("tushare")
    prefer_akshare_fallback(scanner)
    return scanner


def _default_trade_date():
    watchlist = load_watchlist_codes()
    candidates = []
    try:
        scanner = _build_blindbox_scanner()
        data_skill = getattr(scanner, "data_skill", None)
        if data_skill is not None and hasattr(data_skill, "get_last_trade_date"):
            dt = data_skill.get_last_trade_date()
            if dt:
                candidates.append(str(dt))
        if watchlist:
            for code in watchlist[:20]:
                history = None
                if hasattr(scanner, "get_history"):
                    history = scanner.get_history(code, days=120)
                elif data_skill is not None and hasattr(data_skill, "get_history"):
                    history = data_skill.get_history(code, days=120)
                if history is None:
                    continue
                try:
                    rows = history.to_dict("records")
                except Exception:
                    rows = history if isinstance(history, list) else []
                for row in rows:
                    if isinstance(row, dict) and row.get("date"):
                        candidates.append(str(row.get("date")))
    except Exception:
        pass
    return resolve_reference_trade_date(candidates, today=datetime.date.today().isoformat())


def run_once(target_dates=None, latest=None, day_runner=None, save=True, scanner=None, max_allowed_date=None):
    latest = dict(latest or {})
    day_runner = day_runner or run_blindbox_day
    target_dates = [str(x) for x in (target_dates or []) if str(x)]
    if not target_dates:
        target_dates = [_default_trade_date()]
    target_dates = sorted(target_dates)

    max_allowed = str(max_allowed_date) if max_allowed_date else ""
    if max_allowed:
        if any(d > max_allowed for d in target_dates):
            return {
                "ok": False,
                "skipped": False,
                "processed_days": 0,
                "last_trade_date": latest.get("last_trade_date") or max_allowed,
                "reason": "future_trade_date",
                "results": [],
            }

        if save:
            sanitize_future_state(reference_trade_date=max_allowed)
            latest = _load_json(LATEST_PATH, default=latest)

    last_trade_date = str(latest.get("last_trade_date") or "")
    pending = [d for d in target_dates if not last_trade_date or d > last_trade_date]
    if not pending:
        row = {
            "ok": True,
            "skipped": True,
            "processed_days": 0,
            "last_trade_date": last_trade_date or target_dates[-1],
            "results": [],
        }
        if save:
            _save_json(LATEST_PATH, row)
            _append_jsonl(HISTORY_PATH, row)
        return row

    results = []
    universe = resolve_universe(load_watchlist_codes(), fallback=["000001.SZ", "000002.SZ", "000858.SZ"])
    scanner = scanner or _build_blindbox_scanner()
    for trade_date in pending:
        result = day_runner(trade_date=trade_date, universe=universe, scanner=scanner, apply=save)
        if isinstance(result, dict):
            results.append(result)

    row = {
        "ok": all(bool(r.get("ok", False)) for r in results) if results else True,
        "skipped": False,
        "processed_days": len(results),
        "last_trade_date": pending[-1],
        "reason": "",
        "results": results,
    }
    if save:
        _save_json(LATEST_PATH, row)
        _append_jsonl(HISTORY_PATH, row)
    return row


def main():
    parser = argparse.ArgumentParser(description="Run blindbox paper loop for one or more trade dates.")
    parser.add_argument("--once", action="store_true", help="run one cycle for today")
    parser.add_argument("--date", default="", help="run one cycle for an explicit YYYY-MM-DD date")
    args = parser.parse_args()

    latest = _load_json(LATEST_PATH, default={})
    if args.date:
        target_dates = [args.date]
    else:
        target_dates = [_default_trade_date()]

    row = run_once(target_dates=target_dates, latest=latest, save=True, max_allowed_date=_default_trade_date())
    print(json.dumps({"ok": row.get("ok"), "skipped": row.get("skipped"), "processed_days": row.get("processed_days"), "last_trade_date": row.get("last_trade_date")}, ensure_ascii=False))
    return 0 if row.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
