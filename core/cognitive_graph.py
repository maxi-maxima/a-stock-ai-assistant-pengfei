import sys
import os
import json
import uuid
from typing import TypedDict, Annotated, List, Dict, Any
import operator
import datetime
from core.tri_brain import TriBrainCouncil
from skills.data_factory import TushareMaster
from skills.dealer_hunter import DealerHunter
from skills.chip_analyst import ChipAnalyst
from skills.cycle_compass import CycleCompass
from skills.liquidity_guard import LiquidityGuard
from skills.sentiment_engine import SentimentEngine
from skills.news_verifier import NewsVerifier
from core.memory import MemoryManager
from core.knowledge_base import KnowledgeBase
from core.portfolio import VirtualPortfolio
from core.experience_store import ExperienceStore
from core.threshold_profiles import load_profiles, get_active_profile_name, get_profile
from core.experience_feedback import load_bias
from core.learning_log import record_feature_weights, log_event
from core.logger import warn
from core.ta_utils import resolve_ma_periods, ma_series
from core.event_bus import EventBus
from core.browser_use_adapter import register_browser_use_tool
from core.letta_adapter import read_semantic, write_semantic_from_state
from core.protocols import get_protocol_version, sanitize_tool_tasks, validate_decision_payload
from core.news_fetch import build_news_tool_tasks, should_fetch, extract_news_items, merge_news
from core.decision_sample import build_decision_sample, ensure_decision_sample

# 初始化全局单例
council = TriBrainCouncil()
data_master = TushareMaster()
memory = MemoryManager()
kb = KnowledgeBase()
experience = ExperienceStore()
event_bus = EventBus()

class CognitiveState(TypedDict):
    stock_code: str
    market_data: Dict[str, Any]
    fundamental_data: Dict[str, Any]
    news_data: List[str]
    macro_news: List[str]
    global_index: Dict[str, Any]
    capital_data: Dict[str, Any] 
    chip_data: Dict[str, Any]
    tech_factors: Dict[str, Any]
    dealer_hunter: Dict[str, Any]
    chip_analyst: Dict[str, Any]
    cycle_compass: Dict[str, Any]
    liquidity_guard: Dict[str, Any]
    sentiment_weather: Dict[str, Any]
    
    user_position: Dict[str, Any]
    user_funds: Dict[str, Any]
    
    morning_strategy: str 

    position_context: str 
    technical_analysis: str
    fundamental_analysis: str
    news_analysis: str
    capital_analysis: str
    memory_context: str
    knowledge_context: str
    knowledge_titles: List[str]
    knowledge_items: List[Dict[str, Any]]
    
    # 🔥 Python 算好的硬数据
    calculated_grid: Dict[str, Any]
    reference_pack: Dict[str, Any]
    feature_pack: Dict[str, Any]
    macro_pack: Dict[str, Any]
    factor_snapshot: Dict[str, Any]
    tool_tasks: List[Dict[str, Any]]
    composio_tasks: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    autogen_review: str
    letta_context: str
    
    trading_signal: Dict[str, Any]
    risk_assessment: str
    stop_policy: str
    risk_budget: Dict[str, Any]
    execution_result: str
    deep_risk: bool
    skill_plan: Dict[str, Any]
    profile_name: str
    profile: Dict[str, Any]
    signal_source: Dict[str, Any]
    decision_id: str
    data_quality: Dict[str, Any]
    news_check: Dict[str, Any]
    critic_report: Dict[str, Any]
    messages: Annotated[List[str], operator.add]
    paper_execute: bool

def _calculate_python_grid(current_price, ma20, atr, position_dict, adapt=None):
    """
    🔥 内部算子：双向网格生成 (无论持仓与否，都生成买卖点)
    """
    if current_price <= 0:
        current_price = 0
    if atr <= 0: atr = current_price * 0.02 # 兜底波动率

    # 让网格更“贴身”：将 ATR 限制在 1%~4.5% 的价格区间
    if current_price > 0:
        atr = max(current_price * 0.01, min(atr, current_price * 0.045))
        base_gap1 = atr * 0.7
        base_gap2 = atr * 1.4

        # adaptive scaling based on weights
        scale = 1.0
        if isinstance(adapt, dict):
            tech_w = float(adapt.get("technical", 0) or 0)
            cap_w = float(adapt.get("capital", 0) or 0)
            risk_w = float(adapt.get("risk", 0) or 0)
            # tighter grid when technical/capital weight higher
            if tech_w >= 20 or cap_w >= 20:
                scale = 0.85
            # wider grid when risk weight high
            if risk_w >= 20:
                scale = 1.15
        gap1 = base_gap1 * scale
        gap2 = base_gap2 * scale
    else:
        gap1 = 0
        gap2 = 0
    
    # 初始化结构
    grid = {
        "buy1_price": 0, "buy1_action": "",
        "buy2_price": 0, "buy2_action": "",
        "sell1_price": 0, "sell1_action": "",
        "sell2_price": 0, "sell2_action": "",
        "note": "AI 动态网格"
    }
    
    # 场景 A：有持仓 (生成 止盈卖点 + 补仓买点)
    if position_dict and position_dict.get('volume', 0) > 0:
        cost = position_dict.get('cost', 0)
        
        # --- 卖方 (上方) ---
        # 卖一：成本/现价上方紧凑 ATR
        target_sell = max(current_price, cost) + gap1
        grid['sell1_price'] = round(target_sell, 2)
        grid['sell1_action'] = "减仓做T / 获利了结"
        
        grid['sell2_price'] = round(target_sell + gap1, 2)
        grid['sell2_action'] = "清仓 / 止盈离场"
        
        # --- 买方 (下方) ---
        # 买一：现价下方紧凑 ATR (支撑位接回)
        grid['buy1_price'] = round(current_price - gap1, 2)
        grid['buy1_action'] = "低吸做T / 摊低成本"
        
        grid['buy2_price'] = round(current_price - gap2, 2)
        grid['buy2_action'] = "深跌补仓 (倍投)"
        
        grid['note'] = f"🛡️ 持仓防御网格 (成本 {cost})：紧凑上卖下买"

    # 场景 B：空仓 (生成 建仓买点 + 预期卖点)
    else:
        # --- 买方 (下方) ---
        base = ma20 if ma20 and ma20 > 0 else current_price
        # 如果均线距离过大，收紧到 3% 内
        if current_price > 0:
            max_drop = current_price * 0.03
            if current_price - base > max_drop:
                base = current_price - max_drop
            # 保证买点低于现价至少 1%
            base = min(base, current_price - current_price * 0.01)
        grid['buy1_price'] = round(base, 2)
        grid['buy1_action'] = "均线首仓 (轻仓试错)"
        
        grid['buy2_price'] = round(base - gap1, 2)
        grid['buy2_action'] = "超跌补仓 (倍投)"
        
        # --- 卖方 (上方 - 预估) ---
        grid['sell1_price'] = round(current_price + gap1, 2)
        grid['sell1_action'] = "日内超买压力位 (预设)"
        
        grid['note'] = "⚔️ 趋势博弈网格：紧凑切入，提升成交概率"
        
    return grid


def _fallback_decision_id(code=None):
    base = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    if code:
        code = str(code).strip().upper().replace(".", "")
        return f"{code}_{base}_{uuid.uuid4().hex[:6]}"
    return f"DEC_{base}_{uuid.uuid4().hex[:6]}"

