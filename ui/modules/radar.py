import streamlit as st
import pandas as pd
import os
import json
import datetime
from core.stock_name import display_name
from core.strategy_display import display_strategy_name
from core.watchlist import load_entries, append_entries
from skills.dealer_hunter import DealerHunter
from core.cognitive_graph import build_cognitive_graph
from core.threshold_profiles import (
    load_profiles,
    list_profile_names,
    get_profile,
    get_active_profile_name,
    set_active_profile_name,
    PROFILE_DESC,
)

DATA_DIR = "data"
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.json")
BROKER_POOL_PATH = os.path.join(DATA_DIR, "broker_pool.json")
STRATEGY_RESULTS_PATH = os.path.join(DATA_DIR, "strategy_results.json")
STRATEGY_POOL_PATH = os.path.join(DATA_DIR, "strategy_pools.json")
FIN_SETTINGS_PATH = os.path.join(DATA_DIR, "financial_settings.json")
RADAR_HISTORY_PATH = os.path.join(DATA_DIR, "radar_history.json")
RADAR_LAST_PATH = os.path.join(DATA_DIR, "radar_last.json")


def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def _load_watchlist_codes():
    entries = load_entries()
    return [e.get("code") for e in entries if e.get("code")]


def _save_watchlist_codes(codes, source_detail=None, price_map=None):
    price_map = price_map or {}
    entries = []
    for item in codes or []:
        if isinstance(item, dict):
            entry = dict(item)
        else:
            entry = {"code": item}
        code = entry.get("code") or entry.get("ts_code") or entry.get("symbol")
        entry["code"] = code
        if entry.get("init_price") is None and code in price_map:
            entry["init_price"] = price_map.get(code)
        entries.append(entry)
    append_entries(entries, source="radar", source_detail=source_detail, fill_price=True, fill_name=True)


def _load_broker_pool():
    if not os.path.exists(BROKER_POOL_PATH):
        return [], {}
    try:
        with open(BROKER_POOL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], {}
    meta = {}
    if isinstance(data, dict):
        meta = {
            "month": data.get("month"),
            "updated_at": data.get("updated_at"),
            "meta": data.get("meta", {})
        }
        entries = data.get("codes", [])
    elif isinstance(data, list):
        entries = data
    else:
        entries = []

    out = []
    seen = set()
    for item in entries:
        if isinstance(item, dict):
            code = item.get("code") or item.get("ts_code") or item.get("symbol")
            name = item.get("name") or code
        else:
            code = str(item)
            name = code
        if code and code not in seen:
            seen.add(code)
            out.append({"code": code, "name": name})
    return out, meta


def _load_strategy_pool(strategy_code):
    if not os.path.exists(STRATEGY_POOL_PATH):
        return [], {}
    try:
        with open(STRATEGY_POOL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], {}
    if not isinstance(data, dict):
        return [], {}
    item = data.get(strategy_code)
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
        if code and code not in seen:
            seen.add(code)
            out.append({"code": code, "name": name})
    return out, meta


def _append_watchlist(code, price=None, source_detail=None):
    if not code:
        return
    append_entries(
        [{"code": code, "init_price": price}],
        source="radar",
        source_detail=source_detail,
        fill_price=True,
        fill_name=True
    )


