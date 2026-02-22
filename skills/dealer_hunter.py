import pandas as pd
import numpy as np
from core.ta_utils import resolve_ma_periods, ma_series

class DealerHunter:
    def __init__(self):
        pass

    def analyze(self, df):
        """
        输入: K线 DataFrame (包含 open, close, high, low, vol)
        输出: 风险评估报告 (dict)
        """
        if df.empty or len(df) < 20:
            return {"risk_level": "未知", "risk_score": 0, "warnings": []}

        warnings = []
        risk_score = 0
        periods = resolve_ma_periods()
        p_short1 = periods.get('short1', 5)
        p_mid1 = periods.get('mid1', 20)
        
        # 提取最近数据
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # -------------------------------------------------
        # 1. 识别【避雷针 / 仙人指路】(长上影线)
        # -------------------------------------------------
        upper_shadow = curr['high'] - max(curr['open'], curr['close'])
        body = abs(curr['close'] - curr['open'])
        if upper_shadow > body * 2 and upper_shadow > (curr['close'] * 0.02):
            if curr['high'] >= df['high'].iloc[-20:].max() * 0.95:
                warnings.append("⚠️ 高位避雷针：主力疑似借冲高出货")
                risk_score += 30
            else:
                warnings.append("ℹ️ 仙人指路：主力试探上方抛压")

        # -------------------------------------------------
        # 2. 识别【放量滞涨】
        # -------------------------------------------------
        vol_ma5 = ma_series(df['vol'], p_short1).iloc[-1]
        if curr['vol'] > vol_ma5 * 1.8: 
            if abs(curr['pct_chg']) < 1.0:
                warnings.append("⚠️ 放量滞涨：主力可能正在派发筹码")
                risk_score += 40

        # -------------------------------------------------
        # 3. 识别【断头铡刀】
        # -------------------------------------------------
        ma5 = ma_series(df['close'], p_short1).iloc[-1]
        ma20 = ma_series(df['close'], p_mid1).iloc[-1]
        if curr['close'] < ma5 and curr['close'] < ma20 and prev['close'] > ma5:
            if curr['pct_chg'] < -3:
                warnings.append("☠️ 断头铡刀：主力凶狠出逃，跌破重要均线")
                risk_score += 50

        # -------------------------------------------------
        # 总结
        # -------------------------------------------------
        if risk_score >= 60:
            level = "🔴 极高风险 (庄家出货)"
        elif risk_score >= 30:
            level = "🟠 中度风险 (主力异动)"
        else:
            level = "🟢 相对安全"

        return {
            "risk_level": level,
            "risk_score": risk_score,
            "warnings": warnings
        }