def perception_node(state: CognitiveState):
    code = state['stock_code']
    pack = data_master.get_full_analysis_pack(code)
    
    hist = pack.get('history')
    latest_price = 0
    tech_summary = "n/a"
    ma20 = 0
    last_date = None
    pct_chg = 0.0
    vol = 0.0
    data_quality = {"rows": int(len(hist)) if hist is not None else 0}
    if not hist.empty:
        latest = hist.iloc[-1]
        latest_price = float(latest['close'])
        periods = resolve_ma_periods()
        p_mid1 = periods.get('mid1', 20)
        ma20 = ma_series(hist['close'], p_mid1).iloc[-1]
        tech_summary = f"price={latest_price}, ema{p_mid1}={ma20:.2f}, pct={latest['pct_chg']}%"
        try:
            last_date = str(latest['date'])
        except Exception:
            last_date = None
        try:
            pct_chg = float(latest['pct_chg'])
        except Exception:
            pct_chg = 0.0
        try:
            vol = float(latest['vol'])
        except Exception:
            vol = 0.0
        data_quality.update({
            "last_date": last_date,
            "pct_chg": pct_chg,
            "vol": vol
        })
        try:
            if last_date:
                last_dt = datetime.datetime.strptime(last_date[:10], "%Y-%m-%d").date()
                delta_days = (datetime.date.today() - last_dt).days
                data_quality["stale_days"] = delta_days
                data_quality["stale"] = True if delta_days >= 4 else False
        except Exception:
            pass

    idx = pack.get('market_index', {})
    info = pack.get('stock_info', {})
    
    # Add EMA mid to tech_factors for downstream
    tf = pack.get('tech_factors', {})
    if 'boll_mid' not in tf and ma20 > 0: tf['boll_mid'] = ma20

    # allow upstream overrides (e.g., UI passes pre-fetched news)
    news_data = state.get("news_data") if isinstance(state.get("news_data"), list) and state.get("news_data") else pack.get('stock_news', [])
    macro_news = state.get("macro_news") if isinstance(state.get("macro_news"), list) and state.get("macro_news") else pack.get('macro_news', [])

    return {
        "market_data": {
            "latest_price": latest_price, 
            "index_context": f"上证 {idx.get('trend', '震荡')}",
            "sector_context": f"【板块】{info.get('name')} | {info.get('industry')}",
            "stock_name": info.get('name', code),
            "last_date": last_date,
            "pct_chg": pct_chg,
            "vol": vol
        },
        "fundamental_data": pack.get('valuation', {}),
        "news_data": news_data,
        "macro_news": macro_news,
        "capital_data": pack.get('money_flow', {}),
        "chip_data": pack.get('chip_perf', {}),
        "tech_factors": tf,
        "sector_flow": pack.get('sector_flow', {}),
        "global_index": pack.get('global_index', {}),
        "technical_analysis": tech_summary,
        "data_quality": data_quality
    }

def skill_router_node(state: CognitiveState):
    """
    Lightweight skill routing and profile injection.
    """
    profile_name = None
    profile = {}
    try:
        profiles = load_profiles()
        profile_name = get_active_profile_name(profiles)
        profile = get_profile(profile_name, profiles)
    except Exception:
        profile = {}

    tactics_profile = profile.get("tactics", {}) if isinstance(profile, dict) else {}
    deep_risk = state.get("deep_risk")
    if deep_risk is None:
        deep_risk = bool(tactics_profile.get("deep_risk", False))

    # heuristic overrides
    market = state.get("market_data", {}) or {}
    tech = state.get("tech_factors", {}) or {}
    price = float(market.get("latest_price", 0) or 0)
    atr = float(tech.get("atr", 0) or 0)
    vol_pct = (atr / price) if price else 0.0
    try:
        pct_chg = float(market.get("pct_chg", 0) or 0)
    except Exception:
        pct_chg = 0.0
    if vol_pct >= 0.06 or pct_chg <= -5:
        deep_risk = True

    enable_news = bool(tactics_profile.get("enable_news", True))
    enable_sentiment = bool(tactics_profile.get("enable_sentiment", True))

    tasks = ["dealer_hunter", "chip_analyst", "cycle_compass", "liquidity_guard"]
    if enable_sentiment:
        tasks.append("sentiment_weather")
    if enable_news:
        tasks.append("news_verifier")

    plan = {
        "profile": profile_name,
        "deep_risk": bool(deep_risk),
        "volatility": vol_pct,
        "reason": "volatility" if vol_pct >= 0.06 else ("drawdown" if pct_chg <= -5 else "profile"),
        "tasks": tasks
    }
    return {"deep_risk": bool(deep_risk), "skill_plan": plan, "profile_name": profile_name, "profile": profile}

def skill_execute_node(state: CognitiveState):
    """
    Execute selected skills if upstream modules didn't provide results.
    """
    plan = state.get("skill_plan", {}) if isinstance(state.get("skill_plan", {}), dict) else {}
    tasks = plan.get("tasks", []) if isinstance(plan.get("tasks"), list) else []
    if not tasks:
        return {}

    code = state.get("stock_code")
    try:
        df = data_master.get_history(code, days=250)
    except Exception:
        df = None

    out = {}
    if "dealer_hunter" in tasks and not state.get("dealer_hunter"):
        try:
            out["dealer_hunter"] = _hunter.analyze(df)
        except Exception:
            out["dealer_hunter"] = None
    if "chip_analyst" in tasks and not state.get("chip_analyst"):
        try:
            out["chip_analyst"] = _chip.analyze(df)
        except Exception:
            out["chip_analyst"] = None
    if "cycle_compass" in tasks and not state.get("cycle_compass"):
        try:
            out["cycle_compass"] = _cycle.detect_phase(df)
        except Exception:
            out["cycle_compass"] = None
    if "liquidity_guard" in tasks and not state.get("liquidity_guard"):
        try:
            out["liquidity_guard"] = _liq.check(df)
        except Exception:
            out["liquidity_guard"] = None
    if "sentiment_weather" in tasks and not state.get("sentiment_weather"):
        try:
            out["sentiment_weather"] = _sentiment.get_weather_report()
        except Exception:
            out["sentiment_weather"] = {}
    if "news_verifier" in tasks and not state.get("news_check"):
        try:
            out["news_check"] = _news_verifier.check_divergence(df, state.get("news_data", []))
        except Exception:
            out["news_check"] = None

    return out

def planner_node(state: CognitiveState):
    """
    Planner: build a skill plan based on profile + heuristics.
    """
    out = skill_router_node(state)
    plan = out.get("skill_plan", {}) if isinstance(out.get("skill_plan", {}), dict) else {}
    plan["planner"] = "heuristic_v1"
    out["skill_plan"] = plan
    # auto build tool tasks (e.g., news fetch)
    tool_tasks = []
    existing = state.get("tool_tasks")
    if isinstance(existing, list):
        tool_tasks.extend(existing)
    try:
        if should_fetch(state):
            tool_tasks.extend(build_news_tool_tasks(state))
    except Exception:
        pass
    if tool_tasks:
        valid_tasks, _ = sanitize_tool_tasks(tool_tasks)
        out["tool_tasks"] = valid_tasks
    return out

def executor_node(state: CognitiveState):
    """
    Executor: run skills based on planner output.
    """
    return skill_execute_node(state)

def critic_node(state: CognitiveState):
    """
    Critic: sanity checks and cross-skill risk flags.
    """
    score = 0
    flags = []

    dh = state.get("dealer_hunter")
    if isinstance(dh, dict):
        try:
            rs = float(dh.get("risk_score", 0) or 0)
            if rs >= 60:
                score += 30
                flags.append("dealer_high_risk")
            elif rs >= 25:
                score += 15
                flags.append("dealer_mid_risk")
        except Exception:
            pass

    lg = state.get("liquidity_guard")
    if isinstance(lg, dict) and lg.get("is_zombie"):
        score += 40
        flags.append("liquidity_zombie")

    nv = state.get("news_check")
    news_neg = False
    if isinstance(nv, dict):
        try:
            ds = float(nv.get("divergence_score", 0) or 0)
            if ds < 0:
                score += 20
                flags.append("news_divergence_negative")
                news_neg = True
        except Exception:
            pass

    cc = state.get("cycle_compass")
    if isinstance(cc, dict):
        try:
            imp = float(cc.get("score_impact", 0) or 0)
            if imp <= -50:
                score += 50
                flags.append("cycle_phase4")
            elif imp <= -10:
                score += 20
                flags.append("cycle_weak")
        except Exception:
            pass

    sw = state.get("sentiment_weather")
    sentiment_cold = False
    if isinstance(sw, dict):
        weather = str(sw.get("weather", ""))
        try:
            temp = float(sw.get("temperature", 0) or 0)
        except Exception:
            temp = 0.0
        cold_markers = ["\u51b7", "\u5bd2", "\u51b0", "\u96ea"]
        is_cold = temp <= 30 or any(marker in weather for marker in cold_markers)
        if is_cold:
            score += 15
            flags.append("sentiment_cold")
            sentiment_cold = True

    # liquidity mid-risk: weak turnover but not zombie
    if isinstance(lg, dict) and not lg.get("is_zombie"):
        try:
            amount_w = float(lg.get("amount_w", 0) or 0)
            if amount_w > 0 and amount_w < 8000:
                score += 10
                flags.append("liquidity_weak")
        except Exception:
            pass

    # combo bonus: news divergence + sentiment cold
    if news_neg and sentiment_cold:
        score += 5
        flags.append("news_sentiment_combo")


    if score >= 50:
        level = "high"
    elif score >= 15:
        level = "medium"
    else:
        level = "low"

    block_trade = True if score >= 70 else False
    return {"critic_report": {"score": score, "level": level, "flags": flags, "block_trade": block_trade}}

