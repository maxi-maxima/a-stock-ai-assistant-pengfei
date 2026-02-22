from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time as dtime
from typing import Optional, Dict, Any


ACTION_CN = {
    "BUY": "买入",
    "HOLD": "观望",
    "SELL": "卖出",
}


def action_to_cn(action: str) -> str:
    return ACTION_CN.get(action, action)


@dataclass(frozen=True)
class Palace:
    name: str
    emoji: str
    meaning: str
    action: str


PALACES = [
    Palace("大安", "🟢", "主安稳，宜守不宜攻。", "HOLD"),
    Palace("留连", "🟡", "事难速成，宜缓不宜进。", "HOLD"),
    Palace("速喜", "🟢", "喜事临门，宜进取。", "BUY"),
    Palace("赤口", "🔴", "口舌是非，宜谨慎。", "SELL"),
    Palace("小吉", "🟢", "小有吉兆，宜小进。", "BUY"),
    Palace("空亡", "🔴", "虚耗无利，宜止损。", "SELL"),
]


EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

HOUR_TO_BRANCH = {
    23: 0, 0: 0,
    1: 1, 2: 1,
    3: 2, 4: 2,
    5: 3, 6: 3,
    7: 4, 8: 4,
    9: 5, 10: 5,
    11: 6, 12: 6,
    13: 7, 14: 7,
    15: 8, 16: 8,
    17: 9, 18: 9,
    19: 10, 20: 10,
    21: 11, 22: 11,
}


@dataclass(frozen=True)
class LunarDate:
    month: int
    day: int
    hour_branch: int


class XiaoLiuRen:
    LUNAR_MONTH_DAYS = [29, 30, 29, 30, 29, 30, 29, 30, 29, 30, 29, 30]
    BASE_DATE = date(2024, 2, 10)  # 2024-02-10 近似为农历正月初一

    def _get_palace(self, index: int) -> Palace:
        return PALACES[index % 6]

    def _solar_to_lunar_simple(self, dt: datetime) -> LunarDate:
        delta = (dt.date() - self.BASE_DATE).days
        lunar_month = 1
        lunar_day = 1
        if delta >= 0:
            for _ in range(delta):
                lunar_day += 1
                month_days = self.LUNAR_MONTH_DAYS[(lunar_month - 1) % 12]
                if lunar_day > month_days:
                    lunar_day = 1
                    lunar_month += 1
                    if lunar_month > 12:
                        lunar_month = 1
        else:
            for _ in range(abs(delta)):
                lunar_day -= 1
                if lunar_day < 1:
                    lunar_month -= 1
                    if lunar_month < 1:
                        lunar_month = 12
                    lunar_day = self.LUNAR_MONTH_DAYS[(lunar_month - 1) % 12]
        hour_branch = HOUR_TO_BRANCH.get(dt.hour, 0)
        return LunarDate(month=lunar_month, day=lunar_day, hour_branch=hour_branch)

    def predict(self, dt: Optional[datetime] = None) -> Dict[str, Any]:
        dt = dt or datetime.now()
        lunar = self._solar_to_lunar_simple(dt)

        month_idx = (lunar.month - 1) % 6
        month_palace = self._get_palace(month_idx)
        day_idx = (month_idx + lunar.day - 1) % 6
        day_palace = self._get_palace(day_idx)
        hour_idx = (day_idx + lunar.hour_branch) % 6
        hour_palace = self._get_palace(hour_idx)

        return {
            "solar": dt,
            "lunar": lunar,
            "month": month_palace,
            "day": day_palace,
            "hour": hour_palace,
            "final": hour_palace,
        }

    def format_result(self, result: Dict[str, Any]) -> str:
        solar = result["solar"]
        lunar = result["lunar"]
        final = result["final"]
        return (
            f"小六壬结果: {final.emoji} {final.name}\n"
            f"公历: {solar.strftime('%Y-%m-%d %H:%M')}\n"
            f"农历(简化): {lunar.month}月{lunar.day}日 {EARTHLY_BRANCHES[lunar.hour_branch]}时\n"
            f"解释: {final.meaning}\n"
            f"建议: {action_to_cn(final.action)}"
        )

