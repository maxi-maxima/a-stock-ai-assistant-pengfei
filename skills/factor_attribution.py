import pandas as pd
from core.learning_log import load_events


def _extract_features(ev):
    payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
    return payload.get("features", {}) if isinstance(payload.get("features"), dict) else {}


def summarize_factor_effects():
    events = load_events(5000)
    sells = []
    for ev in events:
        if ev.get("event") != "paper_trade":
            continue
        payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
        if payload.get("action") != "SELL":
            continue
        pnl = payload.get("pnl", 0)
        features = _extract_features(ev)
        sells.append({"pnl": pnl, "features": features})

    if not sells:
        return pd.DataFrame()

    rows = []
    for s in sells:
        feats = s["features"] or {}
        tech = feats.get("tech_factors", {}) if isinstance(feats.get("tech_factors"), dict) else {}
        cap = feats.get("capital_data", {}) if isinstance(feats.get("capital_data"), dict) else {}
        chip = feats.get("chip_data", {}) if isinstance(feats.get("chip_data"), dict) else {}
        fund = feats.get("fundamental", {}) if isinstance(feats.get("fundamental"), dict) else {}
        rows.append({
            "pnl": s["pnl"],
            "atr": tech.get("atr"),
            "boll_mid": tech.get("boll_mid"),
            "net_mf": cap.get("net_mf_amount"),
            "chip_win": chip.get("win_rate"),
            "pe": fund.get("PE")
        })

    df = pd.DataFrame(rows).dropna(how="all")
    if df.empty:
        return df
    # simple correlation as proxy
    corr = df.corr(numeric_only=True)
    return corr


def split_factor_stats():
    events = load_events(5000)
    sells = []
    for ev in events:
        if ev.get("event") != "paper_trade":
            continue
        payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
        if payload.get("action") != "SELL":
            continue
        pnl = payload.get("pnl", 0)
        features = _extract_features(ev)
        sells.append({"pnl": pnl, "features": features})

    if not sells:
        return None, None

    rows = []
    for s in sells:
        feats = s["features"] or {}
        tech = feats.get("tech_factors", {}) if isinstance(feats.get("tech_factors"), dict) else {}
        cap = feats.get("capital_data", {}) if isinstance(feats.get("capital_data"), dict) else {}
        chip = feats.get("chip_data", {}) if isinstance(feats.get("chip_data"), dict) else {}
        fund = feats.get("fundamental", {}) if isinstance(feats.get("fundamental"), dict) else {}
        rows.append({
            "pnl": s["pnl"],
            "atr": tech.get("atr"),
            "boll_mid": tech.get("boll_mid"),
            "net_mf": cap.get("net_mf_amount"),
            "chip_win": chip.get("win_rate"),
            "pe": fund.get("PE")
        })

    df = pd.DataFrame(rows).dropna(how="all")
    if df.empty:
        return None, None
    win = df[df["pnl"] > 0]
    lose = df[df["pnl"] <= 0]
    return win.describe(), lose.describe()
