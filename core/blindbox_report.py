import json
import os

from core.blindbox_strategies import CONTROL_STRATEGY_IDS, PRIMARY_STRATEGY_ID


BLINDBOX_RUNNER_LATEST_PATH = "data/blindbox_runner_latest.json"
BLINDBOX_STRATEGY_STATE_PATH = "data/blindbox_strategy_state.json"
BLINDBOX_POSITIONS_PATH = "data/blindbox_positions.json"
BLINDBOX_DAILY_REPORT_PATH = "data/blindbox_daily_report.jsonl"


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def build_blindbox_report(latest_day=None, strategies=None):
    latest_day = latest_day if isinstance(latest_day, dict) else {}
    strategies = [dict(row) for row in (strategies or []) if isinstance(row, dict)]
    strategies_sorted = sorted(strategies, key=lambda x: float(x.get("weight", 0) or 0), reverse=True)
    weak_sorted = sorted(strategies, key=lambda x: float(x.get("avg_realized_pnl", 0) or 0))
    return {
        "trade_date": latest_day.get("trade_date", ""),
        "opened_count": int(latest_day.get("opened_count", 0) or 0),
        "closed_count": int(latest_day.get("closed_count", 0) or 0),
        "realized_pnl_sum": float(latest_day.get("realized_pnl_sum", 0.0) or 0.0),
        "top_strategies": [
            {
                "strategy_id": row.get("strategy_id"),
                "weight": row.get("weight"),
                "status": row.get("status"),
            }
            for row in strategies_sorted[:5]
        ],
        "weak_strategies": [
            {
                "strategy_id": row.get("strategy_id"),
                "avg_realized_pnl": row.get("avg_realized_pnl"),
                "status": row.get("status"),
            }
            for row in weak_sorted[:5]
        ],
    }


def load_blindbox_health_snapshot(
    latest_path=BLINDBOX_RUNNER_LATEST_PATH,
    strategies_path=BLINDBOX_STRATEGY_STATE_PATH,
    positions_path=BLINDBOX_POSITIONS_PATH,
    report_path=BLINDBOX_DAILY_REPORT_PATH,
):
    latest = _load_json(latest_path, {})
    strategies = _load_json(strategies_path, [])
    positions = _load_json(positions_path, [])
    reports = _load_jsonl(report_path)

    latest_result = {}
    results = latest.get("results", []) if isinstance(latest, dict) else []
    if isinstance(results, list) and results:
        latest_result = results[-1] if isinstance(results[-1], dict) else {}

    strategies = [row for row in strategies if isinstance(row, dict)] if isinstance(strategies, list) else []
    positions = [row for row in positions if isinstance(row, dict)] if isinstance(positions, list) else []
    top_strategy = None
    if strategies:
        top_strategy = sorted(strategies, key=lambda x: float(x.get("weight", 0) or 0), reverse=True)[0]

    primary = next((row for row in strategies if str(row.get("strategy_id")) == PRIMARY_STRATEGY_ID), {})
    controls = [row for row in strategies if str(row.get("strategy_id")) in CONTROL_STRATEGY_IDS]
    control_calls = sum(int(row.get("calls", 0) or 0) for row in controls)
    control_closed = sum(int(row.get("closed_trades", 0) or 0) for row in controls)
    control_pnl = sum(float(row.get("realized_pnl_sum", 0.0) or 0.0) for row in controls)
    control_avg = (control_pnl / control_closed) if control_closed else 0.0
    primary_pnl = float(primary.get("realized_pnl_sum", 0.0) or 0.0) if isinstance(primary, dict) else 0.0
    curves = build_blindbox_cumulative_series(reports)
    primary_curve = [float(row.get("主策略累计已实现盈亏", 0.0) or 0.0) for row in curves]
    control_curve = [float(row.get("随机对照组累计已实现盈亏", 0.0) or 0.0) for row in curves]

    return {
        "available": bool(latest or strategies or positions),
        "last_trade_date": (latest.get("last_trade_date") if isinstance(latest, dict) else "") or "",
        "processed_days": int((latest.get("processed_days") if isinstance(latest, dict) else 0) or 0),
        "opened_count": int(latest_result.get("opened_count", 0) or 0),
        "closed_count": int(latest_result.get("closed_count", 0) or 0),
        "realized_pnl_sum": float(latest_result.get("realized_pnl_sum", 0.0) or 0.0),
        "strategy_count": len(strategies),
        "active_strategies": sum(1 for row in strategies if str(row.get("status") or "").lower() == "active"),
        "open_positions": sum(1 for row in positions if str(row.get("status") or "open").lower() == "open"),
        "top_strategy_id": str(top_strategy.get("strategy_id")) if isinstance(top_strategy, dict) else "",
        "top_strategy_weight": float(top_strategy.get("weight", 0.0) or 0.0) if isinstance(top_strategy, dict) else 0.0,
        "primary_strategy_id": str(primary.get("strategy_id") or ""),
        "primary_weight": float(primary.get("weight", 0.0) or 0.0) if isinstance(primary, dict) else 0.0,
        "primary_calls": int(primary.get("calls", 0) or 0) if isinstance(primary, dict) else 0,
        "primary_closed_trades": int(primary.get("closed_trades", 0) or 0) if isinstance(primary, dict) else 0,
        "primary_avg_realized_pnl": float(primary.get("avg_realized_pnl", 0.0) or 0.0) if isinstance(primary, dict) else 0.0,
        "primary_realized_pnl_sum": primary_pnl,
        "control_calls": control_calls,
        "control_closed_trades": control_closed,
        "control_avg_realized_pnl": control_avg,
        "control_realized_pnl_sum": control_pnl,
        "primary_max_drawdown": _calc_max_drawdown(primary_curve),
        "control_max_drawdown": _calc_max_drawdown(control_curve),
    }


