import streamlit as st
import pandas as pd
import datetime
import json
import os
from skills.data_factory import TushareMaster
from core.stock_name import display_name
from core.watchlist import load_entries, append_entries
from core.code_gen import StrategyGenerator

tm = TushareMaster()

DATA_DIR = "data"
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.json")
BROKER_POOL_PATH = os.path.join(DATA_DIR, "broker_pool.json")
STRATEGY_POOL_PATH = os.path.join(DATA_DIR, "strategy_pools.json")


def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


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


def _load_watchlist_entries():
    entries = load_entries()
    out = []
    for e in entries:
        code = e.get("code")
        name = e.get("name") or code
        if code:
            row = dict(e)
            row["code"] = code
            row["name"] = name
            out.append(row)
    return _dedup_entries(out)


def _save_watchlist_entries(entries, source_detail=None):
    clean = _dedup_entries(entries)
    append_entries(clean, source="broker_recommend", source_detail=source_detail, fill_price=True, fill_name=True)


def _save_broker_pool(entries, month_str, meta=None):
    _ensure_data_dir()
    clean = _dedup_entries(entries)
    payload = {
        "month": month_str,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "codes": clean
    }
    if meta:
        payload["meta"] = meta
    with open(BROKER_POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_strategy_pools():
    if not os.path.exists(STRATEGY_POOL_PATH):
        return {}
    try:
        with open(STRATEGY_POOL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _normalize_pool_entries(entries):
    out = []
    seen = set()
    for e in entries or []:
        if isinstance(e, dict):
            code = e.get("code") or e.get("ts_code") or e.get("symbol")
            name = e.get("name") or code
        else:
            code = str(e)
            name = code
        if code and code not in seen:
            seen.add(code)
            out.append({"code": code, "name": name})
    return out


def _safe_name(name):
    if not name:
        return "strategy_pool"
    cleaned = "".join([c if (c.isalnum() or c == "_") else "_" for c in str(name)])
    cleaned = cleaned.strip("_")
    return cleaned or "strategy_pool"


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


def _load_strategy_results(path="data/strategy_results.json"):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_strategy_result_record(key, record, path="data/strategy_results.json"):
    _ensure_data_dir()
    data = _load_strategy_results(path)
    data[key] = record
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _save_timeframe_pools(base_name, entries, meta=None):
    codes = [e.get("code") for e in entries if isinstance(e, dict)]
    n = len(codes)
    if n == 0:
        return []
    short_n = max(10, int(n * 0.3))
    mid_n = max(10, int(n * 0.6))
    short_codes = codes[:short_n]
    mid_codes = codes[:mid_n]
    long_codes = codes

    results = []
    for tag, subset in [("short", short_codes), ("mid", mid_codes), ("long", long_codes)]:
        name = f"{base_name}_{tag}"
        code = _build_pool_strategy_code(subset, f"{base_name}-{tag}")
        gen = StrategyGenerator()
        success, msg, saved_path, is_draft = gen.save_strategy(name, code)
        if success:
            _save_strategy_pool(
                name,
                [{"code": c, "name": c} for c in subset],
                meta={"type": "timeframe", "base": base_name, "tag": tag, **(meta or {})}
            )
        results.append((name, success, msg))
    return results


def _month_options(n=24):
    today = datetime.date.today()
    y, m = today.year, today.month
    opts = []
    for i in range(n):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        label = f"{yy}-{mm:02d}"
        value = f"{yy}{mm:02d}"
        opts.append((label, value))
    return opts


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_broker_recommend(month_str):
    return tm.reference.get_broker_recommend(month=month_str, with_error=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _calc_returns(codes, windows):
    out = []
    try:
        win_list = list(windows)
    except Exception:
        win_list = [30, 60, 120]
    if not win_list:
        return out
    max_days = max(win_list) + 5
    for code in codes:
        try:
            df = tm.market.get_history(code, days=max_days)
            if df is None or df.empty or "close" not in df.columns:
                continue
            df = df.dropna(subset=["close"])
            if df.empty:
                continue
            last = float(df.iloc[-1]["close"])
            row = {"ts_code": code, "last": last}
            for w in win_list:
                if len(df) > w:
                    past = float(df.iloc[-(w + 1)]["close"])
                    row[f"ret_{w}d"] = (last / past - 1) * 100 if past else None
                else:
                    row[f"ret_{w}d"] = None
            out.append(row)
        except Exception:
            continue
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _calc_drawdown(codes, window):
    rows = []
    if not window:
        return rows
    days = int(window) + 5
    for code in codes:
        try:
            df = tm.market.get_history(code, days=days)
            if df is None or df.empty or "close" not in df.columns:
                continue
            s = pd.to_numeric(df["close"], errors="coerce").dropna()
            if len(s) < 2:
                continue
            running_max = s.cummax()
            dd = (s / running_max - 1.0) * 100
            rows.append({"ts_code": code, "mdd": float(dd.min())})
        except Exception:
            continue
    return rows


def _build_consensus_strategy_code():
    return (
        "def check(df):\n"
        "    if df is None or len(df) < 1:\n"
        "        return False, \"数据不足\"\n"
        "    return True, \"券商共识池\"\n"
    )


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


def render():
    st.header("🏆 券商月度金股 (Broker Recommendations)")
    st.caption("查看各大券商的月度推荐金股，捕捉机构共识。（需 Tushare 6000积分）")

    month_opts = _month_options(24)
    labels = [x[0] for x in month_opts]
    values = [x[1] for x in month_opts]

    col1, col2 = st.columns([1, 3])
    with col1:
        month_label = st.selectbox("选择月份", labels, index=0)
        month_str = values[labels.index(month_label)]
    with col2:
        st.write("")
        st.write("")
        query_btn = st.button("🔍 查询金股", type="primary")

    st.divider()

    df = None
    err = ""
    if query_btn:
        with st.spinner(f"正在拉取 {month_str} 券商金股数据..."):
            df, err = _fetch_broker_recommend(month_str)
        st.session_state["broker_df"] = df
        st.session_state["broker_err"] = err
        st.session_state["broker_month"] = month_str
    else:
        if st.session_state.get("broker_month") == month_str:
            df = st.session_state.get("broker_df")
            err = st.session_state.get("broker_err", "")

    if err:
        st.warning(err)

    if df is None or df.empty:
        if query_btn:
            st.warning(f"⚠️ 未查询到 {month_str} 的数据")
        return

    st.success(f"✅ 获取到 {len(df)} 条推荐记录")

    df_use = df.copy()
    with st.expander("筛选条件", expanded=False):
        if "broker" in df_use.columns:
            brokers = sorted(df_use["broker"].dropna().unique().tolist())
            sel_brokers = st.multiselect("券商过滤", brokers, default=brokers)
            if sel_brokers:
                df_use = df_use[df_use["broker"].isin(sel_brokers)]
        else:
            sel_brokers = []

        industry_col = None
        for c in ["industry", "industry_name", "sector"]:
            if c in df_use.columns:
                industry_col = c
                break
        if industry_col:
            industries = sorted(df_use[industry_col].dropna().unique().tolist())
            sel_industry = st.multiselect("行业过滤", industries, default=industries)
            if sel_industry:
                df_use = df_use[df_use[industry_col].isin(sel_industry)]
        else:
            sel_industry = []

        rating_col = None
        for c in ["rating", "rating_name", "recommend"]:
            if c in df_use.columns:
                rating_col = c
                break
        if rating_col:
            ratings = sorted(df_use[rating_col].dropna().unique().tolist())
            sel_rating = st.multiselect("评级过滤", ratings, default=ratings)
            if sel_rating:
                df_use = df_use[df_use[rating_col].isin(sel_rating)]
        else:
            sel_rating = []

        keyword = st.text_input("名称/代码包含", value="")
        if keyword:
            kw = str(keyword).strip()
            if kw:
                mask = pd.Series([False] * len(df_use))
                if "name" in df_use.columns:
                    mask = mask | df_use["name"].astype(str).str.contains(kw, case=False, na=False)
                if "ts_code" in df_use.columns:
                    mask = mask | df_use["ts_code"].astype(str).str.contains(kw, case=False, na=False)
                df_use = df_use[mask]

    if df_use.empty:
        st.warning("筛选后无数据，请调整筛选条件")
        return

    if "ts_code" in df_use.columns and "name" in df_use.columns and "broker" in df_use.columns:
        total_records = len(df_use)
        uniq_stocks = df_use["ts_code"].nunique()
        uniq_brokers = df_use["broker"].nunique()

        m1, m2, m3 = st.columns(3)
        m1.metric("推荐记录", total_records)
        m2.metric("覆盖股票", uniq_stocks)
        m3.metric("参与券商", uniq_brokers)

        broker_counts = df_use["broker"].value_counts()
        broker_rank = broker_counts.head(10).reset_index()
        broker_rank.columns = ["券商", "推荐次数"]

        total_broker_recs = broker_counts.sum()
        top1 = broker_counts.iloc[0] if len(broker_counts) > 0 else 0
        top3 = broker_counts.iloc[:3].sum() if len(broker_counts) >= 3 else broker_counts.sum()
        top5 = broker_counts.iloc[:5].sum() if len(broker_counts) >= 5 else broker_counts.sum()
        hhi = 0
        if total_broker_recs > 0:
            hhi = float(((broker_counts / total_broker_recs) ** 2).sum())

        s1, s2, s3 = st.columns(3)
        s1.metric("券商集中度 TOP1", f"{top1/total_broker_recs*100:.1f}%" if total_broker_recs else "0%")
        s2.metric("券商集中度 TOP3", f"{top3/total_broker_recs*100:.1f}%" if total_broker_recs else "0%")
        s3.metric("券商集中度 TOP5", f"{top5/total_broker_recs*100:.1f}%" if total_broker_recs else "0%")
        st.caption(f"券商集中度 HHI: {hhi:.3f}" if total_broker_recs else "券商集中度 HHI: 0.000")

        st.subheader("券商热度 TOP10")
        st.dataframe(broker_rank, use_container_width=True)

        hot_picks = df_use.groupby(["ts_code", "name"])["broker"].count().reset_index()
        hot_picks["股票"] = hot_picks["ts_code"].apply(lambda x: display_name(x, with_code=True))
        hot_picks = hot_picks[["股票", "ts_code", "name", "broker"]].rename(columns={"broker": "推荐次数"})
        hot_picks = hot_picks.sort_values("推荐次数", ascending=False).reset_index(drop=True)

        max_hits = int(hot_picks["推荐次数"].max()) if not hot_picks.empty else 1
        min_hits = st.slider("最低推荐次数", 1, max_hits, 1)
        hot_picks = hot_picks[hot_picks["推荐次数"] >= min_hits]
        if hot_picks.empty:
            st.warning("无符合推荐次数阈值的标的")
            return

        st.subheader("🔥 机构共识度 TOP10")
        st.dataframe(hot_picks.head(10)[["股票", "推荐次数"]], use_container_width=True)

        st.subheader("📈 券商热度趋势")
        if "month" in df_use.columns:
            trend = df_use.groupby("month")["broker"].count().reset_index()
            trend = trend.sort_values("month")
            st.line_chart(trend.set_index("month")["broker"], height=200)

            st.subheader("分组趋势")
            if "broker" in df_use.columns:
                top_brokers = df_use["broker"].value_counts().head(5).index.tolist()
                broker_trend = df_use[df_use["broker"].isin(top_brokers)].groupby(["month", "broker"]).size().reset_index(name="cnt")
                pivot = broker_trend.pivot(index="month", columns="broker", values="cnt").fillna(0)
                st.line_chart(pivot, height=220)
                st.download_button(
                    "导出券商趋势 CSV",
                    data=pivot.reset_index().to_csv(index=False),
                    file_name="broker_trend.csv",
                    mime="text/csv"
                )

            industry_col = None
            for c in ["industry", "industry_name", "sector"]:
                if c in df_use.columns:
                    industry_col = c
                    break
            if industry_col:
                top_ind = df_use[industry_col].value_counts().head(5).index.tolist()
                ind_trend = df_use[df_use[industry_col].isin(top_ind)].groupby(["month", industry_col]).size().reset_index(name="cnt")
                pivot_i = ind_trend.pivot(index="month", columns=industry_col, values="cnt").fillna(0)
                st.line_chart(pivot_i, height=220)
                st.download_button(
                    "导出行业趋势 CSV",
                    data=pivot_i.reset_index().to_csv(index=False),
                    file_name="industry_trend.csv",
                    mime="text/csv"
                )
        else:
            st.info("数据缺少 month 字段，无法绘制热度趋势")

        st.subheader("联动操作")
        top_entries = [
            {"code": row["ts_code"], "name": row["name"]}
            for _, row in hot_picks.iterrows()
        ]
        label_map = {f"{e['name']} ({e['code']})": e["code"] for e in top_entries}
        option_labels = list(label_map.keys())
        if not option_labels:
            st.warning("无可用标的")
            return
        top_n_max = min(50, len(option_labels))
        top_n_default = min(10, len(option_labels))
        top_n = st.slider("默认选中 TOPN", 1, top_n_max, top_n_default)
        default_labels = option_labels[:top_n]
        selected = st.multiselect("选择加入观察池的标的", option_labels, default=default_labels)
        selected_codes = {label_map.get(lbl) for lbl in selected}
        selected_entries = [e for e in top_entries if e["code"] in selected_codes]

        scanner = st.session_state.get("scanner")
        if scanner:
            strategy_options = scanner.get_strategy_list()
        else:
            strategy_options = ["HotMoney (游资回马枪)", "DNA (风格克隆)", "Oversold (超跌反弹)", "Standard (放量突破)"]
        scan_strategy = st.selectbox("雷达策略", strategy_options, index=0, key="broker_scan_strategy")

        c1, c2, c3, c4 = st.columns(4)
        if c1.button("✅ 加入观察池"):
            if not selected_entries:
                st.warning("请先选择标的")
            else:
                _save_watchlist_entries(selected_entries, source_detail=f"券商金股 {month_str}")
                st.success("已写入观察池 (data/watchlist.json)")
        if c2.button("💾 保存为金股池"):
            if not selected_entries:
                st.warning("请先选择标的")
            else:
                meta = {
                    "brokers": sel_brokers,
                    "industries": sel_industry,
                    "ratings": sel_rating,
                    "keyword": keyword,
                    "min_hits": min_hits
                }
                _save_broker_pool(selected_entries, month_str, meta=meta)
                st.success("已保存金股池 (data/broker_pool.json)")
        if c3.button("🧠 生成共识策略"):
            gen = StrategyGenerator()
            code = _build_consensus_strategy_code()
            success, msg, saved_path, is_draft = gen.save_strategy("broker_consensus", code)
            if success:
                st.success(f"共识策略已生成：{msg}")
            elif is_draft:
                st.warning(msg)
            else:
                st.error(msg)
        if c4.button("🚀 一键雷达扫描"):
            if not selected_entries:
                st.warning("请先选择标的")
            else:
                meta = {
                    "brokers": sel_brokers,
                    "industries": sel_industry,
                    "ratings": sel_rating,
                    "keyword": keyword,
                    "min_hits": min_hits
                }
                _save_broker_pool(selected_entries, month_str, meta=meta)
                st.session_state["radar_scope"] = "🏆 券商金股池"
                st.session_state["radar_strategy"] = scan_strategy
                st.session_state["radar_auto_run"] = True
                st.session_state["radar_save_result"] = True
                st.session_state["current_page"] = "🔭 猎手雷达"
                st.success("已切换到猎手雷达并自动扫描")

        st.caption("提示：共识策略建议与“观察池/金股池”一起使用，避免全市场泛滥命中。")

        st.subheader("📊 共识强度分布")
        q50 = hot_picks["推荐次数"].quantile(0.5)
        q75 = hot_picks["推荐次数"].quantile(0.75)
        q90 = hot_picks["推荐次数"].quantile(0.9)
        c1, c2, c3 = st.columns(3)
        c1.metric("中位推荐次数", f"{q50:.0f}")
        c2.metric("75%分位", f"{q75:.0f}")
        c3.metric("90%分位", f"{q90:.0f}")

        st.subheader("📤 数据导出")
        csv_data = df_use.to_csv(index=False)
        st.download_button(
            "导出 CSV",
            data=csv_data,
            file_name=f"broker_recommend_{month_str}.csv",
            mime="text/csv"
        )
        code_list = hot_picks["ts_code"].tolist()
        st.text_area("代码列表", value="\n".join(code_list), height=120)
    else:
        st.info("字段不足，无法生成共识分析，请检查数据接口")

    st.subheader("⏱️ 金股池收益概览")
    backtest_cols = st.columns([1, 2, 1])
    with backtest_cols[0]:
        top_n_bt = st.slider("取前 N 只", 10, 100, 30, step=5)
    with backtest_cols[1]:
        win_opts = [30, 60, 120]
        win_sel = st.multiselect("回测窗口(天)", win_opts, default=win_opts)
    with backtest_cols[2]:
        run_bt = st.button("计算收益")
    if run_bt:
        if "ts_code" not in df_use.columns:
            st.warning("数据缺少 ts_code")
        elif not win_sel:
            st.warning("请选择回测窗口")
        else:
            codes = df_use["ts_code"].dropna().unique().tolist()[:top_n_bt]
            rows = _calc_returns(tuple(codes), tuple(sorted(win_sel)))
            if not rows:
                st.warning("回测无结果，可能数据不足或接口限制")
            else:
                df_ret = pd.DataFrame(rows)
                name_map = {}
                if "name" in df_use.columns:
                    for _, r in df_use.drop_duplicates("ts_code").iterrows():
                        name_map[r["ts_code"]] = r["name"]
                df_ret["name"] = df_ret["ts_code"].map(name_map).fillna(df_ret["ts_code"])
                cols = ["ts_code", "name", "last"] + [f"ret_{w}d" for w in sorted(win_sel)]
                st.dataframe(df_ret[cols], use_container_width=True)
                avg_row = {f"ret_{w}d": df_ret[f"ret_{w}d"].mean() for w in sorted(win_sel)}
                st.caption("平均收益(%)：" + " | ".join([f"{k}:{v:.2f}" for k, v in avg_row.items()]))

                st.subheader("胜率与分布")
                win_cols = st.columns(len(win_sel))
                for idx, w in enumerate(sorted(win_sel)):
                    col = win_cols[idx] if idx < len(win_cols) else None
                    win_rate = (df_ret[f"ret_{w}d"] > 0).mean() * 100
                    if col:
                        col.metric(f"{w}日胜率", f"{win_rate:.1f}%")
                    else:
                        st.metric(f"{w}日胜率", f"{win_rate:.1f}%")

                for w in sorted(win_sel):
                    series = df_ret[f"ret_{w}d"].dropna()
                    if series.empty:
                        continue
                    bins = [-100, -30, -10, -5, 0, 5, 10, 20, 50, 100]
                    labels = [f"{bins[i]}~{bins[i+1]}" for i in range(len(bins) - 1)]
                    dist = pd.cut(series, bins=bins, labels=labels, include_lowest=True).value_counts().sort_index()
                    st.bar_chart(dist, height=160)

                st.subheader("回撤概览")
                dd_window = max(sorted(win_sel)) if win_sel else 60
                dd_rows = _calc_drawdown(tuple(codes), dd_window)
                if dd_rows:
                    df_dd = pd.DataFrame(dd_rows)
                    avg_dd = df_dd["mdd"].mean()
                    worst_dd = df_dd["mdd"].min()
                    d1, d2 = st.columns(2)
                    d1.metric(f"{dd_window}日平均最大回撤", f"{avg_dd:.2f}%")
                    d2.metric(f"{dd_window}日最差最大回撤", f"{worst_dd:.2f}%")
                    df_dd = df_dd.sort_values("mdd")
                    st.dataframe(df_dd.head(20), use_container_width=True)
                else:
                    st.info("回撤计算无结果")

    st.subheader("📅 月度对比")
    compare_cols = st.columns([1, 1, 1])
    with compare_cols[0]:
        month_a = st.selectbox("对比月A", labels, index=1 if len(labels) > 1 else 0, key="compare_a")
    with compare_cols[1]:
        month_b = st.selectbox("对比月B", labels, index=0, key="compare_b")
    with compare_cols[2]:
        do_compare = st.button("生成对比")

    if do_compare:
        month_a_str = values[labels.index(month_a)]
        month_b_str = values[labels.index(month_b)]
        df_a, err_a = _fetch_broker_recommend(month_a_str)
        df_b, err_b = _fetch_broker_recommend(month_b_str)
        if err_a:
            st.warning(f"A月异常: {err_a}")
        if err_b:
            st.warning(f"B月异常: {err_b}")
        if df_a is None or df_a.empty or df_b is None or df_b.empty:
            st.warning("对比数据不足")
        else:
            set_a = set(df_a["ts_code"].dropna().tolist()) if "ts_code" in df_a.columns else set()
            set_b = set(df_b["ts_code"].dropna().tolist()) if "ts_code" in df_b.columns else set()
            added = sorted(list(set_b - set_a))
            removed = sorted(list(set_a - set_b))
            kept = sorted(list(set_a & set_b))

            m1, m2, m3 = st.columns(3)
            m1.metric("新增", len(added))
            m2.metric("剔除", len(removed))
            m3.metric("连续推荐", len(kept))

            st.subheader("自动写入策略池")
            gen = StrategyGenerator()
            b1, b2, b3 = st.columns(3)
            if b1.button("生成新增策略"):
                code = _build_pool_strategy_code(added, f"金股新增 {month_b_str}")
                name = f"broker_added_{month_a_str}_{month_b_str}"
                success, msg, saved_path, is_draft = gen.save_strategy(name, code)
                if success:
                    _save_strategy_pool(
                        name,
                        [{"code": c, "name": name_map_b.get(c, c)} for c in added],
                        meta={"type": "added", "from": month_a_str, "to": month_b_str}
                    )
                    st.success(f"新增策略已生成：{msg}")
                elif is_draft:
                    st.warning(msg)
                else:
                    st.error(msg)
            if b2.button("生成剔除策略"):
                code = _build_pool_strategy_code(removed, f"金股剔除 {month_a_str}")
                name = f"broker_removed_{month_a_str}_{month_b_str}"
                success, msg, saved_path, is_draft = gen.save_strategy(name, code)
                if success:
                    _save_strategy_pool(
                        name,
                        [{"code": c, "name": name_map_a.get(c, c)} for c in removed],
                        meta={"type": "removed", "from": month_a_str, "to": month_b_str}
                    )
                    st.success(f"剔除策略已生成：{msg}")
                elif is_draft:
                    st.warning(msg)
                else:
                    st.error(msg)
            if b3.button("生成连续策略"):
                code = _build_pool_strategy_code(kept, f"金股连续 {month_a_str}->{month_b_str}")
                name = f"broker_kept_{month_a_str}_{month_b_str}"
                success, msg, saved_path, is_draft = gen.save_strategy(name, code)
                if success:
                    _save_strategy_pool(
                        name,
                        [{"code": c, "name": name_map_b.get(c, name_map_a.get(c, c))} for c in kept],
                        meta={"type": "kept", "from": month_a_str, "to": month_b_str}
                    )
                    st.success(f"连续策略已生成：{msg}")
                elif is_draft:
                    st.warning(msg)
                else:
                    st.error(msg)

            name_map_a = {}
            name_map_b = {}
            if "ts_code" in df_a.columns and "name" in df_a.columns:
                for _, r in df_a.drop_duplicates("ts_code").iterrows():
                    name_map_a[r["ts_code"]] = r["name"]
            if "ts_code" in df_b.columns and "name" in df_b.columns:
                for _, r in df_b.drop_duplicates("ts_code").iterrows():
                    name_map_b[r["ts_code"]] = r["name"]

            def _pack_rows(codes, name_map):
                rows = []
                for c in codes:
                    rows.append({"ts_code": c, "name": name_map.get(c, c)})
                return rows

            st.subheader("新增列表")
            st.dataframe(pd.DataFrame(_pack_rows(added, name_map_b)).head(50), use_container_width=True)
            st.subheader("剔除列表")
            st.dataframe(pd.DataFrame(_pack_rows(removed, name_map_a)).head(50), use_container_width=True)

            if "broker" in df_a.columns and "broker" in df_b.columns and "name" in df_a.columns and "name" in df_b.columns:
                cnt_a = df_a.groupby("ts_code")["broker"].count()
                cnt_b = df_b.groupby("ts_code")["broker"].count()
                rows = []
                for code in kept:
                    rows.append({
                        "ts_code": code,
                        "name": name_map_b.get(code, name_map_a.get(code, code)),
                        "A月推荐": int(cnt_a.get(code, 0)),
                        "B月推荐": int(cnt_b.get(code, 0)),
                        "变化": int(cnt_b.get(code, 0)) - int(cnt_a.get(code, 0))
                    })
                df_keep = pd.DataFrame(rows).sort_values("变化", ascending=False)
                st.subheader("连续推荐变化 TOP20")
                st.dataframe(df_keep.head(20), use_container_width=True)

    st.subheader("🎯 策略绑定池管理")
    pools = _load_strategy_pools()
    if not pools:
        st.info("暂无策略绑定池，请先在【月度对比】生成策略")
    else:
        pool_names = sorted(list(pools.keys()))
        sel_pool = st.selectbox("选择策略池", pool_names, key="pool_select")
        pool_item = pools.get(sel_pool, {})
        pool_entries = _normalize_pool_entries(pool_item.get("codes", []))
        pool_codes = [e["code"] for e in pool_entries]
        pool_meta = pool_item.get("meta", {})

        st.caption(f"池规模: {len(pool_entries)} | 更新时间: {pool_item.get('updated_at', '')}")
        if pool_meta:
            st.caption(f"元信息: {pool_meta}")

        c1, c2 = st.columns(2)
        if c1.button("同步到观察池"):
            if not pool_entries:
                st.warning("绑定池为空")
            else:
                _save_watchlist_entries(pool_entries, source_detail=f"券商金股池 {month_str}")
                st.success("已同步到观察池 (data/watchlist.json)")
        if c2.button("导出代码列表"):
            st.text_area("绑定池代码", value="\n".join(pool_codes), height=120)

        st.subheader("策略池对比")
        p1, p2 = st.columns(2)
        with p1:
            pool_a = st.selectbox("策略池A", pool_names, key="pool_a")
        with p2:
            pool_b = st.selectbox("策略池B", pool_names, key="pool_b")
        if pool_a and pool_b:
            a_entries = _normalize_pool_entries(pools.get(pool_a, {}).get("codes", []))
            b_entries = _normalize_pool_entries(pools.get(pool_b, {}).get("codes", []))
            set_a = {e["code"] for e in a_entries}
            set_b = {e["code"] for e in b_entries}
            only_a = sorted(list(set_a - set_b))
            only_b = sorted(list(set_b - set_a))
            both = sorted(list(set_a & set_b))
            m1, m2, m3 = st.columns(3)
            m1.metric("仅A", len(only_a))
            m2.metric("仅B", len(only_b))
            m3.metric("交集", len(both))

            st.subheader("对比结果生成策略")
            gen = StrategyGenerator()
            s1, s2, s3 = st.columns(3)
            safe_a = _safe_name(pool_a)
            safe_b = _safe_name(pool_b)
            if s1.button("生成交集策略"):
                name = f"pool_inter_{safe_a}_{safe_b}"
                code = _build_pool_strategy_code(both, f"策略池交集 {pool_a}&{pool_b}")
                success, msg, saved_path, is_draft = gen.save_strategy(name, code)
                if success:
                    _save_strategy_pool(
                        name,
                        [{"code": c, "name": c} for c in both],
                        meta={"type": "intersection", "a": pool_a, "b": pool_b}
                    )
                    st.success(f"交集策略已生成：{msg}")
                elif is_draft:
                    st.warning(msg)
                else:
                    st.error(msg)
            if s2.button("生成仅A策略"):
                name = f"pool_only_{safe_a}"
                code = _build_pool_strategy_code(only_a, f"策略池仅 {pool_a}")
                success, msg, saved_path, is_draft = gen.save_strategy(name, code)
                if success:
                    _save_strategy_pool(
                        name,
                        [{"code": c, "name": c} for c in only_a],
                        meta={"type": "only_a", "a": pool_a, "b": pool_b}
                    )
                    st.success(f"仅A策略已生成：{msg}")
                elif is_draft:
                    st.warning(msg)
                else:
                    st.error(msg)
            if s3.button("生成仅B策略"):
                name = f"pool_only_{safe_b}"
                code = _build_pool_strategy_code(only_b, f"策略池仅 {pool_b}")
                success, msg, saved_path, is_draft = gen.save_strategy(name, code)
                if success:
                    _save_strategy_pool(
                        name,
                        [{"code": c, "name": c} for c in only_b],
                        meta={"type": "only_b", "a": pool_a, "b": pool_b}
                    )
                    st.success(f"仅B策略已生成：{msg}")
                elif is_draft:
                    st.warning(msg)
                else:
                    st.error(msg)

            st.subheader("自动分层策略池")
            lf1, lf2, lf3 = st.columns(3)
            if lf1.button("交集分层(短/中/长)"):
                results = _save_timeframe_pools(
                    f"pool_inter_{safe_a}_{safe_b}",
                    [{"code": c, "name": c} for c in both],
                    meta={"type": "intersection", "a": pool_a, "b": pool_b}
                )
                st.success("交集分层完成")
            if lf2.button("仅A分层(短/中/长)"):
                results = _save_timeframe_pools(
                    f"pool_only_{safe_a}",
                    [{"code": c, "name": c} for c in only_a],
                    meta={"type": "only_a", "a": pool_a, "b": pool_b}
                )
                st.success("仅A分层完成")
            if lf3.button("仅B分层(短/中/长)"):
                results = _save_timeframe_pools(
                    f"pool_only_{safe_b}",
                    [{"code": c, "name": c} for c in only_b],
                    meta={"type": "only_b", "a": pool_a, "b": pool_b}
                )
                st.success("仅B分层完成")

            st.subheader("对比结果同步观察池")
            t1, t2, t3 = st.columns(3)
            if t1.button("同步交集到观察池"):
                _save_watchlist_entries([{"code": c, "name": c} for c in both], source_detail="策略池交集")
                st.success("交集已同步到观察池")
            if t2.button("同步仅A到观察池"):
                _save_watchlist_entries([{"code": c, "name": c} for c in only_a], source_detail="策略池仅A")
                st.success("仅A已同步到观察池")
            if t3.button("同步仅B到观察池"):
                _save_watchlist_entries([{"code": c, "name": c} for c in only_b], source_detail="策略池仅B")
                st.success("仅B已同步到观察池")

            st.subheader("交集列表")
            st.dataframe(pd.DataFrame([{"ts_code": c} for c in both]).head(50), use_container_width=True)
            st.subheader("仅A列表")
            st.dataframe(pd.DataFrame([{"ts_code": c} for c in only_a]).head(50), use_container_width=True)
            st.subheader("仅B列表")
            st.dataframe(pd.DataFrame([{"ts_code": c} for c in only_b]).head(50), use_container_width=True)

            st.subheader("对比结果一键回测")
            bt_cols = st.columns([1, 2, 1])
            with bt_cols[0]:
                top_n_cmp = st.slider("取前 N 只(对比)", 10, 200, 50, step=10)
            with bt_cols[1]:
                win_opts_cmp = [30, 60, 120]
                win_sel_cmp = st.multiselect("回测窗口(天)", win_opts_cmp, default=win_opts_cmp, key="cmp_bt_windows")
            with bt_cols[2]:
                run_cmp = st.button("运行对比回测")

            def _bt_summary(codes, label):
                rows = _calc_returns(tuple(codes[:top_n_cmp]), tuple(sorted(win_sel_cmp)))
                if not rows:
                    st.warning(f"{label}: 无结果")
                    return
                df_ret = pd.DataFrame(rows)
                avg_row = {f"ret_{w}d": df_ret[f"ret_{w}d"].mean() for w in sorted(win_sel_cmp)}
                st.caption(f"{label} 平均收益(%)：" + " | ".join([f"{k}:{v:.2f}" for k, v in avg_row.items()]))
                win_rate = {f"ret_{w}d": (df_ret[f'ret_{w}d'] > 0).mean() * 100 for w in sorted(win_sel_cmp)}
                st.caption(f"{label} 胜率(%)：" + " | ".join([f"{k}:{v:.1f}" for k, v in win_rate.items()]))

            if run_cmp:
                if not win_sel_cmp:
                    st.warning("请选择回测窗口")
                else:
                    _bt_summary(both, "交集")
                    _bt_summary(only_a, "仅A")
                    _bt_summary(only_b, "仅B")

                    st.subheader("对比回测图")
                    stats_data = {
                        "交集": _calc_stats(both),
                        "仅A": _calc_stats(only_a),
                        "仅B": _calc_stats(only_b)
                    }
                    if win_sel_cmp:
                        for w in sorted(win_sel_cmp):
                            col = f"ret_{w}d"
                            series = pd.Series(
                                {k: v.get(col, {}).get("avg", 0) for k, v in stats_data.items()},
                                name=f"{w}日平均收益"
                            )
                            st.bar_chart(series, height=180)

                    record = {
                        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "type": "pool_compare",
                        "pool_a": pool_a,
                        "pool_b": pool_b,
                        "windows": win_sel_cmp,
                        "summary": {
                            "both": {"size": len(both)},
                            "only_a": {"size": len(only_a)},
                            "only_b": {"size": len(only_b)}
                        }
                    }
                    def _calc_stats(codes):
                        rows = _calc_returns(tuple(codes[:top_n_cmp]), tuple(sorted(win_sel_cmp)))
                        if not rows:
                            return {}
                        df_ret = pd.DataFrame(rows)
                        stats = {}
                        for w in sorted(win_sel_cmp):
                            col = f"ret_{w}d"
                            if col in df_ret.columns:
                                stats[col] = {
                                    "avg": float(df_ret[col].mean()),
                                    "win_rate": float((df_ret[col] > 0).mean() * 100)
                                }
                        return stats
                    record["stats"] = {
                        "both": _calc_stats(both),
                        "only_a": _calc_stats(only_a),
                        "only_b": _calc_stats(only_b)
                    }
                    _save_strategy_result_record(f"pool_compare_{safe_a}_{safe_b}", record)

            st.subheader("绑定池结果可视化")
            series_labels = ["交集", "仅A", "仅B"]
            series_counts = [len(both), len(only_a), len(only_b)]
            st.bar_chart(pd.Series(series_counts, index=series_labels), height=180)

        st.subheader("策略池回测概览")
        bt_cols = st.columns([1, 2, 1])
        with bt_cols[0]:
            top_n_pool = st.slider("取前 N 只(池)", 10, 200, min(50, len(pool_entries) or 10), step=10)
        with bt_cols[1]:
            win_opts_pool = [30, 60, 120]
            win_sel_pool = st.multiselect("回测窗口(天)", win_opts_pool, default=win_opts_pool, key="pool_bt_windows")
        with bt_cols[2]:
            run_bt_pool = st.button("计算策略池收益")

        if run_bt_pool:
            if not pool_codes:
                st.warning("绑定池为空")
            elif not win_sel_pool:
                st.warning("请选择回测窗口")
            else:
                codes = pool_codes[:top_n_pool]
                rows = _calc_returns(tuple(codes), tuple(sorted(win_sel_pool)))
                if not rows:
                    st.warning("回测无结果，可能数据不足或接口限制")
                else:
                    df_ret = pd.DataFrame(rows)
                    name_map = {e["code"]: e.get("name", e["code"]) for e in pool_entries}
                    df_ret["name"] = df_ret["ts_code"].map(name_map).fillna(df_ret["ts_code"])
                    cols = ["ts_code", "name", "last"] + [f"ret_{w}d" for w in sorted(win_sel_pool)]
                    st.dataframe(df_ret[cols], use_container_width=True)
                    avg_row = {f"ret_{w}d": df_ret[f"ret_{w}d"].mean() for w in sorted(win_sel_pool)}
                    st.caption("平均收益(%)：" + " | ".join([f"{k}:{v:.2f}" for k, v in avg_row.items()]))

                    dd_window = max(sorted(win_sel_pool))
                    dd_rows = _calc_drawdown(tuple(codes), dd_window)
                    if dd_rows:
                        df_dd = pd.DataFrame(dd_rows).sort_values("mdd")
                        st.caption(f"{dd_window}日回撤最差 TOP20")
                        st.dataframe(df_dd.head(20), use_container_width=True)
                    else:
                        st.info("回撤计算无结果")

    with st.expander("📄 查看完整推荐名单", expanded=True):
        df_view = df_use.copy()
        if "ts_code" in df_view.columns:
            df_view["股票"] = df_view["ts_code"].apply(lambda x: display_name(x, with_code=True))
            df_view = df_view.drop(columns=["ts_code"])
        st.dataframe(df_view, use_container_width=True)
