from skills.strategies.strategy_params import get_params, as_int, as_float
from core.ta_utils import resolve_ma_periods, ma_series


def check(df):
    periods = resolve_ma_periods()
    defaults = {
        "min_bars": 40,
        "range_lookback": 25,
        "min_width": 0.08,
        "breakout_pct": 0.03,
        "vol_ma": periods.get('short1', 5),
        "vol_mult": 1.3
    }
    params = get_params("skill_pattern_breakout", defaults)
    min_bars = as_int(params.get("min_bars", 40), 40, 1)
    range_lookback = as_int(params.get("range_lookback", 25), 25, 2)
    min_width = as_float(params.get("min_width", 0.08), 0.08, 0.0)
    breakout_pct = as_float(params.get("breakout_pct", 0.03), 0.03, 0.0)
    vol_ma = as_int(params.get("vol_ma", 5), 5, 1)
    vol_mult = as_float(params.get("vol_mult", 1.3), 1.3, 0.1)

    min_bars = max(min_bars, range_lookback + 5, vol_ma + 5)
    if len(df) < min_bars:
        return False, "not_enough_data"

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["vol"]
    vol_ma_n = ma_series(vol, vol_ma)

    range_high = high.iloc[-range_lookback:-1].max()
    range_low = low.iloc[-range_lookback:-1].min()
    if range_low <= 0:
        return False, ""

    width = (range_high - range_low) / range_low
    breakout = close.iloc[-1] >= range_high * (1 + breakout_pct)
    vol_ok = vol.iloc[-1] > vol_ma_n.iloc[-1] * vol_mult

    if width >= min_width and breakout and vol_ok:
        return True, "pattern_breakout_pullback_ready"

    return False, ""
