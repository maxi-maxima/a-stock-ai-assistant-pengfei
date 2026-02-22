
from core.ta_utils import adx


def _bullish_divergence(close, dif, lookback=20):
    if len(close) < lookback + 2:
        return False
    price_new_low = close.iloc[-1] <= close.rolling(lookback).min().iloc[-1]
    dif_new_low = dif.iloc[-1] <= dif.rolling(lookback).min().iloc[-1]
    # price makes new low but DIF does not -> bullish divergence
    return bool(price_new_low and not dif_new_low)


def check(df):
    # 示例：MACD 领先信号（背离优先）
    # df 包含: open, close, high, low, vol, pct_chg 等
    if len(df) < 40:
        return False, ""

    close = df["close"]
    ema_fast = close.ewm(span=8, adjust=False).mean()
    ema_slow = close.ewm(span=17, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=9, adjust=False).mean()

    # 领先信号：背离优先
    bull_div = _bullish_divergence(close, dif, lookback=20)

    # 顺势信号（弱化）
    macd_cross = dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]
    hist_up = (dif - dea).iloc[-1] > (dif - dea).iloc[-2]

    # 环境过滤：ADX>25重视顺势，ADX<20降低权重
    adx_series = adx(df, period=14)
    adx_val = float(adx_series.iloc[-1]) if adx_series is not None else None

    if adx_val is not None:
        if adx_val > 25:
            if bull_div or macd_cross or hist_up:
                return True, "MACD背离/顺势(ADX>25)"
        elif adx_val < 20:
            if bull_div:
                return True, "MACD背离(ADX<20)"
        else:
            if bull_div or hist_up:
                return True, "MACD背离/动能"
    else:
        if bull_div or hist_up:
            return True, "MACD背离/动能"

    return False, ""
