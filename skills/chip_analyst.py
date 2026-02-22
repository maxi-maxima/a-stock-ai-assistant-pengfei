import pandas as pd
import numpy as np

class ChipAnalyst:
    def __init__(self):
        pass

    def analyze(self, df, bins=60):
        """
        基于历史成交量估算筹码分布 (Volume Profile)
        """
        if df.empty or len(df) < 60:
            return None

        # 取最近 120 天的数据进行统计（模拟半年内的筹码沉淀）
        recent_df = df.iloc[-120:].copy()
        
        current_price = recent_df['close'].iloc[-1]
        min_p = recent_df['low'].min()
        max_p = recent_df['high'].max()
        
        # 1. 创建价格区间 (Bins)
        try:
            price_bins = np.linspace(min_p, max_p, bins)
            
            # 2. 将成交量分配到对应的价格区间 (近似算法)
            chip_dist = pd.cut(recent_df['close'], bins=price_bins, labels=False, include_lowest=True)
            volume_profile = recent_df.groupby(chip_dist)['vol'].sum()
            
            # 3. 计算获利盘 (Winner Ratio)
            # 所有成本在当前价格下方的筹码，都算获利盘
            # 找到当前价格对应的 bin index
            current_bin_idx = pd.cut([current_price], bins=price_bins, labels=False, include_lowest=True)[0]
            
            # 累加当前价格下方的所有成交量
            winner_vol = volume_profile.loc[:current_bin_idx].sum() if current_bin_idx >= 0 else 0
            total_vol = volume_profile.sum()
            
            winner_ratio = (winner_vol / total_vol) * 100 if total_vol > 0 else 0
            
            # 4. 寻找筹码峰 (最大成交量的价格区间)
            max_vol_idx = volume_profile.idxmax()
            # 估算筹码峰价格
            peak_price = (price_bins[int(max_vol_idx)] + price_bins[int(max_vol_idx)+1]) / 2
            
            # 5. 判断状态
            status = "震荡洗盘"
            score_impact = 0
            
            distance_to_peak = (current_price - peak_price) / peak_price * 100
            
            if winner_ratio < 6:
                status = "❄️ 极度冰点 (超跌)"
                score_impact = 10
            elif winner_ratio > 90:
                status = "🔥 获利了结 (高危)"
                score_impact = -20
            else:
                if distance_to_peak < -15:
                    status = "🧱 压力山大"
                    score_impact = -10
                elif distance_to_peak > 3 and distance_to_peak < 10:
                    status = "🚀 突破筹码峰"
                    score_impact = 15

            return {
                "winner_ratio": round(winner_ratio, 1),
                "peak_price": round(peak_price, 2),
                "status": status,
                "score_impact": score_impact
            }
            
        except Exception as e:
            print(f"Chip Analysis Error: {e}")
            return None