def _build_context_tags(state: CognitiveState):
    tags = []
    market = state.get("market_data", {}) or {}
    tech = state.get("tech_factors", {}) or {}
    dq = state.get("data_quality", {}) or {}

    try:
        price = float(market.get("latest_price", 0) or 0)
    except Exception:
        price = 0.0
    try:
        atr = float(tech.get("atr", 0) or 0)
    except Exception:
        atr = 0.0
    vol_pct = (atr / price) if price > 0 else 0.0
    if vol_pct >= 0.08:
        tags.append("vol_high")
    elif vol_pct >= 0.05:
        tags.append("vol_mid")
    else:
        tags.append("vol_low")

    try:
        pct_chg = float(market.get("pct_chg", 0) or 0)
    except Exception:
        pct_chg = 0.0
    if pct_chg >= 5:
        tags.append("strong_up")
    elif pct_chg <= -5:
        tags.append("strong_down")

    try:
        ma20 = float(tech.get("boll_mid", 0) or 0)
    except Exception:
        ma20 = 0.0
    if price > 0 and ma20 > 0:
        tags.append("above_ma20" if price >= ma20 else "below_ma20")

    cycle = state.get("cycle_compass")
    if isinstance(cycle, dict):
        phase = str(cycle.get("phase", "") or "")
        if phase:
            tags.append(phase.replace(" ", "").replace("(", "_").replace(")", "").lower())
        try:
            imp = float(cycle.get("score_impact", 0) or 0)
            if imp <= -50:
                tags.append("cycle_risk_high")
            elif imp <= -10:
                tags.append("cycle_risk_mid")
            elif imp >= 20:
                tags.append("cycle_trend_strong")
        except Exception:
            pass

    sentiment = state.get("sentiment_weather")
    if isinstance(sentiment, dict):
        try:
            temp = float(sentiment.get("temperature", 0) or 0)
        except Exception:
            temp = 0.0
        if temp >= 60:
            tags.append("sentiment_hot")
        elif temp <= 30:
            tags.append("sentiment_cold")

    lg = state.get("liquidity_guard")
    if isinstance(lg, dict) and lg.get("is_zombie"):
        tags.append("liquidity_low")

    nv = state.get("news_check")
    if isinstance(nv, dict):
        try:
            ds = float(nv.get("divergence_score", 0) or 0)
            if ds < 0:
                tags.append("news_divergence_neg")
            elif ds > 0:
                tags.append("news_divergence_pos")
        except Exception:
            pass

    if dq.get("stale"):
        tags.append("data_stale")

    prof = state.get("profile_name")
    if prof:
        tags.append(f"profile_{prof}")

    return tags

def _clip_text(val, limit=600):
    if val is None:
        return ""
    try:
        text = str(val).strip()
    except Exception:
        return ""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."

def _to_text(val, limit=600):
    if isinstance(val, (dict, list)):
        try:
            return _clip_text(json.dumps(val, ensure_ascii=False), limit=limit)
        except Exception:
            return _clip_text(val, limit=limit)
    return _clip_text(val, limit=limit)

def tool_bridge_node(state: CognitiveState):
    tasks = state.get("tool_tasks") or state.get("composio_tasks")
    if not isinstance(tasks, list) or not tasks:
        return {}
    tasks, _ = sanitize_tool_tasks(tasks)

    from core.capability_registry import get_capability
    from core.tool_registry import call_tool, get_registry

    needs_composio = False
    needs_browser_use = False
    for task in tasks:
        if not isinstance(task, dict):
            continue
        tool_name = str(task.get("tool") or task.get("tool_name") or "").strip()
        kind = str(task.get("kind") or task.get("type") or "").strip().lower()
        if tool_name.startswith("composio_") or kind == "composio":
            needs_composio = True
            break
        if tool_name.startswith("browser_use") or kind == "browser_use":
            needs_browser_use = True

    if needs_composio:
        cap = get_capability("tools", "composio")
        if not isinstance(cap, dict) or not cap.get("enabled"):
            return {"tool_results": [{"tool": "composio", "ok": False, "error": "capability_disabled"}]}
        reg = get_registry()
        if not reg.has_tool("composio_execute"):
            try:
                from core.composio_adapter import register_composio_tools
                register_composio_tools(reg)
            except Exception:
                pass
    if needs_browser_use:
        cap = get_capability("tools", "browser_use")
        if not isinstance(cap, dict) or not cap.get("enabled"):
            return {"tool_results": [{"tool": "browser_use", "ok": False, "error": "capability_disabled"}]}
        reg = get_registry()
        if not reg.has_tool("browser_use_run"):
            try:
                register_browser_use_tool(reg)
            except Exception:
                pass

    results = []
    merged_news = state.get("news_data") if isinstance(state.get("news_data"), list) else []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        tool_name = str(task.get("tool") or task.get("tool_name") or "").strip()
        args = task.get("args")
        result = None
        if tool_name:
            result = call_tool(tool_name, args=args, caller="tool_bridge")
        else:
            kind = str(task.get("kind") or task.get("type") or "").strip().lower()
            if kind == "composio":
                action = str(task.get("action") or "").strip().lower()
                if action in ("list", "get", "discover"):
                    args = {
                        "toolkits": task.get("toolkits"),
                        "tools": task.get("tools"),
                        "search": task.get("search"),
                        "limit": task.get("limit"),
                        "user_id": task.get("user_id")
                    }
                    result = call_tool("composio_list_tools", args=args, caller="tool_bridge")
                else:
                    args = {
                        "tool": task.get("name") or task.get("composio_tool") or task.get("tool_name"),
                        "arguments": task.get("arguments") or task.get("params") or task.get("args") or {},
                        "user_id": task.get("user_id")
                    }
                    result = call_tool("composio_execute", args=args, caller="tool_bridge")
            elif kind == "browser_use":
                args = {
                    "task": task.get("task") or task.get("prompt") or task.get("query"),
                    "max_steps": task.get("max_steps"),
                    "headless": task.get("headless", True),
                    "use_cloud": task.get("use_cloud", False)
                }
                result = call_tool("browser_use_run", args=args, caller="tool_bridge")
        if isinstance(result, dict):
            results.append({
                "tool": result.get("tool"),
                "ok": result.get("ok"),
                "error": result.get("error"),
                "data": result.get("data")
            })
            if task.get("map_to") == "news_data" and result.get("ok"):
                max_items = task.get("max_items")
                try:
                    items = extract_news_items(result.get("data"), max_items=max_items)
                except Exception:
                    items = []
                if items:
                    merged_news = merge_news(
                        merged_news,
                        items,
                        mode=task.get("merge") or "prepend",
                        max_items=max_items
                    )

    if not results:
        return {}
    out = {"tool_results": results}
    if merged_news:
        out["news_data"] = merged_news
    return out

def autogen_review_node(state: CognitiveState):
    from core.capability_registry import get_capability
    cap = get_capability("orchestrators", "autogen")
    if not isinstance(cap, dict) or not cap.get("enabled"):
        return {}

    from core.tool_registry import call_tool, get_registry
    reg = get_registry()
    if not reg.has_tool("autogen_run"):
        try:
            from core.autogen_orchestrator import register_autogen_tool
            register_autogen_tool(reg)
        except Exception:
            pass

    code = str(state.get("stock_code") or "").strip()
    prompt = "\n".join([
        "你是独立复核员，请基于以下信息给出简短复核：",
        f"标的: {code}",
        f"技术: {_to_text(state.get('technical_analysis'), limit=400)}",
        f"资金: {_to_text(state.get('capital_analysis'), limit=200)}",
        f"筹码: {_to_text(state.get('chip_data'), limit=200)}",
        f"新闻: {_to_text(state.get('news_analysis'), limit=300)}",
        f"记忆: {_to_text(state.get('memory_context'), limit=300)}",
        f"知识: {_to_text(state.get('knowledge_context'), limit=300)}",
        f"critic: {_to_text(state.get('critic_report'), limit=200)}",
        "输出要求: 1句结论 + 3条风险点 + 1条动作建议(BUY/SELL/HOLD/KEEP)。"
    ]).strip()
    if not prompt:
        return {}
    result = call_tool(
        "autogen_run",
        args={
            "prompt": prompt,
            "system_prompt": "你是冷静的复核审计员，输出务必简洁、明确。",
            "max_turns": 1,
            "temperature": 0.2
        },
        caller="autogen_review"
    )
    if not isinstance(result, dict) or not result.get("ok"):
        return {}
    data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
    output = data.get("output") or data.get("result") or ""
    output = _clip_text(output, limit=800)
    if not output:
        return {}
    return {"autogen_review": output}

