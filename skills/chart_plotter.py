import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from core.ta_utils import resolve_ma_periods, ma_series

class ChartPlotter:
    def plot_kline(self, df, title="K-Line"):
        if df is None or df.empty: return None

        # 确保按日期正序 (Critical for line connecting)
        df = df.sort_values('date')
        
        # 计算均线
        periods = resolve_ma_periods()
        p_short1 = periods.get("short1", 5)
        p_mid1 = periods.get("mid1", 20)
        ma_s_col = f"ma{p_short1}"
        ma_m_col = f"ma{p_mid1}"
        if ma_s_col not in df.columns: df[ma_s_col] = ma_series(df['close'], p_short1)
        if ma_m_col not in df.columns: df[ma_m_col] = ma_series(df['close'], p_mid1)

        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.03, 
            subplot_titles=(title, 'Volume'),
            row_width=[0.2, 0.7]
        )

        # K线 (Red up, Green down)
        fig.add_trace(go.Candlestick(
            x=df['date'],
            open=df['open'], high=df['high'],
            low=df['low'], close=df['close'],
            name='K线',
            increasing_line_color='#ef5350',
            decreasing_line_color='#26a69a'
        ), row=1, col=1)

        # MA Lines
        fig.add_trace(go.Scatter(x=df['date'], y=df[ma_s_col], line=dict(color='orange', width=1), name=f'EMA{p_short1}'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df[ma_m_col], line=dict(color='purple', width=1), name=f'EMA{p_mid1}'), row=1, col=1)

        # Volume
        colors = ['#ef5350' if row['open'] < row['close'] else '#26a69a' for index, row in df.iterrows()]
        fig.add_trace(go.Bar(
            x=df['date'], y=df['vol'],
            marker_color=colors,
            name='成交量'
        ), row=2, col=1)

        fig.update_layout(height=600, title_text=title, xaxis_rangeslider_visible=False)
        return fig