def build_blindbox_control_panel(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    return {
        "primary": {
            "strategy_id": snapshot.get("primary_strategy_id", ""),
            "weight": float(snapshot.get("primary_weight", 0.0) or 0.0),
            "calls": int(snapshot.get("primary_calls", 0) or 0),
            "closed_trades": int(snapshot.get("primary_closed_trades", 0) or 0),
            "avg_realized_pnl": float(snapshot.get("primary_avg_realized_pnl", 0.0) or 0.0),
            "realized_pnl_sum": float(snapshot.get("primary_realized_pnl_sum", 0.0) or 0.0),
            "max_drawdown": float(snapshot.get("primary_max_drawdown", 0.0) or 0.0),
        },
        "control": {
            "calls": int(snapshot.get("control_calls", 0) or 0),
            "closed_trades": int(snapshot.get("control_closed_trades", 0) or 0),
            "avg_realized_pnl": float(snapshot.get("control_avg_realized_pnl", 0.0) or 0.0),
            "realized_pnl_sum": float(snapshot.get("control_realized_pnl_sum", 0.0) or 0.0),
            "max_drawdown": float(snapshot.get("control_max_drawdown", 0.0) or 0.0),
        },
    }


def build_blindbox_cumulative_series(rows):
    primary_sum = 0.0
    control_sum = 0.0
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            pnl = float(row.get("realized_pnl_sum", 0.0) or 0.0)
        except Exception:
            pnl = 0.0
        strategy_id = str(row.get("chosen_strategy_id") or "")
        if strategy_id == PRIMARY_STRATEGY_ID:
            primary_sum += pnl
        elif strategy_id in CONTROL_STRATEGY_IDS:
            control_sum += pnl
        out.append(
            {
                "交易日期": row.get("trade_date", ""),
                "主策略累计已实现盈亏": round(primary_sum, 2),
                "随机对照组累计已实现盈亏": round(control_sum, 2),
            }
        )
    return out


def _clamp_score(value):
    return max(0.0, min(100.0, float(value)))


def _relative_score(primary, control, reverse=False, scale=1.0):
    try:
        primary = float(primary or 0.0)
        control = float(control or 0.0)
    except Exception:
        return 50.0
    diff = (control - primary) if reverse else (primary - control)
    score = 50.0 + (diff * scale)
    return _clamp_score(score)


def _confidence_label(primary_closed, control_closed):
    min_closed = min(int(primary_closed or 0), int(control_closed or 0))
    if min_closed < 5:
        return "样本不足"
    if min_closed < 10:
        return "初步可信"
    return "较可信"


def _conclusion_from_diff(diff, confidence):
    if confidence == "样本不足":
        return "样本不足，暂不下结论"
    if diff > 2:
        return "主策略跑赢随机对照组"
    if diff < -2:
        return "主策略落后随机对照组"
    return "主策略与随机对照组基本持平"


def build_blindbox_scorecard(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    primary_closed = int(snapshot.get("primary_closed_trades", 0) or 0)
    control_closed = int(snapshot.get("control_closed_trades", 0) or 0)

    profit_score = _relative_score(
        snapshot.get("primary_realized_pnl_sum", 0.0),
        snapshot.get("control_realized_pnl_sum", 0.0),
        reverse=False,
        scale=200.0,
    )
    avg_score = _relative_score(
        snapshot.get("primary_avg_realized_pnl", 0.0),
        snapshot.get("control_avg_realized_pnl", 0.0),
        reverse=False,
        scale=1000.0,
    )
    drawdown_score = _relative_score(
        snapshot.get("primary_max_drawdown", 0.0),
        snapshot.get("control_max_drawdown", 0.0),
        reverse=True,
        scale=500.0,
    )
    sample_score = _relative_score(primary_closed, control_closed, reverse=False, scale=5.0)

    primary_score = round(profit_score * 0.5 + avg_score * 0.2 + drawdown_score * 0.2 + sample_score * 0.1, 2)
    control_score = round(100.0 - primary_score, 2)
    score_diff = round(primary_score - control_score, 2)
    confidence = _confidence_label(primary_closed, control_closed)
    if confidence == "样本不足":
        winner = "insufficient"
    elif score_diff > 2:
        winner = "primary"
    elif score_diff < -2:
        winner = "control"
    else:
        winner = "tie"

    return {
        "winner": winner,
        "conclusion": _conclusion_from_diff(score_diff, confidence),
        "confidence": confidence,
        "primary_score": primary_score,
        "control_score": control_score,
        "score_diff": score_diff,
        "contributions": {
            "累计收益": round(profit_score * 0.5, 2),
            "平均单笔收益": round(avg_score * 0.2, 2),
            "最大回撤": round(drawdown_score * 0.2, 2),
            "样本量": round(sample_score * 0.1, 2),
        },
    }


def _calc_max_drawdown(curve):
    peak = None
    max_dd = 0.0
    for value in curve or []:
        try:
            value = float(value)
        except Exception:
            continue
        if peak is None or value > peak:
            peak = value
        if peak is None:
            continue
        dd = peak - value
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 6)
