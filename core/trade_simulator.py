import datetime
import os
import json
from core.portfolio import VirtualPortfolio
from core.learning_log import log_event
from core.memory import MemoryManager
from core.experience_store import ExperienceStore
from core.skill_registry import SkillRegistry
from core.event_bus import EventBus
from skills.data_factory import DataSkillFactory
from skills.risk_budget import max_drawdown, var_gaussian, risk_level_from_metrics


TRADE_LOG = "data/trades.jsonl"
COSTS_PATH = "config/trading_costs.json"


def _load_trading_costs():
    defaults = {
        "commission": 0.0003,
        "slippage": 0.0005,
        "stamp_duty": 0.001,
        "min_commission": 5.0,
        "lot_size": 100
    }
    data = {}
    if os.path.exists(COSTS_PATH):
        try:
            with open(COSTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

    out = dict(defaults)
    if data:
        for k in defaults.keys():
            if k in data:
                out[k] = data.get(k)

    env_map = {
        "commission": "TRADING_COMMISSION",
        "slippage": "TRADING_SLIPPAGE",
        "stamp_duty": "TRADING_STAMP_DUTY",
        "min_commission": "TRADING_MIN_COMMISSION",
        "lot_size": "TRADING_LOT_SIZE"
    }
    for key, env in env_map.items():
        val = os.getenv(env, "").strip()
        if val:
            out[key] = val

    try:
        out["commission"] = max(0.0, float(out.get("commission", 0.0) or 0.0))
    except Exception:
        out["commission"] = defaults["commission"]
    try:
        out["slippage"] = max(0.0, float(out.get("slippage", 0.0) or 0.0))
    except Exception:
        out["slippage"] = defaults["slippage"]
    try:
        out["stamp_duty"] = max(0.0, float(out.get("stamp_duty", 0.0) or 0.0))
    except Exception:
        out["stamp_duty"] = defaults["stamp_duty"]
    try:
        out["min_commission"] = max(0.0, float(out.get("min_commission", 0.0) or 0.0))
    except Exception:
        out["min_commission"] = defaults["min_commission"]
    try:
        out["lot_size"] = max(1, int(out.get("lot_size", 100) or 100))
    except Exception:
        out["lot_size"] = defaults["lot_size"]

    return out


def _write_trade(record):
    os.makedirs(os.path.dirname(TRADE_LOG), exist_ok=True)
    try:
        with open(TRADE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


class PaperBroker:
    def __init__(self, portfolio_path="data/paper_portfolio.json"):
        self.portfolio = VirtualPortfolio(portfolio_path)
        self._equity_curve = []
        self._rules_cache = None
        self._data_skill = None
        self._experience = ExperienceStore()
        self._registry = SkillRegistry()
        self._event_bus = EventBus()
        self._costs_cache = None

    def _ensure_decision(self, action, code, reason="", signal_source=None, features=None):
        """
        Ensure there is a decision_id for manual/implicit trades so outcomes can be linked.
        """
        payload = {
            "code": code,
            "action": action,
            "reason": reason,
            "signal_source": signal_source or {}
        }
        if isinstance(features, dict) and features:
            payload["features"] = features
        decision_id = self._experience.log_decision(payload)
        try:
            event_payload = dict(payload)
            if "suggested_action" not in event_payload:
                event_payload["suggested_action"] = action
            self._event_bus.log(
                "decision",
                payload=event_payload,
                code=code,
                decision_id=decision_id,
                source="paper_broker"
            )
        except Exception:
            pass
        return decision_id

    def _get_rules(self):
        try:
            return MemoryManager().get_rules()
        except Exception:
            return {}

    def _get_costs(self):
        if self._costs_cache is None:
            self._costs_cache = _load_trading_costs()
        return self._costs_cache

    def _calc_commission(self, turnover, rate, min_commission):
        try:
            turnover = float(turnover)
        except Exception:
            turnover = 0.0
        try:
            rate = float(rate)
        except Exception:
            rate = 0.0
        try:
            min_commission = float(min_commission)
        except Exception:
            min_commission = 0.0
        commission = turnover * rate if turnover > 0 else 0.0
        if min_commission and commission < min_commission:
            commission = min_commission
        return max(0.0, commission)

    def _get_constraints(self):
        rules = self._get_rules()
        if isinstance(rules, dict):
            cons = rules.get("constraints", {})
            if isinstance(cons, dict):
                return cons
        return {}

    def _get_data_skill(self):
        if self._data_skill is None:
            try:
                self._data_skill = DataSkillFactory.get_skill("tushare")
            except Exception:
                self._data_skill = None
        return self._data_skill

    def _infer_strategy(self, signal_source):
        if not isinstance(signal_source, dict):
            return None
        strat = signal_source.get("strategy")
        if isinstance(strat, str) and strat.strip():
            return strat.strip()
        strategies = signal_source.get("strategies")
        if isinstance(strategies, list):
            for s in strategies:
                if isinstance(s, str) and s.strip():
                    return s.strip()
        if isinstance(strategies, str) and strategies.strip():
            return strategies.strip()
        votes = signal_source.get("votes") or signal_source.get("strategy_votes")
        if isinstance(votes, list):
            best_name = None
            best_weight = None
            for v in votes:
                if not isinstance(v, dict):
                    continue
                name = v.get("strategy") or v.get("name")
                w = v.get("weight", 0)
                try:
                    w = float(w)
                except Exception:
                    w = 0.0
                if name and (best_weight is None or w > best_weight):
                    best_name = name
                    best_weight = w
            if best_name:
                return best_name
        return None

    def _count_trades_today(self):
        if not os.path.exists(TRADE_LOG):
            return 0
        today = datetime.datetime.now().date().isoformat()
        cnt = 0
        try:
            with open(TRADE_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip() or "{}")
                        ts = str(rec.get("ts", ""))
                        if ts.startswith(today):
                            cnt += 1
                    except Exception:
                        continue
        except Exception:
            return 0
        return cnt

    def _load_equity_curve(self, limit=2000):
        if not os.path.exists(TRADE_LOG):
            return []
        eq = []
        try:
            with open(TRADE_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip() or "{}")
                        if "equity" in rec:
                            eq.append(float(rec.get("equity") or 0))
                    except Exception:
                        continue
        except Exception:
            return []
        if len(eq) > limit:
            eq = eq[-limit:]
        return eq

    def _current_mdd(self):
        eq = self._equity_curve if self._equity_curve else self._load_equity_curve()
        if not eq:
            return 0.0
        try:
            return max_drawdown(eq)
        except Exception:
            return 0.0

    def _get_industry(self, code):
        skill = self._get_data_skill()
        if not skill:
            return "未知"
        try:
            info = skill.get_stock_basic_info(code)
            if isinstance(info, dict):
                return info.get("industry", "未知") or "未知"
        except Exception:
            pass
        return "未知"

    def _industry_value_map(self, price_map=None):
        price_map = price_map or {}
        by_ind = {}
        total = 0.0
        for code, info in self.portfolio.get_all_positions().items():
            if not isinstance(info, dict):
                continue
            vol = float(info.get("volume", 0) or 0)
            if vol <= 0:
                continue
            price = float(price_map.get(code, info.get("cost", 0) or 0))
            val = vol * price
            ind = self._get_industry(code)
            by_ind[ind] = by_ind.get(ind, 0.0) + val
            total += val
        return by_ind, total

    def _open_position_count(self):
        count = 0
        try:
            for _, info in self.portfolio.get_all_positions().items():
                if isinstance(info, dict) and float(info.get("volume", 0) or 0) > 0:
                    count += 1
        except Exception:
            pass
        return count

    def _today_realized_pnl(self):
        if not os.path.exists(TRADE_LOG):
            return 0.0
        today = datetime.datetime.now().date().isoformat()
        pnl = 0.0
        try:
            with open(TRADE_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("action") != "SELL":
                        continue
                    ts = str(rec.get("ts", ""))
                    if not ts.startswith(today):
                        continue
                    try:
                        pnl += float(rec.get("pnl", 0) or 0.0)
                    except Exception:
                        pass
        except Exception:
            return pnl
        return pnl

    def _today_loss_pct(self):
        finfo = self.portfolio.get_fund_info()
        principal = float(finfo.get("principal", 0) or 0)
        if principal <= 0:
            return 0.0
        pnl = self._today_realized_pnl()
        return pnl / principal

    def _apply_buy_constraints(self, code, price, shares, pct_chg=None):
        cons = self._get_constraints()
        if not cons:
            return shares, ""

        max_daily = cons.get("max_daily_trades")
        try:
            if max_daily and self._count_trades_today() >= int(max_daily):
                return 0, f"家规限制：日内交易次数≥{int(max_daily)}"
        except Exception:
            pass

        # daily loss limit (block new buys only)
        try:
            daily_loss = cons.get("daily_loss_pct", None)
            if daily_loss is not None:
                loss_pct = self._today_loss_pct()
                if loss_pct <= -float(daily_loss):
                    return 0, f"家规限制：日内亏损超限({loss_pct*100:.1f}%)"
        except Exception:
            pass

        # no chase
        try:
            allow_chase = bool(cons.get("allow_chase", True))
            if not allow_chase and pct_chg is not None:
                if float(pct_chg) >= 5:
                    return 0, "家规禁止追高"
        except Exception:
            pass

        # drawdown cap
        try:
            mdd_limit = cons.get("max_drawdown", None)
            if mdd_limit is not None:
                mdd = self._current_mdd()
                if mdd <= -float(mdd_limit):
                    return 0, f"家规限制：最大回撤超限({mdd*100:.1f}%)"
        except Exception:
            pass

        finfo = self.portfolio.get_fund_info()
        principal = float(finfo.get("principal", 0) or 0)
        if principal <= 0:
            return shares, ""

        try:
            lot = int(self._get_costs().get("lot_size", 100) or 100)
        except Exception:
            lot = 100
        note = ""

        # max single position
        try:
            max_single = cons.get("max_single_position", None)
            if max_single is not None:
                max_value = principal * float(max_single)
                pos = self.portfolio.get_specific_position(code) or {}
                curr_shares = float(pos.get("volume", 0) or 0)
                curr_val = curr_shares * price
                allowed_value = max_value - curr_val
                allowed_shares = int(allowed_value / price / lot) * lot if price > 0 else 0
                if allowed_shares <= 0:
                    return 0, f"家规限制：单票仓位上限 {float(max_single)*100:.0f}%"
                if allowed_shares < shares:
                    shares = allowed_shares
                    note = f"仓位上限限制为 {shares} 股"
        except Exception:
            pass

        # max open positions (skip if already holding the same code)
        try:
            max_open = cons.get("max_open_positions", None)
            if max_open is not None:
                pos = self.portfolio.get_specific_position(code) or {}
                has_pos = float(pos.get("volume", 0) or 0) > 0
                if not has_pos and self._open_position_count() >= int(max_open):
                    return 0, f"家规限制：持仓数量上限 {int(max_open)}"
        except Exception:
            pass

        # industry concentration
        try:
            max_ind = cons.get("max_industry_concentration", None)
            if max_ind is not None:
                ind = self._get_industry(code)
                by_ind, _ = self._industry_value_map(price_map={code: price})
                curr_ind_val = float(by_ind.get(ind, 0.0) or 0.0)
                max_ind_val = principal * float(max_ind)
                allowed_value = max_ind_val - curr_ind_val
                allowed_shares = int(allowed_value / price / lot) * lot if price > 0 else 0
                if allowed_shares <= 0:
                    return 0, f"家规限制：行业集中度上限 {float(max_ind)*100:.0f}%"
                if allowed_shares < shares:
                    shares = allowed_shares
                    note = f"{note}；行业集中度限制为 {shares} 股" if note else f"行业集中度限制为 {shares} 股"
        except Exception:
            pass

        return shares, note

    def _apply_sell_constraints(self):
        cons = self._get_constraints()
        if not cons:
            return True, ""
        max_daily = cons.get("max_daily_trades")
        try:
            if max_daily and self._count_trades_today() >= int(max_daily):
                return False, f"家规限制：日内交易次数≥{int(max_daily)}"
        except Exception:
            pass
        return True, ""

    def _can_trade(self, trade_allowed=True, pct_chg=None, action="BUY", pct_limit=9.8):
        if not trade_allowed:
            return False, "交易日或停牌限制"
        if pct_chg is None:
            return True, ""
        try:
            pct = float(pct_chg)
        except Exception:
            return True, ""
        if action == "BUY" and pct >= pct_limit:
            return False, "涨停限制，无法买入"
        if action == "SELL" and pct <= -pct_limit:
            return False, "跌停限制，无法卖出"
        return True, ""

    def buy(self, code, price, target_cash, pct_chg=None, trade_allowed=True, reason="", pct_limit=9.8, liquidity_cap=None, features=None, decision_id=None, signal_source=None):
        ok, msg = self._can_trade(trade_allowed, pct_chg, action="BUY", pct_limit=pct_limit)
        if not ok:
            return False, msg

        finfo = self.portfolio.get_fund_info()
        available = float(finfo.get("available", 0) or 0)
        cash = min(float(target_cash), available)
        if cash <= 0:
            return False, "可用资金不足"
        try:
            price = float(price)
        except Exception:
            return False, "价格无效"
        if price <= 0:
            return False, "价格无效"

        costs = self._get_costs()
        try:
            slippage = float(costs.get("slippage", 0) or 0)
        except Exception:
            slippage = 0.0
        try:
            commission_rate = float(costs.get("commission", 0) or 0)
        except Exception:
            commission_rate = 0.0
        try:
            min_commission = float(costs.get("min_commission", 0) or 0)
        except Exception:
            min_commission = 0.0
        try:
            lot = int(costs.get("lot_size", 100) or 100)
        except Exception:
            lot = 100

        exec_price = price * (1.0 + max(0.0, slippage))
        if exec_price <= 0:
            return False, "价格无效"

        shares = int(cash / exec_price / lot) * lot
        if shares <= 0:
            return False, "资金不足以买入一手"

        if liquidity_cap is not None:
            try:
                cap_shares = int(liquidity_cap)
                if cap_shares > 0:
                    shares = min(shares, cap_shares)
            except Exception:
                pass

        shares, note = self._apply_buy_constraints(code, exec_price, shares, pct_chg=pct_chg)
        if shares <= 0:
            return False, note or "家规限制"

        def _calc_buy_fees(shares_val):
            turnover = exec_price * shares_val
            commission = self._calc_commission(turnover, commission_rate, min_commission)
            total = turnover + commission
            return commission, total

        commission, total_cost = _calc_buy_fees(shares)
        while shares > 0 and total_cost > cash:
            shares -= lot
            if shares <= 0:
                break
            commission, total_cost = _calc_buy_fees(shares)
        if shares <= 0:
            return False, "资金不足(含手续费)"

        effective_price = exec_price
        if shares > 0 and commission > 0:
            effective_price = (exec_price * shares + commission) / shares

        pos = self.portfolio.get_specific_position(code) or {}
        meta_existing = pos.get("meta", {}) if isinstance(pos.get("meta"), dict) else {}
        meta = dict(meta_existing)
        if not decision_id:
            decision_id = self._ensure_decision("BUY", code, reason=reason, signal_source=signal_source, features=features)
        if decision_id:
            if not meta.get("origin_decision_id"):
                meta["origin_decision_id"] = decision_id
            meta["last_buy_decision_id"] = decision_id
            ids = meta.get("decision_ids", [])
            if isinstance(ids, list):
                if decision_id not in ids:
                    ids.append(decision_id)
                meta["decision_ids"] = ids
        if not isinstance(signal_source, dict):
            signal_source = {}
        if isinstance(signal_source, dict):
            if not meta.get("origin_strategy"):
                inferred = self._infer_strategy(signal_source)
                if inferred:
                    meta["origin_strategy"] = inferred
            if meta.get("origin_strategy") and not signal_source.get("strategy"):
                signal_source["strategy"] = meta.get("origin_strategy")
            if not signal_source.get("source"):
                signal_source["source"] = "manual"
            meta["last_signal_source"] = signal_source

        self.portfolio.add_position(code, shares, effective_price, meta=meta)
        # update equity curve
        finfo = self.portfolio.get_fund_info()
        equity = finfo.get("principal", 0)
        self._equity_curve.append(equity)
        record = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "action": "BUY",
            "code": code,
            "price": exec_price,
            "raw_price": price,
            "shares": shares,
            "reason": reason,
            "features": features or {},
            "commission": commission,
            "slippage_rate": slippage,
            "stamp_duty": 0.0,
            "fee_total": commission
        }
        if decision_id:
            record["decision_id"] = decision_id
        if isinstance(signal_source, dict):
            record["signal_source"] = signal_source
        # log equity after trade
        record["equity"] = equity
        _write_trade(record)
        log_event("paper_trade", record)
        try:
            self._experience.log_execution({
                "decision_id": decision_id,
                "code": code,
                "action": "BUY",
                "price": exec_price,
                "shares": shares,
                "reason": reason,
                "signal_source": signal_source,
                "commission": commission,
                "slippage_rate": slippage,
                "fee_total": commission
            })
        except Exception:
            pass
        try:
            self._event_bus.log(
                "execution",
                payload={
                    "action": "BUY",
                    "price": exec_price,
                    "shares": shares,
                    "reason": reason,
                    "signal_source": signal_source,
                    "features": features or {},
                    "equity": equity,
                    "commission": commission,
                    "slippage_rate": slippage,
                    "fee_total": commission
                },
                code=code,
                decision_id=decision_id,
                source="paper_broker"
            )
        except Exception:
            pass
        try:
            MemoryManager().save_episode(
                code,
                "BUY",
                exec_price,
                {
                    "decision_id": decision_id,
                    "reason": reason,
                    "shares": shares,
                    "signal_source": signal_source,
                    "features": features or {},
                    "equity": equity,
                    "execution": "paper_broker",
                    "commission": commission,
                    "slippage_rate": slippage,
                    "fee_total": commission,
                    "raw_price": price
                },
                manual_teach=False
            )
        except Exception:
            pass
        msg = f"买入 {shares} 股"
        if note:
            msg = f"{msg} ({note})"
        return True, msg

    def sell(self, code, price, shares=None, pct_chg=None, trade_allowed=True, reason="", pct_limit=9.8, features=None, decision_id=None, signal_source=None):
        ok_limit, msg_limit = self._apply_sell_constraints()
        if not ok_limit:
            return False, msg_limit
        ok, msg = self._can_trade(trade_allowed, pct_chg, action="SELL", pct_limit=pct_limit)
        if not ok:
            return False, msg

        pos = self.portfolio.get_specific_position(code)
        if not pos or pos.get("volume", 0) <= 0:
            return False, "无持仓"
        try:
            price = float(price)
        except Exception:
            price = float(pos.get("cost", 0) or 0)
        if price <= 0:
            return False, "价格无效"

        total = int(pos.get("volume", 0))
        if shares is None or shares <= 0:
            shares = total
        if shares > total:
            shares = total

        cost = float(pos.get("cost", 0) or 0)
        costs = self._get_costs()
        try:
            slippage = float(costs.get("slippage", 0) or 0)
        except Exception:
            slippage = 0.0
        try:
            commission_rate = float(costs.get("commission", 0) or 0)
        except Exception:
            commission_rate = 0.0
        try:
            stamp_duty_rate = float(costs.get("stamp_duty", 0) or 0)
        except Exception:
            stamp_duty_rate = 0.0
        try:
            min_commission = float(costs.get("min_commission", 0) or 0)
        except Exception:
            min_commission = 0.0

        exec_price = price * (1.0 - max(0.0, slippage))
        if exec_price <= 0:
            return False, "价格无效"
        meta_existing = pos.get("meta", {}) if isinstance(pos.get("meta"), dict) else {}
        origin_decision_id = meta_existing.get("origin_decision_id")
        origin_strategy = meta_existing.get("origin_strategy")
        if not decision_id:
            if origin_decision_id:
                decision_id = origin_decision_id
            else:
                last_buy = meta_existing.get("last_buy_decision_id")
                if last_buy:
                    decision_id = last_buy
                else:
                    ids = meta_existing.get("decision_ids", [])
                    if isinstance(ids, list) and ids:
                        decision_id = ids[-1]
        if not decision_id:
            decision_id = self._ensure_decision("SELL", code, reason=reason, signal_source=signal_source, features=features)
        if not origin_decision_id and decision_id:
            origin_decision_id = decision_id
        if not isinstance(signal_source, dict):
            if isinstance(meta_existing.get("last_signal_source"), dict):
                signal_source = dict(meta_existing.get("last_signal_source"))
            else:
                signal_source = {}
        if isinstance(signal_source, dict):
            if origin_strategy and not signal_source.get("strategy"):
                signal_source["strategy"] = origin_strategy
            if not signal_source.get("source"):
                signal_source["source"] = "manual"
        turnover = exec_price * shares
        commission = self._calc_commission(turnover, commission_rate, min_commission)
        stamp_duty = turnover * max(0.0, stamp_duty_rate)
        fee_total = commission + stamp_duty
        effective_price = exec_price
        if shares > 0 and fee_total > 0:
            effective_price = exec_price - (fee_total / shares)

        pnl = (exec_price - cost) * shares - fee_total
        self.portfolio.sell_position(code, shares, effective_price)
        finfo = self.portfolio.get_fund_info()
        equity = finfo.get("principal", 0)
        self._equity_curve.append(equity)

        record = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "action": "SELL",
            "code": code,
            "price": exec_price,
            "raw_price": price,
            "shares": shares,
            "pnl": pnl,
            "reason": reason,
            "features": features or {},
            "commission": commission,
            "stamp_duty": stamp_duty,
            "slippage_rate": slippage,
            "fee_total": fee_total
        }
        if decision_id:
            record["decision_id"] = decision_id
        if origin_decision_id:
            record["origin_decision_id"] = origin_decision_id
        if isinstance(signal_source, dict):
            record["signal_source"] = signal_source
        record["equity"] = equity
        _write_trade(record)
        log_event("paper_trade", record)
        pnl_pct = None
        try:
            denom = cost * shares
            pnl_pct = (pnl / denom) if denom else None
        except Exception:
            pnl_pct = None
        try:
            if origin_strategy and pnl_pct is not None:
                self._registry.update_performance(origin_strategy, pnl_pct)
        except Exception:
            pass
        try:
            self._experience.log_outcome(origin_decision_id or decision_id, {
                "code": code,
                "action": "SELL",
                "price": exec_price,
                "shares": shares,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "origin_decision_id": origin_decision_id,
                "signal_source": signal_source,
                "commission": commission,
                "stamp_duty": stamp_duty,
                "slippage_rate": slippage,
                "fee_total": fee_total,
                "raw_price": price
            })
        except Exception:
            pass
        try:
            self._event_bus.log(
                "execution",
                payload={
                    "action": "SELL",
                    "price": exec_price,
                    "shares": shares,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "reason": reason,
                    "origin_decision_id": origin_decision_id,
                    "signal_source": signal_source,
                    "features": features or {},
                    "equity": equity,
                    "commission": commission,
                    "stamp_duty": stamp_duty,
                    "slippage_rate": slippage,
                    "fee_total": fee_total,
                    "raw_price": price
                },
                code=code,
                decision_id=decision_id or origin_decision_id,
                source="paper_broker"
            )
        except Exception:
            pass
        try:
            self._event_bus.log(
                "outcome",
                payload={
                    "action": "SELL",
                    "price": exec_price,
                    "shares": shares,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "origin_decision_id": origin_decision_id,
                    "signal_source": signal_source,
                    "commission": commission,
                    "stamp_duty": stamp_duty,
                    "slippage_rate": slippage,
                    "fee_total": fee_total,
                    "raw_price": price
                },
                code=code,
                decision_id=origin_decision_id or decision_id,
                source="paper_broker"
            )
        except Exception:
            pass
        try:
            MemoryManager().save_episode(
                code,
                "SELL",
                exec_price,
                {
                    "decision_id": decision_id,
                    "origin_decision_id": origin_decision_id,
                    "reason": reason,
                    "shares": shares,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "signal_source": signal_source,
                    "features": features or {},
                    "equity": equity,
                    "execution": "paper_broker",
                    "commission": commission,
                    "stamp_duty": stamp_duty,
                    "slippage_rate": slippage,
                    "fee_total": fee_total,
                    "raw_price": price
                },
                manual_teach=False
            )
        except Exception:
            pass

        # adaptive learning hooks (after outcome logging)
        try:
            if os.getenv("AUTO_BIAS_UPDATE", "1") == "1":
                from core.experience_feedback import update_bias
                update_bias()
        except Exception:
            pass
        try:
            from core.threshold_adaptor import maybe_update_overrides
            maybe_update_overrides()
        except Exception:
            pass

        # risk budget metrics
        mdd = max_drawdown(self._equity_curve)
        if len(self._equity_curve) >= 2:
            rets = []
            for i in range(1, len(self._equity_curve)):
                prev = self._equity_curve[i-1]
                curr = self._equity_curve[i]
                if prev > 0:
                    rets.append((curr - prev) / prev)
            var = var_gaussian(rets, alpha=0.95)
        else:
            var = 0.0
        level = risk_level_from_metrics(mdd, var)
        log_event("risk_budget", {"mdd": mdd, "var": var, "level": level})

        return True, f"卖出 {shares} 股，盈亏 {pnl:.0f}"
