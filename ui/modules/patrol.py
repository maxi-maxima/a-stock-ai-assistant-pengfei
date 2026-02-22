import streamlit as st
import pandas as pd
import datetime
import os
import json

from core.learning_log import get_last_feature_weights
from core.stock_name import display_name
from core.watchlist import load_entries, append_entries
from core.financial_analysis import extract_metrics, score_financial
from core.threshold_profiles import (
    load_profiles,
    list_profile_names,
    get_profile,
    get_active_profile_name,
    set_active_profile_name,
    PROFILE_DESC,
)
from core.code_gen import StrategyGenerator

DATA_DIR = "data"
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.json")
BROKER_POOL_PATH = os.path.join(DATA_DIR, "broker_pool.json")
STRATEGY_POOL_PATH = os.path.join(DATA_DIR, "strategy_pools.json")
FIN_SETTINGS_PATH = os.path.join(DATA_DIR, "financial_settings.json")
PATROL_HISTORY_PATH = os.path.join(DATA_DIR, "patrol_history.json")
PATROL_LAST_PATH = os.path.join(DATA_DIR, "patrol_last.json")
STRATEGY_RESULTS_PATH = os.path.join(DATA_DIR, "strategy_results.json")


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
    append_entries(entries, source="patrol", source_detail=source_detail, fill_price=True, fill_name=True)


def _append_watchlist(code, price=None, source_detail=None):
    if not code:
        return
    append_entries(
        [{"code": code, "init_price": price}],
        source="patrol",
        source_detail=source_detail,
        fill_price=True,
        fill_name=True
    )


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




