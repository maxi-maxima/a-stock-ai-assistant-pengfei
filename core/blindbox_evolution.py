import datetime


def apply_realized_reward(state, pnl_pct, min_weight=0.1, max_weight=5.0):
    row = dict(state or {})
    try:
        pnl_pct = float(pnl_pct)
    except Exception:
        pnl_pct = 0.0

    try:
        current_weight = float(row.get("weight", 1.0) or 1.0)
    except Exception:
        current_weight = 1.0

    closed_trades = int(row.get("closed_trades", 0) or 0) + 1
    wins = int(row.get("wins", 0) or 0) + (1 if pnl_pct > 0 else 0)
    realized_pnl_sum = float(row.get("realized_pnl_sum", 0.0) or 0.0) + pnl_pct
    avg_realized_pnl = realized_pnl_sum / closed_trades if closed_trades else 0.0

    new_weight = current_weight * (1.0 + pnl_pct * 2.0)
    new_weight = max(float(min_weight), min(float(max_weight), new_weight))

    status = str(row.get("status") or "active")
    if closed_trades >= 5 and avg_realized_pnl < -0.03:
        status = "disabled"
    elif closed_trades >= 3 and avg_realized_pnl < 0:
        status = "watch"
    elif status != "disabled":
        status = "active"

    row.update(
        {
            "weight": round(new_weight, 6),
            "closed_trades": closed_trades,
            "wins": wins,
            "realized_pnl_sum": round(realized_pnl_sum, 6),
            "avg_realized_pnl": round(avg_realized_pnl, 6),
            "last_realized_pnl": round(pnl_pct, 6),
            "status": status,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
    )
    return row
