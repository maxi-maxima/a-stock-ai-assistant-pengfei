import tushare as ts
import pandas as pd
import datetime
import yaml
from core.ta_utils import resolve_ma_periods, ma_series, rsi_dynamic_thresholds

class MarketDetectorSkill:
    def __init__(self):
        self.pro = self._init_tushare()

    def _init_tushare(self):
        """初始化 Tushare 接口"""
        try:
            with open("config/llm_config.yaml", "r", encoding="utf-8") as f:
                conf = yaml.safe_load(f)
                token = conf.get('system', {}).get('tushare_token', '')
            
            if not token or len(token) < 10:
                print("⚠️ 警告: 未检测到有效的 Tushare Token，将使用模拟数据！")
                return None
            
            ts.set_token(token)
            return ts.pro_api()
        except Exception as e:
            print(f"❌ Tushare 初始化失败: {e}")
            return None

    def get_kline_data(self, stock_code: str):
        """获取日线数据并计算指标"""
        # 1. 如果没有 Token，返回模拟数据 (防止报错)
        if not self.pro:
            return self._mock_data(stock_code)

        try:
            # 2. 格式化代码 (Tushare 要求 000001.SZ 格式)
            # 如果用户输入 000001，尝试自动补全 (简单逻辑)
            if "." not in stock_code:
                if stock_code.startswith("6"): stock_code += ".SH"
                else: stock_code += ".SZ"

            # 3. 获取最近 60 天数据 (为了计算 EMA??, RSI)
            end_date = datetime.datetime.now().strftime("%Y%m%d")
            start_date = (datetime.datetime.now() - datetime.timedelta(days=100)).strftime("%Y%m%d")
            
            df = self.pro.daily(ts_code=stock_code, start_date=start_date, end_date=end_date)
            
            if df.empty:
                return {"error": "未获取到数据，可能是停牌或代码错误"}

            # Tushare 返回是倒序的 (最新在最前)，我们要转成正序计算指标
            df = df.sort_values('trade_date')
            
            # 4. 计算技术指标 (Pandas 魔法)
            df[f'ma{p_short1}'] = ma_series(df['close'], p_short1)
            df[f'ma{p_short2}'] = ma_series(df['close'], p_short2)
            df[f'ma{p_mid1}'] = ma_series(df['close'], p_mid1)
            
            # 简单 RSI 计算
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(6).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
            df['rsi_6'] = 100 - (100 / (1 + gain / loss))

            # 5. 取最新一天的数据
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            dyn = rsi_dynamic_thresholds(df)
            upper = dyn.get("upper", 70)
            lower = dyn.get("lower", 30)
            regime = dyn.get("regime", "neutral")
            contrarian_note = " | high RSI implies sentiment heat and lower future returns" if latest['rsi_6'] >= upper else ""
            
            # 6. 生成自然语言描述 (给 AI 读的)
            summary = f"""
            Symbol {stock_code} ({latest['trade_date']})
            - Close: {latest['close']} (pct: {latest['pct_chg']}%)
            - EMA: ema{p_short1}={latest[f'ma{p_short1}']:.2f}, ema{p_short2}={latest[f'ma{p_short2}']:.2f}, ema{p_mid1}={latest[f'ma{p_mid1}']:.2f}
            - Cross: {'ema_short_cross' if latest[f'ma{p_short1}'] > latest[f'ma{p_short2}'] and prev[f'ma{p_short1}'] <= prev[f'ma{p_short2}'] else 'no_cross'}
            - RSI(6): {latest['rsi_6']:.2f} ({'overbought' if latest['rsi_6']>upper else 'oversold' if latest['rsi_6']<lower else 'neutral'}) [regime={regime}, thresh={upper}/{lower}]{contrarian_note}
            - Volume: {latest['vol']}
            """
            
            return {
                "raw_df": df.tail(5).to_dict(), # 保留最近5天原始数据
                "summary": summary,
                "latest_price": latest['close']
            }

        except Exception as e:
            return {"error": f"获取行情失败: {str(e)}"}

    def _mock_data(self, code):
        return {
            "summary": f"[mock] {code} price 100.0, ema short above ema mid, RSI 45 (neutral). Configure Tushare Token for real data.",
            "latest_price": 100.0
        }

if __name__ == "__main__":
    # 测试代码
    skill = MarketDetectorSkill()
    print(skill.get_kline_data("000001.SZ")['summary'])