def letta_memory_node(state: CognitiveState):
    from core.capability_registry import get_capability
    cap = get_capability("memory", "letta")
    if not isinstance(cap, dict) or not cap.get("enabled"):
        return {}
    try:
        hint = read_semantic()
    except Exception:
        hint = ""
    if not hint:
        return {}
    return {"letta_context": hint}

def _extract_strategy_info(signal_source):
    info = {"strategy": "", "strategies": [], "strategy_votes": [], "strategy_weight": None}
    if not isinstance(signal_source, dict):
        return info
    primary = signal_source.get("strategy")
    if isinstance(primary, str) and primary.strip():
        info["strategy"] = primary.strip()
        info["strategies"].append(info["strategy"])
    strategies = signal_source.get("strategies")
    if isinstance(strategies, list):
        for s in strategies:
            if isinstance(s, str) and s.strip():
                info["strategies"].append(s.strip())
    elif isinstance(strategies, str) and strategies.strip():
        info["strategies"].append(strategies.strip())
    votes = signal_source.get("strategy_votes") or signal_source.get("votes")
    if isinstance(votes, list):
        for v in votes[:6]:
            if not isinstance(v, dict):
                continue
            name = v.get("strategy") or v.get("name")
            weight = v.get("weight")
            info["strategy_votes"].append({
                "strategy": name,
                "weight": weight,
                "reason": v.get("reason")
            })
        if not info["strategy"]:
            best = None
            best_w = None
            for v in votes:
                if not isinstance(v, dict):
                    continue
                name = v.get("strategy") or v.get("name")
                w = v.get("weight", 0)
                try:
                    w = float(w)
                except Exception:
                    w = 0.0
                if name and (best_w is None or w > best_w):
                    best = name
                    best_w = w
            if best:
                info["strategy"] = str(best).strip()
                info["strategy_weight"] = best_w
                info["strategies"].append(info["strategy"])
    # de-dup strategies
    seen = set()
    uniq = []
    for s in info["strategies"]:
        if not s or s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    info["strategies"] = uniq
    return info

def analysis_node(state: CognitiveState):
    code = state['stock_code']
    
    # 1. 记忆与知识库
    mem_ctx = memory.retrieve_context(code, query_text=state['technical_analysis'])
    kb_ctx = state.get("knowledge_context")
    kb_titles = state.get("knowledge_titles")
    kb_items = state.get("knowledge_items")
    
    # 2. 宏观
    news_list = state.get('news_data', []) or []
    macro_list = state.get('macro_news', []) or []
    news_str = "\n".join(news_list[:3]) if news_list else ""
    macro_str = "\n".join(macro_list[:3]) if macro_list else ""
    kb_news_str = "\n".join((news_list + macro_list)[:3]) if (news_list or macro_list) else ""

    if not kb_ctx or not isinstance(kb_ctx, str) or (not kb_titles and not kb_items):
        md = state.get("market_data", {}) or {}
        kb_query = " ".join([
            str(state.get("technical_analysis", "") or ""),
            str(md.get("index_context", "") or ""),
            str(md.get("sector_context", "") or ""),
            str(md.get("stock_name", "") or ""),
            kb_news_str
        ]).strip()
        kb_pack = kb.build_context(kb_query, limit=5)
        kb_ctx = kb_pack.get("context")
        if not kb_titles:
            kb_titles = kb_pack.get("titles", [])
        if not kb_items:
            kb_items = kb_pack.get("items", [])
    
    # 3. 资金
    cap = state.get('capital_data', {})
    net_flow = cap.get('net_mf_amount', 0)
    
    # 4. 强制读取最新持仓
    current_portfolio = VirtualPortfolio("data/real_portfolio.json")
    funds = current_portfolio.get_fund_info()
    
    # 智能匹配
    pos = current_portfolio.get_specific_position(code)
    if not pos:
        target_digits = ''.join(filter(str.isdigit, str(code)))
        all_pos = current_portfolio.get_all_positions()
        for k, v in all_pos.items():
            if ''.join(filter(str.isdigit, str(k))) == target_digits:
                pos = v
                break

    pos_str = f"可用资金 {funds.get('principal', 0):.0f}。"
    user_pos_data = {}
    
    if pos and pos.get('volume', 0) > 0:
        vol = pos.get('volume', 0)
        cost = pos.get('cost', 0.0)
        current_price = state['market_data']['latest_price']
        
        profit = (current_price - cost) * vol
        pct = (current_price - cost) / cost * 100 if cost > 0 else 0
        
        pos_str += f" 【系统已锁定持仓】: {vol}股, 成本 {cost:.2f}。浮动盈亏 {profit:.0f} ({pct:.1f}%)。"
        user_pos_data = {
            "code": code, "volume": vol, "cost": cost, "profit": profit, "profit_pct": pct
        }
    else: 
        pos_str += " 目前无持仓。"

    # --- 📐 Python 硬核计算网格 ---
    curr_p = state['market_data']['latest_price']
    tf = state.get('tech_factors', {})
    ma20 = tf.get('boll_mid', curr_p)
    atr = tf.get('atr', curr_p * 0.02)
    
    calc_grid = _calculate_python_grid(curr_p, ma20, atr, user_pos_data, adapt=None)

    extra_ref = {}
    extra_feat = {}
    extra_macro = {}
    if state.get("deep_risk"):
        try:
            extra_ref = data_master.get_reference_pack(code)
            extra_feat = data_master.get_feature_pack(code)
            extra_macro = data_master.get_macro_pack()
        except Exception:
            pass

    # attach basic factor snapshot for learning/attribution
    factor_snapshot = {
        "tech_factors": state.get("tech_factors", {}),
        "capital_data": state.get("capital_data", {}),
        "chip_data": state.get("chip_data", {}),
        "news_data": state.get("news_data", [])[:3],
        "fundamental": state.get("fundamental_data", {})
    }

    return {
        "memory_context": mem_ctx,
        "knowledge_context": kb_ctx,
        "knowledge_titles": kb_titles or [],
        "knowledge_items": kb_items or [],
        "fundamental_analysis": f"PE: {state['fundamental_data'].get('PE', 'N/A')}",
        "news_analysis": macro_str or news_str,
        "macro_news": macro_list,
        "capital_analysis": f"主力净流: {net_flow}",
        "technical_analysis": state['technical_analysis'],
        "position_context": pos_str,
        "user_position": user_pos_data,
        "user_funds": funds,
        "calculated_grid": calc_grid, # 🔥 传递硬算结果
        "reference_pack": extra_ref,
        "feature_pack": extra_feat,
        "macro_pack": extra_macro,
        "factor_snapshot": factor_snapshot
    }

