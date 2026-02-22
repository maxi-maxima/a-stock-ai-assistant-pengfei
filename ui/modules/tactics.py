import streamlit as st
import pandas as pd
import datetime
import os
import json

from core.learning_log import log_event
from core.cognitive_graph import build_cognitive_graph
from core.tri_brain import TriBrainCouncil
from skills.data_factory import TushareMaster
from core.portfolio import VirtualPortfolio
from skills.dealer_hunter import DealerHunter
from skills.news_verifier import NewsVerifier
from skills.smart_grid import SmartGrid
from skills.liquidity_guard import LiquidityGuard
from skills.chip_analyst import ChipAnalyst
from skills.sentiment_engine import SentimentEngine
from skills.cycle_compass import CycleCompass
from core.stock_name import display_name
from core.financial_analysis import extract_metrics, score_financial
from core.threshold_profiles import (
    load_profiles,
    list_profile_names,
    get_profile,
    get_active_profile_name,
    set_active_profile_name,
    PROFILE_DESC,
)

# 初始化组件
tm = TushareMaster()
council = TriBrainCouncil()
portfolio_manager = VirtualPortfolio("data/real_portfolio.json")
hunter = DealerHunter()
verifier = NewsVerifier()
smart_grid = SmartGrid()
liq_guard = LiquidityGuard()
chip_analyst = ChipAnalyst()
sentiment = SentimentEngine()
compass = CycleCompass()

DATA_DIR = "data"
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.json")
BROKER_POOL_PATH = os.path.join(DATA_DIR, "broker_pool.json")
STRATEGY_POOL_PATH = os.path.join(DATA_DIR, "strategy_pools.json")
STRATEGY_RESULTS_PATH = os.path.join(DATA_DIR, "strategy_results.json")
PATROL_HISTORY_PATH = os.path.join(DATA_DIR, "patrol_history.json")
TACTICS_HISTORY_PATH = os.path.join(DATA_DIR, "tactics_history.json")
FIN_SETTINGS_PATH = os.path.join(DATA_DIR, "financial_settings.json")


def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return default


def _save_json(path, data):
    _ensure_data_dir()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _normalize_code(code):
    return str(code or "").strip().upper()


def _parse_codes(data):
    if isinstance(data, dict) and "codes" in data:
        data = data.get("codes")
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
        else:
            code = item
        code = _normalize_code(code)
        if code:
            out.append(code)
    return list(dict.fromkeys(out))


def _load_watchlist_codes():
    data = _load_json(WATCHLIST_PATH, [])
    if isinstance(data, dict) and "codes" in data:
        data = data.get("codes", [])
    return _parse_codes(data)


def _load_broker_pool():
    data = _load_json(BROKER_POOL_PATH, {})
    meta = {}
    entries = []
    if isinstance(data, dict):
        meta = {
            "month": data.get("month"),
            "updated_at": data.get("updated_at"),
            "meta": data.get("meta", {})
        }
        entries = data.get("codes", [])
    elif isinstance(data, list):
        entries = data
    out = []
    seen = set()
    for item in entries:
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
            name = item.get("name") or code
        else:
            code = str(item)
            name = code
        code = _normalize_code(code)
        if code and code not in seen:
            seen.add(code)
            out.append({"code": code, "name": name})
    return out, meta


def _load_strategy_pools():
    data = _load_json(STRATEGY_POOL_PATH, {})
    return data if isinstance(data, dict) else {}


def _load_strategy_pool(pool_key):
    pools = _load_strategy_pools()
    item = pools.get(pool_key)
    if not isinstance(item, dict):
        return [], {}
    entries = item.get("codes", [])
    meta = item.get("meta", {})
    out = []
    seen = set()
    for e in entries:
        if isinstance(e, dict):
            code = e.get("code") or e.get("ts_code") or e.get("symbol")
            name = e.get("name") or code
        else:
            code = str(e)
            name = code
        code = _normalize_code(code)
        if code and code not in seen:
            seen.add(code)
            out.append({"code": code, "name": name})
    return out, meta


def _load_strategy_results():
    data = _load_json(STRATEGY_RESULTS_PATH, {})
    return data if isinstance(data, dict) else {}


def _load_patrol_history():
    data = _load_json(PATROL_HISTORY_PATH, [])
    return data if isinstance(data, list) else []


def _load_tactics_history():
    data = _load_json(TACTICS_HISTORY_PATH, [])
    return data if isinstance(data, list) else []


def _save_tactics_record(record):
    if not isinstance(record, dict):
        return
    history = _load_tactics_history()
    history.insert(0, record)
    history = history[:80]
    _save_json(TACTICS_HISTORY_PATH, history)


def _load_fin_settings():
    data = _load_json(FIN_SETTINGS_PATH, {})
    return data if isinstance(data, dict) else {}


def _save_fin_settings(data):
    if not isinstance(data, dict):
        return
    _save_json(FIN_SETTINGS_PATH, data)


def _apply_tactics_profile(profile):
    if not isinstance(profile, dict):
        return
    tactics = profile.get("tactics", {})
    if not isinstance(tactics, dict):
        return
    updates = {
        "tac_enable_morning": tactics.get("enable_morning"),
        "tac_enable_kb": tactics.get("enable_kb"),
        "tac_enable_sentiment": tactics.get("enable_sentiment"),
        "tac_enable_news": tactics.get("enable_news"),
        "tac_enable_fin": tactics.get("enable_fin"),
        "tac_save_history": tactics.get("save_history"),
        "tac_grid_period": tactics.get("grid_period"),
        "tac_grid_mult": tactics.get("grid_multiplier"),
        "tac_fin_threshold": tactics.get("fin_threshold"),
        "tac_deep_risk": tactics.get("deep_risk"),
    }
    for key, val in updates.items():
        if val is not None:
            st.session_state[key] = val
    fin_th = tactics.get("fin_threshold")
    if fin_th is not None:
        fin_settings = _load_fin_settings()
        fin_settings["threshold"] = int(fin_th)
        _save_fin_settings(fin_settings)


def _extract_codes_from_run(run):
    if not isinstance(run, dict):
        return []
    if isinstance(run.get("candidates"), list):
        return _parse_codes(run.get("candidates", []))
    if isinstance(run.get("codes"), list):
        return _parse_codes(run.get("codes", []))
    return []


def _fmt_money(val):
    try:
        v = float(val)
    except Exception:
        return "-"
    if abs(v) >= 1e8:
        return f"{v/1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v/1e4:.2f}万"
    return f"{v:.2f}"


def _tags_to_list(tags):
    if tags is None:
        return []
    if isinstance(tags, (list, tuple, set)):
        return [str(t).strip() for t in tags if str(t).strip()]
    text = str(tags)
    for sep in [",", ";", "|", "/", " ", "\uFF0C", "\uFF1B", "\u3001"]:
        text = text.replace(sep, ",")
    return [t.strip() for t in text.split(",") if t.strip()]


