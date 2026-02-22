import numpy as np


def max_drawdown(equity):
    if not equity:
        return 0.0
    arr = np.array(equity, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / peak
    return float(dd.min()) if len(dd) else 0.0


def var_gaussian(returns, alpha=0.95):
    if returns is None or len(returns) < 5:
        return 0.0
    r = np.array(returns, dtype=float)
    mu = r.mean()
    sigma = r.std()
    # normal approximation
    from math import erf, sqrt
    # inverse CDF for alpha (approx via erfinv)
    try:
        from scipy.special import erfinv
        z = sqrt(2) * erfinv(2 * (1 - alpha) - 1)
    except Exception:
        # fallback: rough quantile using numpy
        z = np.quantile(r, 1 - alpha) - mu
        return float(abs(mu + z))
    return float(abs(mu + z * sigma))


def risk_level_from_metrics(mdd, var):
    # mdd is negative
    if mdd <= -0.20 or var >= 0.06:
        return "HIGH"
    if mdd <= -0.12 or var >= 0.04:
        return "MEDIUM"
    return "LOW"


def reduce_ratio_by_level(level):
    if level == "HIGH":
        return 0.3
    if level == "MEDIUM":
        return 0.6
    return 1.0