def decision_node(state: CognitiveState):
    def _trim_list(val, n=5):
        if isinstance(val, list):
            return val[:n]
        return val

    def _trim_dict_lists(d, n=5):
        if not isinstance(d, dict):
            return d
        out = {}
        for k, v in d.items():
            if isinstance(v, list):
                out[k] = v[:n]
            else:
                out[k] = v
        return out

    def _select_top_moneyflow(mf):
        if isinstance(mf, dict):
            return mf
        if isinstance(mf, list):
            try:
                mf = sorted(mf, key=lambda x: x.get("net_amount", 0), reverse=True)
            except Exception:
                pass
            return mf[:3]
        return mf

    def _select_top_concepts(concepts):
        if not isinstance(concepts, list):
            return concepts
        # keep small subset
        return concepts[:5]

    def _select_research(reports):
        if not isinstance(reports, list):
            return reports
        return reports[:3]

    def _compress_features(feat_raw):
        if not isinstance(feat_raw, dict):
            return feat_raw
        return {
            "concept_members": _select_top_concepts(feat_raw.get("concept_members", [])),
            "moneyflow_hsgt": _select_top_moneyflow(feat_raw.get("moneyflow_hsgt", [])),
            "moneyflow_industry": _select_top_moneyflow(feat_raw.get("moneyflow_industry", [])),
            "chip": feat_raw.get("chip", {}),
            "factors": _trim_list(feat_raw.get("factors", []), n=3),
            "forecast": _trim_list(feat_raw.get("forecast", []), n=3),
            "research": _select_research(feat_raw.get("research", [])),
            "auction": _trim_list(feat_raw.get("auction", []), n=3)
        }

    def _kb_adjust(items):
        if not items:
            return 0.0, ""
        score = 0.0
        used = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
            pnl_count = int(stats.get("pnl_count", 0) or 0)
            pnl_sum = float(stats.get("pnl_sum", 0) or 0)
            wins = int(stats.get("wins", 0) or 0)
            losses = int(stats.get("losses", 0) or 0)
            if pnl_count <= 0 and (wins + losses) <= 0:
                continue
            used += 1
            if pnl_count > 0:
                avg_pnl = pnl_sum / pnl_count
                score += max(-2.0, min(2.0, avg_pnl / 1000.0))
                win_rate = wins / pnl_count if pnl_count else 0.0
                score += (win_rate - 0.5) * 4.0
            else:
                total = wins + losses
                win_rate = wins / total if total else 0.0
                score += (win_rate - 0.5) * 2.0
        if used <= 0:
            return 0.0, ""
        score = score / max(1, used)
        score = max(-3.0, min(3.0, score))
        return score, f"kb_effect={score:.2f}"

    deep = bool(state.get("deep_risk"))
    ref = _trim_dict_lists(state.get("reference_pack", {}), n=3) if deep else {}
    feat_raw = state.get("feature_pack", {}) if deep else {}
    feat = _compress_features(feat_raw) if deep else {}
    macro = _trim_dict_lists(state.get("macro_pack", {}), n=3) if deep else {}

    context_tags = _build_context_tags(state)
    context = {
        "macro_env": state.get('news_analysis'),
        "macro_news": _trim_list(state.get('macro_news', []), n=5),
        "macro_data": macro,
        "market_tech": state.get('technical_analysis'),
        "tech_factors": state.get('tech_factors'),
        "market_data": state.get('market_data', {}),
        "context_tags": context_tags,
        "position_info": state.get('position_context'),
        "user_position_detail": state.get('user_position', {}),
        "user_fund_detail": state.get('user_funds', {}),
        "capital": state.get('capital_data', {}),
        "chip": state.get('chip_data', {}),
        "dealer_hunter": state.get('dealer_hunter'),
        "chip_analyst": state.get('chip_analyst'),
        "liquidity_guard": state.get('liquidity_guard'),
        "cycle_compass": state.get('cycle_compass'),
        "sentiment_weather": state.get('sentiment_weather'),
        "news": _trim_list(state.get('news_data', []), n=5),
        "news_check": state.get("news_check"),
        "fundamental": state.get('fundamental_data', {}),
        "reference": ref,
        "features": feat,
        "morning_briefing_guidance": state.get('morning_strategy', '无早盘指导'),
        "memory": state.get('memory_context'),
        "knowledge_base": state.get('knowledge_context'),
        "knowledge_titles": _trim_list(state.get('knowledge_titles', []), n=5),
        "knowledge_items": _trim_list(state.get('knowledge_items', []), n=3),
        "critic_report": state.get("critic_report", {}),
        "tool_results": _trim_list(state.get("tool_results", []), n=3),
        "agent_review": state.get("autogen_review"),
        "semantic_hint": state.get("letta_context")
    }
    rules = memory.get_rules()
    debate = council.debate(context, custom_rules=rules, mode="stock")

    # ensure scores contain all six factors
    try:
        scores = debate.get("scores", {}) if isinstance(debate, dict) else {}
        if not isinstance(scores, dict):
            scores = {}
        required = ["capital", "technical", "macro", "news", "memory", "knowledge", "total", "reason"]
        missing = [k for k in required if k not in scores]
        if missing:
            defaults = {
                "capital": 50, "technical": 50, "macro": 50, "news": 50,
                "memory": 50, "knowledge": 50, "total": 50, "reason": ""
            }
            for k in missing:
                scores[k] = defaults.get(k, 50 if k != "reason" else "")
            debate["scores"] = scores
            debate.setdefault("policy_notes", []).append("scores_missing_filled")
            debate["scores_missing"] = missing
    except Exception:
        pass

    # factor usage snapshot (for debug / linkage)
    try:
        factor_usage = {
            "capital": bool(state.get("capital_data")),
            "technical": bool(state.get("tech_factors")),
            "macro": bool(state.get("news_analysis") or state.get("macro_news") or state.get("global_index")),
            "news": bool(state.get("news_data")),
            "memory": bool(state.get("memory_context")),
            "knowledge": bool(state.get("knowledge_context"))
        }
        debate["factor_usage"] = factor_usage
    except Exception:
        pass

    # apply learned weight bias from recent outcomes
    try:
        bias_pack = load_bias()
        bias = bias_pack.get("bias") if isinstance(bias_pack, dict) else {}
    except Exception:
        bias = {}
    if isinstance(bias, dict) and bias:
        fw = debate.get("feature_weights", {}) if isinstance(debate.get("feature_weights"), dict) else {}
        if fw:
            # apply bias and renormalize
            adjusted = {}
            for k, v in fw.items():
                try:
                    base = float(v)
                except Exception:
                    base = 0.0
                delta = float(bias.get(k, 0) or 0)
                adjusted[k] = max(0.0, base + delta)
            total = sum(adjusted.values())
            if total > 0:
                adjusted = {k: round(v / total * 100) for k, v in adjusted.items()}
            debate["feature_weights"] = adjusted
            debate["weight_bias"] = bias
            try:
                record_feature_weights(adjusted)
            except Exception:
                pass

    # 🔥 结果融合：将 Python 算好的网格强行注入
    # 自适应网格（根据因子权重收紧/放宽）
    adaptive_grid = None
    try:
        fw = debate.get("feature_weights", {})
        if isinstance(fw, dict) and fw:
            curr_p = (state.get("market_data", {}) or {}).get("latest_price", 0)
            tf = state.get("tech_factors", {}) or {}
            ma20 = tf.get("boll_mid", curr_p)
            atr = tf.get("atr", curr_p * 0.02)
            adapt = {
                "technical": fw.get("technical", 0),
                "capital": fw.get("capital", 0),
                "risk": fw.get("reference", 0)
            }
            adaptive_grid = _calculate_python_grid(curr_p, ma20, atr, state.get("user_position", {}), adapt=adapt)
    except Exception:
        adaptive_grid = None

    if 'grid_strategy' not in debate or not debate['grid_strategy']:
        debate['grid_strategy'] = adaptive_grid or state['calculated_grid']
    else:
        # 如果 LLM 没算出卖点但我们有持仓，强行补上卖点
        if not debate['grid_strategy'].get('sell1_price') and state['user_position']:
            debate['grid_strategy'] = adaptive_grid or state['calculated_grid']
        # 如果 LLM 没算出买点，也补上
        if not debate['grid_strategy'].get('buy1_price'):
             src = adaptive_grid or state['calculated_grid']
             debate['grid_strategy']['buy1_price'] = src['buy1_price']
             debate['grid_strategy']['buy1_action'] = src['buy1_action']

    suggested_action = str(debate.get('action', 'HOLD')).upper()
    if suggested_action not in ["BUY", "SELL", "HOLD"]:
        suggested_action = "HOLD"
    debate["suggested_action"] = suggested_action
    action = suggested_action
    policy_notes = []

    # If weights and scores conflict, downgrade aggressive action
    try:
        fw = debate.get("feature_weights", {})
        scores = debate.get("scores", {})
        if isinstance(fw, dict) and isinstance(scores, dict):
            tech_w = float(fw.get("technical", 0) or 0)
            cap_w = float(fw.get("capital", 0) or 0)
            tech_s = float(scores.get("technical", 0) or 0)
            cap_s = float(scores.get("capital", 0) or 0)
            # high weight but low score => inconsistency
            if (tech_w >= 20 and tech_s < 45) or (cap_w >= 20 and cap_s < 45):
                if action == "BUY":
                    action = "HOLD"
                    policy_notes.append("weights_score_conflict")
    except Exception:
        pass

    # Adaptive stop-loss guidance based on weights
    try:
        fw = debate.get("feature_weights", {})
        if isinstance(fw, dict):
            risk_w = float(fw.get("reference", 0) or 0)
            tech_w = float(fw.get("technical", 0) or 0)
            # higher risk weight => tighter stop
            if "risk" not in debate:
                debate["risk"] = {}
            if "stop_policy" not in debate["risk"]:
                if risk_w >= 20:
                    debate["risk"]["stop_policy"] = "tight"
                elif tech_w >= 20:
                    debate["risk"]["stop_policy"] = "normal"
                else:
                    debate["risk"]["stop_policy"] = "wide"
    except Exception:
        pass

    # Weight-driven action thresholds
    try:
        fw = debate.get("feature_weights", {})
        scores = debate.get("scores", {})
        total = float(scores.get("total", 50) or 50)
        if isinstance(fw, dict):
            tech_w = float(fw.get("technical", 0) or 0)
            cap_w = float(fw.get("capital", 0) or 0)
            risk_w = float(fw.get("reference", 0) or 0)

            # Dynamic buy threshold
            buy_threshold = 60 + (risk_w * 0.2) - (tech_w * 0.1) - (cap_w * 0.1)
            buy_threshold = max(55, min(75, buy_threshold))
            # Knowledge effect
            kb_score, kb_reason = _kb_adjust(state.get("knowledge_items", []))
            if kb_score:
                buy_threshold -= kb_score
                debate.setdefault("knowledge_adjust", {})["score"] = kb_score
                debate["knowledge_adjust"]["reason"] = kb_reason

            # Profile bias
            profile_name = state.get("profile_name")
            if profile_name == "保守":
                buy_threshold += 3
            elif profile_name == "激进":
                buy_threshold -= 3
            if action == "BUY" and total < buy_threshold:
                action = "HOLD"
                policy_notes.append("below_buy_threshold")

            # Dynamic sell threshold (only soften when confidence is not low)
            sell_threshold = 45 + (tech_w + cap_w) * 0.1
            sell_threshold = max(40, min(60, sell_threshold))
            if profile_name == "保守":
                sell_threshold -= 2
            elif profile_name == "激进":
                sell_threshold += 2
            if action == "SELL" and total > sell_threshold and risk_w < 20:
                action = "HOLD"
                policy_notes.append("above_sell_threshold")
    except Exception:
        pass

    # Critic override
    try:
        critic = state.get("critic_report", {}) or {}
        if bool(critic.get("block_trade")) and action == "BUY":
            action = "HOLD"
            policy_notes.append("critic_block_trade")
    except Exception:
        pass

    # No position => cannot sell
    try:
        pos = state.get("user_position", {}) or {}
        if action == "SELL" and (not pos or pos.get("volume", 0) <= 0):
            action = "HOLD"
            policy_notes.append("no_position")
    except Exception:
        pass

    debate["policy_action"] = action
    if policy_notes:
        debate["policy_notes"] = policy_notes

    decision_sample = build_decision_sample(
        debate=debate,
        action=action,
        suggested_action=suggested_action,
        signal_source=state.get("signal_source"),
        context_tags=context_tags,
        policy_notes=policy_notes,
    )
    debate["decision_sample"] = decision_sample

    # Experience logging
    decision_id = None
    try:
        decision_id = experience.log_decision({
            "code": state.get("stock_code"),
            "action": action,
            "suggested_action": suggested_action,
            "scores": debate.get("scores", {}),
            "feature_weights": debate.get("feature_weights", {}),
            "risk": debate.get("risk", {}),
            "knowledge_titles": state.get("knowledge_titles", []),
            "profile": state.get("profile_name"),
            "signal_source": state.get("signal_source"),
            "data_quality": state.get("data_quality"),
            "market_data": state.get("market_data", {}),
            "factor_snapshot": state.get("factor_snapshot", {}),
            "policy_notes": policy_notes,
            "decision_sample": decision_sample
        })
    except Exception:
        decision_id = None

    if not decision_id:
        decision_id = _fallback_decision_id(state.get("stock_code"))

    if decision_id:
        debate["decision_id"] = decision_id
    # Unified event bus
    try:
        proto_version = get_protocol_version()
        decision_payload = {
            "action": action,
            "suggested_action": suggested_action,
            "scores": debate.get("scores", {}),
            "feature_weights": debate.get("feature_weights", {}),
            "factor_usage": debate.get("factor_usage", {}),
            "scores_missing": debate.get("scores_missing", []),
            "risk": debate.get("risk", {}),
            "context_tags": context_tags,
            "knowledge_titles": state.get("knowledge_titles", []),
            "profile": state.get("profile_name"),
            "signal_source": state.get("signal_source"),
            "data_quality": state.get("data_quality"),
            "market_data": state.get("market_data", {}),
            "factor_snapshot": state.get("factor_snapshot", {}),
            "policy_notes": policy_notes,
            "decision_sample": decision_sample,
            "protocol_version": proto_version
        }
        decision_payload = ensure_decision_sample(decision_payload, fallback_sample=decision_sample)
        ok, errs = validate_decision_payload(decision_payload)
        if not ok:
            warn("protocol.decision_payload_invalid", {"errors": errs})
        event_bus.log(
            "decision",
            payload=decision_payload,
            code=state.get("stock_code"),
            decision_id=decision_id,
            source="cognitive_graph"
        )
    except Exception:
        pass
    # Knowledge analysis snapshot for learning loop
    try:
        k_titles = state.get("knowledge_titles", []) or []
        if k_titles:
            strat_info = _extract_strategy_info(state.get("signal_source"))
            log_event(
                "analysis_run",
                payload={
                    "code": state.get("stock_code"),
                    "decision_id": decision_id,
                    "action": action,
                    "suggested_action": suggested_action,
                    "strategy": strat_info.get("strategy"),
                    "strategies": strat_info.get("strategies", []),
                    "strategy_votes": strat_info.get("strategy_votes", []),
                    "strategy_weight": strat_info.get("strategy_weight"),
                    "knowledge_titles": k_titles,
                    "profile": state.get("profile_name"),
                    "context_tags": context_tags,
                    "env_tags": context_tags
                },
                meta={"source": "cognitive_graph"}
            )
    except Exception:
        pass
    # Memory snapshot (only when actionable)
    if action in ("BUY", "SELL"):
        try:
            price = (state.get("market_data", {}) or {}).get("latest_price", 0)
        except Exception:
            price = 0
        try:
            memory.save_episode(
                state.get("stock_code"),
                action,
                price,
                {
                    "core_view": debate.get("core_view", ""),
                    "scores": debate.get("scores", {}),
                    "risk": debate.get("risk", {}),
                    "decision_id": decision_id,
                    "suggested_action": suggested_action,
                    "policy_action": action,
                    "signal_source": state.get("signal_source"),
                    "context_tags": context_tags,
                    "profile": state.get("profile_name"),
                    "policy_notes": policy_notes
                },
                manual_teach=False
            )
        except Exception:
            pass
        try:
            # semantic memory writeback (L2)
            write_semantic_from_state(
                {**state, "context_tags": context_tags},
                debate=debate
            )
        except Exception:
            pass
    # Optional: adaptive threshold update
    try:
        from core.threshold_adaptor import maybe_update_overrides
        maybe_update_overrides()
    except Exception:
        pass
    return {"decision_id": decision_id, "trading_signal": {"action": action, "details": debate, "decision_id": decision_id}}

