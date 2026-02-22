import json
import os
import inspect

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from skills.scanner import MarketScanner
from skills.risk_budget import var_gaussian, risk_level_from_metrics
from core.ta_utils import resolve_ma_periods, ma_series, add_ma_columns, add_vol_ma_columns, adx, rsi_dynamic_thresholds


class Backtester:
    def __init__(self):
        self.scanner = MarketScanner()
        self.initial_capital = 100000.0
        self.profile_path = "config/style_profile.json"
        self.param_path = "config/backtest_params.json"
        self._last_data_quality = {}
        self._costs_cache = None

    def _load_dna_profile(self):
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    prof = json.load(f)
                    if isinstance(prof, dict):
                        return prof
            except Exception:
                pass
        return {"rsi": 50, "bias_20": 0.0, "vol_ratio": 1.0, "amplitude": 0.03}

    def _get_strategy_code(self, strategy_name):
        if "HotMoney" in strategy_name:
            return "hot_money"
        if "Oversold" in strategy_name:
            return "oversold"
        if "DNA" in strategy_name:
            return "dna"
        if "TailStrength" in strategy_name or "尾盘强势" in strategy_name:
            return "tail_strength"
        if "Custom" in strategy_name or "(" in strategy_name:
            return strategy_name.split(" (")[0]
        return "standard"

    def _load_param_cache(self):
        if os.path.exists(self.param_path):
            try:
                with open(self.param_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}

    def _load_trading_costs(self):
        if self._costs_cache is not None:
            return self._costs_cache
        defaults = {
            "commission": 0.0003,
            "slippage": 0.0005,
            "stamp_duty": 0.001,
            "lot_size": 100
        }
        data = {}
        path = "config/trading_costs.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
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
            out["lot_size"] = max(1, int(out.get("lot_size", 100) or 100))
        except Exception:
            out["lot_size"] = defaults["lot_size"]

        self._costs_cache = out
        return out

    def _resolve_costs(self, commission, slippage, stamp_duty, lot_size):
        costs = self._load_trading_costs()
        if commission is None:
            commission = costs.get("commission")
        if slippage is None:
            slippage = costs.get("slippage")
        if stamp_duty is None:
            stamp_duty = costs.get("stamp_duty")
        if lot_size is None:
            lot_size = costs.get("lot_size")
        return commission, slippage, stamp_duty, lot_size

    def get_saved_params(self, strategy_name):
        cache = self._load_param_cache()
        key = self._get_strategy_code(strategy_name)
        return cache.get(key, {})

    def save_best_params(self, strategy_name, params):
        cache = self._load_param_cache()
        key = self._get_strategy_code(strategy_name)
        data = {
            "tp": float(params.get("tp", 0) or 0),
            "sl": float(params.get("sl", 0) or 0),
            "days": int(params.get("days", 0) or 0),
            "updated_at": pd.Timestamp.now().isoformat()
        }
        cache[key] = data
        try:
            os.makedirs(os.path.dirname(self.param_path), exist_ok=True)
            with open(self.param_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def collect_system_params(self, code):
        ctx = {"code": code, "ts": pd.Timestamp.now().isoformat()}
        try:
            data_master = self.scanner.data_skill
        except Exception:
            data_master = None

        if data_master:
            try:
                ctx["full_pack"] = data_master.get_full_analysis_pack(code)
            except Exception:
                ctx["full_pack"] = {}
            try:
                ctx["feature_pack"] = data_master.get_feature_pack(code)
            except Exception:
                ctx["feature_pack"] = {}
            try:
                ctx["reference_pack"] = data_master.get_reference_pack(code)
            except Exception:
                ctx["reference_pack"] = {}
            try:
                ctx["macro_pack"] = data_master.get_macro_pack()
            except Exception:
                ctx["macro_pack"] = {}

        ctx["style_profile"] = self._load_dna_profile()
        full = ctx.get("full_pack", {}) if isinstance(ctx.get("full_pack", {}), dict) else {}
        ctx["factor_snapshot"] = {
            "tech_factors": full.get("tech_factors", {}),
            "capital_data": full.get("money_flow", {}),
            "chip_data": full.get("chip_perf", {}),
            "fundamental": full.get("valuation", {})
        }
        return ctx

    def normalize_equity_curve(self, eq_df, base=None):
        if eq_df is None or eq_df.empty:
            return pd.DataFrame()
        out = eq_df[["date", "equity"]].copy()
        try:
            base_val = float(base) if base is not None else float(out["equity"].iloc[0] or 1.0)
        except Exception:
            base_val = 1.0
        if base_val == 0:
            base_val = 1.0
        out["equity"] = out["equity"].astype(float) / base_val
        return out

    def combine_equity_curves(self, curves, weights=None, base_value=1.0):
        if not curves:
            return pd.DataFrame()
        merged = None
        idx = 0
        weight_list = []
        use_weights = weights if weights else []
        for c in curves:
            if c is None or c.empty:
                continue
            tmp = c[["date", "equity"]].copy()
            tmp = tmp.rename(columns={"equity": f"eq_{idx}"})
            tmp = tmp.set_index("date")
            if merged is None:
                merged = tmp
            else:
                merged = merged.join(tmp, how="outer")
            if use_weights and idx < len(use_weights):
                try:
                    weight_list.append(float(use_weights[idx]))
                except Exception:
                    weight_list.append(1.0)
            else:
                weight_list.append(1.0)
            idx += 1
        if merged is None:
            return pd.DataFrame()
        merged = merged.sort_index().ffill()
        merged = merged.fillna(float(base_value))
        cols = [f"eq_{i}" for i in range(len(weight_list))]
        if weight_list and len(cols) == len(weight_list):
            w = np.array(weight_list, dtype=float)
            w_sum = float(w.sum())
            if w_sum == 0:
                merged["equity"] = merged[cols].mean(axis=1)
            else:
                merged["equity"] = (merged[cols] * w).sum(axis=1) / w_sum
        else:
            merged["equity"] = merged.mean(axis=1)
        return merged[["equity"]].reset_index()

    def _align_context_history(self, context, df):
        if context is None or df is None or df.empty:
            return context
        if not isinstance(context, dict):
            return context
        try:
            full = context.get("full_pack", {})
            if not isinstance(full, dict):
                return context
            hist = full.get("history")
            if isinstance(hist, pd.DataFrame) and "date" in hist.columns and "date" in df.columns:
                last_date = df["date"].iloc[-1]
                full = dict(full)
                full["history"] = hist[hist["date"] <= last_date].copy()
                context = dict(context)
                context["full_pack"] = full
        except Exception:
            pass
        return context

    def _prepare_df(self, df):
        if df is None or df.empty:
            return None, {"error": "empty"}
        df = df.copy()
        if "date" not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                df["date"] = df.index
            else:
                return None, {"error": "missing date"}
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        # ensure core columns exist
        if "open" not in df.columns:
            df["open"] = df.get("close")
        if "high" not in df.columns:
            df["high"] = df.get("close")
        if "low" not in df.columns:
            df["low"] = df.get("close")
        if "vol" not in df.columns:
            df["vol"] = 0
        df = df.dropna(subset=["date", "close", "open"])
        df = df.sort_values("date")
        dup_dates = int(df["date"].duplicated().sum())
        if dup_dates > 0:
            df = df.drop_duplicates(subset=["date"], keep="last")
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        data_quality = {
            "rows": len(df),
            "dup_dates": dup_dates
        }
        self._last_data_quality = data_quality
        return df, data_quality

    def compute_metrics_from_equity_curve(self, eq_df, base_capital=1.0):
        if eq_df is None or eq_df.empty:
            return {}
        eq = eq_df["equity"].astype(float)
        if eq.iloc[0] == 0:
            return {}
        ret_pct = (eq.iloc[-1] / eq.iloc[0] - 1) * 100
        ann_return = 0.0
        years = len(eq_df) / 252
        if years > 0:
            ann_return = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1

        sharpe = 0.0
        max_dd = 0.0
        dd_start = ""
        dd_end = ""
        var_95 = 0.0
        if len(eq) > 2:
            rets = eq.pct_change().fillna(0)
            std = rets.std()
            if std and std != 0:
                sharpe = (rets.mean() / std) * np.sqrt(252)
            peak = eq.cummax()
            dd = (eq - peak) / peak
            max_dd = dd.min()
            try:
                dd_end_idx = dd.idxmin()
                dd_end = eq_df.loc[dd_end_idx, "date"]
                dd_start_idx = eq.loc[:dd_end_idx].idxmax()
                dd_start = eq_df.loc[dd_start_idx, "date"]
            except Exception:
                dd_start = ""
                dd_end = ""
            try:
                var_95 = var_gaussian(rets.tolist(), alpha=0.95)
            except Exception:
                var_95 = 0.0

        risk_level = risk_level_from_metrics(max_dd, var_95)
        return {
            "return_pct": ret_pct,
            "annualized_return": ann_return * 100,
            "max_drawdown": max_dd,
            "drawdown_start": dd_start,
            "drawdown_end": dd_end,
            "sharpe": sharpe,
            "var_95": var_95,
            "risk_level": risk_level
        }

    def _call_strategy_func(self, func, df_slice, context):
        if func is None:
            return False, ""
        if context is not None:
            try:
                sig = inspect.signature(func)
                if len(sig.parameters) >= 2:
                    return func(df_slice, context)
            except Exception:
                try:
                    return func(df_slice, context)
                except Exception:
                    pass
        try:
            return func(df_slice)
        except Exception:
            return False, ""

    def _check_signal(self, df_slice, strategy_code, dna_profile=None, context=None):
        curr = df_slice.iloc[-1]
        periods = resolve_ma_periods()
        p_short1 = periods.get('short1', 5)
        p_short2 = periods.get('short2', 10)
        p_mid1 = periods.get('mid1', 20)
        ma_m1 = ma_series(df_slice["close"], p_mid1).iloc[-1]

        if strategy_code == "hot_money":
            vol_ma_s1 = ma_series(df_slice["vol"], p_short1).iloc[-1]
            if curr["vol"] > vol_ma_s1 and curr["pct_chg"] > 3.0 and curr["close"] > ma_m1:
                return True, "HotMoney"

        elif strategy_code == "oversold":
            delta = df_slice["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + gain / loss))
            dyn = rsi_dynamic_thresholds(df_slice)
            lower = dyn.get("lower", 30)
            if rsi.iloc[-1] < lower:
                return True, f"Oversold RSI<{lower}"

        elif strategy_code == "dna":
            delta = df_slice["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + gain / loss))
            curr_rsi = rsi.iloc[-1]
            vol_ma_s1 = ma_series(df_slice["vol"], p_short1).iloc[-1]
            curr_bias = (curr["close"] - ma_m1) / ma_m1 if ma_m1 and ma_m1 != 0 else 0
            curr_vol_ratio = curr["vol"] / vol_ma_s1 if vol_ma_s1 and vol_ma_s1 != 0 else 0
            curr_amp = (curr["high"] - curr["low"]) / curr["close"] if curr["close"] else 0
            prof = dna_profile or self._load_dna_profile()
            target_rsi = float(prof.get("rsi", 50) or 50)
            target_bias = float(prof.get("bias_20", 0) or 0)
            target_vol = float(prof.get("vol_ratio", 1) or 1)
            target_amp = float(prof.get("amplitude", 0.03) or 0.03)
            if (
                abs(curr_rsi - target_rsi) < 15
                and abs(curr_bias - target_bias) < 0.1
                and curr_vol_ratio > target_vol * 0.8
                and abs(curr_amp - target_amp) < 0.05
            ):
                return True, f"DNA (RSI:{curr_rsi:.1f})"

        elif strategy_code == "standard":
            vol_ma_s1 = ma_series(df_slice["vol"], p_short1).iloc[-1]
            if curr["close"] > ma_m1 and curr["vol"] > vol_ma_s1 * 1.5:
                return True, "Volume Break"

        elif strategy_code == "tail_strength":
            if len(df_slice) < 60:
                return False, ""
            ma_s1 = ma_series(df_slice["close"], p_short1).iloc[-1]
            ma10 = ma_series(df_slice["close"], p_short2).iloc[-1]
            ma_m1 = ma_series(df_slice["close"], p_mid1).iloc[-1]
            close_pos_day = (curr["close"] - curr["low"]) / (curr["high"] - curr["low"]) if curr["high"] > curr["low"] else 0
            ret_5 = (curr["close"] / df_slice["close"].iloc[-6] - 1) if len(df_slice) >= 6 else 0
            ret_10 = (curr["close"] / df_slice["close"].iloc[-11] - 1) if len(df_slice) >= 11 else 0
            ret_20 = (curr["close"] / df_slice["close"].iloc[-21] - 1) if len(df_slice) >= 21 else 0
            low_20 = df_slice["low"].iloc[-20:].min()
            high_20 = df_slice["high"].iloc[-20:].max()
            pos_20 = (curr["close"] - low_20) / (high_20 - low_20) if high_20 > low_20 else 0
            low_60 = df_slice["low"].iloc[-60:].min()
            high_60 = df_slice["high"].iloc[-60:].max()
            pos_60 = (curr["close"] - low_60) / (high_60 - low_60) if high_60 > low_60 else 0
            vol_ref = df_slice["vol"].iloc[-(p_mid1+1):-1].mean() if len(df_slice) >= (p_mid1 + 1) else ma_series(df_slice["vol"], p_mid1).iloc[-1]
            vol_ratio_20 = curr["vol"] / vol_ref if vol_ref and vol_ref > 0 else 0

            hard = (
                curr["pct_chg"] > 0
                and curr["close"] >= ma_s1
                and curr["close"] >= ma10
                and close_pos_day >= 0.7
                and ret_5 > 0
                and ret_10 > 0
            )
            score = 0
            if ret_20 >= -0.02: score += 1
            if pos_20 >= 0.60: score += 1
            if 0.30 <= pos_60 <= 0.80: score += 1
            if 0.8 <= vol_ratio_20 <= 2.0: score += 1
            if curr["close"] >= ma_m1: score += 1
            if hard and score >= 3:
                return True, "TailStrength"

        elif strategy_code:
            user_strategies = self.scanner._load_user_strategies()
            func = user_strategies.get(strategy_code)
            if func:
                try:
                    is_hit, reason = self._call_strategy_func(func, df_slice, context)
                    return is_hit, reason
                except Exception:
                    pass

        return False, ""

    def _precompute_indicators(self, df):
        out = {}
        try:
            close = df["close"].astype(float)
            vol = df["vol"].astype(float)
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            periods = resolve_ma_periods()
            p_short1 = periods.get('short1', 5)
            p_short2 = periods.get('short2', 10)
            p_mid1 = periods.get('mid1', 20)
            out[f"ma{p_short1}"] = ma_series(close, p_short1)
            out[f"ma{p_short2}"] = ma_series(close, p_short2)
            out[f"ma{p_mid1}"] = ma_series(close, p_mid1)
            out[f"vol_ma{p_short1}"] = ma_series(vol, p_short1)
            out["ret_5"] = close / close.shift(5) - 1
            out["ret_10"] = close / close.shift(10) - 1
            out["ret_20"] = close / close.shift(20) - 1
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            out["rsi"] = 100 - (100 / (1 + rs))
            out[f"bias{p_mid1}"] = (close - out[f"ma{p_mid1}"]) / out[f"ma{p_mid1}"]
            out["vol_ratio"] = vol / out[f"vol_ma{p_short1}"]
            out["amp"] = (high - low) / close
            out["pct_chg"] = df["pct_chg"].astype(float)
            out["adx"] = adx(df, period=14)
            roll_low_20 = low.rolling(20).min()
            roll_high_20 = high.rolling(20).max()
            den_20 = roll_high_20 - roll_low_20
            out["pos_20"] = (close - roll_low_20) / den_20.replace(0, np.nan)
            roll_low_60 = low.rolling(60).min()
            roll_high_60 = high.rolling(60).max()
            den_60 = roll_high_60 - roll_low_60
            out["pos_60"] = (close - roll_low_60) / den_60.replace(0, np.nan)
            out["close_pos_day"] = (close - low) / (high - low).replace(0, np.nan)
            out["vol_ratio_20"] = vol / ma_series(vol, p_mid1).shift(1)
        except Exception:
            pass
        return out

    def _check_signal_fast(self, i, df, strategy_code, ind, dna_profile=None, context=None):
        try:
            if ind is None or i < 20:
                return False, ""
            curr = df.iloc[i]
            curr_close = float(curr["close"])
            curr_vol = float(curr["vol"])
            periods = resolve_ma_periods()
            p_short1 = periods.get('short1', 5)
            p_short2 = periods.get('short2', 10)
            p_mid1 = periods.get('mid1', 20)
            ma_col = f"ma{p_mid1}"
            ma_s1_col = f"ma{p_short1}"
            ma_s2_col = f"ma{p_short2}"
            vol_col = f"vol_ma{p_short1}"
            bias_col = f"bias{p_mid1}"
            ma_m1 = ind.get(ma_col).iloc[i] if ind.get(ma_col) is not None else None
            vol_ma_s1 = ind.get(vol_col).iloc[i] if ind.get(vol_col) is not None else None
            pct_chg = ind.get("pct_chg").iloc[i] if ind.get("pct_chg") is not None else None

            if strategy_code == "hot_money":
                if i < 15:
                    return False, ""
                recent = ind.get("pct_chg").iloc[max(0, i-15):i] if ind.get("pct_chg") is not None else None
                has_zt = bool((recent > 9.5).any()) if recent is not None else False
                is_active = (curr_vol > vol_ma_s1) and (pct_chg is not None and pct_chg > 3.0)
                if has_zt and is_active and ma_m1 is not None and curr_close > ma_m1:
                    return True, "HotMoney"

            elif strategy_code == "oversold":
                rsi = ind.get("rsi").iloc[i] if ind.get("rsi") is not None else None
                adx_val = ind.get("adx").iloc[i] if ind.get("adx") is not None else None
                lower = 30
                try:
                    if adx_val is not None:
                        if float(adx_val) >= 25:
                            lower = 20
                        elif float(adx_val) <= 20:
                            lower = 30
                        else:
                            lower = 30
                except Exception:
                    lower = 30
                if rsi is not None and rsi < lower:
                    return True, f"Oversold RSI<{lower}"

            elif strategy_code == "dna":
                rsi = ind.get("rsi").iloc[i] if ind.get("rsi") is not None else None
                bias = ind.get(bias_col).iloc[i] if ind.get(bias_col) is not None else None
                vol_ratio = ind.get("vol_ratio").iloc[i] if ind.get("vol_ratio") is not None else None
                amp = ind.get("amp").iloc[i] if ind.get("amp") is not None else None
                prof = dna_profile or self._load_dna_profile()
                target_rsi = float(prof.get("rsi", 50) or 50)
                target_bias = float(prof.get("bias_20", 0) or 0)
                target_vol = float(prof.get("vol_ratio", 1) or 1)
                target_amp = float(prof.get("amplitude", 0.03) or 0.03)
                if (
                    rsi is not None and bias is not None and vol_ratio is not None and amp is not None
                    and abs(rsi - target_rsi) < 15
                    and abs(bias - target_bias) < 0.1
                    and vol_ratio > target_vol * 0.8
                    and abs(amp - target_amp) < 0.05
                ):
                    return True, f"DNA (RSI:{rsi:.1f})"

            elif strategy_code == "standard":
                if ma_m1 is not None and vol_ma_s1 is not None:
                    if curr_close > ma_m1 and curr_vol > vol_ma_s1 * 1.5:
                        return True, "Volume Break"
            elif strategy_code == "tail_strength":
                if i < 60:
                    return False, ""
                ma_s1 = ind.get(ma_s1_col).iloc[i] if ind.get(ma_s1_col) is not None else None
                ma10 = ind.get(ma_s2_col).iloc[i] if ind.get(ma_s2_col) is not None else None
                ma_m1 = ind.get(ma_col).iloc[i] if ind.get(ma_col) is not None else None
                ret_5 = ind.get("ret_5").iloc[i] if ind.get("ret_5") is not None else None
                ret_10 = ind.get("ret_10").iloc[i] if ind.get("ret_10") is not None else None
                ret_20 = ind.get("ret_20").iloc[i] if ind.get("ret_20") is not None else None
                pos_20 = ind.get("pos_20").iloc[i] if ind.get("pos_20") is not None else None
                pos_60 = ind.get("pos_60").iloc[i] if ind.get("pos_60") is not None else None
                close_pos_day = ind.get("close_pos_day").iloc[i] if ind.get("close_pos_day") is not None else None
                vol_ratio_20 = ind.get("vol_ratio_20").iloc[i] if ind.get("vol_ratio_20") is not None else None

                hard = (
                    pct_chg is not None and pct_chg > 0
                    and ma_s1 is not None and ma10 is not None
                    and curr_close >= ma_s1 and curr_close >= ma10
                    and close_pos_day is not None and close_pos_day >= 0.7
                    and ret_5 is not None and ret_5 > 0
                    and ret_10 is not None and ret_10 > 0
                )
                score = 0
                if ret_20 is not None and ret_20 >= -0.02: score += 1
                if pos_20 is not None and pos_20 >= 0.60: score += 1
                if pos_60 is not None and 0.30 <= pos_60 <= 0.80: score += 1
                if vol_ratio_20 is not None and 0.8 <= vol_ratio_20 <= 2.0: score += 1
                if ma_m1 is not None and curr_close >= ma_m1: score += 1
                if hard and score >= 3:
                    return True, "TailStrength"
        except Exception:
            pass
        return False, ""

    def run(
        self,
        df,
        strategy_name="standard",
        take_profit=0.10,
        stop_loss=0.05,
        max_days=20,
        position_pct=1.0,
        execution="next_open",
        commission=None,
        slippage=None,
        stamp_duty=None,
        lot_size=None,
        context=None
    ):
        df, data_quality = self._prepare_df(df)
        if df is None or df.empty or len(df) < 50:
            return {"error": "Insufficient data (min 50)"}

        commission, slippage, stamp_duty, lot_size = self._resolve_costs(commission, slippage, stamp_duty, lot_size)

        if context is not None:
            context = self._align_context_history(context, df)

        real_strat = self._get_strategy_code(strategy_name)
        dna_profile = self._load_dna_profile() if real_strat == "dna" else None
        indicators = self._precompute_indicators(df)
        builtins = {"hot_money", "oversold", "dna", "standard", "tail_strength"}

        capital = self.initial_capital
        cash = capital
        position = 0
        cost_price = 0
        days_held = 0

        history = []
        equity_curve = []
        days_in_market = 0
        buy_fee = 0.0
        use_next_open = execution == "next_open"
        loop_end = len(df) - 1 if use_next_open else len(df)

        for i in range(30, loop_end):
            today = df.iloc[i]
            next_day = df.iloc[i + 1] if use_next_open else None
            today_date = today["date"]
            price = today["close"]
            held_today = position > 0

            if use_next_open:
                equity = cash + position * price
                equity_curve.append({"date": today_date, "equity": equity})
                if held_today:
                    days_in_market += 1

            if position > 0:
                days_held += 1
                pct = (price - cost_price) / cost_price

                sell_signal = False
                sell_reason = ""

                if pct >= take_profit:
                    sell_signal = True
                    sell_reason = f"TP (+{pct*100:.1f}%)"
                elif pct <= -stop_loss:
                    sell_signal = True
                    sell_reason = f"SL ({pct*100:.1f}%)"
                elif days_held >= max_days:
                    sell_signal = True
                    sell_reason = f"Time Exit ({days_held}d)"

                if sell_signal:
                    exec_base = next_day["open"] if use_next_open and next_day is not None else price
                    exec_date = next_day["date"] if use_next_open and next_day is not None else today_date
                    exec_price = exec_base * (1 - slippage)
                    proceeds = position * exec_price
                    fee = proceeds * (commission + stamp_duty)
                    cash += proceeds - fee
                    pnl = (exec_price - cost_price) * position - fee - buy_fee
                    history.append({
                        "date": exec_date, "action": "SELL", "reason": sell_reason,
                        "price": exec_price, "pct": pct*100, "capital": cash, "fee": fee,
                        "shares": position, "pnl": pnl, "hold_days": days_held
                    })
                    position = 0
                    days_held = 0
                    buy_fee = 0.0

            if position == 0:
                if real_strat in builtins:
                    is_buy, reason = self._check_signal_fast(i, df, real_strat, indicators, dna_profile=dna_profile, context=context)
                else:
                    df_slice = df.iloc[:i+1]
                    is_buy, reason = self._check_signal(df_slice, real_strat, dna_profile=dna_profile, context=context)

                if is_buy:
                    exec_base = next_day["open"] if use_next_open and next_day is not None else price
                    exec_date = next_day["date"] if use_next_open and next_day is not None else today_date
                    exec_price = exec_base * (1 + slippage)
                    invest_cash = cash * min(max(float(position_pct), 0.0), 1.0)
                    max_shares = int(invest_cash / (exec_price * (1 + commission)) / lot_size) * lot_size
                    if max_shares > 0:
                        cost = max_shares * exec_price
                        buy_fee = cost * commission
                        cash -= cost + buy_fee
                        position = max_shares
                        cost_price = exec_price
                        days_held = 0
                        history.append({
                            "date": exec_date, "action": "BUY", "reason": reason,
                            "price": exec_price, "pct": 0, "capital": cash, "fee": buy_fee, "shares": max_shares
                        })

            if not use_next_open:
                equity = cash + position * price
                equity_curve.append({"date": today_date, "equity": equity})
                if held_today:
                    days_in_market += 1

        if use_next_open and loop_end < len(df):
            last = df.iloc[-1]
            equity_curve.append({"date": last["date"], "equity": cash + position * last["close"]})

        if position > 0:
            final_price = df.iloc[-1]["close"]
            final_equity = cash + position * final_price
            final_pnl = (final_price - cost_price) * position - buy_fee
            history.append({
                "date": df.iloc[-1]["date"], "action": "SELL", "reason": "Backtest End",
                "price": final_price, "pct": ((final_price - cost_price) / cost_price) * 100,
                "capital": final_equity, "fee": 0.0, "shares": position, "pnl": final_pnl, "hold_days": days_held
            })
        else:
            final_equity = cash

        eq_df = pd.DataFrame(equity_curve)
        metrics = self.compute_metrics_from_equity_curve(eq_df, base_capital=capital)
        trade_stats = self._calc_trade_stats(history)

        win_rate = trade_stats.get("win_rate", 0.0)
        profit_factor = trade_stats.get("profit_factor", 0.0)
        avg_hold_days = trade_stats.get("avg_hold_days", 0.0)
        max_consec_losses = trade_stats.get("max_consecutive_losses", 0)

        exposure = (days_in_market / len(eq_df)) if len(eq_df) > 0 else 0.0

        # benchmark: buy & hold
        bench_return = 0.0
        bench_annual = 0.0
        try:
            if len(df) >= 2:
                first_close = float(df.iloc[0]["close"])
                last_close = float(df.iloc[-1]["close"])
                if first_close > 0:
                    bench_return = (last_close / first_close - 1) * 100
                    years = len(df) / 252
                    if years > 0:
                        bench_annual = ((last_close / first_close) ** (1 / years) - 1) * 100
        except Exception:
            bench_return = 0.0
            bench_annual = 0.0

        excess_return = metrics.get("return_pct", 0) - bench_return
        # risk-adjusted score for strategy ranking (higher is better)
        try:
            score = float(metrics.get("return_pct", 0) or 0) - float(metrics.get("max_drawdown", 0) or 0) * 100
            sharpe = float(metrics.get("sharpe", 0) or 0)
            if sharpe:
                score += sharpe * 2.0
        except Exception:
            score = float(metrics.get("return_pct", 0) or 0)

        return {
            "initial": capital,
            "final": final_equity,
            "return_pct": metrics.get("return_pct", 0),
            "annualized_return": metrics.get("annualized_return", 0),
            "benchmark_return_pct": bench_return,
            "benchmark_annualized_return": bench_annual,
            "excess_return_pct": excess_return,
            "score": score,
            "trades": history,
            "equity_curve": eq_df,
            "max_drawdown": metrics.get("max_drawdown", 0),
            "drawdown_start": metrics.get("drawdown_start", ""),
            "drawdown_end": metrics.get("drawdown_end", ""),
            "sharpe": metrics.get("sharpe", 0),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_hold_days": avg_hold_days,
            "max_consecutive_losses": max_consec_losses,
            "exposure": exposure,
            "var_95": metrics.get("var_95", 0.0),
            "risk_level": metrics.get("risk_level", "N/A"),
            "data_quality": data_quality
        }

    def optimize(
        self,
        df,
        strategy_name,
        train_ratio=0.7,
        mode="simple",
        window_count=3,
        position_pct=1.0,
        execution="next_open",
        commission=None,
        slippage=None,
        stamp_duty=None,
        lot_size=None,
        context=None
    ):
        df, _ = self._prepare_df(df)
        if df is None or df.empty or len(df) < 120:
            return []

        results = []
        tp_range = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
        sl_range = [0.03, 0.05, 0.07, 0.10]
        day_range = [5, 10, 20, 30, 50]

        n = len(df)
        split_idx = int(n * train_ratio)
        if split_idx < 80:
            split_idx = 80
        if n - split_idx < 40:
            return []

        df_train = df.iloc[:split_idx]
        start_test = max(split_idx - 30, 0)
        df_test = df.iloc[start_test:] if split_idx < n else df

        windows = []
        if mode == "walk_forward":
            if window_count < 2:
                window_count = 2
            win_size = max(int(n / window_count), 80)
            start = 0
            while start + 60 < n:
                end = min(start + win_size, n)
                seg = df.iloc[start:end]
                if len(seg) >= 80:
                    s_idx = int(len(seg) * train_ratio)
                    if s_idx < 60:
                        s_idx = len(seg)
                    seg_train = seg.iloc[:s_idx]
                    seg_test = seg.iloc[max(s_idx - 30, 0):] if s_idx < len(seg) else seg
                    windows.append((seg_train, seg_test))
                if end >= n:
                    break
                start = end
            if not windows:
                windows = [(df_train, df_test)]

        for tp in tp_range:
            for sl in sl_range:
                for d in day_range:
                    if mode == "walk_forward":
                        test_rets = []
                        test_dds = []
                        train_rets = []
                        for seg_train, seg_test in windows:
                            res_train = self.run(
                                seg_train,
                                strategy_name,
                                take_profit=tp,
                                stop_loss=sl,
                                max_days=d,
                                position_pct=position_pct,
                                execution=execution,
                                commission=commission,
                                slippage=slippage,
                                stamp_duty=stamp_duty,
                                lot_size=lot_size,
                                context=context
                            )
                            if "error" in res_train:
                                continue
                            res_test = self.run(
                                seg_test,
                                strategy_name,
                                take_profit=tp,
                                stop_loss=sl,
                                max_days=d,
                                position_pct=position_pct,
                                execution=execution,
                                commission=commission,
                                slippage=slippage,
                                stamp_duty=stamp_duty,
                                lot_size=lot_size,
                                context=context
                            )
                            train_rets.append(res_train.get("return_pct", 0))
                            test_rets.append(res_test.get("return_pct", 0))
                            test_dds.append(abs(res_test.get("max_drawdown") or 0))
                        if not test_rets:
                            continue
                        test_ret = sum(test_rets) / len(test_rets)
                        test_dd = sum(test_dds) / len(test_dds) if test_dds else 0
                        score = test_ret - test_dd * 100
                        ret_train = sum(train_rets) / len(train_rets) if train_rets else 0
                    else:
                        res_train = self.run(
                            df_train,
                            strategy_name,
                            take_profit=tp,
                            stop_loss=sl,
                            max_days=d,
                            position_pct=position_pct,
                            execution=execution,
                            commission=commission,
                            slippage=slippage,
                            stamp_duty=stamp_duty,
                            lot_size=lot_size,
                            context=context
                        )
                        if "error" in res_train:
                            continue
                        res_test = self.run(
                            df_test,
                            strategy_name,
                            take_profit=tp,
                            stop_loss=sl,
                            max_days=d,
                            position_pct=position_pct,
                            execution=execution,
                            commission=commission,
                            slippage=slippage,
                            stamp_duty=stamp_duty,
                            lot_size=lot_size,
                            context=context
                        )
                        test_ret = res_test.get("return_pct", 0)
                        test_dd = abs(res_test.get("max_drawdown") or 0)
                        score = test_ret - test_dd * 100
                        ret_train = res_train.get("return_pct", 0)

                    results.append({
                        "tp": tp,
                        "sl": sl,
                        "days": d,
                        "ret": ret_train,
                        "test_ret": test_ret,
                        "test_dd": test_dd,
                        "win": res_test.get("win_rate", 0) if mode != "walk_forward" else 0,
                        "trades": len(res_test.get("trades", [])) // 2 if mode != "walk_forward" else 0,
                        "score": score
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:5]

    def _calc_win_rate(self, trades):
        if not trades:
            return 0
        sells = [t for t in trades if t.get("action") == "SELL"]
        if not sells:
            return 0
        wins = 0
        for t in sells:
            if "pnl" in t:
                if float(t.get("pnl", 0) or 0) > 0:
                    wins += 1
            else:
                if "TP" in str(t.get("reason", "")):
                    wins += 1
        return (wins / len(sells) * 100) if sells else 0

    def _calc_trade_stats(self, trades):
        sells = [t for t in trades if t.get("action") == "SELL"]
        if not sells:
            return {
                "profit_factor": 0.0,
                "avg_hold_days": 0.0,
                "max_consecutive_losses": 0,
                "win_rate": 0.0
            }
        pnls = [float(t.get("pnl", 0) or 0) for t in sells]
        profits = sum(p for p in pnls if p > 0)
        losses = abs(sum(p for p in pnls if p < 0))
        profit_factor = (profits / losses) if losses > 0 else float("inf") if profits > 0 else 0.0
        hold_days = [float(t.get("hold_days", 0) or 0) for t in sells]
        avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0.0

        max_consec = 0
        curr = 0
        for p in pnls:
            if p < 0:
                curr += 1
                max_consec = max(max_consec, curr)
            else:
                curr = 0

        win_rate = (len([p for p in pnls if p > 0]) / len(pnls) * 100) if pnls else 0.0
        return {
            "profit_factor": profit_factor,
            "avg_hold_days": avg_hold,
            "max_consecutive_losses": max_consec,
            "win_rate": win_rate
        }

    def plot_result(self, df, res, benchmark_df=None):
        if "error" in res:
            return None
        fig = go.Figure()
        start_idx = 30
        base_price = df.iloc[start_idx]["close"]
        base_norm = df["close"] / base_price * 100
        fig.add_trace(go.Scatter(x=df["date"][start_idx:], y=base_norm[start_idx:], name="Price (Base)", line=dict(color="gray", dash="dot")))

        if benchmark_df is not None and not benchmark_df.empty and "date" in benchmark_df.columns:
            bench = benchmark_df.copy()
            try:
                start_date = df.iloc[start_idx]["date"]
                bench = bench[bench["date"] >= start_date]
            except Exception:
                pass
            if not bench.empty:
                try:
                    base_bench = float(bench.iloc[0]["close"])
                except Exception:
                    base_bench = 0
                if base_bench:
                    bench_norm = bench["close"] / base_bench * 100
                    fig.add_trace(go.Scatter(x=bench["date"], y=bench_norm, name="Benchmark", line=dict(color="blue", width=1)))

        eq_df = res["equity_curve"]
        if not eq_df.empty:
            eq_norm = eq_df["equity"] / self.initial_capital * 100
            fig.add_trace(go.Scatter(x=eq_df["date"], y=eq_norm, name="Strategy Equity", line=dict(color="red", width=2)))

        trades = res["trades"]
        buys = [t for t in trades if t["action"] == "BUY"]
        sells = [t for t in trades if t["action"] == "SELL"]
        if buys:
            buy_y = [float(t["price"]) / base_price * 100 for t in buys]
            fig.add_trace(go.Scatter(x=[t["date"] for t in buys], y=buy_y, mode="markers", marker=dict(symbol="triangle-up", size=10, color="red"), name="BUY"))
        if sells:
            sell_y = [float(t["price"]) / base_price * 100 for t in sells]
            fig.add_trace(go.Scatter(x=[t["date"] for t in sells], y=sell_y, mode="markers", marker=dict(symbol="triangle-down", size=10, color="green"), name="SELL"))

        fig.update_layout(title="Backtest: Strategy vs Price", xaxis_title="Date", yaxis_title="Normalized Value (100=base)", template="plotly_white")
        return fig

    def plot_equity_curve(self, eq_df, benchmark_df=None, title="Equity Curve"):
        if eq_df is None or eq_df.empty or "equity" not in eq_df.columns:
            return None
        fig = go.Figure()
        try:
            base_val = float(eq_df["equity"].iloc[0] or 1.0)
        except Exception:
            base_val = 1.0
        if base_val == 0:
            base_val = 1.0
        eq_norm = eq_df["equity"] / base_val * 100
        fig.add_trace(go.Scatter(x=eq_df["date"], y=eq_norm, name="Equity", line=dict(color="red", width=2)))

        if benchmark_df is not None and not benchmark_df.empty and "date" in benchmark_df.columns:
            bench = benchmark_df.copy()
            try:
                start_date = eq_df.iloc[0]["date"]
                bench = bench[bench["date"] >= start_date]
            except Exception:
                pass
            if not bench.empty:
                try:
                    base_bench = float(bench.iloc[0]["close"])
                except Exception:
                    base_bench = 0
                if base_bench:
                    bench_norm = bench["close"] / base_bench * 100
                    fig.add_trace(go.Scatter(x=bench["date"], y=bench_norm, name="Benchmark", line=dict(color="blue", width=1)))

        fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Normalized Value (100=base)", template="plotly_white")
        return fig
