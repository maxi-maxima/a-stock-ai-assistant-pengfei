from skills.strategies.strategy_params import get_params, as_int, as_float, as_bool
from core.ta_utils import resolve_ma_periods, ma_series


def check(df):
    periods = resolve_ma_periods()
    defaults = {
        "min_bars": 30,
        "breakout_lookback": 20,
        "breakout_pct": 0.0,
        "vol_ma": periods.get('short1', 5),
        "vol_mult": 1.5,
        "require_close_up": True
    }
    params = get_params("skill_volume_confirm", defaults)
    min_bars = as_int(params.get("min_bars", 30), 30, 1)
    breakout_lookback = as_int(params.get("breakout_lookback", 20), 20, 2)
    breakout_pct = as_float(params.get("breakout_pct", 0.0), 0.0, 0.0)
    vol_ma = as_int(params.get("vol_ma", 5), 5, 1)
    vol_mult = as_float(params.get("vol_mult", 1.5), 1.5, 0.1)
    require_close_up = as_bool(params.get("require_close_up", True), True)

    min_bars = max(min_bars, breakout_lookback + 5, vol_ma + 5)
    if len(df) < min_bars:
        return False, "not_enough_data"

    close = df["close"]
    high = df["high"]
    vol = df["vol"]
    vol_ma_n = ma_series(vol, vol_ma)

    prev_high = high.iloc[-breakout_lookback:-1].max()
    breakout = close.iloc[-1] > prev_high * (1 + breakout_pct)
    vol_ok = vol.iloc[-1] > vol_ma_n.iloc[-1] * vol_mult
    close_strong = close.iloc[-1] >= close.iloc[-2]

    if breakout and vol_ok and (close_strong or not require_close_up):
        return True, "volume_confirm_breakout"

    return False, ""
