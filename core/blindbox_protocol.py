import datetime


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def build_strategy_state(
    strategy_id,
    weight=1.0,
    hold_days=2,
    status="active",
    entry_mode="close",
    tp_pct=None,
    sl_pct=None,
):
    row = {
        "strategy_id": str(strategy_id),
        "weight": float(weight),
        "hold_days": int(hold_days or 2),
        "entry_mode": str(entry_mode or "close"),
        "calls": 0,
        "buys": 0,
        "closed_trades": 0,
        "wins": 0,
        "realized_pnl_sum": 0.0,
        "avg_realized_pnl": 0.0,
        "last_realized_pnl": None,
        "status": str(status or "active"),
        "updated_at": _now(),
    }
    if tp_pct is not None:
        row["tp_pct"] = float(tp_pct)
    if sl_pct is not None:
        row["sl_pct"] = float(sl_pct)
    return row


def build_position_plan(
    decision_id,
    code,
    strategy_id,
    buy_date,
    planned_exit_date,
    hold_days=2,
    buy_price=None,
    shares=None,
    status="open",
    signal_date=None,
    planned_buy_date=None,
):
    row = {
        "decision_id": str(decision_id),
        "code": str(code),
        "strategy_id": str(strategy_id),
        "buy_date": str(buy_date),
        "planned_exit_date": str(planned_exit_date),
        "hold_days": int(hold_days or 2),
        "buy_price": None if buy_price is None else float(buy_price),
        "shares": None if shares is None else int(shares),
        "status": str(status or "open"),
        "created_at": _now(),
    }
    if signal_date is not None:
        row["signal_date"] = str(signal_date)
    if planned_buy_date is not None:
        row["planned_buy_date"] = str(planned_buy_date)
    return row
