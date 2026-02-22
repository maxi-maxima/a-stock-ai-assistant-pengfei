import schedule
import time
import sys
import os
import datetime
import json
from collections import deque

# --- 路径修复 (让后台脚本能找到 core/skills) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
# -------------------------------------------

from core.cognitive_graph import build_cognitive_graph
from skills.scanner import MarketScanner
from core.portfolio import VirtualPortfolio
from core.event_bus import EventBus

# 初始化组件
scanner = MarketScanner("tushare") # 默认用 Tushare
portfolio = VirtualPortfolio()
app = build_cognitive_graph()
event_bus = EventBus()
LOOP_REPORT_PATH = "data/loop_health_report.jsonl"
EVENT_BUS_PATH = "data/event_bus.jsonl"

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] 🤖 {msg}")

def _pick_primary_strategy(item):
    """
    Pick a primary strategy name from fusion votes or list for attribution.
    Returns (strategy_name, weight) or (None, None).
    """
    votes = item.get("strategy_votes", []) if isinstance(item, dict) else []
    best_name = None
    best_weight = None
    if isinstance(votes, list):
        for v in votes:
            if not isinstance(v, dict):
                continue
            name = v.get("strategy") or v.get("name")
            w = v.get("weight", 0)
            try:
                w = float(w)
            except Exception:
                w = 0.0
            if name and (best_weight is None or w > best_weight):
                best_name = name
                best_weight = w
    if best_name:
        return best_name, best_weight

    strategies = item.get("strategies") if isinstance(item, dict) else None
    if isinstance(strategies, list):
        for s in strategies:
            if isinstance(s, str) and s.strip():
                return s.strip(), None
    if isinstance(strategies, str) and strategies.strip():
        return strategies.strip(), None
    strat = item.get("strategy") if isinstance(item, dict) else None
    if isinstance(strat, str) and strat.strip():
        return strat.strip(), None
    return None, None

def _load_latest_agent_report(agent_id, max_lines=2000):
    if not os.path.exists(EVENT_BUS_PATH):
        return None
    target = str(agent_id or "").strip().lower()
    if not target:
        return None
    try:
        with open(EVENT_BUS_PATH, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=max_lines)
    except Exception:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if not isinstance(rec, dict) or rec.get("event") != "agent_report":
            continue
        payload = rec.get("payload", {}) if isinstance(rec.get("payload", {}), dict) else {}
        pid = str(payload.get("agent_id") or payload.get("agent_type") or "").strip().lower()
        if pid == target:
            return payload
    return None


def _extract_data_health(report):
    if not isinstance(report, dict):
        return {}
    metrics = report.get("metrics", {}) if isinstance(report.get("metrics"), dict) else {}
    details = report.get("details", {}) if isinstance(report.get("details"), dict) else {}
    health_details = details.get("details", {}) if isinstance(details.get("details"), dict) else {}
    out = {
        "status": str(report.get("status") or "").lower(),
        "network": metrics.get("network"),
        "market_open": metrics.get("market_open"),
        "api_connectivity": metrics.get("api_connectivity")
    }
    if out["market_open"] is None and "market_open" in health_details:
        out["market_open"] = 1 if health_details.get("market_open") else 0
    return out


def _extract_health_score(report):
    if not isinstance(report, dict):
        return None
    metrics = report.get("metrics", {}) if isinstance(report.get("metrics"), dict) else {}
    if "health_score" in metrics:
        try:
            return float(metrics.get("health_score") or 0)
        except Exception:
            return None
    details = report.get("details", {}) if isinstance(report.get("details"), dict) else {}
    if "health_score" in details:
        try:
            return float(details.get("health_score") or 0)
        except Exception:
            return None
    return None

