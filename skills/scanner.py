import pandas as pd
import numpy as np
import json
import os
import importlib.util
import math
from core.financial_analysis import extract_metrics, score_financial
from skills.data_factory import DataSkillFactory
from core.skill_registry import SkillRegistry
from core.ta_utils import resolve_ma_periods, ma_series, add_ma_columns, add_vol_ma_columns, rsi_dynamic_thresholds # 🔥 引入评价系统

class MarketScanner:
    def __init__(self, source="tushare"):
        self.data_skill = DataSkillFactory.get_skill(source)
        self.profile_path = "config/style_profile.json"
        self.registry = SkillRegistry() # 🔥 初始化
        self.financial_threshold = 70

    def get_candidate_pool(self, mode="watchlist", limit=200):
        if mode == "global":
            return self.data_skill.get_all_stocks()[:limit]
        else:
            wl = self._load_watchlist()
            if wl:
                return wl[:limit]
            return [
                {"code": "600519.SH", "name": "贵州茅台"},
                {"code": "300750.SZ", "name": "宁德时代"},
                {"code": "002594.SZ", "name": "比亚迪"},
                {"code": "000001.SZ", "name": "平安银行"},
                {"code": "601138.SH", "name": "工业富联"}
            ]

    def _load_dna_profile(self):
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, 'r') as f: return json.load(f)
            except: pass
        return {"rsi": 45, "bias_20": 0.05, "vol_ratio": 1.5, "amplitude": 0.03}

    def _load_strategy_policy(self):
        path = "config/strategy_policy.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {
            "min_reward_count": 5,
            "min_calls": 5,
            "min_mean_reward": -0.02,
            "disable_below": -0.08,
            "penalty_weight": 0.3
        }

    def _load_strategy_governor(self):
        path = "data/strategy_governor.json"
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data.get("strategies", {}) if isinstance(data.get("strategies", {}), dict) else {}
        except Exception:
            return {}
        return {}

    def _load_watchlist(self):
        path = "data/watchlist.json"
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        if isinstance(data, dict) and "codes" in data:
            data = data.get("codes", [])

        out = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    code = item.get("code") or item.get("ts_code") or item.get("symbol")
                    name = item.get("name") or code
                    if code:
                        out.append({"code": code, "name": name})
                elif isinstance(item, str):
                    out.append({"code": item, "name": item})
        return out

    def _load_user_strategies(self):
        strategies = {}
        strat_dir = "skills/strategies"
        if not os.path.exists(strat_dir): return {}
        
        for file in os.listdir(strat_dir):
            if file.endswith(".py") and not file.startswith("__"):
                name = file.replace(".py", "")
                path = os.path.join(strat_dir, file)
                try:
                    spec = importlib.util.spec_from_file_location(name, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, 'check'):
                        strategies[name] = module.check
                except: pass
        return strategies

    def technical_filter(self, pool, mode="hot_money"):
        candidates = []
        logs = []
        clean_mode = mode.split(" (")[0] if isinstance(mode, str) else str(mode)
        periods = resolve_ma_periods()
        p_short1 = periods.get('short1', 5)
        p_short2 = periods.get('short2', 10)
        p_mid1 = periods.get('mid1', 20)
        
        # 1. 预加载资源
        dna_profile = {}
        if mode == "dna":
            dna_profile = self._load_dna_profile()
            logs.append(f"🧬 加载风格 DNA: RSI偏好 {dna_profile.get('rsi')}")
        
        user_strategies = self._load_user_strategies()

        for i, stock in enumerate(pool):
            code = stock['code']
            name = stock.get('name', code)
            
            # 获取数据
            df = self.data_skill.get_history(code, days=100)
            if df.empty or len(df) < 30: continue
                
            curr = df.iloc[-1]
            ma_s1 = ma_series(df['close'], p_short1).iloc[-1]
            ma_m1 = ma_series(df['close'], p_mid1).iloc[-1]
            vol_ma_s1 = ma_series(df['vol'], p_short1).iloc[-1]
            # 通用指标
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi_val = 100 - (100 / (1 + gain/loss))
            curr_rsi = rsi_val.iloc[-1]
            trend_flag = 1 if curr['close'] > ma_m1 else 0
            vol_ratio = curr['vol'] / vol_ma_s1 if vol_ma_s1 > 0 else 0
            
            is_hit = False
            reason = ""
            fin_score = None
            
            # --- 内置策略 ---
            if mode == "hot_money":
                recent = df.iloc[-15:-1]
                has_zt = (recent['pct_chg'] > 9.5).any()
                is_active = (curr['vol'] > vol_ma_s1) and (curr['pct_chg'] > 3.0)
                if has_zt and is_active and curr['close'] > ma_m1:
                    is_hit = True; reason = "游资回马枪"

            elif mode == "dna":
                # DNA 完整逻辑
                curr_bias = (curr['close'] - ma_m1) / ma_m1
                curr_vol_ratio = vol_ratio
                curr_amp = (curr['high'] - curr['low']) / curr['close'] if curr['close'] else 0
                target_rsi = dna_profile.get('rsi', 50)
                target_bias = dna_profile.get('bias_20', 0)
                target_vol = dna_profile.get('vol_ratio', 1)
                target_amp = dna_profile.get('amplitude', 0.03)
                
                if (abs(curr_rsi - target_rsi) < 15) and (abs(curr_bias - target_bias) < 0.1) and (curr_vol_ratio > target_vol * 0.8) and (abs(curr_amp - target_amp) < 0.05):
                    is_hit = True; reason = f"符合 DNA (RSI:{curr_rsi:.1f})"

            elif mode == "oversold":
                dyn = rsi_dynamic_thresholds(df)
                lower = dyn.get("lower", 30)
                regime = dyn.get("regime", "")
                if curr_rsi < lower:
                    is_hit = True; reason = f"极度超跌 (RSI={curr_rsi:.1f}, {regime}:{lower})"

            elif mode == "standard":
                if curr['close'] > ma_m1 and curr['vol'] > vol_ma_s1 * 1.5:
                    is_hit = True; reason = "???? EMA??"

            elif mode == "tail_strength":
                if len(df) < 60:
                    continue
                if "ST" in name:
                    continue
                code_prefix = str(code).split(".")[0]
                if not code_prefix.startswith(("00", "30", "60")):
                    continue
                ma10 = ma_series(df['close'], p_short2).iloc[-1]
                ret_5 = (curr['close'] / df['close'].iloc[-6] - 1) if len(df) >= 6 else 0
                ret_10 = (curr['close'] / df['close'].iloc[-11] - 1) if len(df) >= 11 else 0
                ret_20 = (curr['close'] / df['close'].iloc[-21] - 1) if len(df) >= 21 else 0
                low_20 = df['low'].iloc[-20:].min()
                high_20 = df['high'].iloc[-20:].max()
                pos_20 = (curr['close'] - low_20) / (high_20 - low_20) if high_20 > low_20 else 0
                low_60 = df['low'].iloc[-60:].min()
                high_60 = df['high'].iloc[-60:].max()
                pos_60 = (curr['close'] - low_60) / (high_60 - low_60) if high_60 > low_60 else 0
                close_pos_day = (curr['close'] - curr['low']) / (curr['high'] - curr['low']) if curr['high'] > curr['low'] else 0
                vol_ref = df['vol'].iloc[-(p_mid1+1):-1].mean() if len(df) >= (p_mid1 + 1) else ma_series(df['vol'], p_mid1).iloc[-1]
                vol_ratio_20 = curr['vol'] / vol_ref if vol_ref and vol_ref > 0 else 0

                hard = (
                    curr['pct_chg'] > 0
                    and curr['close'] >= ma_s1
                    and curr['close'] >= ma10
                    and close_pos_day >= 0.7
                    and ret_5 > 0
                    and ret_10 > 0
                )

                score = 0
                if ret_20 >= -0.02: score += 1
                if pos_20 >= 0.60: score += 1
                if 0.30 <= pos_60 <= 0.80: score += 1
                if 0.8 <= vol_ratio_20 <= 2.0: score += 1
                if curr['close'] >= ma_m1: score += 1

                if hard and score >= 3:
                    is_hit = True
                    reason = f"尾盘强势: 动量{ret_5*100:.1f}%/{ret_10*100:.1f}%, 收盘靠高位{close_pos_day:.2f}, 评分{score}"
            
            # --- 用户自定义策略 ---
            elif clean_mode in user_strategies or mode.startswith("user_"):
                strat_func = user_strategies.get(clean_mode)
                if strat_func:
                    try:
                        df_user = df.copy()
                        if "close" in df_user.columns:
                            df_user = add_ma_columns(df_user, periods.get('all', []))
                            df_user = add_vol_ma_columns(df_user, [p_short1])
                        try:
                            df_user.attrs["ts_code"] = code
                            df_user.attrs["name"] = name
                        except Exception:
                            pass
                        is_hit, reason = strat_func(df_user)
                    except: pass

            # 财务评分因子（非阻断）
            try:
                if mode == "financial_strong":
                    df_inc = self.data_skill.financial.get_income_statement(code)
                    if isinstance(df_inc, tuple):
                        df_inc = df_inc[0]
                    df_bs = self.data_skill.financial.get_balance_sheet(code)
                    if isinstance(df_bs, tuple):
                        df_bs = df_bs[0]
                    df_cf = self.data_skill.financial.get_cashflow(code)
                    if isinstance(df_cf, tuple):
                        df_cf = df_cf[0]
                    if df_inc is not None and not df_inc.empty:
                        metrics = extract_metrics(code, df_inc, df_bs, df_cf)
                        score, grade, _ = score_financial(metrics)
                        fin_score = score
                        if score >= self.financial_threshold:
                            is_hit = True
                            reason = f"财务评分强势({score:.0f}/{grade})"
            except Exception:
                pass
            
            if is_hit:
                payload = {
                    "code": code, "name": name, "reason": reason,
                    "price": curr['close'], "pct": curr['pct_chg'],
                    "ma_mid": float(ma_m1), "vol_ratio": float(vol_ratio),
                    "rsi": float(curr_rsi), "trend": int(trend_flag),
                    "fin_score": float(fin_score) if fin_score is not None else None,
                    "strategy": clean_mode
                }
                payload[f"ma{p_mid1}"] = float(ma_m1)
                candidates.append(payload)
                logs.append(f"✅ {name}: {reason}")
            
        # 🔥 核心：如果扫描到了，就给这个策略记一功
        clean_name = clean_mode
        params = None
        if mode == "financial_strong":
            params = {"fin_threshold": getattr(self, "financial_threshold", None)}
        elif clean_name in user_strategies:
            try:
                from skills.strategies.strategy_params import get_params
                params = get_params(clean_name)
            except Exception:
                params = None
        self.registry.register_usage(clean_name, len(candidates), params=params, calls=1)

        return candidates, logs

    def get_strategy_list(self):
        base = [
            "HotMoney (游资回马枪)",
            "DNA (风格克隆)",
            "Oversold (超跌反弹)",
            "Standard (放量突破)",
            "TailStrength (尾盘强势)",
            "FinancialStrong (财务强势)"
        ]
        user_strats = self._load_user_strategies()
        for name in user_strats.keys():
            base.append(f"{name} (自定义)")
        return base

    def get_preferred_strategy(self, default="hot_money"):
        try:
            weights = self.get_strategy_weights()
            if weights:
                name = max(weights.items(), key=lambda x: x[1])[0]
                return name if name else default
        except Exception:
            pass
        return default

    def get_strategy_weights(self):
        """
        Build a weight map based on historical performance.
        """
        weights = {}
        try:
            governor = self._load_strategy_governor()
            df = self.registry.get_leaderboard()
            if df is None or df.empty or "name" not in df.columns:
                return weights
            try:
                total_calls_all = int(df["total_calls"].sum())
            except Exception:
                total_calls_all = 0
            if total_calls_all <= 0:
                total_calls_all = 1
            try:
                ucb_c = float(os.getenv("STRATEGY_UCB_C", "1.5"))
            except Exception:
                ucb_c = 1.5
            try:
                half_life = float(os.getenv("STRATEGY_DECAY_HALF_LIFE_DAYS", "30"))
            except Exception:
                half_life = 30.0
            policy = self._load_strategy_policy()
            try:
                min_reward_count = int(policy.get("min_reward_count", 5))
            except Exception:
                min_reward_count = 5
            try:
                min_calls = int(policy.get("min_calls", 5))
            except Exception:
                min_calls = 5
            try:
                min_mean_reward = float(policy.get("min_mean_reward", -0.02))
            except Exception:
                min_mean_reward = -0.02
            try:
                disable_below = float(policy.get("disable_below", -0.08))
            except Exception:
                disable_below = -0.08
            try:
                penalty_weight = float(policy.get("penalty_weight", 0.3))
            except Exception:
                penalty_weight = 0.3
            for _, row in df.iterrows():
                name = str(row.get("name", "")).strip()
                if not name:
                    continue
                g = governor.get(name, {}) if isinstance(governor, dict) else {}
                g_status = str(g.get("status", "")).lower()
                if g_status == "disabled":
                    continue
                try:
                    avg_ret = float(row.get("avg_return", 0) or 0)
                except Exception:
                    avg_ret = 0.0
                try:
                    calls = int(row.get("total_calls", 0) or 0)
                except Exception:
                    calls = 0
                try:
                    reward_sum = float(row.get("reward_sum", 0) or 0)
                except Exception:
                    reward_sum = 0.0
                try:
                    reward_count = int(row.get("reward_count", 0) or 0)
                except Exception:
                    reward_count = 0
                # decay factor based on last reward timestamp
                decay = 1.0
                try:
                    last_ts = row.get("last_reward_ts") or row.get("last_used")
                    if last_ts:
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(str(last_ts)[:19])
                            age_days = max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)
                            if half_life > 0:
                                decay = math.exp(-age_days / half_life)
                        except Exception:
                            decay = 1.0
                except Exception:
                    decay = 1.0

                mean_reward = (reward_sum / reward_count) if reward_count > 0 else avg_ret
                mean_reward *= decay
                # clamp to reduce outliers
                mean_reward = max(-0.2, min(0.2, mean_reward))

                # policy gate: penalize or disable weak strategies after enough samples
                sample_ok = (reward_count >= min_reward_count) or (calls >= min_calls)
                weight_scale = 1.0
                if sample_ok:
                    if mean_reward <= disable_below:
                        continue
                    if mean_reward <= min_mean_reward:
                        weight_scale = max(0.0, min(1.0, penalty_weight))

                # UCB score
                ucb = mean_reward + ucb_c * math.sqrt(math.log(total_calls_all + 1) / (calls + 1))
                w = 1.0 + ucb * 5.0
                w = w * max(0.05, min(1.0, weight_scale))
                if g_status == "watch":
                    w *= 0.6
                elif g_status == "seed":
                    w *= 0.8
                if w <= 0:
                    continue
                weights[name] = round(max(0.2, min(5.0, w)), 2)
        except Exception:
            return weights
        return weights

    def get_top_strategies(self, k=3):
        try:
            from core.strategy_pool import get_pool_names
            pool_names = get_pool_names(limit=int(k) if k else None)
        except Exception:
            pool_names = []
        if pool_names:
            return pool_names

        weights = self.get_strategy_weights()
        if not weights:
            return [self.get_preferred_strategy("hot_money")]
        ordered = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        ordered = [(n, w) for n, w in ordered if w and w > 0]
        names = [n for n, _ in ordered[: max(1, int(k))]]
        return names

    def fusion_scan(self, pool, top_k=3, strategies=None):
        """
        Run multiple strategies and merge candidates by weighted voting.
        """
        weights = self.get_strategy_weights()
        if strategies is None:
            strategies = self.get_top_strategies(top_k)
        merged = {}
        logs = []
        for strat in strategies:
            candidates, c_logs = self.technical_filter(pool, mode=strat)
            logs.extend(c_logs)
            w = float(weights.get(strat, 1.0) or 1.0)
            for c in candidates:
                code = c.get("code")
                if not code:
                    continue
                entry = merged.get(code)
                if entry is None:
                    entry = dict(c)
                    entry["strategy_votes"] = []
                    entry["strategy_score"] = 0.0
                entry["strategy_votes"].append({"strategy": strat, "weight": w, "reason": c.get("reason")})
                entry["strategy_score"] = float(entry.get("strategy_score", 0) or 0) + w
                merged[code] = entry
        # finalize ranking
        for entry in merged.values():
            votes = entry.get("strategy_votes", [])
            if isinstance(votes, list) and votes:
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
                    entry["strategy"] = best_name
        out = list(merged.values())
        out.sort(key=lambda x: (x.get("strategy_score", 0), x.get("fin_score") or 0), reverse=True)
        return out, logs
