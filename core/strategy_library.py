import json
import os

from core.ta_utils import resolve_ma_periods


class StrategyLibrary:
    def __init__(self, filepath="data/my_strategies.json"):
        self.filepath = filepath
        self.strategies = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            periods = resolve_ma_periods()
            p_short1 = periods.get("short1", 5)
            p_mid1 = periods.get("mid1", 20)
            self.strategies = {
                "均线金叉 (EMA Cross)": {
                    "code": f"df['ma{p_short1}'] > df['ma{p_mid1}']",
                    "desc": "短期EMA上穿中期EMA，趋势向上"
                },
                "放量突破 (Volume Break)": {
                    "code": f"df['vol'] > df['vol'].ewm(span={p_short1}, adjust=False).mean() * 2",
                    "desc": "成交量超过短期EMA均量2倍，资金入场"
                },
                "RSI超卖 (RSI Oversold)": {
                    "code": "df['rsi'] < 30",
                    "desc": "RSI指标低于30，存在反弹需求"
                }
            }
            self._save()
        else:
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.strategies = json.load(f)
            except Exception:
                self.strategies = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.strategies, f, ensure_ascii=False, indent=2)

    def get_all_names(self):
        return list(self.strategies.keys())

    def get_strategy(self, name):
        return self.strategies.get(name, {})

    def save_strategy(self, name, code, desc="自定义策略"):
        self.strategies[name] = {
            "code": code,
            "desc": desc
        }
        self._save()

    def delete_strategy(self, name):
        if name in self.strategies:
            del self.strategies[name]
            self._save()
            return True
        return False
