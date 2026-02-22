import pandas as pd
from core.ta_utils import resolve_ma_periods, ma_series

class CycleCompass:
    def __init__(self):
        pass

    def detect_phase(self, df):
        """
        基于均线系统识别股票生命周期 (Stan Weinstein / Wyckoff logic)
        """
        periods = resolve_ma_periods()
        p_mid1 = periods.get('mid1', 20)
        p_mid2 = periods.get('mid2', 60)
        p_long1 = periods.get('long1', 120)
        min_len = max(p_long1 + 2, 60)
        if df.empty or len(df) < min_len:
            return {"phase": "未知", "desc": "数据不足", "score_impact": 0, "icon": "❓"}

        # 计算均线
        ma20 = ma_series(df['close'], p_mid1).iloc[-1]
        ma60 = ma_series(df['close'], p_mid2).iloc[-1]
        ma120 = ma_series(df['close'], p_long1).iloc[-1]
        
        # 获取前一天的均线以判断斜率 (Slope)
        ma60_prev = ma_series(df['close'], p_mid2).iloc[-2]
        
        price = df['close'].iloc[-1]
        
        phase = "震荡整理"
        desc = "多空平衡"
        score_impact = 0
        icon = "☁️"

        # --- 判定逻辑 ---
        
        # Phase 2: 主升浪 (最完美的形态)
        # 特征：价格 > 所有均线，且均线多头排列 (20 > 60 > 120)，且 60日线向上
        if price > ma20 and ma20 > ma60 and ma60 > ma120 and ma60 > ma60_prev:
            phase = "Phase 2 (主升浪 - 夏天)"
            desc = "趋势完美，多头排列，正如烈日当空，适合重仓持有。"
            score_impact = 30
            icon = "☀️"
            
        # Phase 4: 主跌浪 (最危险的形态)
        # 特征：价格 < 所有均线，且均线空头排列 (20 < 60 < 120)
        elif price < ma20 and ma20 < ma60 and ma60 < ma120:
            phase = "Phase 4 (主跌浪 - 冬天)"
            desc = "大势已去，空头排列，正如严冬降临，任何反弹都是逃命机会。"
            score_impact = -100 # 🔥 强制扣分，熔断买入建议
            icon = "❄️"
            
        # Phase 3: 顶部派发 (风险区域)
        # 特征：价格跌破20日线，但还在60日线上方
        elif price < ma20 and price > ma60:
            phase = "Phase 3 (顶部派发 - 秋天)"
            desc = "获利回吐，趋势转弱，落叶知秋。"
            score_impact = -10
            icon = "🍂"
            
        # Phase 1: 底部筑底 (潜伏区域)
        # 特征：价格在60日线附近震荡，60日线走平
        elif abs(price - ma60)/ma60 < 0.05 and abs(ma60 - ma60_prev)/ma60 < 0.002:
            phase = "Phase 1 (底部筑底 - 春天)"
            desc = "冰雪消融，万物复苏，主力正在吸筹。"
            score_impact = 10
            icon = "🌱"

        return {
            "phase": phase,
            "desc": desc,
            "score_impact": score_impact,
            "icon": icon
        }