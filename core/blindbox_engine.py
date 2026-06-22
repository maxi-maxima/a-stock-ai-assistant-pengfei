import datetime
import json
import os
import uuid

from core.blindbox_datafeed import calc_planned_exit_date, resolve_universe
from core.blindbox_evolution import apply_realized_reward
from core.blindbox_protocol import build_position_plan
from core.blindbox_strategies import (
    list_builtin_strategies,
    strategy_should_enter,
    weighted_pick_strategy,
)


STRATEGY_STATE_PATH = "data/blindbox_strategy_state.json"
POSITIONS_PATH = "data/blindbox_positions.json"
REPORT_PATH = "data/blindbox_daily_report.jsonl"
TRADE_LOG_PATH = "data/blindbox_trades.jsonl"
EVENT_BUS_PATH = "data/blindbox_event_bus.jsonl"
EXPERIENCE_LOG_PATH = "data/blindbox_experience_log.jsonl"


class JsonBlindboxStateStore:
    def __init__(self, strategies_path=STRATEGY_STATE_PATH, positions_path=POSITIONS_PATH):
        self.strategies_path = strategies_path
        self.positions_path = positions_path

    def load(self):
        strategies = []
        positions = []
        if os.path.exists(self.strategies_path):
            try:
                with open(self.strategies_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    strategies = data
            except Exception:
                strategies = []
        if os.path.exists(self.positions_path):
            try:
                with open(self.positions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    positions = data
            except Exception:
                positions = []
        return {"strategies": strategies, "positions": positions}

    def save(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        strategies = payload.get("strategies", [])
        positions = payload.get("positions", [])
        os.makedirs(os.path.dirname(self.strategies_path), exist_ok=True)
        with open(self.strategies_path, "w", encoding="utf-8") as f:
            json.dump(strategies, f, ensure_ascii=False, indent=2)
        with open(self.positions_path, "w", encoding="utf-8") as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)
        return payload


def _append_jsonl(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _to_rows(history):
    if history is None:
        return []
    if isinstance(history, list):
        return [row for row in history if isinstance(row, dict)]
    try:
        if hasattr(history, "to_dict"):
            return history.to_dict("records")
    except Exception:
        pass
    return []


def _get_history(scanner, code, days=120):
    if scanner is None:
        return []
    if hasattr(scanner, "get_history"):
        return _to_rows(scanner.get_history(code, days=days))
    data_skill = getattr(scanner, "data_skill", None)
    if data_skill is not None and hasattr(data_skill, "get_history"):
        return _to_rows(data_skill.get_history(code, days=days))
    return []


def _get_trade_price(scanner, code, trade_date):
    rows = _get_history(scanner, code, days=365)
    if not rows:
        return None
    trade_date = str(trade_date)
    for row in rows:
        if str(row.get("date")) == trade_date:
            try:
                return float(row.get("close"))
            except Exception:
                return None
    rows = sorted(rows, key=lambda x: str(x.get("date", "")))
    for row in reversed(rows):
        if str(row.get("date", "")) <= trade_date:
            try:
                return float(row.get("close"))
            except Exception:
                return None
    return None


def _estimate_shares(target_cash, buy_price, lot_size=100):
    try:
        target_cash = float(target_cash)
        buy_price = float(buy_price)
        lot_size = int(lot_size)
    except Exception:
        return 0
    if target_cash <= 0 or buy_price <= 0 or lot_size <= 0:
        return 0
    shares = int(target_cash // buy_price)
    shares = (shares // lot_size) * lot_size
    return max(0, shares)


def _normalize_strategies(existing=None, override=None):
    base = [dict(row) for row in list_builtin_strategies()]
    by_id = {row["strategy_id"]: row for row in base}
    for row in existing or []:
        if not isinstance(row, dict):
            continue
        strategy_id = str(row.get("strategy_id") or "").strip()
        if not strategy_id:
            continue
        merged = dict(by_id.get(strategy_id, {}))
        merged.update(row)
        by_id[strategy_id] = merged
    for row in override or []:
        if not isinstance(row, dict):
            continue
        strategy_id = str(row.get("strategy_id") or "").strip()
        if not strategy_id:
            continue
        merged = dict(by_id.get(strategy_id, {}))
        merged.update(row)
        by_id[strategy_id] = merged
    return list(by_id.values())


def _pick_entry_code(universe, scanner, strategy_row, trade_date, rng_seed=None):
    candidates = resolve_universe(universe or [])
    strategy_id = str(strategy_row.get("strategy_id") or "")
    for code in candidates:
        history = _get_history(scanner, code, days=120)
        if not history:
            continue
        if not strategy_should_enter(strategy_id, history, rng_seed=rng_seed):
            continue
        price = _get_trade_price(scanner, code, trade_date)
        if price is None:
            continue
        trading_days = [str(row.get("date")) for row in history if row.get("date")]
        return code, price, trading_days
    return None, None, []


def _get_day_bar(scanner, code, trade_date):
    history = _get_history(scanner, code, days=365)
    for row in history:
        if str(row.get("date")) == str(trade_date):
            return row
    return None


def _get_next_trade_date(current_date, trading_days):
    current_date = str(current_date)
    ordered = sorted(set([str(x) for x in (trading_days or []) if str(x)]))
    if current_date in ordered:
        idx = ordered.index(current_date)
        if idx + 1 < len(ordered):
            return ordered[idx + 1]
    return calc_planned_exit_date(current_date, hold_days=1, trading_days=ordered)


def _get_strategy_row(strategies, strategy_id):
    for row in strategies or []:
        if str(row.get("strategy_id")) == str(strategy_id):
            return row
    return {}


def run_blindbox_day(
    trade_date,
    universe=None,
    scanner=None,
    simulator=None,
    state_store=None,
    strategy_rows=None,
    rng_seed=None,
    apply=True,
    allow_new_positions=True,
    target_cash=10000.0,
    report_path=REPORT_PATH,
):
    from core.trade_simulator import PaperBroker
    from skills.scanner import MarketScanner

    scanner = scanner or MarketScanner("tushare")
    simulator = simulator or PaperBroker(
        portfolio_path="data/blindbox_paper_portfolio.json",
        trade_log_path=TRADE_LOG_PATH,
        event_bus_path=EVENT_BUS_PATH,
        experience_path=EXPERIENCE_LOG_PATH,
        log_learning=False,
        log_memory=False,
        update_registry=False,
    )
    state_store = state_store or JsonBlindboxStateStore()
    trade_date = str(trade_date)

    loaded = state_store.load() if state_store else {}
    strategies = _normalize_strategies(loaded.get("strategies"), override=strategy_rows)
    positions = [dict(row) for row in (loaded.get("positions") or []) if isinstance(row, dict)]
    open_positions = []

    report = {
        "ok": True,
        "trade_date": trade_date,
        "opened_count": 0,
        "closed_count": 0,
        "reward_updates": 0,
        "realized_pnl_sum": 0.0,
        "chosen_strategy_id": "",
        "selected_code": "",
        "errors": [],
    }

    for pos in positions:
        if str(pos.get("status") or "") != "pending_entry":
            continue
        planned_buy_date = str(pos.get("planned_buy_date") or "")
        if not planned_buy_date or planned_buy_date > trade_date:
            open_positions.append(pos)
            continue
        bar = _get_day_bar(scanner, pos.get("code"), trade_date)
        if not bar:
            report["errors"].append(f"missing_buy_bar:{pos.get('code')}")
            open_positions.append(pos)
            continue
        try:
            buy_price = float(bar.get("open"))
        except Exception:
            buy_price = None
        if buy_price is None:
            report["errors"].append(f"missing_buy_open:{pos.get('code')}")
            open_positions.append(pos)
            continue

        signal_source = {"source": "blindbox", "strategy": pos.get("strategy_id"), "label": "Blindbox"}
        ok, msg = simulator.buy(
            pos.get("code"),
            buy_price,
            target_cash=target_cash,
            reason="blindbox_entry",
            decision_id=pos.get("decision_id"),
            signal_source=signal_source,
        )
        if not ok:
            report["errors"].append(f"buy_failed:{pos.get('code')}:{msg}")
            open_positions.append(pos)
            continue
        report["opened_count"] += 1
        report["selected_code"] = pos.get("code")
        pos["status"] = "open"
        pos["buy_date"] = trade_date
        pos["buy_price"] = buy_price
        pos["shares"] = _estimate_shares(target_cash, buy_price)
        open_positions.append(pos)

        for idx, row in enumerate(strategies):
            if str(row.get("strategy_id")) == str(pos.get("strategy_id")):
                strategies[idx]["buys"] = int(strategies[idx].get("buys", 0) or 0) + 1
                break

    for pos in positions:
        if str(pos.get("status") or "open") != "open":
            continue
        strategy_row = _get_strategy_row(strategies, pos.get("strategy_id"))
        tp_pct = strategy_row.get("tp_pct")
        sl_pct = strategy_row.get("sl_pct")
        if tp_pct is not None and sl_pct is not None:
            bar = _get_day_bar(scanner, pos.get("code"), trade_date)
            if bar:
                buy_price = float(pos.get("buy_price") or 0)
                high_price = float(bar.get("high") or bar.get("close") or 0)
                low_price = float(bar.get("low") or bar.get("close") or 0)
                close_price = float(bar.get("close") or 0)
                stop_price = buy_price * (1 - float(sl_pct))
                take_price = buy_price * (1 + float(tp_pct))

                sell_price = None
                if low_price and buy_price and low_price <= stop_price:
                    sell_price = stop_price
                elif high_price and buy_price and high_price >= take_price:
                    sell_price = take_price
                else:
                    exit_date = str(pos.get("planned_exit_date") or "")
                    if exit_date and exit_date <= trade_date:
                        sell_price = close_price or _get_trade_price(scanner, pos.get("code"), trade_date)

                if sell_price is not None:
                    ok, msg = simulator.sell(
                        pos.get("code"),
                        sell_price,
                        shares=pos.get("shares"),
                        reason="blindbox_exit",
                        decision_id=pos.get("decision_id"),
                        signal_source={"source": "blindbox", "strategy": pos.get("strategy_id")},
                    )
                    if not ok:
                        report["errors"].append(f"sell_failed:{pos.get('code')}:{msg}")
                        open_positions.append(pos)
                        continue
                    try:
                        pnl_pct = (float(sell_price) - float(pos.get("buy_price"))) / float(pos.get("buy_price"))
                    except Exception:
                        pnl_pct = 0.0
                    try:
                        shares = int(pos.get("shares") or 0)
                    except Exception:
                        shares = 0
                    report["closed_count"] += 1
                    report["reward_updates"] += 1
                    report["realized_pnl_sum"] += (float(sell_price) - float(pos.get("buy_price") or 0)) * shares
                    for idx, row in enumerate(strategies):
                        if str(row.get("strategy_id")) == str(pos.get("strategy_id")):
                            strategies[idx] = apply_realized_reward(row, pnl_pct=pnl_pct)
                            break
                    continue

        exit_date = str(pos.get("planned_exit_date") or "")
        if exit_date and exit_date <= trade_date:
            sell_price = _get_trade_price(scanner, pos.get("code"), trade_date)
            if sell_price is None:
                report["errors"].append(f"missing_sell_price:{pos.get('code')}")
                open_positions.append(pos)
                continue
            ok, msg = simulator.sell(
                pos.get("code"),
                sell_price,
                shares=pos.get("shares"),
                reason="blindbox_exit",
                decision_id=pos.get("decision_id"),
                signal_source={"source": "blindbox", "strategy": pos.get("strategy_id")},
            )
            if not ok:
                report["errors"].append(f"sell_failed:{pos.get('code')}:{msg}")
                open_positions.append(pos)
                continue
            try:
                pnl_pct = (float(sell_price) - float(pos.get("buy_price"))) / float(pos.get("buy_price"))
            except Exception:
                pnl_pct = 0.0
            try:
                shares = int(pos.get("shares") or 0)
            except Exception:
                shares = 0
            report["closed_count"] += 1
            report["reward_updates"] += 1
            report["realized_pnl_sum"] += (float(sell_price) - float(pos.get("buy_price") or 0)) * shares
            for idx, row in enumerate(strategies):
                if str(row.get("strategy_id")) == str(pos.get("strategy_id")):
                    strategies[idx] = apply_realized_reward(row, pnl_pct=pnl_pct)
                    break
            continue
        open_positions.append(pos)

    if allow_new_positions:
        picked = weighted_pick_strategy(strategies, rng_seed=rng_seed)
        if picked:
            report["chosen_strategy_id"] = str(picked.get("strategy_id") or "")
            for idx, row in enumerate(strategies):
                if str(row.get("strategy_id")) == report["chosen_strategy_id"]:
                    strategies[idx]["calls"] = int(strategies[idx].get("calls", 0) or 0) + 1
                    break
            code, buy_price, trading_days = _pick_entry_code(
                universe=universe,
                scanner=scanner,
                strategy_row=picked,
                trade_date=trade_date,
                rng_seed=rng_seed,
            )
            if code and buy_price is not None:
                decision_id = f"blindbox_{trade_date.replace('-', '')}_{uuid.uuid4().hex[:8]}"
                signal_source = {"source": "blindbox", "strategy": picked.get("strategy_id"), "label": "Blindbox"}
                hold_days = int(picked.get("hold_days", 2) or 2)
                entry_mode = str(picked.get("entry_mode") or "close")
                if entry_mode == "next_open":
                    next_trade_date = _get_next_trade_date(trade_date, trading_days)
                    open_positions.append(
                        build_position_plan(
                            decision_id=decision_id,
                            code=code,
                            strategy_id=picked.get("strategy_id"),
                            buy_date="",
                            planned_exit_date=calc_planned_exit_date(next_trade_date, hold_days=hold_days, trading_days=trading_days),
                            hold_days=hold_days,
                            buy_price=None,
                            shares=None,
                            status="pending_entry",
                            signal_date=trade_date,
                            planned_buy_date=next_trade_date,
                        )
                    )
                else:
                    ok, msg = simulator.buy(
                        code,
                        buy_price,
                        target_cash=target_cash,
                        reason="blindbox_entry",
                        decision_id=decision_id,
                        signal_source=signal_source,
                    )
                    if ok:
                        report["opened_count"] += 1
                        report["selected_code"] = code
                        open_positions.append(
                            build_position_plan(
                                decision_id=decision_id,
                                code=code,
                                strategy_id=picked.get("strategy_id"),
                                buy_date=trade_date,
                                planned_exit_date=calc_planned_exit_date(trade_date, hold_days=hold_days, trading_days=trading_days),
                                hold_days=hold_days,
                                buy_price=buy_price,
                                shares=_estimate_shares(target_cash, buy_price),
                            )
                        )
                        for idx, row in enumerate(strategies):
                            if str(row.get("strategy_id")) == str(picked.get("strategy_id")):
                                strategies[idx]["buys"] = int(strategies[idx].get("buys", 0) or 0) + 1
                                break
                    else:
                        report["errors"].append(f"buy_failed:{code}:{msg}")

    payload = {"strategies": strategies, "positions": open_positions}
    if apply:
        state_store.save(payload)
        _append_jsonl(report_path, report)
    report["realized_pnl_sum"] = round(float(report["realized_pnl_sum"]), 6)
    if report["errors"]:
        report["ok"] = False
    return report
