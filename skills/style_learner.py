import datetime
import json
import os

import pandas as pd
from skills.data_factory import DataSkillFactory
from core.learning_log import summarize_behavior
from core.ta_utils import resolve_ma_periods, ma_series

class StyleLearner:
    def __init__(self):
        self.data_skill = DataSkillFactory.get_skill("tushare")
        self.profile_path = "config/style_profile.json"

    def learn_from_examples(self, stock_list):
        logs = []
        feats = []
        for code in stock_list:
            df = self.data_skill.get_history(code, days=120)
            if df.empty or len(df) < 30:
                logs.append(f"{code}: 无足够数据")
                continue

            df = df.copy()
            df = df.dropna(subset=["close", "high", "low", "vol"])
            if len(df) < 30:
                logs.append(f"{code}: 数据清洗后不足")
                continue

            periods = resolve_ma_periods()
            p_mid1 = periods.get('mid1', 20)
            p_short1 = periods.get('short1', 5)
            ma20 = ma_series(df["close"], p_mid1)
            vol_ma5 = ma_series(df["vol"], p_short1)

            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + gain / loss))

            bias_20 = (df["close"] - ma20) / ma20
            vol_ratio = df["vol"] / vol_ma5
            amplitude = (df["high"] - df["low"]) / df["close"]

            feat_df = pd.DataFrame({
                "rsi": rsi,
                "bias_20": bias_20,
                "vol_ratio": vol_ratio,
                "amplitude": amplitude
            })
            feat_df = feat_df.replace([float("inf"), float("-inf")], pd.NA).dropna()
            if feat_df.empty:
                logs.append(f"{code}: 特征计算失败")
                continue

            window = feat_df.tail(20)
            feats.append({
                "rsi": float(window["rsi"].median()),
                "bias_20": float(window["bias_20"].median()),
                "vol_ratio": float(window["vol_ratio"].median()),
                "amplitude": float(window["amplitude"].median())
            })
            logs.append(f"{code}: 提取完成")

        if not feats:
            return None, logs

        def avg(k):
            return sum(f[k] for f in feats) / len(feats)

        prof = {
            "rsi": round(avg("rsi"), 2),
            "bias_20": round(avg("bias_20"), 4),
            "vol_ratio": round(avg("vol_ratio"), 2),
            "amplitude": round(avg("amplitude"), 4)
        }

        # 风格推断
        if prof["amplitude"] > 0.05 or prof["vol_ratio"] > 1.8:
            dna_risk = "激进"
        elif prof["amplitude"] < 0.02 and prof["vol_ratio"] < 1.1:
            dna_risk = "保守"
        else:
            dna_risk = "平衡"
        prof["risk_appetite_dna"] = dna_risk

        # 行为画像融合
        beh = summarize_behavior()
        prof["behavior"] = beh
        prof["risk_appetite_behavior"] = beh.get("risk_appetite")
        if beh.get("risk_appetite") and beh["risk_appetite"] != "平衡":
            prof["risk_appetite"] = beh["risk_appetite"]
        else:
            prof["risk_appetite"] = dna_risk
        prof["holding_preference"] = beh.get("holding_preference", "中性")

        prof["sample_count"] = len(feats)
        prof["samples"] = [str(s).strip() for s in stock_list]
        prof["window_days"] = 120
        prof["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")

        # 保存
        try:
            os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(prof, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return prof, logs

    def analyze_teaching_case(self, code):
        """
        🔥 教学模式：用户输入一只股票，AI 自动分析它为什么好
        默认取【尾盘】数据进行分析
        """
        df = self.data_skill.get_history(code, days=30)
        if df is None or df.empty:
            return None, "无数据"
        df = df.dropna(subset=["close", "high", "low", "vol"])
        if df.empty:
            return None, "无有效行情数据"

        latest = df.iloc[-1]
        
        # 自动分析逻辑 (Why is it a buy?)
        reasons = []
        periods = resolve_ma_periods()
        p_mid1 = periods.get('mid1', 20)
        p_short1 = periods.get('short1', 5)
        if latest['close'] > ma_series(df['close'], p_mid1).iloc[-1]:
            reasons.append(f"??EMA{p_mid1}")
            reasons.append("站上20日均线")
        if latest['vol'] > ma_series(df['vol'], p_short1).iloc[-1]:
            reasons.append("尾盘放量抢筹")
        try:
            if float(latest.get("pct_chg", 0) or 0) > 0:
                reasons.append("日内收红")
        except Exception:
            pass

        if not reasons:
            reasons.append("无明显信号")

        try:
            pct_str = f"{float(latest.get('pct_chg', 0) or 0):.2f}"
        except Exception:
            pct_str = "N/A"
        analysis = f"用户教学样本: {code}。尾盘表现: 涨幅{pct_str}%。逻辑归因: {', '.join(reasons)}。"
        
        return {
            "price": latest.get("close"),
            "analysis": analysis,
            "tech_data": latest.to_dict()
        }, "分析完成"