def _calc_risk(state: CognitiveState):
    score = 0
    reasons = []
    market = state.get("market_data", {}) or {}
    tech = state.get("tech_factors", {}) or {}
    cap = state.get("capital_data", {}) or {}
    pos = state.get("user_position", {}) or {}
    funds = state.get("user_funds", {}) or {}
    deep = bool(state.get("deep_risk"))
    dq = state.get("data_quality", {}) or {}

    price = market.get("latest_price", 0) or 0
    atr = tech.get("atr", 0) or 0
    ma20 = tech.get("boll_mid", 0) or 0
    last_date = market.get("last_date")
    trade_allowed = True

    if price <= 0:
        score += 10
        reasons.append("价格数据异常")

    # data quality
    try:
        rows = int(dq.get("rows", 0) or 0)
    except Exception:
        rows = 0
    if rows and rows < 60:
        score += 10
        reasons.append("历史数据不足(<60)")
        if rows < 30:
            score += 10
            trade_allowed = False
            reasons.append("历史数据过少，暂停交易")
    if dq.get("stale"):
        score += 15
        reasons.append("数据滞后")
        try:
            if int(dq.get("stale_days", 0) or 0) >= 7:
                trade_allowed = False
        except Exception:
            pass

    # 交易日历/停牌过滤 (简单基于最新交易日)
    if last_date:
        try:
            last_dt = datetime.datetime.strptime(last_date, "%Y-%m-%d").date()
            delta_days = (datetime.date.today() - last_dt).days
            if delta_days >= 7:
                score += 30
                reasons.append("最新交易日过久，疑似停牌/数据中断")
                trade_allowed = False
            elif delta_days >= 4:
                score += 15
                reasons.append("数据非最新交易日")
        except Exception:
            pass

    # 交易日历校验（仅深度风控）
    if deep:
        try:
            last_open = data_master.get_last_trade_date()
            if last_open and last_date:
                last_dt = datetime.datetime.strptime(last_date, "%Y-%m-%d").date()
                if last_dt < last_open:
                    score += 10
                    reasons.append("非最新交易日，可能停牌或未更新")
                    trade_allowed = False
        except Exception:
            pass

    if price > 0 and atr > 0:
        vol_pct = atr / price
        if vol_pct > 0.08:
            score += 20
            reasons.append("波动率过高")
        elif vol_pct > 0.05:
            score += 10
            reasons.append("波动率偏高")

    if price > 0 and ma20 > 0 and price < ma20 * 0.95:
        score += 10
        reasons.append("below ema mid >5%")

    net_flow = cap.get("net_mf_amount", 0) or 0
    if net_flow < -200000:
        score += 20
        reasons.append("主力净流出异常")
    elif net_flow < -50000:
        score += 10
        reasons.append("主力净流出")

    # critic risk overlay
    critic = state.get("critic_report", {}) or {}
    try:
        cscore = float(critic.get("score", 0) or 0)
    except Exception:
        cscore = 0.0
    if cscore >= 70:
        score += 20
        trade_allowed = False
        reasons.append("审查风险过高")
    elif cscore >= 40:
        score += 10
        reasons.append("审查风险偏高")
    try:
        if bool(critic.get("block_trade")):
            trade_allowed = False
            reasons.append("审查阻止交易")
    except Exception:
        pass

    # 组合层仓位上限 & 集中度（深度风控时启用行业集中度）
    principal = float(funds.get("principal", 0) or 0)
    if principal > 0:
        vp = VirtualPortfolio("data/real_portfolio.json")
        price_map = {}
        if state.get("stock_code"):
            price_map[state.get("stock_code")] = price
        per_code, total_val = vp.get_position_value_map(price_map=price_map)

        total_ratio = total_val / principal if principal else 0
        if total_ratio > 0.9:
            score += 20
            reasons.append("总仓位过高 (>90%)")
        elif total_ratio > 0.75:
            score += 10
            reasons.append("总仓位偏高 (>75%)")

        curr_val = per_code.get(state.get("stock_code"), 0) if per_code else 0
        curr_ratio = curr_val / principal if principal else 0
        if curr_ratio > 0.35:
            score += 20
            reasons.append("单标的仓位过高 (>35%)")
        elif curr_ratio > 0.25:
            score += 10
            reasons.append("单标的仓位偏高 (>25%)")

        if deep:
            try:
                by_industry = {}
                for code, val in per_code.items():
                    info = data_master.get_stock_basic_info(code)
                    industry = info.get("industry", "未知") if isinstance(info, dict) else "未知"
                    by_industry[industry] = by_industry.get(industry, 0) + (val or 0)
                if total_val > 0:
                    for ind, val in by_industry.items():
                        ratio = val / total_val
                        if ratio > 0.6:
                            score += 15
                            reasons.append(f"行业集中度过高: {ind} ({ratio*100:.0f}%)")
                            break
                        elif ratio > 0.4:
                            score += 8
                            reasons.append(f"行业集中度偏高: {ind} ({ratio*100:.0f}%)")
                            break
            except Exception:
                pass

    # 参考数据风险（深度风控）
    if deep:
        ref = state.get("reference_pack", {}) or {}
        pledge = ref.get("pledge") or []
        unlock = ref.get("unlock") or []
        holder = ref.get("holdertrade") or []

        # 质押率
        try:
            if pledge:
                sample = pledge[0]
                ratio = None
                for k in sample.keys():
                    if "ratio" in k.lower():
                        ratio = float(sample.get(k) or 0)
                        break
                if ratio and ratio > 50:
                    score += 20
                    reasons.append("质押比例偏高")
                elif ratio and ratio > 30:
                    score += 10
                    reasons.append("质押比例较高")
        except Exception:
            pass

        # 解禁临近（30天内）
        try:
            for item in unlock[:5]:
                for key in ["float_date", "unlock_date", "ann_date"]:
                    if key in item:
                        dt = str(item.get(key))
                        if len(dt) >= 8:
                            if "-" in dt:
                                u = datetime.datetime.strptime(dt[:10], "%Y-%m-%d").date()
                            else:
                                u = datetime.datetime.strptime(dt[:8], "%Y%m%d").date()
                            if 0 <= (u - datetime.date.today()).days <= 30:
                                score += 10
                                reasons.append("存在近30天解禁压力")
                                raise StopIteration
        except StopIteration:
            pass
        except Exception:
            pass

        # 股东减持
        try:
            for item in holder[:5]:
                change = item.get("change") or item.get("in_decr") or ""
                if isinstance(change, str) and "减" in change:
                    score += 10
                    reasons.append("近期股东减持")
                    break
        except Exception:
            pass

        # ST 股票限制
        try:
            info = data_master.get_stock_basic_info(state.get("stock_code"))
            name = info.get("name", "") if isinstance(info, dict) else ""
            if "ST" in name.upper():
                score += 15
                reasons.append("ST 股票，风险上调")
        except Exception:
            pass

    stops = {}
    if pos and pos.get("volume", 0) > 0:
        pct = pos.get("profit_pct", 0) or 0
        cost = pos.get("cost", 0) or 0
        if cost and cost > 0:
            stops = {
                "stop1": round(cost * 0.95, 2),
                "stop2": round(cost * 0.90, 2),
                "tp1": round(cost * 1.10, 2),
                "tp2": round(cost * 1.20, 2)
            }
        if pct <= -15:
            score += 40
            reasons.append("浮亏超过 15% (强制止损区)")
        elif pct <= -10:
            score += 30
            reasons.append("浮亏超过 10% (止损区)")
        elif pct <= -5:
            score += 20
            reasons.append("浮亏超过 5% (预警)")
        elif pct >= 20:
            reasons.append("浮盈超过 20% (分级止盈)")
        elif pct >= 10:
            reasons.append("浮盈超过 10% (分级止盈)")

    level = "LOW"
    if score >= 60:
        level = "HIGH"
    elif score >= 30:
        level = "MEDIUM"

    # adjust stop policy based on debate weights if provided
    policy = state.get("stop_policy")
    if stops and policy:
        if policy == "tight":
            stops["stop1"] = round(cost * 0.97, 2)
            stops["stop2"] = round(cost * 0.94, 2)
        elif policy == "wide":
            stops["stop1"] = round(cost * 0.93, 2)
            stops["stop2"] = round(cost * 0.88, 2)

    return score, level, reasons, trade_allowed, stops