def _get_skill_summaries(kb):
    try:
        knowledge_list = kb.get_all_knowledge()
    except Exception:
        return []
    summaries = []
    for item in knowledge_list:
        tags_list = _tags_to_list(item.get("tags"))
        if "skill_summary" in tags_list:
            summaries.append(item)
    summaries.sort(key=lambda x: str(x.get("title", "")))
    return summaries


def _render_skill_summaries(kb):
    summaries = _get_skill_summaries(kb)
    if not summaries:
        return
    with st.expander("🧭 技能速览", expanded=False):
        for item in summaries:
            title = item.get("title", "无标题")
            tags = "/".join(_tags_to_list(item.get("tags")))
            content = str(item.get("content", "")).strip()
            structure = item.get("structure", {}) if isinstance(item.get("structure", {}), dict) else {}
            st.markdown(f"**{title}**  `{tags}`")
            if content:
                st.caption(content[:200] + ("..." if len(content) > 200 else ""))
            if structure.get("conditions"):
                st.caption(f"触发条件: {structure.get('conditions')}")
            if structure.get("risk"):
                st.caption(f"风险: {structure.get('risk')}")
            st.divider()


def _data_quality(df, last_trade_date=None):
    rows = int(len(df)) if df is not None else 0
    last_date = None
    if df is not None and not df.empty and "date" in df.columns:
        try:
            last_date = str(df.iloc[-1]["date"])
        except Exception:
            last_date = None

    last_trade_str = None
    last_trade_dt = None
    if isinstance(last_trade_date, datetime.date):
        last_trade_dt = last_trade_date
        last_trade_str = last_trade_dt.strftime("%Y-%m-%d")
    elif isinstance(last_trade_date, str):
        last_trade_str = last_trade_date
        try:
            if "-" in last_trade_date:
                last_trade_dt = datetime.datetime.strptime(last_trade_date[:10], "%Y-%m-%d").date()
            else:
                last_trade_dt = datetime.datetime.strptime(last_trade_date[:8], "%Y%m%d").date()
        except Exception:
            last_trade_dt = None

    stale = False
    delta_days = None
    if last_trade_dt and last_date:
        try:
            if "-" in last_date:
                last_dt = datetime.datetime.strptime(last_date[:10], "%Y-%m-%d").date()
            else:
                last_dt = datetime.datetime.strptime(last_date[:8], "%Y%m%d").date()
            delta_days = (last_trade_dt - last_dt).days
            if delta_days > 0:
                stale = True
        except Exception:
            pass

    return {
        "rows": rows,
        "last_date": last_date,
        "last_trade_date": last_trade_str,
        "delta_days": delta_days,
        "stale": stale
    }


def _calc_fin_snapshot(scanner, code, weights=None):
    try:
        df_inc = scanner.data_skill.financial.get_income_statement(code)
        if isinstance(df_inc, tuple):
            df_inc = df_inc[0]
        df_bs = scanner.data_skill.financial.get_balance_sheet(code)
        if isinstance(df_bs, tuple):
            df_bs = df_bs[0]
        df_cf = scanner.data_skill.financial.get_cashflow(code)
        if isinstance(df_cf, tuple):
            df_cf = df_cf[0]
        if df_inc is None or df_inc.empty:
            return None
        metrics = extract_metrics(code, df_inc, df_bs, df_cf)
        score, grade, detail = score_financial(metrics, weights)
        return {"metrics": metrics, "score": score, "grade": grade, "detail": detail}
    except Exception:
        return None


def _get_tac_app():
    if "tactics_app" not in st.session_state:
        st.session_state["tactics_app"] = build_cognitive_graph()
    return st.session_state["tactics_app"]


def _calc_grid_fallback(df, period=14, multiplier=1.0):
    grid = smart_grid.calculate(df, period=period)
    if not grid:
        return None
    try:
        curr_price = float(df.iloc[-1]["close"])
    except Exception:
        return grid
    try:
        atr = float(grid.get("atr", 0))
    except Exception:
        return grid
    if multiplier and abs(float(multiplier) - 1.0) > 1e-6:
        atr *= float(multiplier)
    if atr <= 0 or curr_price <= 0:
        return grid
    return {
        "atr": round(atr, 2),
        "stop_loss": round(curr_price - 2 * atr, 2),
        "buy_grid": [round(curr_price - i * atr, 2) for i in range(1, 4)],
        "sell_grid": [round(curr_price + i * atr, 2) for i in range(1, 4)]
    }


def ensure_morning_briefing(portfolio_obj, enabled=True, force=False):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if not enabled:
        return {"date": today, "view": "", "verdict": "", "details": {}}
    if not force and "morning_result" in st.session_state:
        last = st.session_state.get("morning_result", {})
        if isinstance(last, dict) and last.get("date") == today:
            return last
    try:
        with st.status("🌍 正在扫描全球宏观情报...", expanded=True) as status:
            pack = tm.get_morning_pack()
            ctx = {
                "global_indices": pack.get("indices"),
                "macro_news": pack.get("news"),
                "user_fund_detail": portfolio_obj.get_fund_info()
            }
            res = council.debate(ctx, mode="morning")
            res_pack = {
                "date": today,
                "view": res.get("core_view"),
                "verdict": res.get("final_verdict"),
                "details": res,
                "macro_news": pack.get("news", []),
                "global_indices": pack.get("indices", {})
            }
            st.session_state["morning_result"] = res_pack
            status.update(label="✅ 宏观推演完成", state="complete")
            return res_pack
    except Exception:
        return {"date": today, "view": "", "verdict": "", "details": {}}


