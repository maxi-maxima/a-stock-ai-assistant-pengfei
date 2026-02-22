import json
import os


MA_CONFIG_PATH = "config/ma_periods.json"
DEFAULT_MA_CONFIG = {
    "method": "ema",
    "short": [5, 10],
    "mid": [20, 60],
    "long": [120, 250]
}


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_period_list(val, fallback):
    if isinstance(val, (list, tuple)):
        out = []
        for item in val:
            try:
                p = int(item)
            except Exception:
                continue
            if p >= 1:
                out.append(p)
        if out:
            return out
    return list(fallback)


def get_ma_config():
    cfg = dict(DEFAULT_MA_CONFIG)
    data = _load_json(MA_CONFIG_PATH)
    if isinstance(data, dict):
        if data.get("method"):
            cfg["method"] = str(data.get("method")).strip().lower() or cfg["method"]
        cfg["short"] = _normalize_period_list(data.get("short"), cfg["short"])
        cfg["mid"] = _normalize_period_list(data.get("mid"), cfg["mid"])
        cfg["long"] = _normalize_period_list(data.get("long"), cfg["long"])
    return cfg


def resolve_ma_periods():
    cfg = get_ma_config()
    short = list(cfg.get("short") or [])
    mid = list(cfg.get("mid") or [])
    long_ = list(cfg.get("long") or [])
    def _pick(arr, idx, fallback):
        if len(arr) > idx:
            return arr[idx]
        if arr:
            return arr[-1]
        return fallback
    return {
        "method": cfg.get("method", "ema"),
        "short1": _pick(short, 0, 5),
        "short2": _pick(short, 1, _pick(short, 0, 10)),
        "mid1": _pick(mid, 0, 20),
        "mid2": _pick(mid, 1, _pick(mid, 0, 60)),
        "long1": _pick(long_, 0, 120),
        "long2": _pick(long_, 1, _pick(long_, 0, 250)),
        "all": sorted(set(short + mid + long_))
    }


def ma_series(series, period, method=None):
    if series is None:
        return None
    try:
        period = int(period)
    except Exception:
        period = 20
    method = (method or get_ma_config().get("method") or "ema").lower()
    if method == "sma":
        return series.rolling(period).mean()
    return series.ewm(span=period, adjust=False).mean()


def add_ma_columns(df, periods=None, method=None, prefix="ma"):
    if df is None or df.empty:
        return df
    periods = periods or resolve_ma_periods().get("all", [])
    for p in periods:
        col = f"{prefix}{int(p)}"
        if col not in df.columns:
            df[col] = ma_series(df["close"], p, method=method)
    return df


def add_vol_ma_columns(df, periods=None, method=None, prefix="vol_ma"):
    if df is None or df.empty or "vol" not in df.columns:
        return df
    periods = periods or resolve_ma_periods().get("all", [])
    for p in periods:
        col = f"{prefix}{int(p)}"
        if col not in df.columns:
            df[col] = ma_series(df["vol"], p, method=method)
    return df


def adx(df, period=14):
    """
    Average Directional Index (ADX).
    Returns a pandas Series aligned to df index.
    """
    if df is None or df.empty:
        return None
    try:
        period = int(period)
    except Exception:
        period = 14
    if period < 2:
        period = 2
    if not {"high", "low", "close"}.issubset(df.columns):
        return None

    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = low.shift(1) - low

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = tr1.combine(tr2, max).combine(tr3, max)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, 1e-9))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, 1e-9))

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9) * 100
    adx_series = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_series


def rsi_dynamic_thresholds(
    df,
    trend_upper=80,
    trend_lower=20,
    range_upper=70,
    range_lower=30,
    adx_period=14,
    adx_trend=25,
    adx_range=20
):
    """
    Dynamic RSI thresholds by regime.
    - Trend: 80/20
    - Range: 70/30
    """
    upper = range_upper
    lower = range_lower
    regime = "range"
    adx_val = None

    adx_series = adx(df, period=adx_period)
    if adx_series is not None and len(adx_series) > 0:
        try:
            adx_val = float(adx_series.iloc[-1])
        except Exception:
            adx_val = None

    if adx_val is None:
        return {
            "upper": upper,
            "lower": lower,
            "regime": "unknown",
            "adx": adx_val
        }

    if adx_val >= float(adx_trend):
        upper = trend_upper
        lower = trend_lower
        regime = "trend"
    elif adx_val <= float(adx_range):
        upper = range_upper
        lower = range_lower
        regime = "range"
    else:
        upper = range_upper
        lower = range_lower
        regime = "neutral"

    return {
        "upper": upper,
        "lower": lower,
        "regime": regime,
        "adx": adx_val
    }