def risk_node(state: CognitiveState):
    # pass stop policy from decision node into risk calc
    if isinstance(state.get("trading_signal"), dict):
        dp = state["trading_signal"].get("details", {})
        if isinstance(dp, dict):
            sp = dp.get("risk", {}).get("stop_policy")
            if sp:
                state["stop_policy"] = sp

    score, level, reasons, trade_allowed, stops = _calc_risk(state)
    sig = state.get("trading_signal", {}) or {}
    details = sig.get("details", {}) or {}
    details["risk"] = {
        "score": score,
        "level": level,
        "reasons": reasons,
        "trade_allowed": trade_allowed,
        "stops": stops
    }

    # Incorporate portfolio risk budget if present
    rb = state.get("risk_budget", {}) or {}
    if rb:
        details["risk"]["budget"] = rb
        rb_level = rb.get("level")
        if rb_level == "HIGH":
            level = "HIGH"
        elif rb_level == "MEDIUM" and level == "LOW":
            level = "MEDIUM"
    sig["details"] = details

    action = sig.get("action", "HOLD")
    pos = state.get("user_position", {}) or {}
    if level == "HIGH":
        action = "SELL" if pos and pos.get("volume", 0) > 0 else "HOLD"
    elif level == "MEDIUM" and action == "BUY":
        action = "HOLD"
    if not trade_allowed:
        action = "HOLD"
    sig["action"] = action

    return {"risk_assessment": f"{level} ({score})", "trading_signal": sig}