def run_analysis_logic(stock_code, scanner, plotter, memory, kb, learner, user_portfolio, settings=None, source_info=None):
    settings = settings or {}
    enable_morning = bool(settings.get("enable_morning", True))
    enable_kb = bool(settings.get("enable_kb", True))
    enable_sentiment = bool(settings.get("enable_sentiment", True))
    enable_news = bool(settings.get("enable_news", True))
    enable_fin = bool(settings.get("enable_financial", True))
    grid_period = int(settings.get("grid_period", 14))
    grid_multiplier = float(settings.get("grid_multiplier", 1.0))
    fin_threshold = settings.get("fin_threshold")
    save_history = bool(settings.get("save_history", True))
    deep_risk = bool(settings.get("deep_risk", False))
    paper_execute = bool(settings.get("paper_execute", False))

    source_info = source_info or {"source": "manual", "label": "手动输入"}

    morning_pack = ensure_morning_briefing(user_portfolio, enabled=enable_morning)
    macro_news = morning_pack.get("macro_news", []) if isinstance(morning_pack, dict) else []
    weather = sentiment.get_weather_report() if enable_sentiment else {
        "weather": "中性", "icon": "⛅", "bg_color": "#eeeeee"
    }

    stock_label = display_name(stock_code, with_code=True)
    news_list = []
    news_check = None
    fin_snapshot = None
    fin_warning = None

    last_trade_date = None
    try:
        last_trade_date = scanner.data_skill.get_last_trade_date()
    except Exception:
        last_trade_date = None

    with st.spinner(f"正在调取 {stock_label} 全息数据..."):
        df = scanner.data_skill.get_history(stock_code, days=250)
        if df.empty:
            st.error("K线缺失")
            return

        data_quality = _data_quality(df, last_trade_date)

        # 运行探测器
        dealer_res = hunter.analyze(df)
        chip_res = chip_analyst.analyze(df)
        cycle_res = compass.detect_phase(df)
        liq_res = liq_guard.check(df)

        # 新闻校验
        if enable_news:
            try:
                news_list = tm.news.get_stock_news(stock_code)
            except Exception:
                news_list = []
            try:
                news_check = verifier.check_divergence(df, news_list)
            except Exception:
                news_check = None

        # 财务快照
        if enable_fin:
            fin_snapshot = _calc_fin_snapshot(scanner, stock_code)
            if fin_snapshot and fin_threshold is not None:
                try:
                    if fin_snapshot.get("score", 0) < float(fin_threshold):
                        fin_warning = f"财务评分低于阈值 {fin_threshold}"
                except Exception:
                    fin_warning = None

        # 备选网格
        grid_fallback = _calc_grid_fallback(df, period=grid_period, multiplier=grid_multiplier)

        # 绘图
        st.subheader(f"📈 {stock_label} 态势感知")
        fig = plotter.plot_kline(df, title=stock_label)
        pos = user_portfolio.get_specific_position(stock_code)
        if pos and pos.get("cost", 0) > 0:
            fig.add_hline(y=pos["cost"], line_dash="dash", line_color="blue", annotation_text=f"👮 成本:{pos['cost']}")
        st.plotly_chart(fig, use_container_width=True)

    try:
        style_prompt = f"用户偏好: {learner.learn_from_examples([])[0].get('risk_appetite', '平衡')}"
    except Exception:
        style_prompt = "用户偏好: 平衡"

    # 知识库查询
    if enable_kb:
        try:
            kb_query = " ".join([
                str(cycle_res.get("phase", "") or ""),
                str(cycle_res.get("label", "") or ""),
                str(dealer_res.get("risk_level", "") or ""),
                str(chip_res.get("status", "") or ""),
                str(liq_res.get("status", "") or "")
            ]).strip()
            kb_pack = kb.build_context(kb_query, limit=5)
            k_titles = kb_pack.get("titles", [])
            k_ctx = kb_pack.get("context") or "无特定战法"
            k_items = kb_pack.get("items", [])
            usage_sig = f"{stock_code}|{','.join(k_titles)}"
            if k_items and st.session_state.get("kb_usage_sig") != usage_sig:
                kb.record_usage(k_items)
                st.session_state["kb_usage_sig"] = usage_sig
        except Exception:
            k_titles = []
            k_ctx = "知识库连接异常"
            k_items = []
    else:
        k_titles = []
        k_ctx = "未启用知识库"
        k_items = []

    app = _get_tac_app()

    with st.status("🧠 六维引擎计算中...", expanded=True) as status:
        status.write("🔍 正在检索知识库战法...")
        if k_titles:
            status.write(f"📚 已匹配战法: {', '.join(k_titles[:3])}")
        else:
            status.write("📚 暂无匹配的特定战法")

        morning_view = morning_pack.get("view") if enable_morning else "无晨报"
        final_input = f"{style_prompt}|宏观:{morning_view}|庄家:{dealer_res.get('risk_level')}|筹码:{chip_res.get('status') if chip_res else '未知'}|周期:{cycle_res.get('phase')}"

        res = app.invoke({
            "stock_code": stock_code,
            "messages": [],
            "morning_strategy": final_input,
            "knowledge_context": k_ctx,
            "deep_risk": deep_risk,
            "paper_execute": paper_execute,
            "dealer_hunter": dealer_res,
            "chip_analyst": chip_res,
            "cycle_compass": cycle_res,
            "liquidity_guard": liq_res,
            "sentiment_weather": weather if enable_sentiment else {},
            "news_data": news_list,
            "macro_news": macro_news,
            "knowledge_titles": k_titles,
            "knowledge_items": k_items,
            "source_info": source_info,
            "data_quality": data_quality,
            "signal_source": {"source": source_info.get("source", "manual"), "label": source_info.get("label", "手动输入")}
        })
        status.update(label="✅ 分析完成", state="complete")

        try:
            sig = res.get("trading_signal", {})
            details = sig.get("details", {})
            scores = details.get("scores", {})
            base_score = scores.get("total", 50)
            final_score = base_score + cycle_res.get("score_impact", 0)
            final_score = max(0, min(100, final_score))
            decision_id = res.get("decision_id") or sig.get("decision_id") or details.get("decision_id")
            log_event("analysis_run", {
                "code": stock_code,
                "action": sig.get("action", "HOLD"),
                "score": final_score,
                "base_score": base_score,
                "phase": cycle_res.get("phase"),
                "risk_level": dealer_res.get("risk_level"),
                "knowledge_titles": k_titles,
                "source": source_info.get("source", "manual"),
                "fin_score": fin_snapshot.get("score") if fin_snapshot else None,
                "decision_id": decision_id
            })
        except Exception:
            final_score = None

        if save_history:
            try:
                sig = res.get("trading_signal", {})
                details = sig.get("details", {})
                scores = details.get("scores", {})
                base_score = scores.get("total", 50)
                score_val = base_score + cycle_res.get("score_impact", 0)
                score_val = max(0, min(100, score_val))
            except Exception:
                score_val = None
                sig = {}

            record = {
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "code": stock_code,
                "name": display_name(stock_code),
                "action": sig.get("action", "HOLD"),
                "score": score_val,
                "source": source_info,
                "fin_score": fin_snapshot.get("score") if fin_snapshot else None,
                "data_quality": data_quality,
                "decision_id": res.get("decision_id") or sig.get("decision_id") or details.get("decision_id"),
                "settings": {
                    "deep_risk": deep_risk,
                    "paper_execute": paper_execute,
                    "enable_news": enable_news,
                    "enable_financial": enable_fin,
                    "enable_kb": enable_kb,
                    "enable_morning": enable_morning,
                    "grid_period": grid_period,
                    "grid_multiplier": grid_multiplier
                }
            }
            _save_tactics_record(record)

        render_result({
            "res": res,
            "cycle": cycle_res,
            "weather": weather,
            "dealer": dealer_res,
            "k_titles": k_titles,
            "k_items": k_items,
            "kb": kb,
            "source_info": source_info,
            "data_quality": data_quality,
            "fin_snapshot": fin_snapshot,
            "fin_threshold": fin_threshold,
            "fin_warning": fin_warning,
            "macro_news": macro_news,
            "news_check": news_check,
            "news_list": news_list,
            "grid_fallback": grid_fallback,
            "enable_news": enable_news
        })


