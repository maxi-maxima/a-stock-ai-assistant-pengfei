import random

from core.blindbox_protocol import build_strategy_state


PRIMARY_STRATEGY_ID = "tp10_sl10_t20"
CONTROL_STRATEGY_IDS = {"coin_flip_buy", "random_pick_hold_2d"}


def list_builtin_strategies():
    rows = [
        build_strategy_state("coin_flip_buy", weight=1.0, hold_days=2),
        build_strategy_state("random_pick_hold_2d", weight=1.0, hold_days=2),
        build_strategy_state("prev_day_down_buy", weight=1.0, hold_days=2),
        build_strategy_state("above_ma5_buy", weight=1.0, hold_days=2),
        build_strategy_state("tp10_sl10_t20", weight=1.2, hold_days=20, entry_mode="next_open", tp_pct=0.10, sl_pct=0.10),
    ]
    return rows


def weighted_pick_strategy(strategies, rng_seed=None):
    active = []
    for row in strategies or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "active").lower() != "active":
            continue
        try:
            weight = float(row.get("weight", 0) or 0)
        except Exception:
            weight = 0.0
        if weight <= 0:
            continue
        active.append((dict(row), weight))
    if not active:
        return None

    zero_call_rows = []
    for row, weight in active:
        try:
            calls = int(row.get("calls", 0) or 0)
        except Exception:
            calls = 0
        if calls == 0:
            zero_call_rows.append((row, weight))
    if zero_call_rows:
        primary = [row for row, _ in zero_call_rows if str(row.get("strategy_id")) == PRIMARY_STRATEGY_ID]
        if primary:
            return primary[0]

    if len(active) == 1:
        return active[0][0]

    rng = random.Random(rng_seed)
    total = sum(weight for _, weight in active)
    point = rng.uniform(0, total)
    acc = 0.0
    for row, weight in active:
        acc += weight
        if point <= acc:
            return row
    return active[-1][0]


def _to_rows(history):
    if history is None:
        return []
    if isinstance(history, list):
        return history
    try:
        if hasattr(history, "to_dict"):
            return history.to_dict("records")
    except Exception:
        pass
    return []


def strategy_should_enter(strategy_id, history, rng_seed=None):
    rows = [r for r in _to_rows(history) if isinstance(r, dict)]
    if not rows:
        return False
    sid = str(strategy_id or "").strip()
    if sid == "random_pick_hold_2d":
        return True
    if sid == "coin_flip_buy":
        return random.Random(rng_seed).random() < 0.5
    if sid == "tp10_sl10_t20":
        return True

    closes = []
    for row in rows:
        try:
            closes.append(float(row.get("close")))
        except Exception:
            continue
    if len(closes) < 2:
        return False
    last_close = closes[-1]
    prev_close = closes[-2]
    if sid == "prev_day_down_buy":
        return last_close < prev_close
    if sid == "above_ma5_buy":
        window = closes[-5:] if len(closes) >= 5 else closes
        ma5 = sum(window) / len(window)
        return last_close > ma5
    return False
