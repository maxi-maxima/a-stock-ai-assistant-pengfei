import pandas as pd
import numpy as np

class SmartGrid:
    def __init__(self):
        pass

    def calculate(self, df, period=14):
        """
        计算 ATR 动态网格
        """
        if df.empty or len(df) < period + 1:
            return None

        # 计算 ATR
        df = df.copy()
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = (df['high'] - df['close'].shift()).abs()
        df['low_close'] = (df['low'] - df['close'].shift()).abs()
        df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['atr'] = df['tr'].rolling(period).mean()
        
        curr_atr = df['atr'].iloc[-1]
        curr_price = df['close'].iloc[-1]
        
        # 防止 ATR 为 NaN 或 0
        if pd.isna(curr_atr) or curr_atr == 0:
            curr_atr = curr_price * 0.03 # 兜底 3%

        # 生成网格
        return {
            "atr": round(curr_atr, 2),
            "stop_loss": round(curr_price - 2 * curr_atr, 2),
            "buy_grid": [round(curr_price - i * curr_atr, 2) for i in range(1, 4)],
            "sell_grid": [round(curr_price + i * curr_atr, 2) for i in range(1, 4)]
        }