def _load_strategy_pools():
    if not os.path.exists(STRATEGY_POOL_PATH):
        return {}
    try:
        with open(STRATEGY_POOL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_name(name):
    if not name:
        return ""
    cleaned = "".join([c if (c.isalnum() or c == "_") else "_" for c in str(name)])
    return cleaned.strip("_")


def _dedup_entries(entries):
    seen = set()
    out = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name": item.get("name", code)})
    return out


def _save_strategy_pool(strategy_name, entries, meta=None):
    _ensure_data_dir()
    clean = _dedup_entries(entries)
    data = _load_strategy_pools()
    data[strategy_name] = {
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "codes": clean,
        "meta": meta or {}
    }
    with open(STRATEGY_POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_pool_strategy_code(pool_codes, reason):
    codes = list(dict.fromkeys([c for c in pool_codes if c]))
    code_lines = ["POOL_CODES = {" + ", ".join([f"'{c}'" for c in codes]) + "}"]
    code_lines.append("def check(df):")
    code_lines.append("    code = ''")
    code_lines.append("    try:")
    code_lines.append("        code = df.attrs.get('ts_code') or ''")
    code_lines.append("    except Exception:")
    code_lines.append("        code = ''")
    code_lines.append("    if not code and 'ts_code' in df.columns:")
    code_lines.append("        try:")
    code_lines.append("            code = str(df['ts_code'].iloc[-1])")
    code_lines.append("        except Exception:")
    code_lines.append("            code = ''")
    code_lines.append("    if not code:")
    code_lines.append("        return False, \"无代码\"")
    code_lines.append("    if code in POOL_CODES:")
    code_lines.append(f"        return True, \"{reason}\"")
    code_lines.append("    return False, \"\"")
    return "\n".join(code_lines) + "\n"


def _load_strategy_results():
    if not os.path.exists(STRATEGY_RESULTS_PATH):
        return {}
    try:
        with open(STRATEGY_RESULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_strategy_result_record(key, record):
    _ensure_data_dir()
    data = _load_strategy_results()
    data[key] = record
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


def _apply_patrol_profile(profile):
    if not isinstance(profile, dict):
        return
    patrol = profile.get("patrol", {})
    if not isinstance(patrol, dict):
        return
    updates = {
        "patrol_take_profit": patrol.get("take_profit"),
        "patrol_stop_loss": patrol.get("stop_loss"),
        "patrol_flow_th": patrol.get("flow_th"),
        "patrol_max_scan_global": patrol.get("max_scan_global"),
        "patrol_max_scan_pool": patrol.get("max_scan_pool"),
        "patrol_top_k": patrol.get("top_k"),
        "patrol_min_score": patrol.get("min_score"),
        "patrol_enable_fin_score": patrol.get("enable_fin_score"),
        "patrol_fin_threshold": patrol.get("fin_threshold"),
        "patrol_fin_weight": patrol.get("fin_weight"),
        "patrol_fin_filter": patrol.get("fin_filter"),
    }
    for key, val in updates.items():
        if val is not None:
            st.session_state[key] = val
    fin_th = patrol.get("fin_threshold")
    if fin_th is not None:
        fin_settings = _load_fin_settings()
        fin_settings["threshold"] = int(fin_th)
        _save_fin_settings(fin_settings)


def _save_patrol_run(run):
    _ensure_data_dir()
    history = []
    if os.path.exists(PATROL_HISTORY_PATH):
        try:
            with open(PATROL_HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    history = data
        except Exception:
            history = []
    history.insert(0, run)
    history = history[:50]
    try:
        with open(PATROL_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        with open(PATROL_LAST_PATH, "w", encoding="utf-8") as f:
            json.dump(run, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_patrol_history():
    if not os.path.exists(PATROL_HISTORY_PATH):
        return []
    try:
        with open(PATROL_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _strategy_to_mode(strat):
    if "HotMoney" in strat:
        return "hot_money"
    if "DNA" in strat:
        return "dna"
    if "Oversold" in strat:
        return "oversold"
    if "Standard" in strat:
        return "standard"
    if "TailStrength" in strat or "尾盘强势" in strat:
        return "tail_strength"
    if "FinancialStrong" in strat or "财务强势" in strat:
        return "financial_strong"
    if strat.startswith("user_") or "自定义" in strat:
        return strat.split(" (")[0]
    return "standard"


def _calc_fin_score(scanner, code, cache, weights=None):
    today = datetime.date.today().strftime("%Y-%m-%d")
    cache_key = f"{code}|{today}"
    if cache_key in cache:
        return cache[cache_key]
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
            cache[cache_key] = (None, None)
            return cache[cache_key]
        metrics = extract_metrics(code, df_inc, df_bs, df_cf)
        score, grade, _ = score_financial(metrics, weights)
        cache[cache_key] = (score, grade)
        return cache[cache_key]
    except Exception:
        cache[cache_key] = (None, None)
        return cache[cache_key]


def render(scanner, real_portfolio):
    st.header("👮 AI 盘中巡逻官 (Intraday Patrol)")
    st.caption("一键扫描您的【实盘持仓】和【全市场机会】，捕捉盘中异动，并与战术/财务/观察池联动。")

    positions = real_portfolio.get_all_positions()

    with st.expander("⚙️ 巡逻设置", expanded=True):
        profiles = load_profiles()
        profile_names = list_profile_names(profiles)
        active_profile = get_active_profile_name(profiles)
        if active_profile not in profiles:
            active_profile = profile_names[0]
        active_profile_data = get_profile(active_profile, profiles)
        patrol_profile = active_profile_data.get("patrol", {}) if isinstance(active_profile_data, dict) else {}

        st.markdown("#### 🧭 阈值方案")
        idx = profile_names.index(active_profile) if active_profile in profile_names else 0
        profile_name = st.selectbox("选择方案", profile_names, index=idx, key="patrol_profile_select")
        desc = PROFILE_DESC.get(profile_name)
        if desc:
            st.caption(desc)
        if st.button("一键套用到巡逻参数", key="patrol_profile_apply"):
            _apply_patrol_profile(get_profile(profile_name, profiles))
            set_active_profile_name(profile_name)
            st.success("已应用巡逻阈值方案")
            st.rerun()

        c_run1, c_run2 = st.columns(2)
        with c_run1:
            run_holdings = st.checkbox("执行持仓巡逻", value=True)
        with c_run2:
            run_global = st.checkbox("执行全域扫描", value=True)

        st.markdown("#### 持仓预警阈值")
        c1, c2, c3 = st.columns(3)
        with c1:
            take_profit_default = float(patrol_profile.get("take_profit", 10.0))
            take_profit = st.slider(
                "止盈阈值(%)",
                5.0,
                30.0,
                float(st.session_state.get("patrol_take_profit", take_profit_default)),
                step=0.5,
                key="patrol_take_profit"
            )
        with c2:
            stop_loss_default = float(patrol_profile.get("stop_loss", 5.0))
            stop_loss = st.slider(
                "止损阈值(%)",
                2.0,
                30.0,
                float(st.session_state.get("patrol_stop_loss", stop_loss_default)),
                step=0.5,
                key="patrol_stop_loss"
            )
        with c3:
            flow_th_default = float(patrol_profile.get("flow_th", -10000.0))
            flow_th = st.number_input(
                "主力净流出阈值(万)",
                value=float(st.session_state.get("patrol_flow_th", flow_th_default)),
                step=1000.0,
                format="%.0f",
                key="patrol_flow_th"
            )

        st.markdown("#### 全域扫描设置")
        scope_options = ["我的观察池", "全市场", "券商金股池", "策略绑定池"]
        scope = st.radio("扫描范围", scope_options, horizontal=True, index=1)

        strat_list = scanner.get_strategy_list()
        strat = st.selectbox("机会雷达策略", strat_list, index=0)
        strat_code = _strategy_to_mode(strat)

        if "全市场" in scope:
            max_scan_default = int(patrol_profile.get("max_scan_global", 1500))
            max_scan = st.slider(
                "扫描数量上限",
                500,
                5000,
                int(st.session_state.get("patrol_max_scan_global", max_scan_default)),
                step=100,
                key="patrol_max_scan_global"
            )
        else:
            max_scan_default = int(patrol_profile.get("max_scan_pool", 800))
            max_scan = st.slider(
                "扫描数量上限",
                100,
                3000,
                int(st.session_state.get("patrol_max_scan_pool", max_scan_default)),
                step=100,
                key="patrol_max_scan_pool"
            )
        top_k_default = int(patrol_profile.get("top_k", 80))
        top_k = st.slider(
            "因子联动评估数量",
            20,
            300,
            int(st.session_state.get("patrol_top_k", top_k_default)),
            step=10,
            key="patrol_top_k"
        )
        min_score_default = float(patrol_profile.get("min_score", 0.0))
        min_score = st.slider(
            "综合分最低阈值",
            0.0,
            100.0,
            float(st.session_state.get("patrol_min_score", min_score_default)),
            step=1.0,
            key="patrol_min_score"
        )
        sort_by = st.selectbox("结果排序", ["综合分", "涨跌幅", "财务分", "资金分", "技术分", "筹码分"], index=0)

        st.markdown("#### 联动输出")
        save_watchlist = st.checkbox("入选写入观察池", value=False)
        save_result = st.checkbox("保存巡逻结果", value=True)
        sync_radar = st.checkbox("同步到雷达复盘", value=True)

        gen_pool = st.checkbox("生成策略绑定池", value=False)
        pool_default = f"patrol_{strat_code}_{datetime.date.today().strftime('%Y%m%d')}"
        pool_top_max = max(10, min(300, top_k))
        pool_top_default = min(80, pool_top_max)
        pool_name = st.text_input("策略池名称", value=pool_default, key="patrol_pool_name", disabled=not gen_pool)
        pool_top = st.slider("策略池纳入前 N", 10, pool_top_max, pool_top_default, step=10, disabled=not gen_pool)

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
            bound_entries, bound_meta = _load_strategy_pool(strat_code)
            if bound_entries:
                tip = f"绑定池规模: {len(bound_entries)}"
                if bound_meta.get("type"):
                    tip += f" | 类型: {bound_meta.get('type')}"
                if bound_meta.get("from") and bound_meta.get("to"):
                    tip += f" | 区间: {bound_meta.get('from')}->{bound_meta.get('to')}"
                st.caption(tip)
            else:
                st.warning("未检测到策略绑定池，请先在【券商金股-月度对比】生成策略池")

        fin_force = ("FinancialStrong" in strat) or ("财务强势" in strat)
        enable_fin_default = bool(patrol_profile.get("enable_fin_score", True))
        enable_fin_score = st.checkbox(
            "参与财务评分",
            value=fin_force if fin_force else st.session_state.get("patrol_enable_fin_score", enable_fin_default),
            disabled=fin_force,
            key="patrol_enable_fin_score"
        )
        fin_weight = 10.0
        fin_threshold = None
        fin_filter = False
        if enable_fin_score:
            fin_settings = _load_fin_settings()
            default_fin = fin_settings.get("threshold")
            if default_fin is None:
                default_fin = int(patrol_profile.get("fin_threshold", int(getattr(scanner, "financial_threshold", 70))))
            fin_threshold = st.slider(
                "财务评分阈值",
                50,
                90,
                int(st.session_state.get("patrol_fin_threshold", default_fin)),
                step=5,
                key="patrol_fin_threshold"
            )
            fin_settings["threshold"] = fin_threshold
            _save_fin_settings(fin_settings)
            fin_weight_default = float(patrol_profile.get("fin_weight", 10.0))
            fin_weight = st.slider(
                "财务评分权重",
                0.0,
                30.0,
                float(st.session_state.get("patrol_fin_weight", fin_weight_default)),
                step=2.0,
                key="patrol_fin_weight"
            )
            fin_filter_default = bool(patrol_profile.get("fin_filter", fin_force))
            fin_filter = st.checkbox(
                "启用财务阈值过滤",
                value=st.session_state.get("patrol_fin_filter", fin_filter_default),
                key="patrol_fin_filter"
            )
            if fin_force:
                try:
                    scanner.financial_threshold = fin_threshold
                except Exception:
                    pass

    if st.button("🚨 启动巡逻", type="primary"):
        st.divider()
        holding_alerts = []

        if run_holdings:
            st.subheader("💼 持仓风控巡逻")
            if not positions:
                st.info("实盘目前空仓，无须巡逻。")
                st.session_state["patrol_holding_alerts"] = []
                st.session_state["patrol_action_codes"] = []
                st.session_state.pop("patrol_hold_action", None)
            else:
                alerts = []
                progress_bar = st.progress(0)
                total_tasks = len(positions)
                for i, (code, info) in enumerate(positions.items()):
                    progress_bar.progress((i + 1) / total_tasks)
                    df = scanner.data_skill.get_history(code, days=30)
                    if df.empty:
                        continue
                    curr = df.iloc[-1]
                    price = float(curr.get("close", 0) or 0)
                    pct = float(curr.get("pct_chg", 0) or 0)
                    cost = float(info.get("cost", 0) or 0)
                    profit_pct = None
                    if cost > 0:
                        profit_pct = (price - cost) / cost * 100

                    cap = scanner.data_skill.capital.get_individual_money_flow(code)
                    net_flow = cap.get("net_mf_amount", 0)

                    flags = []
                    suggestion = "持有"

                    if cost <= 0:
                        flags.append("成本缺失")
                        suggestion = "补全成本"
                    else:
                        if profit_pct >= take_profit:
                            flags.append("止盈达标")
                            suggestion = "考虑减仓"
                        if profit_pct <= -abs(stop_loss):
                            flags.append("触及止损")
                            suggestion = "注意风控"

                    if net_flow <= flow_th:
                        flags.append("主力净流出")
                        if suggestion == "持有":
                            suggestion = "警惕下跌"

                    status = " | ".join(flags) if flags else "正常"
                    alerts.append({
                        "code": code,
                        "股票": display_name(code),
                        "现价": f"{price:.2f}",
                        "涨跌幅": f"{pct:.2f}%",
                        "持仓盈亏": f"{profit_pct:.2f}%" if profit_pct is not None else "-",
                        "主力资金": f"{net_flow:.1f}万" if net_flow is not None else "-",
                        "状态": status,
                        "AI建议": suggestion
                    })

                progress_bar.empty()
                if alerts:
                    holding_alerts = alerts
                    df_alerts = pd.DataFrame(alerts)
                    st.dataframe(df_alerts.drop(columns=["code"], errors="ignore"), use_container_width=True)
                    risks = [a for a in alerts if "正常" not in a.get("状态", "")]
                    if risks:
                        st.error(f"⚠️ 发现 {len(risks)} 个持仓预警！")
                    else:
                        st.success("✅ 持仓巡逻完毕，一切正常。")

                    action_codes = [a.get("code") for a in alerts if a.get("code")]
                    st.session_state["patrol_holding_alerts"] = alerts
                    st.session_state["patrol_action_codes"] = action_codes
                    if not action_codes:
                        st.session_state.pop("patrol_hold_action", None)
                else:
                    st.session_state["patrol_holding_alerts"] = []
                    st.session_state["patrol_action_codes"] = []
                    st.session_state.pop("patrol_hold_action", None)

        if run_global:
            st.divider()
            st.subheader("🔭 全域机会雷达")

            if "策略绑定池" in scope:
                scope_code = "strategy_pool"
            elif "券商金股池" in scope:
                scope_code = "broker_pool"
            elif "全市场" in scope:
                scope_code = "global"
            else:
                scope_code = "watchlist"

            with st.spinner("全市场扫描中（可能需要一点时间）..."):
                if scope_code == "strategy_pool":
                    pool, _ = _load_strategy_pool(strat_code)
                elif scope_code == "broker_pool":
                    pool, _ = _load_broker_pool()
                else:
                    pool = scanner.get_candidate_pool(mode=scope_code, limit=max_scan)

            if not pool:
                if scope_code == "strategy_pool":
                    st.error("策略绑定池为空，请先在【券商金股-月度对比】生成策略池")
                elif scope_code == "broker_pool":
                    st.error("金股池为空，请先在【券商金股】保存金股池")
                else:
                    st.error("无法获取股票名单")
            else:
                with st.status(f"⚡ 正在匹配 [{strat}]...", expanded=True) as status:
                    candidates, logs = scanner.technical_filter(pool, mode=strat_code)
                    if not candidates:
                        status.update(label="无目标入选", state="complete")
                        st.info("未扫描到机会")
                    else:
                        status.update(label=f"✅ 扫描完成！锁定 {len(candidates)} 个信号", state="complete")

                        weights = get_last_feature_weights() or {}
                        w_tech = float(weights.get("technical", 25) or 25)
                        w_cap = float(weights.get("capital", 25) or 25)
                        w_chip = float(weights.get("features", 20) or 20)
                        w_news = float(weights.get("news", 10) or 10)
                        w_ref = float(weights.get("reference", 10) or 10)
                        w_fin = float(fin_weight or 0) if enable_fin_score else 0.0
                        w_total = w_tech + w_cap + w_chip + w_news + w_ref + w_fin
                        if w_total <= 0:
                            w_total = 1.0

                        cand_sorted = sorted(candidates, key=lambda x: x.get("pct", 0), reverse=True)[:top_k]
                        scored = []
                        fin_cache = st.session_state.setdefault("patrol_fin_cache", {})
                        progress = st.progress(0)
                        for i, c in enumerate(cand_sorted):
                            progress.progress((i + 1) / len(cand_sorted))
                            code = c.get("code")
                            if not code:
                                continue

                            cap = scanner.data_skill.capital.get_individual_money_flow(code)
                            net_mf = cap.get("net_mf_amount", 0)
                            chip = scanner.data_skill.chip.get_cyq_perf(code)
                            win_rate = chip.get("win_rate", 0)

                            tech_score = 50
                            if c.get("trend", 0) == 1:
                                tech_score += 10
                            if c.get("vol_ratio", 0) > 1.2:
                                tech_score += 10
                            if c.get("pct", 0) > 2:
                                tech_score += 10
                            rsi_val = c.get("rsi", 50)
                            if c.get("trend", 0) == 1:
                                rsi_upper, rsi_lower = 80, 20
                            else:
                                rsi_upper, rsi_lower = 70, 30
                            if rsi_val < rsi_lower:
                                tech_score += 5
                            if rsi_val > rsi_upper:
                                tech_score -= 5

                            cap_score = 50
                            if net_mf > 100000:
                                cap_score = 80
                            elif net_mf > 0:
                                cap_score = 60
                            elif net_mf < -100000:
                                cap_score = 20
                            elif net_mf < 0:
                                cap_score = 40

                            chip_score = 50
                            if win_rate > 70:
                                chip_score = 80
                            elif win_rate > 50:
                                chip_score = 60
                            elif win_rate < 30:
                                chip_score = 35

                            news_score = 50
                            ref_score = 50

                            fin_score = c.get("fin_score")
                            fin_grade = None
                            if enable_fin_score and fin_score is None:
                                fin_score, fin_grade = _calc_fin_score(scanner, code, fin_cache)

                            if fin_filter and fin_threshold is not None:
                                if fin_score is None or fin_score < fin_threshold:
                                    continue

                            fin_component = fin_score if fin_score is not None else 50

                            composite = (
                                tech_score * w_tech +
                                cap_score * w_cap +
                                chip_score * w_chip +
                                news_score * w_news +
                                ref_score * w_ref +
                                fin_component * w_fin
                            ) / w_total

                            if min_score and composite < min_score:
                                continue

                            scored.append({
                                "code": code,
                                "name": display_name(code),
                                "price": float(c.get("price", 0) or 0),
                                "pct": float(c.get("pct", 0) or 0),
                                "tech_score": float(tech_score),
                                "cap_score": float(cap_score),
                                "chip_score": float(chip_score),
                                "fin_score": float(fin_score) if fin_score is not None else None,
                                "composite": float(composite),
                                "reason": c.get("reason", "")
                            })

                        progress.empty()
                        if scored:
                            sort_map = {
                                "综合分": ("composite", True),
                                "涨跌幅": ("pct", True),
                                "财务分": ("fin_score", True),
                                "资金分": ("cap_score", True),
                                "技术分": ("tech_score", True),
                                "筹码分": ("chip_score", True)
                            }
                            sort_key, sort_desc = sort_map.get(sort_by, ("composite", True))
                            scored = sorted(scored, key=lambda x: (x.get(sort_key) is None, x.get(sort_key, 0)), reverse=sort_desc)
                            df_view = pd.DataFrame(scored)
                            df_view["现价"] = df_view["price"].map(lambda v: f"{v:.2f}")
                            df_view["涨跌幅"] = df_view["pct"].map(lambda v: f"{v:.2f}%")
                            df_view["技术分"] = df_view["tech_score"].map(lambda v: f"{v:.0f}")
                            df_view["资金分"] = df_view["cap_score"].map(lambda v: f"{v:.0f}")
                            df_view["筹码分"] = df_view["chip_score"].map(lambda v: f"{v:.0f}")
                            df_view["财务分"] = df_view["fin_score"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "")
                            df_view["综合分"] = df_view["composite"].map(lambda v: f"{v:.1f}")
                            df_view.rename(columns={"name": "股票"}, inplace=True)

                            cols = ["code", "股票", "现价", "涨跌幅", "技术分", "资金分", "筹码分", "财务分", "综合分", "reason"]
                            st.dataframe(df_view[cols].rename(columns={"code": "代码", "reason": "理由"}), use_container_width=True)

                            st.download_button(
                                "导出结果 CSV",
                                data=df_view[cols].rename(columns={"code": "代码", "reason": "理由"}).to_csv(index=False),
                                file_name=f"patrol_scan_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv"
                            )

                            with st.expander("✅ 批量联动操作", expanded=False):
                                option_labels = []
                                label_map = {}
                                for s in scored:
                                    code = s.get("code")
                                    if not code:
                                        continue
                                    name = s.get("name") or display_name(code)
                                    label = f"{name} ({code})"
                                    option_labels.append(label)
                                    label_map[label] = code

                                if not option_labels:
                                    st.info("暂无可选标的")
                                else:
                                    default_labels = option_labels[: min(10, len(option_labels))]
                                    selected = st.multiselect("选择标的", option_labels, default=default_labels, key="patrol_batch_select")
                                    selected_codes = [label_map.get(lbl) for lbl in selected if label_map.get(lbl)]
                                    selected_codes = list(dict.fromkeys(selected_codes))
                                    st.caption(f"已选择 {len(selected_codes)} 只")
                                    st.text_area("代码清单", value="\n".join(selected_codes), height=120)

                                    pool_name_custom = st.text_input("批量策略池名称", value=f"patrol_pick_{datetime.date.today().strftime('%Y%m%d')}", key="patrol_batch_pool_name")
                                    b1, b2 = st.columns(2)
                                    if b1.button("批量加入观察池", key="patrol_batch_wl"):
                                        if not selected_codes:
                                            st.warning("请先选择标的")
                                        else:
                                            price_map = {s.get("code"): s.get("price") for s in scored if s.get("code")}
                                            _save_watchlist_codes(selected_codes, source_detail=scope, price_map=price_map)
                                            st.success("已加入观察池")

                                    if b2.button("生成自定义策略池", key="patrol_batch_pool"):
                                        if not selected_codes:
                                            st.warning("请先选择标的")
                                        else:
                                            safe_name = _safe_name(pool_name_custom) or f"patrol_pick_{datetime.date.today().strftime('%Y%m%d')}"
                                            if safe_name != pool_name_custom:
                                                st.caption(f"名称已自动清洗为: {safe_name}")
                                            reason = f"巡逻批量池 {strat} {datetime.date.today().strftime('%Y-%m-%d')}"
                                            gen = StrategyGenerator()
                                            code = _build_pool_strategy_code(selected_codes, reason)
                                            success, msg, saved_path, is_draft = gen.save_strategy(safe_name, code)
                                            if success:
                                                strategy_key = os.path.splitext(os.path.basename(saved_path))[0]
                                                pool_entries = [{"code": c, "name": display_name(c)} for c in selected_codes]
                                                _save_strategy_pool(
                                                    strategy_key,
                                                    pool_entries,
                                                    meta={
                                                        "type": "patrol_manual",
                                                        "source": scope_code,
                                                        "strategy": strat,
                                                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                                    }
                                                )
                                                st.success(f"批量策略池已生成: {strategy_key} ({len(pool_entries)} 只)")
                                            elif is_draft:
                                                st.warning(msg)
                                            else:
                                                st.error(msg)

                            if save_watchlist:
                                codes = [c.get("code") for c in scored if c.get("code")]
                                if codes:
                                    price_map = {c.get("code"): c.get("price") for c in scored if c.get("code")}
                                    _save_watchlist_codes(codes, source_detail=scope, price_map=price_map)
                                    st.caption("已写入观察池 (data/watchlist.json)")

                            pool_key = None
                            if gen_pool:
                                if not scored:
                                    st.warning("无可用结果生成策略池")
                                else:
                                    pool_name_input = (pool_name or "").strip()
                                    pool_name_safe = _safe_name(pool_name_input) or pool_default
                                    if pool_name_safe != pool_name_input:
                                        st.caption(f"策略池名称已自动清洗为: {pool_name_safe}")
                                    top_entries = scored[:pool_top]
                                    pool_entries = [{"code": c.get("code"), "name": c.get("name")} for c in top_entries]
                                    codes = [c.get("code") for c in top_entries if c.get("code")]
                                    reason = f"巡逻池 {strat} {datetime.date.today().strftime('%Y-%m-%d')}"
                                    gen = StrategyGenerator()
                                    code = _build_pool_strategy_code(codes, reason)
                                    success, msg, saved_path, is_draft = gen.save_strategy(pool_name_safe, code)
                                    if success:
                                        strategy_key = os.path.splitext(os.path.basename(saved_path))[0]
                                        _save_strategy_pool(
                                            strategy_key,
                                            pool_entries,
                                            meta={
                                                "type": "patrol",
                                                "source": scope_code,
                                                "strategy": strat,
                                                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                            }
                                        )
                                        pool_key = strategy_key
                                        st.success(f"策略池已生成: {strategy_key} ({len(pool_entries)} 只)")
                                    elif is_draft:
                                        st.warning(msg)
                                    else:
                                        st.error(msg)

                            run_record = {
                                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "scope": scope_code,
                                "strategy": strat,
                                "strategy_code": strat_code,
                                "count": len(scored),
                                "source": "patrol",
                                "pool_key": pool_key,
                                "settings": {
                                    "take_profit": take_profit,
                                    "stop_loss": stop_loss,
                                    "flow_threshold": flow_th,
                                    "max_scan": max_scan,
                                    "top_k": top_k,
                                    "min_score": min_score,
                                    "sort_by": sort_by,
                                    "fin_enabled": enable_fin_score,
                                    "fin_threshold": fin_threshold,
                                    "fin_weight": fin_weight,
                                    "fin_filter": fin_filter,
                                    "sync_radar": sync_radar,
                                    "gen_pool": gen_pool,
                                    "pool_name": pool_name,
                                    "pool_top": pool_top
                                },
                                "holding_alerts": holding_alerts,
                                "candidates": [
                                    {
                                        "code": c.get("code"),
                                        "price": c.get("price"),
                                        "pct": c.get("pct"),
                                        "reason": c.get("reason"),
                                        "fin_score": c.get("fin_score"),
                                        "composite": c.get("composite")
                                    } for c in scored
                                ]
                            }
                            if save_result:
                                _save_patrol_run(run_record)

                            if sync_radar:
                                radar_key = f"patrol_{strat_code}_{scope_code}"
                                _save_strategy_result_record(radar_key, run_record)
                                st.caption(f"已同步到雷达复盘: {radar_key}")

                            with st.expander("🔗 候选联动操作", expanded=False):
                                for c in scored[:50]:
                                    code = c.get("code")
                                    if not code:
                                        continue
                                    name = display_name(code)
                                    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                                    with c1:
                                        st.markdown(f"**{name}**")
                                        st.caption(display_name(code, with_code=True))
                                    with c2:
                                        st.metric("现价", f"{c.get('price', 0):.2f}")
                                    with c3:
                                        st.metric("涨幅", f"{c.get('pct', 0):.2f}%")
                                    with c4:
                                        if c.get("fin_score") is not None:
                                            st.metric("财务分", f"{c.get('fin_score'):.0f}")

                                    b1, b2, b3 = st.columns(3)
                                    if b1.button("加入观察池", key=f"patrol_wl_{code}"):
                                        _append_watchlist(code, price=c.get("price"), source_detail=scope)
                                        st.success("已加入观察池")
                                    if b2.button("发送到战术指挥室", key=f"patrol_tac_{code}"):
                                        st.session_state["tac_input"] = code
                                        st.session_state["auto_run"] = True
                                        st.session_state["current_page"] = "🧘 战术指挥室"
                                        st.success("已跳转到战术指挥室")
                                        st.rerun()
                                    if b3.button("财务透视", key=f"patrol_fin_{code}"):
                                        st.session_state["fin_code"] = code
                                        st.session_state["current_page"] = "📊 财务透视"
                                        st.success("已跳转到财务透视")
                                        st.rerun()

                            with st.expander("📜 扫描日志", expanded=False):
                                for l in logs[:80]:
                                    st.write(l)
                        else:
                            st.info("筛选后无可用目标")

        action_codes = st.session_state.get("patrol_action_codes") or []
        if action_codes:
            st.subheader("🔗 持仓联动操作")
            current_code = st.session_state.get("patrol_hold_action")
            if current_code not in action_codes:
                st.session_state["patrol_hold_action"] = action_codes[0]
            sel_code = st.selectbox(
                "选择持仓",
                action_codes,
                format_func=lambda x: display_name(x, with_code=True),
                key="patrol_hold_action"
            )
            a1, a2, a3 = st.columns(3)
            if a1.button("发送到战术指挥室", key="patrol_to_tac"):
                st.session_state["tac_input"] = sel_code
                st.session_state["auto_run"] = True
                st.session_state["current_page"] = "🧘 战术指挥室"
                st.success("已跳转到战术指挥室")
                st.rerun()
            if a2.button("财务透视", key="patrol_to_fin"):
                st.session_state["fin_code"] = sel_code
                st.session_state["current_page"] = "📊 财务透视"
                st.success("已跳转到财务透视")
                st.rerun()
            if a3.button("加入观察池", key="patrol_to_wl"):
                _append_watchlist(sel_code, source_detail=scope)
                st.success("已加入观察池")

        with st.expander("📌 巡逻复盘", expanded=False):
            history = _load_patrol_history()
            if not history:
                st.info("暂无巡逻记录")
            else:
                labels = [
                    f"{h.get('time', '')} | {h.get('scope', '')} | {h.get('strategy', '')} | {h.get('count', 0)}"
                    for h in history
                ]
                idx = st.selectbox("选择记录", list(range(len(history))), format_func=lambda i: labels[i])
                run = history[idx] if idx is not None else {}
                if run:
                    st.caption(f"时间: {run.get('time', '')} | 范围: {run.get('scope', '')} | 策略: {run.get('strategy', '')}")
                    if run.get("pool_key"):
                        st.caption(f"策略池: {run.get('pool_key')}")
                    st.metric("命中数量", run.get("count", 0))
                    if run.get("settings"):
                        with st.expander("本次设置", expanded=False):
                            st.json(run.get("settings"))
                    cands = run.get("candidates", [])
                    if cands:
                        df_hist = pd.DataFrame(cands)
                        st.dataframe(df_hist, use_container_width=True)
                    else:
                        st.info("暂无命中明细")
