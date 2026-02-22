import pandas as pd
from core.ta_utils import resolve_ma_periods, ma_series

def check(df):
    if len(df) < 30:
        return False, "数据不足"
    
    # 计算涨停条件：涨幅大于等于9.8%
    df['is_zt'] = df['pct_chg'] >= 9.8
    
    # 计算大实体涨停：涨停且实体长度大于5%（收盘价相对于开盘价的涨幅）
    df['zt_entity'] = (df['close'] - df['open']) / df['open']
    df['big_zt'] = df['is_zt'] & (df['zt_entity'] > 0.05)
    periods = resolve_ma_periods()
    p_short1 = periods.get('short1', 5)
    df[f'vol_ma{p_short1}'] = ma_series(df['vol'], p_short1)
    
    # 计算成交量均线（5日）
    
    # 寻找近期大实体涨停
    big_zt_idx = df[df['big_zt']].index
    if len(big_zt_idx) == 0:
        return False, "无大实体涨停"
    
    # 从最新数据向前寻找符合条件的形态
    for i in range(len(df)-1, 5, -1):
        # 检查当前位置是否为大实体涨停
        if not df.iloc[i]['big_zt']:
            continue
            
        zt_open = df.iloc[i]['open']  # 涨停开盘价
        zt_high = df.iloc[i]['high']  # 涨停最高价
        
        # 寻找回调跌破涨停开盘价的位置
        break_idx = -1
        for j in range(i-1, max(i-20, 0), -1):
            if df.iloc[j]['low'] < zt_open:
                break_idx = j
                break
        
        if break_idx == -1:
            continue
        
        break_high = df.iloc[break_idx]['high']  # 跌破当日的最高价
        break_vol = df.iloc[break_idx]['vol']   # 跌破当日的成交量
        
        # 检查跌破当日是否缩量（成交量低于5日均量）
        if break_idx >= 5:
            if break_vol > df.iloc[break_idx][f'vol_ma{p_short1}']:
                continue
        
        # 检查跌破后的缩量整理期（至少3日）
        if i - break_idx < 4:
            continue
        
        # 检查整理期是否缩量（整理期平均成交量低于跌破日成交量）
        consol_period = df.iloc[break_idx-3:break_idx]
        if len(consol_period) < 3:
            continue
        
        avg_vol_consol = consol_period['vol'].mean()
        if avg_vol_consol > break_vol * 1.2:
            continue
        
        # 检查最新一日是否突破跌破日最高点
        curr = df.iloc[-1]
        if curr['high'] > break_high and curr['close'] > break_high:
            return True, f"大实体涨停后缩量回调{break_idx}日，突破整理高点"
    
    return False, ""
