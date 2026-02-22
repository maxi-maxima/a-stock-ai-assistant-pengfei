from skills.strategies.strategy_params import get_params, as_int, as_bool
from core.ta_utils import resolve_ma_periods, ma_series


def check(df):
    periods = resolve_ma_periods()
    defaults = {
        "min_bars": 260,
        "ma_short": periods.get('short1', 5),
        "ma_mid": periods.get('mid1', 20),
        "ma_long1": periods.get('long1', 120),
        "ma_long2": periods.get('long2', 250),
        "ma_mid_slope_lookback": 3,
        "require_price_above_long": True
    }
    params = get_params("skill_multi_timeframe_proxy", defaults)
    min_bars = as_int(params.get("min_bars", 260), 260, 1)
    ma_short = as_int(params.get("ma_short", 5), 5, 1)
    ma_mid = as_int(params.get("ma_mid", 20), 20, 1)
    ma_long1 = as_int(params.get("ma_long1", 120), 120, 1)
    ma_long2 = as_int(params.get("ma_long2", 250), 250, 1)
    slope_lb = as_int(params.get("ma_mid_slope_lookback", 3), 3, 2)
    require_price_above = as_bool(params.get("require_price_above_long", True), True)

    min_bars = max(min_bars, ma_long2 + 5, slope_lb + 2)
    if len(df) < min_bars:
        return False, "not_enough_data"

    close = df["close"]
    ma_s = ma_series(close, ma_short)
    ma_m = ma_series(close, ma_mid)
    ma_l1 = ma_series(close, ma_long1)
    ma_l2 = ma_series(close, ma_long2)

    long_trend = ma_l1.iloc[-1] > ma_l2.iloc[-1]
    if require_price_above:
        long_trend = long_trend and close.iloc[-1] > ma_l1.iloc[-1]
    short_signal = ma_s.iloc[-2] <= ma_m.iloc[-2] and ma_s.iloc[-1] > ma_m.iloc[-1]
    ma_mid_up = ma_m.iloc[-1] > ma_m.iloc[-slope_lb]

    if long_trend and short_signal and ma_mid_up:
        return True, "multi_timeframe_proxy_resonance"

    return False, ""
