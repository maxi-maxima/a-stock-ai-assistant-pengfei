import datetime
import os
import requests
import logging
import yaml
import json

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WorldModel:
    """
    Layer 0: 世界模型层
    职责：验证物理世界状态（API可用性、市场时间、网络质量）
    """
    def __init__(self):
        self.status = "INIT"
        
    def check_health(self) -> dict:
        """全系统健康检查"""
        market_status = self._get_market_status()
        report = {
            "network": self._check_network(),
            "market_status": market_status,
            "market_open": True if market_status == "OPEN" else False,
            "api_connectivity": self._check_api_connectivity()
        }
        
        # 只要有一个不行，整体状态就是 False
        is_healthy = bool(report.get("network")) and bool(report.get("api_connectivity")) and bool(report.get("market_open"))
        self.status = "READY" if is_healthy else "ERROR"
        
        return {
            "healthy": is_healthy,
            "details": report
        }

    def _check_network(self) -> bool:
        """简单的网络连通性测试"""
        if os.getenv("DISABLE_NETWORK_CHECK", "0") == "1":
            return True

        urls = self._get_net_check_urls()
        timeout = self._get_net_timeout()
        for url in urls:
            try:
                res = requests.get(url, timeout=timeout)
                if res is not None and res.status_code < 500:
                    return True
            except Exception:
                continue
        logging.error("❌ 网络连接失败")
        return False

    def _load_market_calendar(self):
        path = "config/market_calendar.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        # fallback: env var HOLIDAYS, comma-separated YYYY-MM-DD
        env = os.getenv("MARKET_HOLIDAYS", "").strip()
        if env:
            holidays = [d.strip() for d in env.split(",") if d.strip()]
            return {"holidays": holidays}
        return {"holidays": []}

    def _get_market_status(self) -> str:
        """判断当前是否为A股交易时间"""
        now = datetime.datetime.now()

        # holiday calendar
        try:
            cal = self._load_market_calendar()
            holidays = cal.get("holidays", []) if isinstance(cal, dict) else []
            today_str = now.date().isoformat()
            if today_str in holidays:
                return "CLOSED (Holiday)"
        except Exception:
            pass
        
        # 周末
        if now.weekday() > 4: 
            return "CLOSED (Weekend)"
        
        # 交易时段 (9:30-11:30, 13:00-15:00)
        # 简单判定，暂不考虑节假日
        t = now.time()
        morning_start = datetime.time(9, 15) # 包含集合竞价
        morning_end = datetime.time(11, 30)
        afternoon_start = datetime.time(13, 0)
        afternoon_end = datetime.time(15, 0)
        
        if (morning_start <= t <= morning_end) or (afternoon_start <= t <= afternoon_end):
            return "OPEN"
        else:
            return "CLOSED"

    def _check_api_connectivity(self) -> bool:
        """这里预留给后续检查 LLM API 或 Tushare API"""
        # 暂时默认返回 True，后续对接 config
        return True

    def _get_net_check_urls(self):
        env = os.getenv("NET_CHECK_URLS", "").strip()
        if env:
            return [u.strip() for u in env.split(",") if u.strip()]
        # try config file
        try:
            with open("config/llm_config.yaml", "r", encoding="utf-8") as f:
                conf = yaml.safe_load(f) or {}
            urls = conf.get("system", {}).get("net_check_urls")
            if isinstance(urls, list) and urls:
                return [str(u).strip() for u in urls if str(u).strip()]
            if isinstance(urls, str) and urls.strip():
                return [u.strip() for u in urls.split(",") if u.strip()]
        except Exception:
            pass
        # default: mixed global/cn endpoints
        return [
            "https://www.baidu.com",
            "https://www.qq.com",
            "https://www.cloudflare.com/cdn-cgi/trace"
        ]

    def _get_net_timeout(self):
        try:
            return float(os.getenv("NET_CHECK_TIMEOUT", "3"))
        except Exception:
            return 3.0

if __name__ == "__main__":
    # 测试代码
    wm = WorldModel()
    print("🌍 世界模型自检报告:", wm.check_health())
