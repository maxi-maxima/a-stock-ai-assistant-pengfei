import datetime
import json
import os


WATCHLIST_PATH = "data/watchlist.json"


def _normalize_code_list(values):
    out = []
    for item in values or []:
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
        else:
            code = item
        code = str(code or "").strip()
        if code and code not in out:
            out.append(code)
    return out


def load_watchlist_codes(path=WATCHLIST_PATH):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if isinstance(data, dict) and "codes" in data:
        data = data.get("codes", [])
    return _normalize_code_list(data if isinstance(data, list) else [])


def prefer_akshare_fallback(scanner):
    meta = {"akshare_only": False}
    try:
        data_skill = getattr(scanner, "data_skill", None)
        market = getattr(data_skill, "market", None) if data_skill is not None else None
        if market is not None:
            if hasattr(market, "pro"):
                market.pro = None
            if hasattr(market, "token"):
                market.token = ""
            meta["akshare_only"] = True
    except Exception:
        meta["akshare_only"] = False
    return meta


def resolve_universe(watchlist=None, fallback=None, limit=None):
    rows = _normalize_code_list(watchlist or [])
    if not rows:
        rows = _normalize_code_list(fallback or [])
    if limit:
        rows = rows[: int(limit)]
    return rows


def _to_date(text):
    try:
        return datetime.date.fromisoformat(str(text))
    except Exception:
        return None


def resolve_reference_trade_date(candidate_dates=None, today=None):
    today_date = _to_date(today) or datetime.date.today()
    normalized = []
    for item in candidate_dates or []:
        dt = _to_date(item)
        if dt is None:
            continue
        if dt > today_date:
            continue
        normalized.append(dt)
    if normalized:
        return max(normalized).isoformat()

    probe = today_date
    while probe.weekday() >= 5:
        probe -= datetime.timedelta(days=1)
    return probe.isoformat()


def calc_planned_exit_date(buy_date, hold_days, trading_days=None):
    buy_date = str(buy_date)
    hold_days = max(1, int(hold_days or 1))
    ordered = sorted(set([str(x) for x in (trading_days or []) if str(x)]))
    if ordered and buy_date in ordered:
        idx = ordered.index(buy_date)
        target_idx = idx + hold_days
        if target_idx < len(ordered):
            return ordered[target_idx]

    current = datetime.date.fromisoformat(buy_date)
    advanced = 0
    while advanced < hold_days:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:
            advanced += 1
    return current.isoformat()