def job_market_scan():
    """
    定时任务：市场扫描 & 自动交易
    """
    log("⏰ 定时任务启动：全市场猎手扫描...")

    # agent gates: data_health + execution_risk
    strict_net = os.getenv("STRICT_NET_CHECK", "0") == "1"
    data_report = _load_latest_agent_report("data_health")
    if not data_report:
        if strict_net:
            log("   - data_health report missing (strict), stop")
            return
        log("   - data_health report missing, skip gate")
    else:
        dh = _extract_data_health(data_report)
        if dh.get("status") == "fail":
            log("   - data_health=fail, stop")
            return
        if dh.get("market_open") in (0, False):
            log("   - market closed (data_health)")
            return
        if strict_net and dh.get("network") in (0, False):
            log("   - network check failed (strict)")
            return

    if os.getenv("HEALTH_GATE_ENABLED", "0") == "1":
        try:
            min_score = float(os.getenv("HEALTH_GATE_MIN_SCORE", "70"))
        except Exception:
            min_score = 70.0
        exec_report = _load_latest_agent_report("execution_risk")
        if not exec_report:
            log("   - execution_risk report missing (health gate), stop")
            return
        score = _extract_health_score(exec_report)
        if score is None:
            log("   - execution_risk health_score missing, stop")
            return
        if score < min_score:
            log(f"   - health_score below min ({score:.1f}<{min_score}), stop")
            return
    # 1. 获取目标池
    # (为了演示，这里只取少量样本，实际可用沪深300)
    stock_list = scanner.get_candidate_pool()
    log(f"   - 目标池规模: {len(stock_list)} 只")
    
    # 2. 技术面粗筛
    log("   - 使用策略融合路由")
    candidates, _ = scanner.fusion_scan(stock_list, top_k=3)
    
    if not candidates:
        log("   - 💤 本次扫描无标的入选，继续休眠。")
        return

    log(f"   - ✅ 发现 {len(candidates)} 个潜在机会，三脑介入分析中...")
    
    # 3. 深度分析 & 交易
    paper_execute = os.getenv("AUTO_PAPER_EXECUTE", "1") == "1"

    for item in candidates:
        code = item['code']
        log(f"   - 🧠 正在分析 {code} ...")
        
        try:
            # 调用大脑 (会自动触发 execution_node 下单)
            signal_source = {
                "source": "scanner",
                "strategies": [v.get("strategy") for v in item.get("strategy_votes", []) if isinstance(v, dict)],
                "reason": item.get("reason"),
                "votes": item.get("strategy_votes")
            }
            primary, weight = _pick_primary_strategy(item)
            if primary:
                signal_source["strategy"] = primary
            if weight is not None:
                signal_source["strategy_weight"] = weight
            res = app.invoke({
                "stock_code": code,
                "messages": [],
                "signal_source": signal_source,
                "paper_execute": paper_execute,
                "source_info": {"source": "autopilot", "label": "AutoPilot"}
            })
            
            action = res['trading_signal']['action']
            result = res.get('execution_result', '无操作')
            
            if action == "BUY":
                log(f"   - 🚀 【买入指令】 {code} -> {result}")
            elif action == "SELL":
                log(f"   - 💰 【卖出指令】 {code} -> {result}")
            else:
                log(f"   - ✋ 最终决策: {action}")
                
        except Exception as e:
            log(f"   - ❌ 分析出错: {e}")

    log("✅ 本次定时任务结束。")


def _append_loop_report(record):
    try:
        os.makedirs(os.path.dirname(LOOP_REPORT_PATH), exist_ok=True)
        with open(LOOP_REPORT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def job_loop_health_report():
    if os.getenv("ENABLE_LOOP_REPORT", "1") != "1":
        return
    try:
        report = compute_loop_health()
    except Exception:
        report = None
    if not isinstance(report, dict):
        return
    report["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    ok = _append_loop_report(report)
    try:
        event_bus.log("loop_health", payload=report, source="auto_pilot")
    except Exception:
        pass
    if ok:
        log(f"Loop health report saved: {LOOP_REPORT_PATH}")

def job_daily_report():
    """
    定时任务：每日资产汇报
    """
    try:
        job_loop_health_report()
    except Exception:
        pass
    try:
        from core.loop_controller import run_daily
        run_daily()
    except Exception:
        pass
    log("📊 收盘资产盘点...")
    cash = portfolio.get_balance()
    pos = portfolio.get_positions()
    log(f"   - 可用资金: ¥{cash:,.2f}")
    log(f"   - 持仓数量: {len(pos)} 只")
    if not pos.empty:
        for _, row in pos.iterrows():
            log(f"     * {row['stock_code']}: {row['amount']}股 (成本 {row['avg_cost']:.2f})")

def start_autopilot():
    log("🚀 自动驾驶系统 (Auto-Pilot) 已启动！")
    log("📅 计划任务列表:")
    log("   1. 每隔 1 分钟执行一次扫描 (测试用)")
    log("   2. 每天 14:30 执行尾盘偷袭")
    log("   3. 每天 15:05 执行收盘盘点")
    print("-" * 50)

    # --- 定义时间表 ---
    # 为了让你立刻看到效果，我加了一个“每分钟运行一次”的测试任务
    # 实际使用时，你可以把这行注释掉
    schedule.every(1).minutes.do(job_market_scan)
    
    # 真实场景的定时任务
    schedule.every().day.at("10:00").do(job_market_scan) # 早盘
    schedule.every().day.at("14:30").do(job_market_scan) # 尾盘
    schedule.every().day.at("15:05").do(job_daily_report) # 收盘

    # --- 无限循环 ---
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    try:
        start_autopilot()
    except KeyboardInterrupt:
        log("🛑 自动驾驶已停止。")