def render_result(pack):
    res = pack.get("res", {}) or {}
    cycle = pack.get("cycle", {}) or {}
    weather = pack.get("weather") or {"weather": "中性", "icon": "⛅", "bg_color": "#eeeeee"}
    dealer = pack.get("dealer", {}) or {}
    sig = res.get("trading_signal", {}) if isinstance(res, dict) else {}
    tactics = sig.get("details", {}) if isinstance(sig, dict) else {}
    act = sig.get("action", "HOLD")
    scores = tactics.get("scores", {}) if isinstance(tactics, dict) else {}
    k_titles = pack.get("k_titles", []) or []
    k_items = pack.get("k_items", []) or []
    kb = pack.get("kb")
    source_info = pack.get("source_info") or {}
    data_quality = pack.get("data_quality") or {}
    fin_snapshot = pack.get("fin_snapshot")
    fin_threshold = pack.get("fin_threshold")
    fin_warning = pack.get("fin_warning")
    enable_news = pack.get("enable_news", True)
    news_check = pack.get("news_check")
    macro_news = pack.get("macro_news", []) or []
    news_list = pack.get("news_list") if enable_news else []
    if enable_news and not news_list:
        news_list = res.get("news_data", [])
    grid_fallback = pack.get("grid_fallback")

    st.divider()

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        f"<div style='background:{weather.get('bg_color','#eee')};padding:5px;border-radius:5px;text-align:center'>"
        f"{weather.get('icon','⛅')} {weather.get('weather','中性')}</div>",
        unsafe_allow_html=True
    )
    c2.markdown(
        f"<div style='background:#eee;padding:5px;border-radius:5px;text-align:center'>"
        f"{cycle.get('icon','⏱️')} {cycle.get('phase','未知')}</div>",
        unsafe_allow_html=True
    )
    k_msg = f"📚 命中 {len(k_titles)} 个战法" if k_titles else "📚 无战法匹配"
    c3.markdown(f"<div style='background:#e3f2fd;padding:5px;border-radius:5px;text-align:center'>{k_msg}</div>", unsafe_allow_html=True)
    source_label = source_info.get("label") or "手动输入"
    c4.markdown(f"<div style='background:#f3e5f5;padding:5px;border-radius:5px;text-align:center'>{source_label}</div>", unsafe_allow_html=True)
    if source_info.get("detail"):
        c4.caption(source_info.get("detail"))

    if data_quality:
        dq_msg = f"数据行数 {data_quality.get('rows', 0)} | 最新日期 {data_quality.get('last_date', '-')}"
        if data_quality.get("last_trade_date"):
            dq_msg += f" | 最近交易日 {data_quality.get('last_trade_date')}"
        if data_quality.get("delta_days") is not None:
            dq_msg += f" | 滞后 {data_quality.get('delta_days')}天"
        if data_quality.get("stale"):
            st.warning(f"数据质量: {dq_msg}")
        else:
            st.caption(f"数据质量: {dq_msg}")

    if enable_news and news_check:
        ns = news_check.get("status", "")
        score = news_check.get("divergence_score", 0)
        if score < 0:
            st.warning(f"新闻校验: {ns}")
        elif score > 0:
            st.success(f"新闻校验: {ns}")
        else:
            st.info(f"新闻校验: {ns}")

    if fin_snapshot:
        st.subheader("💰 财务快照")
        score = fin_snapshot.get("score")
        grade = fin_snapshot.get("grade")
        metrics = fin_snapshot.get("metrics", {})

        f1, f2, f3 = st.columns(3)
        f1.metric("财务评分", f"{score:.0f}/{grade}" if score is not None else "—")
        f2.metric("收入(近报)", _fmt_money(metrics.get("revenue")))
        f3.metric("净利润", _fmt_money(metrics.get("net_income")))

        f4, f5, f6 = st.columns(3)
        f4.metric("毛利率", f"{metrics.get('gross_margin'):.1f}%" if metrics.get("gross_margin") is not None else "-")
        f5.metric("净利率", f"{metrics.get('net_margin'):.1f}%" if metrics.get("net_margin") is not None else "-")
        f6.metric("负债率", f"{metrics.get('debt_ratio'):.1f}%" if metrics.get("debt_ratio") is not None else "-")

        f7, f8, f9 = st.columns(3)
        f7.metric("ROE", f"{metrics.get('roe'):.1f}%" if metrics.get("roe") is not None else "-")
        f8.metric("ROA", f"{metrics.get('roa'):.1f}%" if metrics.get("roa") is not None else "-")
        f9.metric("经营现金流", _fmt_money(metrics.get("ocf")))

        if metrics.get("end_date"):
            st.caption(f"财报期末: {metrics.get('end_date')}")
        if fin_warning:
            st.warning(fin_warning)

    if enable_news and macro_news:
        with st.expander("🌐 宏观新闻", expanded=False):
            for item in macro_news[:10]:
                st.write(item)

    if enable_news and news_list:
        with st.expander("📰 个股新闻", expanded=False):
            for item in news_list[:10]:
                st.write(item)

    if k_items:
        with st.expander("📚 战法匹配详情", expanded=False):
            for i, item in enumerate(k_items):
                title = item.get("title", "无标题")
                tags = "/".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else str(item.get("tags") or "")
                stats = item.get("stats", {}) if isinstance(item.get("stats"), dict) else {}
                hit_info = f"热度 {stats.get('hits', 0)} | 👍 {stats.get('likes', 0)} | 👎 {stats.get('dislikes', 0)}"
                st.markdown(f"**{title}**  [{tags}]  ·  {hit_info}")
                struct = item.get("structure", {}) if isinstance(item.get("structure"), dict) else {}
                if struct.get("timeframe"):
                    st.caption(f"适用周期: {struct.get('timeframe')}")
                if struct.get("conditions"):
                    st.caption(f"触发条件: {struct.get('conditions')}")
                if struct.get("risk"):
                    st.caption(f"风险: {struct.get('risk')}")
                cfb1, cfb2 = st.columns(2)
                with cfb1:
                    if st.button("👍 有效", key=f"kb_like_{i}"):
                        if kb:
                            kb.record_feedback(title, 1)
                        st.toast(f"已反馈：{title}", icon="👍")
                with cfb2:
                    if st.button("👎 无效", key=f"kb_dislike_{i}"):
                        if kb:
                            kb.record_feedback(title, -1)
                        st.toast(f"已反馈：{title}", icon="👎")

    final_score = scores.get("total", 50) + cycle.get("score_impact", 0)
    final_score = max(0, min(100, final_score))
    color = "red" if final_score < 40 else "green" if final_score > 60 else "orange"

    st.markdown(f"""
    <div style='text-align:center;border:3px solid {color};padding:15px;border-radius:10px;margin:10px 0'>
        <h1 style='color:{color};margin:0'>{act}</h1>
        <h3 style='margin:0'>综合得分: {final_score}</h3>
        <p style='color:gray'>{tactics.get('core_view')}</p>
    </div>
    """, unsafe_allow_html=True)

    exec_msg = res.get("execution_result")
    if exec_msg:
        st.info(f"纸面执行: {exec_msg}")

    with st.expander("📊 六维全息评分详情 (点击展开)", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        def show_s(col, label, key):
            val = scores.get(key, 50)
            col.metric(label, f"{val}分")
            col.progress(min(100, max(0, int(val))))

        show_s(sc1, "💰 资金筹码", "capital")
        show_s(sc2, "📈 技术形态", "technical")
        show_s(sc3, "🌍 宏观环境", "macro")
        show_s(sc1, "📰 消息舆情", "news")
        show_s(sc2, "🧠 历史记忆", "memory")
        show_s(sc3, "📚 知识匹配", "knowledge")
        factor_usage = tactics.get("factor_usage", {}) if isinstance(tactics, dict) else {}
        if isinstance(factor_usage, dict) and factor_usage:
            usage_line = " | ".join([f"{k}:{'OK' if v else 'SKIP'}" for k, v in factor_usage.items()])
            st.caption(f"Factor input: {usage_line}")

    if dealer.get("risk_score", 0) > 0:
        st.error(f"⚠️ {dealer.get('risk_level')}")

    grid = tactics.get("grid_strategy", {}) if isinstance(tactics, dict) else {}
    if grid:
        st.subheader("🕸️ 实战网格 (AI + ATR)")
        g1, g2 = st.columns(2)
        with g1:
            st.success("🟢 买入支撑区")
            st.write(f"买一: {grid.get('buy1_price')} ({grid.get('buy1_action')})")
            st.write(f"买二: {grid.get('buy2_price')} ({grid.get('buy2_action')})")
        with g2:
            st.error("🔴 卖出压力区")
            st.write(f"卖一: {grid.get('sell1_price')} ({grid.get('sell1_action')})")
            st.write(f"卖二: {grid.get('sell2_price')} ({grid.get('sell2_action')})")
        st.info(f"💡 策略: {grid.get('note')}")

    if grid_fallback:
        with st.expander("🧭 备选网格 (ATR)", expanded=False):
            st.caption(f"ATR: {grid_fallback.get('atr')} | 止损: {grid_fallback.get('stop_loss')}")
            buy_grid = grid_fallback.get("buy_grid", [])
            sell_grid = grid_fallback.get("sell_grid", [])
            if buy_grid:
                st.write(f"买入阶梯: {', '.join([str(x) for x in buy_grid])}")
            if sell_grid:
                st.write(f"卖出阶梯: {', '.join([str(x) for x in sell_grid])}")

    risk = tactics.get("risk", {})
    if risk:
        st.subheader("🛡️ 风控评估")
        r1, r2 = st.columns(2)
        r1.metric("风险等级", risk.get("level", "N/A"))
        r2.metric("风险分数", risk.get("score", 0))
        st.caption(f"交易可用: {'是' if risk.get('trade_allowed', True) else '否'}")
        if risk.get("stop_policy"):
            st.caption(f"止损策略: {risk.get('stop_policy')}")
        if risk.get("reasons"):
            st.write("原因：")
            for rsn in risk.get("reasons", []):
                st.write(f"- {rsn}")
        stops = risk.get("stops", {})
        if stops:
            st.write("分级止损/止盈参考：")
            st.write(f"- 止损1: {stops.get('stop1')}")
            st.write(f"- 止损2: {stops.get('stop2')}")
            st.write(f"- 止盈1: {stops.get('tp1')}")
            st.write(f"- 止盈2: {stops.get('tp2')}")

    with st.expander("🧾 决策解释 (Why)", expanded=False):
        if tactics.get("risk_warning"):
            st.warning(tactics.get("risk_warning"))
        st.markdown(f"**蓝军观点**: {tactics.get('blue_view', '')}")
        st.markdown(f"**红军观点**: {tactics.get('red_view', '')}")
        st.markdown(f"**最终裁决**: {tactics.get('final_verdict', '')}")

    fw = tactics.get("feature_weights", {})
    if fw:
        with st.expander("⚖️ 因子权重 (本次分析)", expanded=False):
            try:
                st.json(fw)
            except Exception:
                st.write(fw)
        try:
            from core.learning_log import record_feature_weights
            record_feature_weights(fw)
        except Exception:
            pass

    ref = res.get("reference_pack", {})
    feat = res.get("feature_pack", {})
    if ref or feat:
        with st.expander("📌 参考/特色数据", expanded=False):
            if ref:
                st.markdown("**参考数据**")
                for k, v in ref.items():
                    if v:
                        st.write(f"{k}: {v[:3]}")
            if feat:
                st.markdown("**特色数据**")
                for k, v in feat.items():
                    if v:
                        st.write(f"{k}: {v[:3]}")

    user_pos = res.get("user_position", {})
    if user_pos and user_pos.get("volume", 0) > 0:
        st.warning(f"💰 持仓盈亏: {user_pos.get('profit', 0):.0f} ({user_pos.get('profit_pct', 0):.2f}%)")


def render(scanner, r, p, plotter, memory, kb, learner):
    st.header("🧘 战术指挥室 V4.0 (联动增强)")
    col_asset, col_tactics = st.columns([1, 2.5])

    with col_asset:
        st.markdown("### 🏰 我的持仓")
        finfo = portfolio_manager.get_fund_info()
        st.metric("可用资金", f"¥{finfo.get('available', 0):,.0f}")
        st.caption(f"总资产: ¥{finfo.get('principal', 0):,.0f} | 持仓占用: ¥{finfo.get('invested', 0):,.0f}")
        with st.expander("✏️ 手动调整可用资金", expanded=False):
            with st.form("cash_edit"):
                avail = st.number_input("可用资金 (¥)", min_value=0.0, value=float(finfo.get("available", 0)), step=1000.0)
                if st.form_submit_button("保存"):
                    portfolio_manager.update_available(avail)
                    st.success("已更新可用资金")
                    st.rerun()
        with st.expander("➕ 录入", expanded=False):
            with st.form("add"):
                c, cost, vol = st.text_input("代码"), st.number_input("成本"), st.number_input("股数", step=100)
                if st.form_submit_button("保存") and c and vol > 0:
                    portfolio_manager.add_position(c, vol, cost)
                    log_event("position_update", {"code": c, "volume": float(vol), "cost": float(cost)})
                    st.rerun()

        for code, info in list(portfolio_manager.get_all_positions().items()):
            if not isinstance(info, dict):
                continue
            display = display_name(code, with_code=True)
            st.markdown(f"**{display}**")
            c1, c2 = st.columns(2)
            c1.caption(f"成本:{info.get('cost')}")
            c2.caption(f"股:{info.get('volume')}")
            b1, b2 = st.columns(2)
            if b1.button("🚀", key=f"a_{code}"):
                st.session_state["tac_input"] = code
                st.session_state["auto_run"] = True
                st.rerun()
            with b2:
                with st.popover("卖出", use_container_width=True):
                    st.caption(f"当前持仓：{int(info.get('volume', 0))} 股")
                    with st.form(f"sell_{code}"):
                        qty = st.number_input("卖出股数", min_value=0, max_value=int(info.get("volume", 0)), value=int(info.get("volume", 0)), step=100)
                        price = st.number_input("卖出价格", min_value=0.0, value=float(info.get("cost", 0)), step=0.01)
                        if st.form_submit_button("确认卖出"):
                            if qty <= 0:
                                st.warning("卖出股数需大于 0")
                            else:
                                ok = portfolio_manager.sell_position(code, qty, price)
                                if ok:
                                    log_event("position_sell", {"code": code, "volume": int(qty), "price": float(price)})
                                    st.success("卖出完成")
                                    st.rerun()
                                else:
                                    st.error("卖出失败，请检查数量/价格")
            st.divider()

    with col_tactics:
        st.markdown("### 📡 战术分析终端")
        _render_skill_summaries(kb)

        with st.expander("🔗 联动来源", expanded=False):
            source_options = ["手动输入", "观测池", "雷达结果", "巡逻结果", "券商金股池", "策略池"]
            src = st.selectbox("来源", source_options, key="tac_source_select")

            selected_code = None
            source_label = "手动输入"
            source_detail = ""
            source_key = "manual"

            if src == "观测池":
                codes = _load_watchlist_codes()
                source_key = "watchlist"
                source_label = "观测池"
                source_detail = f"规模 {len(codes)}"
                if not codes:
                    st.info("观测池为空")
                else:
                    label_map = {}
                    labels = []
                    for code in codes:
                        label = display_name(code, with_code=True)
                        if label in label_map:
                            label = f"{label} #{len(label_map) + 1}"
                        label_map[label] = code
                        labels.append(label)
                    sel = st.selectbox("选择标的", labels, key="tac_wl_select")
                    selected_code = label_map.get(sel)

            elif src == "雷达结果":
                results = _load_strategy_results()
                source_key = "radar"
                source_label = "雷达结果"
                if not results:
                    st.info("暂无雷达结果记录")
                else:
                    keys = sorted(list(results.keys()))
                    sel_key = st.selectbox("选择雷达记录", keys, key="tac_radar_run")
                    run = results.get(sel_key, {})
                    codes = _extract_codes_from_run(run)
                    source_detail = f"{run.get('strategy', '')} | {run.get('time', '')}".strip(" |")
                    if not codes:
                        st.info("该记录无候选标的")
                    else:
                        reason_map = {}
                        for item in run.get("candidates", []):
                            if isinstance(item, dict) and item.get("code"):
                                reason_map[_normalize_code(item.get("code"))] = item.get("reason", "")
                        label_map = {}
                        labels = []
                        for code in codes:
                            reason = reason_map.get(_normalize_code(code))
                            base = display_name(code, with_code=True)
                            label = f"{base} | {reason}" if reason else base
                            if label in label_map:
                                label = f"{label} #{len(label_map) + 1}"
                            label_map[label] = code
                            labels.append(label)
                        sel = st.selectbox("选择标的", labels, key="tac_radar_select")
                        selected_code = label_map.get(sel)

            elif src == "巡逻结果":
                history = _load_patrol_history()
                source_key = "patrol"
                source_label = "巡逻结果"
                if not history:
                    st.info("暂无巡逻记录")
                else:
                    labels = [
                        f"{h.get('time','')} | {h.get('strategy','')} | {h.get('scope','')}"
                        for h in history
                    ]
                    idx = st.selectbox("选择巡逻记录", list(range(len(history))), format_func=lambda i: labels[i], key="tac_patrol_run")
                    run = history[idx] if idx is not None else {}
                    codes = _extract_codes_from_run(run)
                    source_detail = f"{run.get('strategy', '')} | {run.get('time', '')}".strip(" |")
                    if not codes:
                        st.info("该记录无候选标的")
                    else:
                        label_map = {}
                        labels = []
                        for code in codes:
                            label = display_name(code, with_code=True)
                            if label in label_map:
                                label = f"{label} #{len(label_map) + 1}"
                            label_map[label] = code
                            labels.append(label)
                        sel = st.selectbox("选择标的", labels, key="tac_patrol_select")
                        selected_code = label_map.get(sel)

            elif src == "券商金股池":
                entries, meta = _load_broker_pool()
                source_key = "broker_pool"
                source_label = "券商金股池"
                month = meta.get("month")
                updated = meta.get("updated_at")
                source_detail = f"{month or ''} {updated or ''}".strip()
                if not entries:
                    st.info("券商金股池为空")
                else:
                    label_map = {}
                    labels = []
                    for item in entries:
                        code = item.get("code")
                        label = display_name(code, with_code=True) if code else str(item)
                        if label in label_map:
                            label = f"{label} #{len(label_map) + 1}"
                        label_map[label] = code
                        labels.append(label)
                    sel = st.selectbox("选择标的", labels, key="tac_broker_select")
                    selected_code = label_map.get(sel)

            elif src == "策略池":
                pools = _load_strategy_pools()
                source_key = "strategy_pool"
                source_label = "策略池"
                if not pools:
                    st.info("暂无策略池")
                else:
                    pool_names = sorted(list(pools.keys()))
                    pool_key = st.selectbox("选择策略池", pool_names, key="tac_pool_select")
                    entries, meta = _load_strategy_pool(pool_key)
                    source_detail = f"{pool_key} | {len(entries)} 只"
                    if not entries:
                        st.info("该策略池为空")
                    else:
                        label_map = {}
                        labels = []
                        for item in entries:
                            code = item.get("code")
                            label = display_name(code, with_code=True) if code else str(item)
                            if label in label_map:
                                label = f"{label} #{len(label_map) + 1}"
                            label_map[label] = code
                            labels.append(label)
                        sel = st.selectbox("选择标的", labels, key="tac_pool_code_select")
                        selected_code = label_map.get(sel)

            if selected_code:
                source_info = {
                    "source": source_key,
                    "label": source_label,
                    "detail": source_detail,
                    "code": selected_code
                }
                b1, b2 = st.columns(2)
                if b1.button("载入到战术", key=f"tac_load_{source_key}"):
                    st.session_state["tac_input"] = selected_code
                    st.session_state["tac_source_info"] = source_info
                    st.success("已载入")
                if b2.button("载入并分析", key=f"tac_load_run_{source_key}"):
                    st.session_state["tac_input"] = selected_code
                    st.session_state["tac_source_info"] = source_info
                    st.session_state["auto_run"] = True
                    st.rerun()

        enable_morning = True
        enable_kb = True
        enable_sentiment = True
        enable_news = True
        enable_fin = True
        save_history = True
        grid_period = 14
        grid_multiplier = 1.0
        fin_threshold = None

        profiles = load_profiles()
        profile_names = list_profile_names(profiles)
        active_profile = get_active_profile_name(profiles)
        if active_profile not in profiles:
            active_profile = profile_names[0]
        active_profile_data = get_profile(active_profile, profiles)
        tac_profile = active_profile_data.get("tactics", {}) if isinstance(active_profile_data, dict) else {}

        with st.expander("🧭 阈值方案（新手推荐）", expanded=False):
            idx = profile_names.index(active_profile) if active_profile in profile_names else 0
            profile_name = st.selectbox("选择方案", profile_names, index=idx, key="tac_profile_select")
            desc = PROFILE_DESC.get(profile_name)
            if desc:
                st.caption(desc)
            if st.button("一键套用到战术参数", key="tac_profile_apply"):
                _apply_tactics_profile(get_profile(profile_name, profiles))
                set_active_profile_name(profile_name)
                st.success("已应用战术阈值方案")
                st.rerun()

        with st.expander("⚙️ 参数面板", expanded=False):
            c1, c2, c3 = st.columns(3)
            enable_morning = c1.checkbox(
                "晨报指引",
                value=st.session_state.get("tac_enable_morning", bool(tac_profile.get("enable_morning", True))),
                key="tac_enable_morning"
            )
            enable_kb = c2.checkbox(
                "知识库匹配",
                value=st.session_state.get("tac_enable_kb", bool(tac_profile.get("enable_kb", True))),
                key="tac_enable_kb"
            )
            enable_sentiment = c3.checkbox(
                "情绪天气",
                value=st.session_state.get("tac_enable_sentiment", bool(tac_profile.get("enable_sentiment", True))),
                key="tac_enable_sentiment"
            )
            c4, c5, c6 = st.columns(3)
            enable_news = c4.checkbox(
                "新闻校验",
                value=st.session_state.get("tac_enable_news", bool(tac_profile.get("enable_news", True))),
                key="tac_enable_news"
            )
            enable_fin = c5.checkbox(
                "财务快照",
                value=st.session_state.get("tac_enable_fin", bool(tac_profile.get("enable_fin", True))),
                key="tac_enable_fin"
            )
            save_history = c6.checkbox(
                "写入战术复盘",
                value=st.session_state.get("tac_save_history", bool(tac_profile.get("save_history", True))),
                key="tac_save_history"
            )

            grid_period_default = int(tac_profile.get("grid_period", 14))
            grid_multiplier_default = float(tac_profile.get("grid_multiplier", 1.0))
            grid_period = st.slider(
                "网格 ATR 周期",
                7,
                30,
                int(st.session_state.get("tac_grid_period", grid_period_default)),
                key="tac_grid_period"
            )
            grid_multiplier = st.slider(
                "网格倍数",
                0.5,
                3.0,
                float(st.session_state.get("tac_grid_mult", grid_multiplier_default)),
                step=0.1,
                key="tac_grid_mult"
            )

            if enable_fin:
                fin_settings = _load_fin_settings()
                default_fin = fin_settings.get("threshold")
                if default_fin is None:
                    default_fin = int(tac_profile.get("fin_threshold", 70))
                fin_threshold = st.slider("财务评分阈值", 50, 90, int(default_fin), step=5, key="tac_fin_threshold")
                fin_settings["threshold"] = fin_threshold
                _save_fin_settings(fin_settings)

            if st.button("重置战术引擎"):
                if "tactics_app" in st.session_state:
                    del st.session_state["tactics_app"]
                st.success("战术引擎已重置")
                st.rerun()

        if "tac_input" not in st.session_state:
            st.session_state["tac_input"] = "000001.SZ"
        target = st.text_input("代码", key="tac_input")
        deep_risk_default = bool(tac_profile.get("deep_risk", False))
        deep_risk = st.checkbox(
            "启用深度风控/参考数据（消耗积分）",
            value=st.session_state.get("tac_deep_risk", deep_risk_default),
            key="tac_deep_risk"
        )
        paper_exec = st.checkbox("纸面执行（模拟下单）", value=False, key="tac_paper_exec")

        do_run = st.session_state.get("auto_run", False)
        if do_run:
            st.session_state["auto_run"] = False

        if st.button("🔥 部署战术", type="primary", use_container_width=True) or do_run:
            if target:
                source_info = st.session_state.get("tac_source_info") or {"source": "manual", "label": "手动输入"}
                if source_info.get("code") and _normalize_code(source_info.get("code")) != _normalize_code(target):
                    source_info = {"source": "manual", "label": "手动输入"}

                settings = {
                    "enable_morning": enable_morning,
                    "enable_kb": enable_kb,
                    "enable_sentiment": enable_sentiment,
                    "enable_news": enable_news,
                    "enable_financial": enable_fin,
                    "grid_period": grid_period,
                    "grid_multiplier": grid_multiplier,
                    "fin_threshold": fin_threshold,
                    "save_history": save_history,
                    "deep_risk": deep_risk,
                    "paper_execute": paper_exec
                }
                run_analysis_logic(target, scanner, plotter, memory, kb, learner, portfolio_manager, settings, source_info)

        with st.expander("📦 批量分析", expanded=False):
            batch_source = st.selectbox("来源", ["观测池", "雷达结果", "巡逻结果", "券商金股池", "策略池"], key="tac_batch_source")
            batch_codes = []
            batch_label = ""

            if batch_source == "观测池":
                batch_codes = _load_watchlist_codes()
                batch_label = "观测池"
            elif batch_source == "券商金股池":
                entries, meta = _load_broker_pool()
                batch_codes = [e.get("code") for e in entries if e.get("code")]
                batch_label = f"券商金股池 {meta.get('month','')}"
            elif batch_source == "策略池":
                pools = _load_strategy_pools()
                if pools:
                    pool_names = sorted(list(pools.keys()))
                    sel_pool = st.selectbox("选择策略池", pool_names, key="tac_batch_pool")
                    entries, _ = _load_strategy_pool(sel_pool)
                    batch_codes = [e.get("code") for e in entries if e.get("code")]
                    batch_label = f"策略池 {sel_pool}"
                else:
                    st.info("暂无策略池")
            elif batch_source == "雷达结果":
                results = _load_strategy_results()
                if results:
                    keys = sorted(list(results.keys()))
                    sel_key = st.selectbox("选择雷达记录", keys, key="tac_batch_radar")
                    run = results.get(sel_key, {})
                    batch_codes = _extract_codes_from_run(run)
                    batch_label = f"雷达 {run.get('strategy','')}"
                else:
                    st.info("暂无雷达结果")
            elif batch_source == "巡逻结果":
                history = _load_patrol_history()
                if history:
                    labels = [
                        f"{h.get('time','')} | {h.get('strategy','')} | {h.get('scope','')}"
                        for h in history
                    ]
                    idx = st.selectbox("选择巡逻记录", list(range(len(history))), format_func=lambda i: labels[i], key="tac_batch_patrol")
                    run = history[idx] if idx is not None else {}
                    batch_codes = _extract_codes_from_run(run)
                    batch_label = f"巡逻 {run.get('strategy','')}"
                else:
                    st.info("暂无巡逻记录")

            batch_codes = [c for c in batch_codes if c]
            batch_codes = list(dict.fromkeys(batch_codes))

            if not batch_codes:
                st.caption("无可用标的")
            else:
                limit_max = min(300, len(batch_codes))
                top_n_default = min(50, limit_max)
                top_n = st.slider("批量数量上限", 5, limit_max, top_n_default, step=5, key="tac_batch_topn")
                batch_mode = st.radio("分析模式", ["快评", "深度"], horizontal=True, key="tac_batch_mode")
                batch_save = st.checkbox("写入战术复盘", value=False, key="tac_batch_save")

                if st.button("开始批量分析", key="tac_batch_run"):
                    app = _get_tac_app()
                    progress = st.progress(0)
                    results = []
                    total = min(top_n, len(batch_codes))
                    codes = batch_codes[:total]

                    last_trade_date = None
                    try:
                        last_trade_date = scanner.data_skill.get_last_trade_date()
                    except Exception:
                        last_trade_date = None

                    weather = sentiment.get_weather_report() if enable_sentiment and batch_mode == "深度" else {
                        "weather": "中性", "icon": "⛅", "bg_color": "#eeeeee"
                    }
                    morning_pack = ensure_morning_briefing(portfolio_manager, enabled=enable_morning and batch_mode == "深度")

                    for i, code in enumerate(codes):
                        progress.progress((i + 1) / total)
                        df = scanner.data_skill.get_history(code, days=200)
                        if df is None or df.empty:
                            continue
                        data_quality = _data_quality(df, last_trade_date)

                        if batch_mode == "深度":
                            dealer_res = hunter.analyze(df)
                            chip_res = chip_analyst.analyze(df)
                            cycle_res = compass.detect_phase(df)
                            liq_res = liq_guard.check(df)
                        else:
                            dealer_res = {}
                            chip_res = {}
                            cycle_res = {"score_impact": 0, "phase": "N/A", "icon": "⏱️"}
                            liq_res = {}

                        if enable_kb and batch_mode == "深度":
                            try:
                                kb_query = " ".join([
                                    str(cycle_res.get("phase", "") or ""),
                                    str(dealer_res.get("risk_level", "") or ""),
                                    str(chip_res.get("status", "") or ""),
                                    str(liq_res.get("status", "") or "")
                                ]).strip()
                                kb_pack = kb.build_context(kb_query, limit=3)
                                k_ctx = kb_pack.get("context") or "无特定战法"
                                k_titles = kb_pack.get("titles", [])
                            except Exception:
                                k_ctx = "知识库连接异常"
                                k_titles = []
                        else:
                            k_ctx = "批量快评"
                            k_titles = []

                        morning_view = morning_pack.get("view") if enable_morning and batch_mode == "深度" else "无晨报"
                        final_input = f"批量分析|宏观:{morning_view}|周期:{cycle_res.get('phase')}"

                        try:
                            res = app.invoke({
                                "stock_code": code,
                                "messages": [],
                                "morning_strategy": final_input,
                                "knowledge_context": k_ctx,
                                "deep_risk": batch_mode == "深度",
                                "paper_execute": False,
                                "dealer_hunter": dealer_res,
                                "chip_analyst": chip_res,
                                "cycle_compass": cycle_res,
                                "liquidity_guard": liq_res,
                                "sentiment_weather": weather if enable_sentiment else {},
                                "knowledge_titles": k_titles,
                                "knowledge_items": []
                            })
                        except Exception:
                            continue

                        sig = res.get("trading_signal", {})
                        details = sig.get("details", {})
                        scores = details.get("scores", {})
                        score_val = scores.get("total", 50) + cycle_res.get("score_impact", 0)
                        score_val = max(0, min(100, score_val))

                        price = df.iloc[-1].get("close") if "close" in df.columns else None
                        pct = df.iloc[-1].get("pct_chg") if "pct_chg" in df.columns else None

                        fin_snapshot = _calc_fin_snapshot(scanner, code) if enable_fin else None
                        fin_score = fin_snapshot.get("score") if fin_snapshot else None

                        row = {
                            "code": code,
                            "name": display_name(code),
                            "action": sig.get("action", "HOLD"),
                            "score": score_val,
                            "price": price,
                            "pct": pct,
                            "fin_score": fin_score,
                            "last_date": data_quality.get("last_date"),
                            "last_trade_date": data_quality.get("last_trade_date"),
                            "source": batch_label
                        }
                        results.append(row)

                        if batch_save:
                            record = {
                                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "code": code,
                                "name": display_name(code),
                                "action": sig.get("action", "HOLD"),
                                "score": score_val,
                                "source": {"source": "batch", "label": batch_label},
                                "fin_score": fin_score,
                                "data_quality": data_quality,
                                "settings": {
                                    "batch_mode": batch_mode,
                                    "enable_financial": enable_fin,
                                    "enable_kb": enable_kb
                                }
                            }
                            _save_tactics_record(record)

                    progress.empty()
                    if results:
                        df_view = pd.DataFrame(results)
                        st.dataframe(df_view, use_container_width=True)
                        st.download_button(
                            "导出批量结果 CSV",
                            data=df_view.to_csv(index=False),
                            file_name=f"tactics_batch_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("批量分析无结果")

        with st.expander("📝 战术复盘", expanded=False):
            history = _load_tactics_history()
            if not history:
                st.info("暂无战术复盘记录")
            else:
                labels = [
                    f"{h.get('time','')} | {h.get('code','')} | {h.get('action','')}"
                    for h in history
                ]
                idx = st.selectbox("选择记录", list(range(len(history))), format_func=lambda i: labels[i], key="tac_hist_select")
                record = history[idx] if idx is not None else {}
                if record:
                    st.caption(f"时间: {record.get('time','')} | 得分: {record.get('score','')}")
                    st.json(record)
                    if st.button("载入到战术", key="tac_hist_load"):
                        st.session_state["tac_input"] = record.get("code", "")
                        st.session_state["auto_run"] = True
                        st.rerun()
