import pandas as pd
from core.ta_utils import resolve_ma_periods, ma_series

class NewsVerifier:
    def __init__(self):
        pass

    def check_divergence(self, df, news_list=None):
        """
        检测 【股价趋势】 与 【消息面】 是否背离
        """
        if df.empty or len(df) < 5:
            return {"status": "数据不足", "divergence_score": 0}

        # 1. 计算短期趋势
        curr = df.iloc[-1]
        pct_3d = df['pct_chg'].tail(3).sum()
        trend = "上涨" if pct_3d > 2 else "下跌" if pct_3d < -2 else "震荡"

        # 2. 模拟消息面评分 (如果没有接入真实NLP，使用随机或规则)
        # 这里为了不报错，我们做一个基础逻辑：
        # 如果涨幅巨大但放巨量滞涨 -> 疑似利好出货
        
        status = "消息面共振"
        score = 0
        
        if trend == "上涨" and curr['pct_chg'] < 0.5 and curr['vol'] > vol_ma * 1.5:
             status = "⚠️ 利好出货嫌疑 (放量滞涨)"
             score = -10
        elif trend == "下跌" and curr['pct_chg'] > -0.5 and curr['vol'] < vol_ma * 0.5:
             status = "🛡️ 利空不跌 (惜售)"
             score = 10
             
        return {
            "status": status,
            "divergence_score": score,
            "trend": trend
        }