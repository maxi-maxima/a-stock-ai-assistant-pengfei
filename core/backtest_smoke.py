import datetime
import json
import os


from skills.backtester import Backtester
from skills.scanner import MarketScanner


LATEST_PATH = "data/backtest_smoke_latest.json"
HISTORY_PATH = "data/backtest_smoke_report.jsonl"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except Exception:
        return float(default)


def _save_json(path, payload):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _append_jsonl(path, payload):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _normalize_list(values):
    out = []
    seen = set()
    for v in values or []:
        if v is None:
            continue
        s = str(v).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _default_codes():
    env = str(os.getenv("BACKTEST_SMOKE_CODES", "")).strip()
    if env:
        return _normalize_list([x.strip().upper() for x in env.split(",") if x.strip()])
    return ["000001.SZ", "600519.SH", "300750.SZ", "000858.SZ", "601318.SH"]


def run_backtest_smoke(
    codes=None,
    strategies=None,
    days=240,
    max_strategies=4,
    max_cases=12,
    apply=True,
    latest_path=LATEST_PATH,
    history_path=HISTORY_PATH,
    scanner=None,
    backtester=None,
):
    scanner = scanner or MarketScanner("tushare")
    backtester = backtester or Backtester()

    codes = _normalize_list(codes or _default_codes())
    all_strategies = _normalize_list(strategies or scanner.get_strategy_list())
    if max_strategies and len(all_strategies) > int(max_strategies):
        all_strategies = all_strategies[: int(max_strategies)]

    rows = []
    total = 0
    passed = 0
    no_data = 0
    errors = 0

    for code in codes:
        for strategy in all_strategies:
            if max_cases and total >= int(max_cases):
                break
            total += 1

            try:
                df = scanner.data_skill.get_history(code, days=int(days))
            except Exception as exc:
                errors += 1
                rows.append(
                    {
                        "code": code,
                        "strategy": strategy,
                        "status": "error",
                        "error": f"data_fetch_failed: {exc}",
                    }
                )
                continue

            if df is None or df.empty:
                no_data += 1
                rows.append({"code": code, "strategy": strategy, "status": "no_data"})
                continue

            try:
                result = backtester.run(
                    df,
                    strategy,
                    take_profit=0.1,
                    stop_loss=0.05,
                    max_days=20,
                    position_pct=1.0,
                    execution="next_open",
                )
            except Exception as exc:
                errors += 1
                rows.append(
                    {
                        "code": code,
                        "strategy": strategy,
                        "status": "error",
                        "error": f"backtest_crash: {exc}",
                    }
                )
                continue

            if not isinstance(result, dict):
                errors += 1
                rows.append({"code": code, "strategy": strategy, "status": "error", "error": "invalid_result"})
                continue

            if result.get("error"):
                errors += 1
                rows.append(
                    {
                        "code": code,
                        "strategy": strategy,
                        "status": "error",
                        "error": str(result.get("error")),
                    }
                )
                continue

            passed += 1
            rows.append(
                {
                    "code": code,
                    "strategy": strategy,
                    "status": "ok",
                    "return_pct": _safe_float(result.get("return_pct"), 0.0),
                    "max_drawdown": _safe_float(result.get("max_drawdown"), 0.0),
                    "sharpe": _safe_float(result.get("sharpe"), 0.0),
                    "score": _safe_float(result.get("score"), 0.0),
                    "trades": len(result.get("trades", []) or []),
                }
            )
        if max_cases and total >= int(max_cases):
            break

    passed_rows = [r for r in rows if isinstance(r, dict) and r.get("status") == "ok"]
    champion = None
    if passed_rows:
        champion = max(passed_rows, key=lambda x: (_safe_float(x.get("score"), 0.0), _safe_float(x.get("return_pct"), 0.0)))

    ok = passed > 0 and errors == 0
    summary = {
        "ts": _now(),
        "status": "pass" if ok else "fail",
        "ok": ok,
        "days": int(days),
        "total_cases": int(total),
        "passed_cases": int(passed),
        "no_data_cases": int(no_data),
        "error_cases": int(errors),
        "pass_rate": (float(passed) / float(total)) if total else 0.0,
        "champion_strategy": champion.get("strategy") if isinstance(champion, dict) else "",
        "champion_code": champion.get("code") if isinstance(champion, dict) else "",
        "champion_score": _safe_float(champion.get("score"), 0.0) if isinstance(champion, dict) else 0.0,
        "champion_return_pct": _safe_float(champion.get("return_pct"), 0.0) if isinstance(champion, dict) else 0.0,
        "rows": rows,
    }

    if apply:
        _save_json(latest_path, summary)
        _append_jsonl(history_path, summary)
    return summary