def _save_radar_run(run):
    _ensure_data_dir()
    history = []
    if os.path.exists(RADAR_HISTORY_PATH):
        try:
            with open(RADAR_HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    history = data
        except Exception:
            history = []
    history.insert(0, run)
    history = history[:50]
    try:
        with open(RADAR_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        with open(RADAR_LAST_PATH, "w", encoding="utf-8") as f:
            json.dump(run, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _save_strategy_results(strategy_code, run):
    _ensure_data_dir()
    data = {}
    if os.path.exists(STRATEGY_RESULTS_PATH):
        try:
            with open(STRATEGY_RESULTS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data = raw
        except Exception:
            data = {}
    data[strategy_code] = run
    try:
        with open(STRATEGY_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_fin_settings():
    if not os.path.exists(FIN_SETTINGS_PATH):
        return {}
    try:
        with open(FIN_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_fin_settings(data):
    _ensure_data_dir()
    try:
        with open(FIN_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _apply_radar_profile(profile):
    if not isinstance(profile, dict):
        return
    radar = profile.get("radar", {})
    if not isinstance(radar, dict):
        return
    updates = {
        "radar_deep_risk": radar.get("deep_risk"),
        "fin_threshold": radar.get("fin_threshold"),
    }
    for key, val in updates.items():
        if val is not None:
            st.session_state[key] = val
    fin_th = radar.get("fin_threshold")
    if fin_th is not None:
        fin_settings = _load_fin_settings()
        fin_settings["threshold"] = int(fin_th)
        _save_fin_settings(fin_settings)


def _load_strategy_results():
    if not os.path.exists(STRATEGY_RESULTS_PATH):
        return {}
    try:
        with open(STRATEGY_RESULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def render(scanner, plotter):
    st.header("🔭 猎手雷达 (Global Hunter)")
    st.markdown("双阶段漏斗：**全市场粗筛 (免费)** -> **AI 深度精算 (按需)**")
    
    # 动态获取策略列表
    strategy_options = scanner.get_strategy_list()
    hunter = DealerHunter()
    
    scope_options = ["我的观察池 (默认)", "🌍 全市场 (沪深A股/创业板)", "🏆 券商金股池", "🎯 策略绑定池"]
    bound_pool, bound_meta = _load_strategy_pool(st.session_state.get("radar_strategy", ""))
    default_scope = st.session_state.get("radar_scope")
    if default_scope not in scope_options:
        default_scope = scope_options[0]
    if bound_pool:
        default_scope = "🎯 策略绑定池"

    with st.expander("⚙️ 扫描雷达设置", expanded=True):
        profiles = load_profiles()
        profile_names = list_profile_names(profiles)
        active_profile = get_active_profile_name(profiles)
        if active_profile not in profiles:
            active_profile = profile_names[0]
        active_profile_data = get_profile(active_profile, profiles)
        radar_profile = active_profile_data.get("radar", {}) if isinstance(active_profile_data, dict) else {}

        st.markdown("#### 🧭 阈值方案")
        idx = profile_names.index(active_profile) if active_profile in profile_names else 0
        profile_name = st.selectbox("选择方案", profile_names, index=idx, key="radar_profile_select")
        desc = PROFILE_DESC.get(profile_name)
        if desc:
            st.caption(desc)
        if st.button("一键套用到雷达参数", key="radar_profile_apply"):
            _apply_radar_profile(get_profile(profile_name, profiles))
            set_active_profile_name(profile_name)
            st.success("已应用雷达阈值方案")
            st.rerun()

        c1, c2 = st.columns([2, 1])
        with c1:
            scope = st.radio(
                "扫描范围",
                scope_options,
                horizontal=True,
                index=scope_options.index(default_scope),
                key="radar_scope"
            )
        with c2:
            # 🔥 这里现在包含自定义策略了
            default_strat = st.session_state.get("radar_strategy")
            if default_strat not in strategy_options:
                default_strat = strategy_options[0] if strategy_options else ""
            strat = st.selectbox(
                "核心策略",
                strategy_options,
                index=strategy_options.index(default_strat) if default_strat in strategy_options else 0,
                key="radar_strategy"
            )
            
        limit = 200
        if "全市场" in scope:
            limit = st.slider("扫描样本数量", 100, 3000, 200, step=100)
        if "券商金股池" in scope:
            pool_entries, pool_meta = _load_broker_pool()
            if pool_entries:
                tip = f"金股池规模: {len(pool_entries)}"
                if pool_meta.get("month"):
                    tip += f" | 月份: {pool_meta.get('month')}"
                if pool_meta.get("updated_at"):
                    tip += f" | 更新: {pool_meta.get('updated_at')}"
                st.caption(tip)
            else:
                st.warning("未检测到金股池，请先在【券商金股】保存金股池")
        if "策略绑定池" in scope:
            bound_entries, bound_meta = _load_strategy_pool(strat)
            if bound_entries:
                tip = f"绑定池规模: {len(bound_entries)}"
                if bound_meta.get("type"):
                    tip += f" | 类型: {bound_meta.get('type')}"
                if bound_meta.get("from") and bound_meta.get("to"):
                    tip += f" | 区间: {bound_meta.get('from')}->{bound_meta.get('to')}"
                st.caption(tip)
            else:
                st.warning("未检测到策略绑定池，请先在【券商金股-月度对比】生成策略")
        c3, c4, c5, c6 = st.columns(4)
        with c3:
            risk_scan = st.checkbox("风险雷达(主力)", value=True, key="radar_risk_scan")
        with c4:
            save_watchlist = st.checkbox("入选写入观察池", value=False, key="radar_save_watchlist")
        with c5:
            deep_risk_default = bool(radar_profile.get("deep_risk", False))
            deep_risk = st.checkbox(
                "深度风控",
                value=st.session_state.get("radar_deep_risk", deep_risk_default),
                key="radar_deep_risk"
            )
        with c6:
            save_result = st.checkbox("保存策略结果", value=bool(st.session_state.get("radar_save_result")), key="radar_save_result")

        if "FinancialStrong" in strat:
            fin_settings = _load_fin_settings()
            default_fin = fin_settings.get("threshold")
            if default_fin is None:
                default_fin = int(radar_profile.get("fin_threshold", int(getattr(scanner, "financial_threshold", 70))))
            fin_th = st.slider(
                "财务评分阈值",
                50,
                90,
                int(st.session_state.get("fin_threshold", default_fin)),
                step=5,
                key="fin_threshold"
            )
            fin_settings["threshold"] = fin_th
            _save_fin_settings(fin_settings)
            try:
                scanner.financial_threshold = fin_th
            except Exception:
                pass

    auto_run = st.session_state.pop("radar_auto_run", False)
    if st.button("🛰️ 启动雷达", type="primary") or auto_run:
        if "策略绑定池" in scope:
            mode_code = "strategy_pool"
        elif "券商金股池" in scope:
            mode_code = "broker_pool"
        else:
            mode_code = "global" if "全市场" in scope else "watchlist"
        
        # 解析策略代码
        if "游资回马枪" in strat: strat_code = "hot_money"
        elif "风格克隆" in strat: strat_code = "dna"
        elif "超跌" in strat: strat_code = "oversold"
        elif "放量突破" in strat: strat_code = "standard"
        elif "尾盘强势" in strat or "TailStrength" in strat: strat_code = "tail_strength"
        elif "财务强势" in strat or "FinancialStrong" in strat: strat_code = "financial_strong"
        else:
            # 提取自定义策略名 "user_xxx (自定义)" -> "user_xxx"
            raw_name = strat.split(" (")[0]
            strat_code = raw_name # 直接用文件名
        
        with st.spinner("📡 正在建立目标清单..."):
            if mode_code == "strategy_pool":
                pool, _ = _load_strategy_pool(strat_code)
            elif mode_code == "broker_pool":
                pool, _ = _load_broker_pool()
            else:
                pool = scanner.get_candidate_pool(mode=mode_code, limit=limit)
        
        if not pool:
            if mode_code == "strategy_pool":
                st.error("策略绑定池为空，请先在【券商金股-月度对比】生成策略")
            elif mode_code == "broker_pool":
                st.error("金股池为空，请先在【券商金股】保存金股池")
            else:
                st.error("无法获取股票名单。")
            return

        with st.status(f"⚡ 正在匹配 [{strat}]...", expanded=True) as status:
            cands, logs = scanner.technical_filter(pool, mode=strat_code)
            
            if cands:
                status.update(label=f"✅ 扫描完成！锁定 {len(cands)} 个信号", state="complete")
                if strat_code == "financial_strong":
                    try:
                        cands = sorted(cands, key=lambda x: (x.get("fin_score") is None, -(x.get("fin_score") or 0)))
                    except Exception:
                        pass
                if save_watchlist:
                    codes = [c.get("code") for c in cands if c.get("code")]
                    if codes:
                        price_map = {c.get("code"): c.get("price") for c in cands if c.get("code")}
                        _save_watchlist_codes(codes, source_detail=scope, price_map=price_map)
                        st.caption("已写入观察池 (data/watchlist.json)")

                run_record = {
                    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "scope": "strategy_pool" if "策略绑定池" in scope else ("broker_pool" if "券商金股池" in scope else ("global" if "全市场" in scope else "watchlist")),
                    "strategy": strat,
                    "strategy_code": strat_code,
                    "count": len(cands),
                    "candidates": [
                        {
                            "code": c.get("code"),
                            "price": c.get("price"),
                            "pct": c.get("pct"),
                            "reason": c.get("reason"),
                            "fin_score": c.get("fin_score")
                        } for c in cands
                    ]
                }
                if strat_code == "financial_strong":
                    run_record["fin_threshold"] = getattr(scanner, "financial_threshold", None)
                _save_radar_run(run_record)
                if save_result:
                    _save_strategy_results(strat_code, run_record)
                st.divider()
                for c in cands:
                    with st.container():
                        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                        with c1:
                            code = c.get("code")
                            name = display_name(code) if code else c.get("name", "")
                            st.markdown(f"**{name}**")
                            if code:
                                st.caption(display_name(code, with_code=True))
                            if st.button("加入观察池", key=f"wl_{code}"):
                                _append_watchlist(code, price=c.get("price"), source_detail=scope)
                                st.success("已加入观察池")
                        with c2: st.metric("现价", f"{c['price']:.2f}")
                        with c3: st.metric("涨幅", f"{c['pct']:.2f}%")
                        with c4:
                            if c.get("fin_score") is not None:
                                st.metric("财务评分", f"{c.get('fin_score'):.0f}")
                        risk_res = None
                        df_chart = None
                        if risk_scan and code:
                            df_chart = scanner.data_skill.get_history(code, days=80)
                            if df_chart is not None and not df_chart.empty:
                                risk_res = hunter.analyze(df_chart)
                                st.caption(f"风险: {risk_res.get('risk_level', 'N/A')}")
                        
                        with st.expander("查看 K线与理由"):
                            st.info(f"⚡ 触发信号: {c['reason']}")
                            df = df_chart if df_chart is not None else scanner.data_skill.get_history(c['code'], days=120)
                            if df is not None and not df.empty:
                                st.plotly_chart(plotter.plot_kline(df, title=name or c['code']), use_container_width=True)

                            btn_cols = st.columns(3)
                            if btn_cols[0].button("发送到战术指挥室", key=f"to_tac_{code}"):
                                st.session_state['tac_input'] = code
                                st.session_state['auto_run'] = True
                                st.session_state['current_page'] = "🧘 战术指挥室"
                                st.success("已跳转到战术指挥室")
                                st.rerun()
                            if btn_cols[1].button("财务透视", key=f"to_fin_{code}"):
                                st.session_state["fin_code"] = code
                                st.session_state["current_page"] = "📊 财务透视"
                                st.success("已跳转到财务透视")
                                st.rerun()
                            if btn_cols[2].button("深度分析", key=f"deep_{code}"):
                                if "radar_app" not in st.session_state:
                                    st.session_state["radar_app"] = build_cognitive_graph()
                                app = st.session_state["radar_app"]
                                with st.spinner("分析中..."):
                                    res = app.invoke({
                                        "stock_code": code,
                                        "messages": [],
                                        "deep_risk": deep_risk
                                    })
                                sig = res.get("trading_signal", {})
                                act = sig.get("action", "HOLD")
                                core_view = sig.get("details", {}).get("core_view", "")
                                st.success(f"结论: {act}")
                                if core_view:
                                    st.caption(core_view)

                            st.caption("💡 扫描结果已可用于战术指挥室/巡逻官/工坊联动。")
                        st.divider()
            else:
                status.update(label="无目标入选", state="complete")

    with st.expander("📌 策略结果复盘", expanded=False):
        data = _load_strategy_results()
        if not data:
            st.info("暂无策略结果记录")
        else:
            strategies = sorted(list(data.keys()))
            sel = st.selectbox("选择策略", strategies, format_func=display_strategy_name)
            run = data.get(sel, {})
            if not run:
                st.info("无可用记录")
            else:
                st.caption(f"时间: {run.get('time', '')} | 范围: {run.get('scope', '')} | 策略: {display_strategy_name(run.get('strategy', ''))}")
                st.metric("命中数量", run.get("count", 0))
                cands = run.get("candidates", [])
                if cands:
                    df_view = pd.DataFrame(cands)
                    st.dataframe(df_view, use_container_width=True)
                else:
                    st.info("暂无命中明细")

    with st.expander("📈 财务评分趋势", expanded=False):
        data = _load_strategy_results()
        fin_runs = []
        for _, v in data.items():
            if isinstance(v, dict) and v.get("strategy_code") == "financial_strong":
                fin_runs.append(v)
        if not fin_runs:
            st.info("暂无财务评分扫描记录")
        else:
            fin_runs = sorted(fin_runs, key=lambda x: x.get("time", ""))
            points = []
            for r in fin_runs:
                cands = r.get("candidates", [])
                if not cands:
                    continue
                scores = [c.get("fin_score") for c in cands if c.get("fin_score") is not None]
                if not scores:
                    continue
                points.append({
                    "time": r.get("time"),
                    "avg_score": sum(scores) / len(scores),
                    "count": len(scores),
                    "threshold": r.get("fin_threshold")
                })
            if points:
                df_tr = pd.DataFrame(points)
                st.line_chart(df_tr.set_index("time")[["avg_score"]], height=200)
                st.bar_chart(df_tr.set_index("time")["count"], height=160)
                st.dataframe(df_tr, use_container_width=True)
            else:
                st.info("暂无可绘制的数据")
