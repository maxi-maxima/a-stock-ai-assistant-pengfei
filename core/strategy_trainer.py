import datetime
import json
import os
import uuid

from skills.backtester import Backtester
from skills.scanner import MarketScanner
from core.skill_registry import SkillRegistry
from core.event_bus import EventBus
from core.experiment_log import log_experiment
from core.logger import exception


CONFIG_PATH = "config/strategy_training.json"
REPORT_PATH = "data/strategy_training_report.jsonl"
LATEST_PATH = "data/strategy_training_latest.json"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load_config(path=CONFIG_PATH):
    defaults = {
        "enabled": True,
        "pool": "watchlist",
        "mode": "walk_forward",
        "days": 1000,
        "max_codes": 100,
        "max_strategies": 0,
        "min_trades": 2,
        "train_ratio": 0.7,
        "window_count": 3,
        "use_saved_params": True,
        "default_params": {
            "tp": 0.10,
            "sl": 0.05,
            "days": 20,
            "position_pct": 1.0,
            "execution": "next_open"
        },
        "include_strategies": [],
        "exclude_strategies": [],
        "custom_codes": []
    }
    if not os.path.exists(path):
        return defaults
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        out = dict(defaults)
        out.update(data)
        return out
    except Exception:
        return defaults


def _append_report(record):
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _normalize_codes(entries):
    out = []
    seen = set()
    for item in entries or []:
        code = None
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
        elif isinstance(item, str):
            code = item
        if not code:
            continue
        code = str(code).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _select_codes(scanner, cfg):
    pool = str(cfg.get("pool") or "watchlist").strip().lower()
    max_codes = int(cfg.get("max_codes", 100) or 100)
    if pool == "custom":
        codes = _normalize_codes(cfg.get("custom_codes", []))
        return codes[:max_codes]
    if pool == "global":
        candidates = scanner.get_candidate_pool(mode="global", limit=max_codes)
    else:
        candidates = scanner.get_candidate_pool(mode="watchlist", limit=max_codes)
    codes = _normalize_codes(candidates)
    return codes[:max_codes]


def _filter_strategies(strategies, cfg):
    include = [str(s).strip() for s in cfg.get("include_strategies", []) if str(s).strip()]
    exclude = [str(s).strip() for s in cfg.get("exclude_strategies", []) if str(s).strip()]
    out = []
    for s in strategies:
        if include and s not in include:
            continue
        if exclude and s in exclude:
            continue
        out.append(s)
    max_strategies = int(cfg.get("max_strategies", 0) or 0)
    if max_strategies > 0:
        out = out[:max_strategies]
    return out


