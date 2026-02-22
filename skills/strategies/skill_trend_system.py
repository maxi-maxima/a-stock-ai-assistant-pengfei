from skills.strategies.strategy_params import get_params, as_int
from core.ta_utils import resolve_ma_periods, ma_series, adx


def check(df):
    periods = resolve_ma_periods()
    defaults = {
        "min_bars": 260,
        "ema_short": periods.get('short1', 5),
        "ema_mid": periods.get('mid1', 20),
        "ema_long1": periods.get('mid2', 60),
        "ema_long2": periods.get('long1', 120),
        "ema_long3": periods.get('long2', 250),
        "ema_mid_slope_lookback": 3,
        "macd_fast": 8,
        "macd_slow": 17,
        "macd_signal": 9,
        "boll_period": 10
    }
    params = get_params("skill_trend_system", defaults)
    min_bars = as_int(params.get("min_bars", 260), 260, 1)
    ema_short = as_int(params.get("ema_short", 5), 5, 1)
    ema_mid = as_int(params.get("ema_mid", 20), 20, 1)
    ema_long1 = as_int(params.get("ema_long1", 60), 60, 1)
    ema_long2 = as_int(params.get("ema_long2", 120), 120, 1)
    ema_long3 = as_int(params.get("ema_long3", 250), 250, 1)
    slope_lb = as_int(params.get("ema_mid_slope_lookback", 3), 3, 2)
    macd_fast = as_int(params.get("macd_fast", 8), 8, 1)
    macd_slow = as_int(params.get("macd_slow", 17), 17, 1)
    macd_signal = as_int(params.get("macd_signal", 9), 9, 1)
    div_lookback = as_int(params.get("divergence_lookback", 20), 20, 5)
    boll_period = as_int(params.get("boll_period", 10), 10, 2)

    min_bars = max(min_bars, ema_long3 + 5, macd_slow + 5, boll_period + 5, slope_lb + 2)
    if len(df) < min_bars:
        return False, "not_enough_data"

    close = df["close"]
    ema_s = close.ewm(span=ema_short, adjust=False).mean()
    ema_m = close.ewm(span=ema_mid, adjust=False).mean()
    ema_l1 = close.ewm(span=ema_long1, adjust=False).mean()
    ema_l2 = close.ewm(span=ema_long2, adjust=False).mean()
    ema_l3 = close.ewm(span=ema_long3, adjust=False).mean()

    cross_up = ema_s.iloc[-2] <= ema_m.iloc[-2] and ema_s.iloc[-1] > ema_m.iloc[-1]
    stack_bull = ema_m.iloc[-1] > ema_l1.iloc[-1] > ema_l2.iloc[-1] > ema_l3.iloc[-1]
    ema_mid_up = ema_m.iloc[-1] > ema_m.iloc[-slope_lb]

    ema_fast = close.ewm(span=macd_fast, adjust=False).mean()
    ema_slow = close.ewm(span=macd_slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=macd_signal, adjust=False).mean()
    macd_cross = dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]
    hist = dif - dea
    hist_up = hist.iloc[-1] > hist.iloc[-2]

    # 领先信号：背离优先
    price_new_low = close.iloc[-1] <= close.rolling(div_lookback).min().iloc[-1]
    dif_new_low = dif.iloc[-1] <= dif.rolling(div_lookback).min().iloc[-1]
    bull_div = bool(price_new_low and not dif_new_low)

    # 环境过滤：ADX>25重视顺势，ADX<20降低权重
    adx_series = adx(df, period=14)
    adx_val = float(adx_series.iloc[-1]) if adx_series is not None else None
    if adx_val is not None:
        if adx_val > 25:
            macd_ok = bull_div or macd_cross or hist_up
        elif adx_val < 20:
            macd_ok = bull_div
        else:
            macd_ok = bull_div or hist_up
    else:
        macd_ok = bull_div or hist_up

    boll_mid = ma_series(close, boll_period).iloc[-1]

    if cross_up and stack_bull and ema_mid_up and macd_ok and close.iloc[-1] >= boll_mid:
        return True, "trend_system_resonance"

    return False, ""
