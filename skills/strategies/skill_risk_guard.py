from skills.strategies.strategy_params import get_params, as_int, as_float
from core.ta_utils import resolve_ma_periods, ma_series


def check(df):
    periods = resolve_ma_periods()
    defaults = {
        "min_bars": 40,
        "atr_period": 14,
        "atr_max_pct": 0.05,
        "vol_ma": periods.get('mid1', 20),
        "vol_min_ratio": 0.8
    }
    params = get_params("skill_risk_guard", defaults)
    min_bars = as_int(params.get("min_bars", 40), 40, 1)
    atr_period = as_int(params.get("atr_period", 14), 14, 1)
    atr_max_pct = as_float(params.get("atr_max_pct", 0.05), 0.05, 0.0)
    vol_ma = as_int(params.get("vol_ma", 20), 20, 1)
    vol_min_ratio = as_float(params.get("vol_min_ratio", 0.8), 0.8, 0.0)

    min_bars = max(min_bars, atr_period + 5, vol_ma + 5)
    if len(df) < min_bars:
        return False, "not_enough_data"

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["vol"]

    tr = (high - low).abs()
    atr = tr.rolling(atr_period).mean()
    if close.iloc[-1] <= 0:
        return False, ""

    vol_ma_n = ma_series(vol, vol_ma)
    atr_pct = atr.iloc[-1] / close.iloc[-1]
    vol_ok = vol.iloc[-1] >= vol_ma_n.iloc[-1] * vol_min_ratio

    if atr_pct <= atr_max_pct and vol_ok:
        return True, "risk_guard_ok"

    return False, ""
