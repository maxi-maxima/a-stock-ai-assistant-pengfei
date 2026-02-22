import pandas as pd


def calc_yoy(df, col, end_date):
    if df is None or df.empty:
        return None
    if not end_date or col not in df.columns:
        return None
    try:
        year = int(str(end_date)[:4]) - 1
        target = f"{year}{str(end_date)[4:]}"
        prev = df[df["end_date"] == target]
        if prev.empty:
            return None
        prev_val = float(prev.iloc[0].get(col, 0))
        curr_val = float(df.iloc[0].get(col, 0))
        if prev_val == 0:
            return None
        return (curr_val - prev_val) / abs(prev_val) * 100
    except Exception:
        return None


def calc_ttm(df, col):
    if df is None or df.empty or col not in df.columns:
        return None
    try:
        vals = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(vals) < 4:
            return None
        return float(vals.iloc[:4].sum())
    except Exception:
        return None


def extract_metrics(code, df_inc, df_bs, df_cf):
    metrics = {"code": code}
    if df_inc is not None and not df_inc.empty:
        latest = df_inc.iloc[0]
        end_date = latest.get("end_date")
        rev = latest.get("total_revenue", 0)
        net = latest.get("n_income", 0)
        cost = latest.get("oper_cost", 0)
        metrics.update({
            "end_date": end_date,
            "revenue": float(rev) if pd.notna(rev) else 0.0,
            "net_income": float(net) if pd.notna(net) else 0.0,
            "eps": latest.get("basic_eps", 0)
        })
        if rev and pd.notna(cost):
            metrics["gross_margin"] = (rev - cost) / rev * 100
        if rev:
            metrics["net_margin"] = float(net) / float(rev) * 100
        metrics["yoy_revenue"] = calc_yoy(df_inc, "total_revenue", end_date)
        metrics["yoy_net"] = calc_yoy(df_inc, "n_income", end_date)
        metrics["ttm_revenue"] = calc_ttm(df_inc, "total_revenue")
        metrics["ttm_net"] = calc_ttm(df_inc, "n_income")
    if df_bs is not None and not df_bs.empty:
        b = df_bs.iloc[0]
        assets = b.get("total_assets", 0)
        liab = b.get("total_liab", 0)
        equity = b.get("total_hldr_eqy_exc_min_int", 0)
        metrics["assets"] = float(assets) if pd.notna(assets) else 0.0
        metrics["liab"] = float(liab) if pd.notna(liab) else 0.0
        metrics["equity"] = float(equity) if pd.notna(equity) else 0.0
        if assets:
            metrics["debt_ratio"] = float(liab) / float(assets) * 100
        if metrics.get("net_income") is not None and equity:
            metrics["roe"] = float(metrics["net_income"]) / float(equity) * 100
        if metrics.get("net_income") is not None and assets:
            metrics["roa"] = float(metrics["net_income"]) / float(assets) * 100
    if df_cf is not None and not df_cf.empty:
        c = df_cf.iloc[0]
        ocf = c.get("n_cashflow_act", 0)
        metrics["ocf"] = float(ocf) if pd.notna(ocf) else 0.0
        if metrics.get("net_income") is not None and metrics.get("net_income") != 0:
            metrics["ocf_to_net"] = float(ocf) / float(metrics["net_income"])
        metrics["ttm_ocf"] = calc_ttm(df_cf, "n_cashflow_act")
    return metrics


def score_financial(metrics, weights=None):
    weights = weights or {"profit": 1.0, "growth": 1.0, "quality": 1.0, "cash": 1.0, "stability": 1.0}
    score = 0
    detail = {}

    gm = metrics.get("gross_margin")
    nm = metrics.get("net_margin")
    gm_score = 0
    nm_score = 0
    if gm is not None:
        if gm >= 30:
            gm_score = 15
        elif gm >= 20:
            gm_score = 10
        elif gm >= 10:
            gm_score = 5
    if nm is not None:
        if nm >= 10:
            nm_score = 10
        elif nm >= 5:
            nm_score = 6
        elif nm > 0:
            nm_score = 3
    detail["profit"] = (gm_score + nm_score) * weights.get("profit", 1.0)
    score += detail["profit"]

    yr = metrics.get("yoy_revenue")
    yn = metrics.get("yoy_net")
    yr_score = 0
    yn_score = 0
    if yr is not None:
        if yr >= 20:
            yr_score = 10
        elif yr >= 10:
            yr_score = 7
        elif yr >= 0:
            yr_score = 4
    if yn is not None:
        if yn >= 20:
            yn_score = 10
        elif yn >= 10:
            yn_score = 7
        elif yn >= 0:
            yn_score = 4
    detail["growth"] = (yr_score + yn_score) * weights.get("growth", 1.0)
    score += detail["growth"]

    dr = metrics.get("debt_ratio")
    roe = metrics.get("roe")
    dr_score = 0
    roe_score = 0
    if dr is not None:
        if dr < 30:
            dr_score = 10
        elif dr < 50:
            dr_score = 7
        elif dr < 70:
            dr_score = 4
    if roe is not None:
        if roe >= 15:
            roe_score = 10
        elif roe >= 10:
            roe_score = 7
        elif roe >= 5:
            roe_score = 4
    detail["quality"] = (dr_score + roe_score) * weights.get("quality", 1.0)
    score += detail["quality"]

    ocf = metrics.get("ocf")
    ocf_ratio = metrics.get("ocf_to_net")
    ocf_score = 10 if ocf is not None and ocf > 0 else 0
    ocf_ratio_score = 0
    if ocf_ratio is not None:
        if ocf_ratio >= 1:
            ocf_ratio_score = 10
        elif ocf_ratio >= 0.7:
            ocf_ratio_score = 7
        elif ocf_ratio >= 0.3:
            ocf_ratio_score = 4
    detail["cash"] = (ocf_score + ocf_ratio_score) * weights.get("cash", 1.0)
    score += detail["cash"]

    ttm_rev = metrics.get("ttm_revenue")
    ttm_net = metrics.get("ttm_net")
    stab = 0
    if ttm_rev is not None and ttm_rev > 0:
        stab += 5
    if ttm_net is not None and ttm_net > 0:
        stab += 5
    detail["stability"] = stab * weights.get("stability", 1.0)
    score += detail["stability"]

    if score > 100:
        score = 100

    if score >= 80:
        grade = "A"
    elif score >= 65:
        grade = "B"
    elif score >= 50:
        grade = "C"
    else:
        grade = "D"

    return score, grade, detail
