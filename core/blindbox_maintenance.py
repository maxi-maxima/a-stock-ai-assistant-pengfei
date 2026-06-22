import json
import os
from typing import Optional

from core.blindbox_evolution import apply_realized_reward
from core.blindbox_strategies import list_builtin_strategies


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _save_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_trade_date_from_decision_id(decision_id: Optional[str]) -> str:
    text = str(decision_id or "").strip()
    if text.startswith("blindbox_") and len(text) >= 17:
        digits = text.split("_", 2)[1]
        if len(digits) == 8 and digits.isdigit():
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return ""


def _payload_decision_date(row):
    if not isinstance(row, dict):
        return ""
    payload = row.get("payload", {}) if isinstance(row.get("payload"), dict) else {}
    for key in ("decision_id", "origin_decision_id"):
        dt = extract_trade_date_from_decision_id(payload.get(key))
        if dt:
            return dt
    for key in ("decision_id", "origin_decision_id"):
        dt = extract_trade_date_from_decision_id(row.get(key))
        if dt:
            return dt
    return ""


def _keep_report(row, reference_trade_date):
    if not isinstance(row, dict):
        return False
    trade_date = str(row.get("trade_date") or "")
    if trade_date and trade_date > reference_trade_date:
        return False
    return True


def _keep_history_row(row, reference_trade_date):
    if not isinstance(row, dict):
        return False
    last_trade_date = str(row.get("last_trade_date") or "")
    if last_trade_date and last_trade_date > reference_trade_date:
        return False
    return True


def _keep_position(row, reference_trade_date):
    if not isinstance(row, dict):
        return False
    status = str(row.get("status") or "open")
    if status == "pending_entry":
        signal_date = str(row.get("signal_date") or "")
        return not signal_date or signal_date <= reference_trade_date
    buy_date = str(row.get("buy_date") or "")
    return not buy_date or buy_date <= reference_trade_date


def _keep_trade_like(row, reference_trade_date):
    dt = _payload_decision_date(row)
    return not dt or dt <= reference_trade_date


def _rebuild_strategy_state(reference_trade_date, reports, event_rows):
    strategies = {row["strategy_id"]: dict(row) for row in list_builtin_strategies()}
    for report in sorted(reports, key=lambda x: str(x.get("trade_date") or "")):
        strategy_id = str(report.get("chosen_strategy_id") or "")
        if strategy_id and strategy_id in strategies:
            strategies[strategy_id]["calls"] = int(strategies[strategy_id].get("calls", 0) or 0) + 1
            if int(report.get("opened_count", 0) or 0) > 0:
                strategies[strategy_id]["buys"] = int(strategies[strategy_id].get("buys", 0) or 0) + int(report.get("opened_count", 0) or 0)

    cleaned_outcomes = []
    for row in event_rows:
        if not isinstance(row, dict) or row.get("event") != "outcome":
            continue
        if not _keep_trade_like(row, reference_trade_date):
            continue
        payload = row.get("payload", {}) if isinstance(row.get("payload"), dict) else {}
        signal_source = payload.get("signal_source") if isinstance(payload.get("signal_source"), dict) else {}
        strategy_id = str(signal_source.get("strategy") or "").strip()
        if not strategy_id or strategy_id not in strategies:
            continue
        pnl_pct = payload.get("pnl_pct")
        if pnl_pct is None:
            continue
        try:
            pnl_pct = float(pnl_pct)
        except Exception:
            continue
        cleaned_outcomes.append((str(row.get("ts") or ""), strategy_id, pnl_pct))

    for _, strategy_id, pnl_pct in sorted(cleaned_outcomes, key=lambda x: x[0]):
        strategies[strategy_id] = apply_realized_reward(strategies[strategy_id], pnl_pct)

    return list(strategies.values())


def sanitize_future_state(
    reference_trade_date,
    positions_path="data/blindbox_positions.json",
    report_path="data/blindbox_daily_report.jsonl",
    history_path="data/blindbox_runner_history.jsonl",
    latest_path="data/blindbox_runner_latest.json",
    trades_path="data/blindbox_trades.jsonl",
    event_bus_path="data/blindbox_event_bus.jsonl",
    experience_path="data/blindbox_experience_log.jsonl",
    strategy_state_path="data/blindbox_strategy_state.json",
):
    reference_trade_date = str(reference_trade_date)

    positions = _load_json(positions_path, [])
    reports = _load_jsonl(report_path)
    history = _load_jsonl(history_path)
    latest = _load_json(latest_path, {})
    trades = _load_jsonl(trades_path)
    event_rows = _load_jsonl(event_bus_path)
    experience_rows = _load_jsonl(experience_path)

    kept_positions = [row for row in positions if _keep_position(row, reference_trade_date)] if isinstance(positions, list) else []
    kept_reports = [row for row in reports if _keep_report(row, reference_trade_date)]
    kept_history = [row for row in history if _keep_history_row(row, reference_trade_date)]
    kept_trades = [row for row in trades if _keep_trade_like(row, reference_trade_date)]
    kept_events = [row for row in event_rows if _keep_trade_like(row, reference_trade_date)]
    kept_experience = [row for row in experience_rows if _keep_trade_like(row, reference_trade_date)]

    removed = {
        "removed_positions": max(0, len(positions) - len(kept_positions)),
        "removed_reports": max(0, len(reports) - len(kept_reports)),
        "removed_history": max(0, len(history) - len(kept_history)),
        "removed_trades": max(0, len(trades) - len(kept_trades)),
        "removed_events": max(0, len(event_rows) - len(kept_events)),
        "removed_experience": max(0, len(experience_rows) - len(kept_experience)),
    }

    cleaned_latest = latest if isinstance(latest, dict) else {}
    if not _keep_history_row(cleaned_latest, reference_trade_date):
        if kept_history:
            cleaned_latest = dict(kept_history[-1])
        else:
            cleaned_latest = {
                "ok": True,
                "skipped": True,
                "processed_days": 0,
                "last_trade_date": reference_trade_date,
                "results": [],
            }

    rebuilt_state = _rebuild_strategy_state(reference_trade_date, kept_reports, kept_events)

    _save_json(positions_path, kept_positions)
    _save_jsonl(report_path, kept_reports)
    _save_jsonl(history_path, kept_history)
    _save_json(latest_path, cleaned_latest)
    _save_jsonl(trades_path, kept_trades)
    _save_jsonl(event_bus_path, kept_events)
    _save_jsonl(experience_path, kept_experience)
    _save_json(strategy_state_path, rebuilt_state)

    return {
        **removed,
        "reference_trade_date": reference_trade_date,
        "last_trade_date": cleaned_latest.get("last_trade_date") if isinstance(cleaned_latest, dict) else reference_trade_date,
    }