def run_training(config=None, progress_callback=None):
    cfg = config or _load_config()
    if not cfg.get("enabled", True):
        return {"enabled": False, "ts": _now()}

    scanner = MarketScanner()
    backtester = Backtester()
    registry = SkillRegistry()
    bus = EventBus()

    codes = _select_codes(scanner, cfg)
    strategies = _filter_strategies(scanner.get_strategy_list(), cfg)

    def _emit_progress(done, total, message=None):
        if not progress_callback:
            return
        try:
            progress_callback(done, total, message)
        except Exception:
            pass

    # preload history to reduce repeated API calls
    history_map = {}
    for code in codes:
        try:
            df = scanner.data_skill.get_history(code, days=int(cfg.get("days", 1000) or 1000))
        except Exception:
            df = None
        if df is not None and not df.empty:
            history_map[code] = df

    mode = str(cfg.get("mode", "walk_forward")).strip().lower()
    train_ratio = float(cfg.get("train_ratio", 0.7) or 0.7)
    window_count = int(cfg.get("window_count", 3) or 3)
    min_trades = int(cfg.get("min_trades", 2) or 2)

    default_params = cfg.get("default_params", {}) if isinstance(cfg.get("default_params", {}), dict) else {}
    default_tp = float(default_params.get("tp", 0.10) or 0.10)
    default_sl = float(default_params.get("sl", 0.05) or 0.05)
    default_days = int(default_params.get("days", 20) or 20)
    default_pos = float(default_params.get("position_pct", 1.0) or 1.0)
    default_exec = str(default_params.get("execution", "next_open") or "next_open")

    run_id = uuid.uuid4().hex
    report = {
        "run_id": run_id,
        "ts": _now(),
        "mode": mode,
        "pool": cfg.get("pool"),
        "days": int(cfg.get("days", 1000) or 1000),
        "max_codes": int(cfg.get("max_codes", 100) or 100),
        "strategies": {},
        "codes_total": len(codes),
        "codes_with_data": len(history_map)
    }

    total_steps = max(1, len(strategies) * max(1, len(history_map)))
    done_steps = 0
    _emit_progress(done_steps, total_steps, "准备训练...")

    for strategy in strategies:
        strat_code = backtester._get_strategy_code(strategy)
        saved = backtester.get_saved_params(strategy) if cfg.get("use_saved_params", True) else {}
        tp = float(saved.get("tp", default_tp) or default_tp)
        sl = float(saved.get("sl", default_sl) or default_sl)
        hold_days = int(saved.get("days", default_days) or default_days)

        stats = {
            "strategy": strategy,
            "strategy_code": strat_code,
            "samples": 0,
            "skipped": 0,
            "errors": 0,
            "avg_score": 0.0,
            "avg_return": 0.0,
            "avg_drawdown": 0.0
        }

        sum_score = 0.0
        sum_ret = 0.0
        sum_dd = 0.0
        best_params = None
        best_score = None

        for code, df in history_map.items():
            try:
                if df is None or df.empty or len(df) < 120:
                    stats["skipped"] += 1
                else:
                    if mode == "walk_forward":
                        best = backtester.optimize(
                            df,
                            strategy,
                            train_ratio=train_ratio,
                            mode="walk_forward",
                            window_count=window_count,
                            position_pct=default_pos,
                            execution=default_exec,
                            commission=None,
                            slippage=None,
                            stamp_duty=None,
                            lot_size=None,
                            context=None
                        )
                        if not best:
                            stats["skipped"] += 1
                        else:
                            top = best[0]
                            score = float(top.get("score", 0) or 0)
                            ret = float(top.get("test_ret", 0) or 0)
                            dd = float(top.get("test_dd", 0) or 0)
                            reward = float(score) / 100.0
                            registry.update_reward(strat_code, reward, source="trainer")
                            sum_score += score
                            sum_ret += ret
                            sum_dd += dd
                            stats["samples"] += 1
                            if best_score is None or score > best_score:
                                best_score = score
                                best_params = {"tp": top.get("tp"), "sl": top.get("sl"), "days": top.get("days")}
                    else:
                        res = backtester.run(
                            df,
                            strategy,
                            take_profit=tp,
                            stop_loss=sl,
                            max_days=hold_days,
                            position_pct=default_pos,
                            execution=default_exec,
                            commission=None,
                            slippage=None,
                            stamp_duty=None,
                            lot_size=None,
                            context=None
                        )
                        if "error" in res:
                            stats["errors"] += 1
                        else:
                            trades = res.get("trades", []) or []
                            sells = [t for t in trades if t.get("action") == "SELL"]
                            if len(sells) < min_trades:
                                stats["skipped"] += 1
                            else:
                                score = float(res.get("score", 0) or 0)
                                ret = float(res.get("return_pct", 0) or 0)
                                dd = float(res.get("max_drawdown", 0) or 0)
                                reward = float(score) / 100.0
                                registry.update_reward(strat_code, reward, source="trainer")
                                sum_score += score
                                sum_ret += ret
                                sum_dd += dd
                                stats["samples"] += 1
            except Exception:
                stats["errors"] += 1
            finally:
                done_steps += 1
                _emit_progress(done_steps, total_steps, f"训练中: {strategy} ({done_steps}/{total_steps})")

        if stats["samples"] > 0:
            stats["avg_score"] = sum_score / stats["samples"]
            stats["avg_return"] = sum_ret / stats["samples"]
            stats["avg_drawdown"] = sum_dd / stats["samples"]

        if best_params and cfg.get("auto_save_params", True):
            try:
                backtester.save_best_params(strategy, best_params)
                stats["best_params"] = best_params
            except Exception as e:
                exception("strategy_trainer.save_params_failed", e, {"strategy": strategy})

        report["strategies"][strat_code] = stats
        if not history_map:
            done_steps += 1
            _emit_progress(done_steps, total_steps, f"训练中: {strategy} ({done_steps}/{total_steps})")

    # auto update strategy pool from training results
    if cfg.get("auto_update_pool", True):
        try:
            from core.strategy_pool import update_pool_from_training
            pool_result = update_pool_from_training(report, cfg)
            report["strategy_pool"] = pool_result
        except Exception:
            report["strategy_pool"] = {}

    if cfg.get("auto_update_watchlist", False):
        try:
            from core.auto_watchlist import update_watchlist_from_pool
            pool_names = []
            if isinstance(report.get("strategy_pool", {}), dict):
                pool_payload = report.get("strategy_pool", {}).get("pool")
                if isinstance(pool_payload, dict):
                    rows = pool_payload.get("strategies", []) if isinstance(pool_payload.get("strategies", []), list) else []
                    for r in rows:
                        if isinstance(r, dict) and r.get("name"):
                            pool_names.append(str(r.get("name")).strip())
            wl_result = update_watchlist_from_pool(cfg=cfg, pool_names=pool_names or None)
            report["watchlist_update"] = wl_result
        except Exception:
            report["watchlist_update"] = {}

    if cfg.get("auto_update_strategy_pools", False):
        try:
            from core.auto_strategy_pools import update_strategy_pools
            pool_names = []
            if isinstance(report.get("strategy_pool", {}), dict):
                pool_payload = report.get("strategy_pool", {}).get("pool")
                if isinstance(pool_payload, dict):
                    rows = pool_payload.get("strategies", []) if isinstance(pool_payload.get("strategies", []), list) else []
                    for r in rows:
                        if isinstance(r, dict) and r.get("name"):
                            pool_names.append(str(r.get("name")).strip())
            sp_result = update_strategy_pools(cfg=cfg, pool_names=pool_names or None)
            report["strategy_pools_update"] = sp_result
        except Exception:
            report["strategy_pools_update"] = {}

    _emit_progress(total_steps, total_steps, "训练完成，正在保存报告...")
    _append_report(report)
    try:
        bus.log("strategy_training", payload=report, source="strategy_trainer")
    except Exception:
        pass
    return report


if __name__ == "__main__":
    print(run_training())
