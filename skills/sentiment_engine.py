import random

class SentimentEngine:
    def __init__(self):
        pass

    def get_weather_report(self):
        """
        生成市场情绪天气报告
        (实际项目中这里应该读取大盘涨跌家数、连板高度等)
        """
        # 这里为了演示，我们返回一个基于随机但合理的模拟值，
        # 或者你可以改成固定值
        
        # 模拟：30%概率热，40%震荡，30%冷
        seed = random.random()
        
        if seed > 0.7:
            return {
                "temperature": random.randint(60, 90),
                "weather": "艳阳高照 (做多窗口)",
                "icon": "☀️",
                "bg_color": "rgba(255, 0, 0, 0.1)" # 暖色
            }
        elif seed < 0.3:
            return {
                "temperature": random.randint(0, 30),
                "weather": "冰天雪地 (防御为主)",
                "icon": "❄️",
                "bg_color": "rgba(0, 0, 255, 0.1)" # 冷色
            }
        else:
            return {
                "temperature": random.randint(31, 59),
                "weather": "多云震荡 (精选个股)",
                "icon": "☁️",
                "bg_color": "rgba(200, 200, 200, 0.1)" # 中性色
            }