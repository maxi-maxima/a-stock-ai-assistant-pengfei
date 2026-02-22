import pandas as pd
from core.ta_utils import resolve_ma_periods, ma_series

class LiquidityGuard:
    def __init__(self, min_turnover=3000): 
        # 默认要求日成交额大于 3000万
        self.min_turnover_w = min_turnover 

    def check(self, df):
        if df.empty:
            return {"is_zombie": False, "status": "未知", "value_str": "0"}

        # 估算成交额 (Vol * Close)
        # 注意：tushare vol 单位是手(100股)，所以成交额 = vol * 100 * close
        periods = resolve_ma_periods()
        p_short1 = periods.get('short1', 5)
        avg_vol = ma_series(df['vol'], p_short1).iloc[-1]
        price = df['close'].iloc[-1]
        
        # 单位：万
        amount_w = (avg_vol * 100 * price) / 10000 
        
        is_zombie = amount_w < self.min_turnover_w
        
        status = "流动性充沛" if not is_zombie else "⛔ 流动性枯竭 (僵尸股)"
        
        value_str = f"{amount_w/10000:.2f}亿" if amount_w > 10000 else f"{amount_w:.0f}万"
        
        return {
            "is_zombie": is_zombie,
            "status": status,
            "value_str": value_str,
            "amount_w": amount_w
        }