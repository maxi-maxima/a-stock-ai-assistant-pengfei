from skills.strategies.strategy_params import get_params, as_int, as_bool
from core.ta_utils import rsi_dynamic_thresholds, adx


def _kdj_bull_divergence(close, k, d, lookback=20):
    if len(close) < lookback + 2:
        return False
    price_new_low = close.iloc[-1] <= close.rolling(lookback).min().iloc[-1]
    k_new_low = k.iloc[-1] <= k.rolling(lookback).min().iloc[-1]
    d_new_low = d.iloc[-1] <= d.rolling(lookback).min().iloc[-1]
    # price new low but K/D do not -> bullish divergence
    return bool(price_new_low and (not k_new_low) and (not d_new_low))


def check(df):
    defaults = {
        "min_bars": 30,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "kdj_period": 9,
        "kdj_com": 2,
        "kdj_divergence_lookback": 20,
        "require_price_up": True
    }
    params = get_params("skill_oscillator_combo", defaults)
    min_bars = as_int(params.get("min_bars", 30), 30, 1)
    rsi_period = as_int(params.get("rsi_period", 14), 14, 2)
    rsi_oversold = as_int(params.get("rsi_oversold", 30), 30, 1)
    kdj_period = as_int(params.get("kdj_period", 9), 9, 2)
    kdj_com = as_int(params.get("kdj_com", 2), 2, 1)
    kdj_div_lb = as_int(params.get("kdj_divergence_lookback", 20), 20, 5)
    require_price_up = as_bool(params.get("require_price_up", True), True)

    min_bars = max(min_bars, rsi_period + 5, kdj_period + 5)
    if len(df) < min_bars:
        return False, "not_enough_data"

    close = df["close"]
    high = df["high"]
    low = df["low"]

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))

    low_n = low.rolling(kdj_period, min_periods=kdj_period).min()
    high_n = high.rolling(kdj_period, min_periods=kdj_period).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, 1e-9) * 100
    k = rsv.ewm(com=kdj_com).mean()
    d = k.ewm(com=kdj_com).mean()

    dyn = rsi_dynamic_thresholds(df)
    lower = int(dyn.get("lower", rsi_oversold) or rsi_oversold)
    rsi_recover = rsi.iloc[-2] < lower and rsi.iloc[-1] > rsi.iloc[-2]

    # Trend filter: disable KDJ in strong trends; only use in ranges
    adx_series = adx(df, period=14)
    adx_val = float(adx_series.iloc[-1]) if adx_series is not None else None
    if adx_val is not None and adx_val >= 20:
        return False, "kdj_disabled_trend"

    # Pattern recognition: KDJ divergence preferred over simple cross
    kdj_div = _kdj_bull_divergence(close, k, d, lookback=kdj_div_lb)
    price_up = close.iloc[-1] > close.iloc[-2]

    if rsi_recover and kdj_div and (price_up or not require_price_up):
        return True, "oscillator_combo_divergence"

    return False, ""
