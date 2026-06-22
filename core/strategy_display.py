STRATEGY_NAME_MAP = {
    "coin_flip_buy": "抛硬币买入",
    "random_pick_hold_2d": "随机买入持有2天",
    "prev_day_down_buy": "前一日下跌买入",
    "above_ma5_buy": "站上5日线买入",
    "tp10_sl10_t20": "10%止盈 / 10%止损 / 20天强平",
    "tri_brain_default": "三脑默认策略",
    "strong_down": "强势下跌",
    "strong_up": "强势上涨",
    "oversold": "超跌反弹",
    "hot_money": "游资回马枪",
    "tail_strength": "尾盘走强",
    "dna": "风格克隆",
    "demo_macd": "MACD示例策略",
    "user_try": "用户试验策略",
    "user_tdx_tg": "通达信条件策略",
    "Standard": "放量突破",
    "FinancialStrong": "财务强势",
}


def display_strategy_name(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if text in STRATEGY_NAME_MAP:
        return STRATEGY_NAME_MAP[text]
    lowered = text.lower()
    if lowered in STRATEGY_NAME_MAP:
        return STRATEGY_NAME_MAP[lowered]
    return text.replace("_", " ")