def execution_node(state: CognitiveState):
    # Optional paper execution
    try:
        do_paper = state.get("paper_execute")
        if do_paper is None:
            do_paper = os.getenv("PAPER_EXECUTE_DEFAULT", "0") == "1"
        if do_paper:
            from core.trade_simulator import PaperBroker
            from skills.risk_budget import max_drawdown, var_gaussian, risk_level_from_metrics
            try:
                from core.world_model import WorldModel
                wm = WorldModel()
                market_status = wm._get_market_status()
                if market_status != "OPEN":
                    return {"execution_result": f"未执行: 市场未开盘({market_status})"}
                strict_net = os.getenv("STRICT_NET_CHECK", "0") == "1"
                if strict_net and not wm._check_network():
                    return {"execution_result": "未执行: 网络检查未通过(严格模式)"}
            except Exception:
                pass
            broker = PaperBroker("data/paper_portfolio.json")
            sig = state.get("trading_signal", {}) or {}
            action = sig.get("action", "HOLD")
            details = sig.get("details", {}) or {}
            risk = details.get("risk", {}) or {}
            trade_allowed = bool(risk.get("trade_allowed", True))
            price = (state.get("market_data", {}) or {}).get("latest_price", 0)
            pct = (state.get("market_data", {}) or {}).get("pct_chg")
            vol = (state.get("market_data", {}) or {}).get("vol", 0)
            code = state.get("stock_code")
            policy_reason = ""

            # apply house rules (hard constraints)
            try:
                rules = memory.get_rules()
                cons = rules.get("constraints", {}) if isinstance(rules, dict) else {}
                pos = state.get("user_position", {}) or {}
                if pos and pos.get("volume", 0) > 0:
                    cost = float(pos.get("cost", 0) or 0)
                    if cost > 0 and price:
                        pnl_pct = (float(price) - cost) / cost
                        sl = cons.get("stop_loss_pct", None)
                        tp = cons.get("take_profit_pct", None)
                        if sl is not None and pnl_pct <= -float(sl):
                            action = "SELL"
                            policy_reason = f"家规止损触发({pnl_pct*100:.1f}%)"
                        elif tp is not None and pnl_pct >= float(tp):
                            action = "SELL"
                            policy_reason = f"家规止盈触发({pnl_pct*100:.1f}%)"
                if action == "BUY":
                    allow_chase = bool(cons.get("allow_chase", True))
                    if not allow_chase and pct is not None:
                        try:
                            if float(pct) >= 5:
                                action = "HOLD"
                                policy_reason = "家规禁止追高"
                        except Exception:
                            pass
            except Exception:
                pass

            # size by available cash and risk level
            finfo = state.get("user_funds", {}) or {}
            available = float(finfo.get("available", finfo.get("cash", 0)) or 0)
            level = risk.get("level", "LOW")
            ratio = 0.2
            if level == "MEDIUM":
                ratio = 0.1
            elif level == "HIGH":
                ratio = 0.05
            target_cash = available * ratio

            # liquidity cap: max 10% of daily volume
            liquidity_cap = None
            try:
                if vol and vol > 0:
                    liquidity_cap = int(vol * 0.10)
            except Exception:
                liquidity_cap = None

            # ST limit (simple)
            pct_limit = 9.8
            try:
                info = data_master.get_stock_basic_info(code)
                name = info.get("name", "") if isinstance(info, dict) else ""
                if "ST" in name.upper():
                    pct_limit = 4.8
            except Exception:
                pass

            features = state.get("factor_snapshot", {})
            # risk budget pre-check
            rb = {}
            try:
                eq = broker._equity_curve
                mdd = max_drawdown(eq)
                if len(eq) >= 2:
                    rets = []
                    for i in range(1, len(eq)):
                        prev = eq[i-1]
                        curr = eq[i]
                        if prev > 0:
                            rets.append((curr - prev) / prev)
                    var = var_gaussian(rets, alpha=0.95)
                else:
                    var = 0.0
                rb = {"mdd": mdd, "var": var, "level": risk_level_from_metrics(mdd, var)}
            except Exception:
                rb = {}

            state["risk_budget"] = rb

            if rb.get("level") == "HIGH" and action == "BUY":
                return {"execution_result": "未执行: 组合风险预算过高"}

            # dynamic sizing by risk budget
            from skills.risk_budget import reduce_ratio_by_level
            target_cash *= reduce_ratio_by_level(rb.get("level"))

            # weight-driven sizing
            fw = details.get("feature_weights", {}) if isinstance(details, dict) else {}
            try:
                if isinstance(fw, dict):
                    tech_w = float(fw.get("technical", 0) or 0)
                    cap_w = float(fw.get("capital", 0) or 0)
                    risk_w = float(fw.get("reference", 0) or 0)
                    scale = 1.0
                    if tech_w + cap_w >= 40:
                        scale *= 1.2
                    if risk_w >= 20:
                        scale *= 0.7
                    target_cash *= scale
            except Exception:
                pass

            # context tag sizing
            try:
                tags = _build_context_tags(state)
                tag_scale = 1.0
                if "vol_high" in tags:
                    tag_scale *= 0.7
                elif "vol_mid" in tags:
                    tag_scale *= 0.85
                if "data_stale" in tags:
                    tag_scale *= 0.6
                if "liquidity_low" in tags:
                    tag_scale *= 0.6
                if "cycle_risk_high" in tags:
                    tag_scale *= 0.6
                elif "cycle_risk_mid" in tags:
                    tag_scale *= 0.85
                if "sentiment_cold" in tags:
                    tag_scale *= 0.85
                if "strong_up" in tags:
                    tag_scale *= 0.9
                if "strong_down" in tags:
                    tag_scale *= 0.8
                if ("cycle_trend_strong" in tags) and ("sentiment_hot" in tags) and ("vol_low" in tags):
                    tag_scale *= 1.15
                target_cash *= tag_scale
            except Exception:
                pass

            # clamp final target cash between 5% and 30% of available
            min_cash = available * 0.05
            max_cash = available * 0.30
            if target_cash < min_cash:
                target_cash = min_cash
            if target_cash > max_cash:
                target_cash = max_cash

            decision_id = state.get("decision_id")
            signal_source = state.get("signal_source")
            if action == "BUY":
                ok, msg = broker.buy(
                    code, price, target_cash,
                    pct_chg=pct,
                    trade_allowed=trade_allowed,
                    reason=policy_reason or "signal",
                    pct_limit=pct_limit,
                    liquidity_cap=liquidity_cap,
                    features=features,
                    decision_id=decision_id,
                    signal_source=signal_source
                )
                return {"execution_result": msg if ok else f"未执行: {msg}"}
            elif action == "SELL":
                ok, msg = broker.sell(
                    code, price,
                    shares=None,
                    pct_chg=pct,
                    trade_allowed=trade_allowed,
                    reason=policy_reason or "signal",
                    pct_limit=pct_limit,
                    features=features,
                    decision_id=decision_id,
                    signal_source=signal_source
                )
                return {"execution_result": msg if ok else f"未执行: {msg}"}
            return {"execution_result": "已评估 (HOLD)"}
    except Exception:
        pass

    return {"execution_result": "已归档"}

# 🔥🔥🔥 关键：这个函数必须存在，且在文件末尾 🔥🔥🔥
def build_cognitive_graph():
    try:
        from langgraph.graph import StateGraph, END

        workflow = StateGraph(CognitiveState)
        workflow.add_node("perception", perception_node)
        workflow.add_node("planner", planner_node)
        workflow.add_node("executor", executor_node)
        workflow.add_node("tool_bridge", tool_bridge_node)
        workflow.add_node("letta_memory", letta_memory_node)
        workflow.add_node("critic", critic_node)
        workflow.add_node("analysis", analysis_node)
        workflow.add_node("autogen_review", autogen_review_node)
        workflow.add_node("decision", decision_node)
        workflow.add_node("risk_control", risk_node)
        workflow.add_node("execution", execution_node)
        workflow.set_entry_point("perception")
        workflow.add_edge("perception", "planner")
        workflow.add_edge("planner", "executor")
        workflow.add_edge("executor", "tool_bridge")
        workflow.add_edge("tool_bridge", "letta_memory")
        workflow.add_edge("letta_memory", "critic")
        workflow.add_edge("critic", "analysis")
        workflow.add_edge("analysis", "autogen_review")
        workflow.add_edge("autogen_review", "decision")
        workflow.add_edge("decision", "risk_control")
        workflow.add_edge("risk_control", "execution")
        workflow.add_edge("execution", END)
        return workflow.compile()
    except Exception:
        nodes = {
            "perception": perception_node,
            "planner": planner_node,
            "executor": executor_node,
            "tool_bridge": tool_bridge_node,
            "letta_memory": letta_memory_node,
            "critic": critic_node,
            "analysis": analysis_node,
            "autogen_review": autogen_review_node,
            "decision": decision_node,
            "risk_control": risk_node,
            "execution": execution_node
        }
        order = ["perception", "planner", "executor", "tool_bridge", "letta_memory", "critic", "analysis", "autogen_review", "decision", "risk_control", "execution"]

        class _SimpleGraph:
            def __init__(self, nodes_map, order_list):
                self._nodes = nodes_map
                self._order = order_list

            def invoke(self, state):
                s = dict(state)
                for name in self._order:
                    out = self._nodes[name](s)
                    if isinstance(out, dict):
                        s.update(out)
                return s

        return _SimpleGraph(nodes, order)
_hunter = DealerHunter()
_chip = ChipAnalyst()
_cycle = CycleCompass()
_liq = LiquidityGuard()
_sentiment = SentimentEngine()
_news_verifier = NewsVerifier()
