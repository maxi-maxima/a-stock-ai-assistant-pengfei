import streamlit as st
import pandas as pd
import datetime
import json
import os
from skills.data_factory import TushareMaster
from core.stock_name import display_name
from core.financial_analysis import extract_metrics, score_financial

tm = TushareMaster()

DATA_DIR = "data"
FIN_HISTORY_PATH = os.path.join(DATA_DIR, "financial_history.json")
STRATEGY_RESULTS_PATH = os.path.join(DATA_DIR, "strategy_results.json")


def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def _normalize_code(code):
    if not code:
        return ""
    c = str(code).strip().upper()
    if "." in c:
        return c
    if c.isdigit() and len(c) == 6:
        if c.startswith("6"):
            return f"{c}.SH"
        if c.startswith(("0", "3")):
            return f"{c}.SZ"
    return c


def _format_money(val):
    if pd.isna(val):
        return "0.00"
    try:
        v = float(val)
    except Exception:
        return "0.00"
    if abs(v) >= 100000000:
        return f"{v/100000000:.2f}亿"
    if abs(v) >= 10000:
        return f"{v/10000:.2f}万"
    return f"{v:.2f}"


@st.cache_data(ttl=3600, show_spinner=False)
def _get_industry_peers(industry, limit=30):
    if not industry:
        return []
    peers = []
    try:
        data = tm.base.get_stock_list()
        for item in data:
            if item.get("industry") == industry and not str(item.get("name", "")).startswith("ST"):
                code = item.get("ts_code") or item.get("code") or item.get("symbol")
                if code:
                    peers.append(code)
            if len(peers) >= limit:
                break
    except Exception:
        pass
    return peers


@st.cache_data(ttl=3600, show_spinner=False)
def _calc_industry_baseline(industry, limit, period, mv_range=None):
    peers = _get_industry_peers(industry, limit * 5)
    if not peers:
        return {}
    rows = []
    count = 0
    for code in peers:
        df_inc, _ = _fetch_income(code, period)
        df_bs, _ = _fetch_balance(code, period)
        df_cf, _ = _fetch_cashflow(code, period)
        metrics = extract_metrics(code, df_inc, df_bs, df_cf)
        if mv_range:
            # 这里用 total_mv/industry 无法直接拿到，先按收入规模过滤
            rev = metrics.get("revenue")
            if rev is None:
                continue
            low, high = mv_range
            if rev < low or rev > high:
                continue
        rows.append(metrics)
        count += 1
        if count >= limit:
            break
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    baseline = {}
    for col in ["revenue", "net_income", "gross_margin", "net_margin", "roe", "roa", "debt_ratio", "ocf", "ocf_to_net"]:
        if col in df.columns:
            baseline[col] = float(df[col].median())
    return baseline

def _save_financial_record(record):
    _ensure_data_dir()
    history = []
    if os.path.exists(FIN_HISTORY_PATH):
        try:
            with open(FIN_HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    history = data
        except Exception:
            history = []
    history.insert(0, record)
    history = history[:50]
    try:
        with open(FIN_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_strategy_results():
    if not os.path.exists(STRATEGY_RESULTS_PATH):
        return {}
    try:
        with open(STRATEGY_RESULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_income(code, period):
    return tm.financial.get_income_statement(code, period=period, with_error=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_forecast(code):
    return tm.financial.get_forecast(code, with_error=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_balance(code, period):
    return tm.financial.get_balance_sheet(code, period=period, with_error=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_cashflow(code, period):
    return tm.financial.get_cashflow(code, period=period, with_error=True)


def _build_alerts(metrics):
    alerts = []
    if metrics.get("net_income", 0) < 0:
        alerts.append("净利润为负")
    if metrics.get("ocf", 0) < 0:
        alerts.append("经营现金流为负")
    if metrics.get("debt_ratio", 0) > 70:
        alerts.append("资产负债率偏高")
    if metrics.get("yoy_revenue") is not None and metrics.get("yoy_revenue") < 0:
        alerts.append("营收同比下降")
    if metrics.get("yoy_net") is not None and metrics.get("yoy_net") < 0:
        alerts.append("净利同比下降")
    return alerts


def render():
    st.header("📊 财务透视 (Financial X-Ray)")
    st.caption("深度透视上市公司三大报表、核心指标与趋势。")

    default_code = st.session_state.get("fin_code", "000001.SZ")
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        code_input = st.text_input("输入代码（支持多个，用逗号分隔）", default_code, key="fin_code")
    with col2:
        period = st.text_input("报告期(可选)", "", key="fin_period")
    with col3:
        btn = st.button("🔍 深度审计", type="primary", key="fin_btn")
    with col4:
        enable_peer = st.checkbox("行业基准", value=False, key="fin_peer")

    peer_limit = 30
    if enable_peer:
        peer_limit = st.slider("行业样本数", 10, 80, 30, step=5)
        mv_bucket = st.selectbox("行业基准分层", ["不限", "小盘(营收<=10亿)", "中盘(10-100亿)", "大盘(>100亿)"], index=0)
        if mv_bucket == "小盘(营收<=10亿)":
            mv_range = (0, 1e9)
        elif mv_bucket == "中盘(10-100亿)":
            mv_range = (1e9, 1e10)
        elif mv_bucket == "大盘(>100亿)":
            mv_range = (1e10, 1e20)
        else:
            mv_range = None
    else:
        mv_range = None

    with st.expander("评分权重", expanded=False):
        w_profit = st.slider("盈利权重", 0.5, 2.0, 1.0, 0.1)
        w_growth = st.slider("增长权重", 0.5, 2.0, 1.0, 0.1)
        w_quality = st.slider("质量权重", 0.5, 2.0, 1.0, 0.1)
        w_cash = st.slider("现金流权重", 0.5, 2.0, 1.0, 0.1)
        w_stab = st.slider("稳定性权重", 0.5, 2.0, 1.0, 0.1)
    weights = {
        "profit": w_profit,
        "growth": w_growth,
        "quality": w_quality,
        "cash": w_cash,
        "stability": w_stab
    }

    st.divider()

    if not btn:
        return

    raw_codes = [c.strip() for c in code_input.replace("\n", ",").split(",") if c.strip()]
    codes = []
    for c in raw_codes:
        nc = _normalize_code(c)
        if nc and nc not in codes:
            codes.append(nc)

    if not codes:
        st.error("请输入有效股票代码")
        return

    results = []
    for code in codes:
        with st.spinner(f"拉取 {code} 财务数据..."):
            info = tm.get_stock_basic_info(code)
            name = info.get("name") or display_name(code)
            industry = info.get("industry") or ""

            df_inc, err_inc = _fetch_income(code, period or None)
            df_bs, err_bs = _fetch_balance(code, period or None)
            df_cf, err_cf = _fetch_cashflow(code, period or None)
            df_for, err_for = _fetch_forecast(code)

            errors = [e for e in [err_inc, err_bs, err_cf, err_for] if e]
            if errors:
                st.warning(" | ".join(sorted(set(errors))))

            metrics = extract_metrics(code, df_inc, df_bs, df_cf)
            metrics["name"] = name
            metrics["industry"] = industry
            score, grade, detail = score_financial(metrics, weights)
            metrics["score"] = score
            metrics["grade"] = grade
            metrics["score_detail"] = detail
            alerts = _build_alerts(metrics)
            metrics["alerts"] = "；".join(alerts) if alerts else ""

            baseline = {}
            if enable_peer and industry:
                baseline = _calc_industry_baseline(industry, peer_limit, period or None, mv_range=mv_range)
            metrics["baseline"] = baseline

            results.append({
                "code": code,
                "name": name,
                "industry": industry,
                "metrics": metrics,
                "income": df_inc,
                "balance": df_bs,
                "cashflow": df_cf,
                "forecast": df_for
            })

            record = {
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "code": code,
                "name": name,
                "industry": industry,
                "metrics": metrics,
                "alerts": alerts
            }
            _save_financial_record(record)

    if len(results) > 1:
        st.subheader("多公司对比")
        rows = []
        for r in results:
            m = r["metrics"]
            rows.append({
                "代码": r["code"],
                "名称": r["name"],
                "行业": r["industry"],
                "营收": _format_money(m.get("revenue")),
                "净利": _format_money(m.get("net_income")),
                "评分": f"{m.get('score', 0):.0f}",
                "毛利率%": f"{m.get('gross_margin', 0):.2f}" if m.get("gross_margin") is not None else "",
                "净利率%": f"{m.get('net_margin', 0):.2f}" if m.get("net_margin") is not None else "",
                "ROE%": f"{m.get('roe', 0):.2f}" if m.get("roe") is not None else "",
                "ROA%": f"{m.get('roa', 0):.2f}" if m.get("roa") is not None else "",
                "负债率%": f"{m.get('debt_ratio', 0):.2f}" if m.get("debt_ratio") is not None else "",
                "经营现金流": _format_money(m.get("ocf")),
                "预警": m.get("alerts", "")
            })
        df_cmp = pd.DataFrame(rows)
        st.dataframe(df_cmp, use_container_width=True)

        try:
            base = pd.DataFrame([r["metrics"] for r in results])
            baseline = {
                "代码": "样本中位数",
                "名称": "",
                "行业": "",
                "营收": _format_money(base["revenue"].median()),
                "净利": _format_money(base["net_income"].median()),
                "毛利率%": f"{base['gross_margin'].median():.2f}" if "gross_margin" in base else "",
                "净利率%": f"{base['net_margin'].median():.2f}" if "net_margin" in base else "",
                "ROE%": f"{base['roe'].median():.2f}" if "roe" in base else "",
                "ROA%": f"{base['roa'].median():.2f}" if "roa" in base else "",
                "负债率%": f"{base['debt_ratio'].median():.2f}" if "debt_ratio" in base else "",
                "经营现金流": _format_money(base["ocf"].median()),
                "预警": ""
            }
            st.write("样本基准（中位数）")
            st.dataframe(pd.DataFrame([baseline]), use_container_width=True)
        except Exception:
            pass

    for r in results:
        st.markdown("---")
        st.subheader(f"{r['name']} ({r['code']}) - {r['industry']}")
        m = r["metrics"]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("营收", _format_money(m.get("revenue")))
        c1.caption(f"同比: {m.get('yoy_revenue', 0):.2f}%" if m.get("yoy_revenue") is not None else "同比: -")
        c2.metric("净利", _format_money(m.get("net_income")))
        c2.caption(f"同比: {m.get('yoy_net', 0):.2f}%" if m.get("yoy_net") is not None else "同比: -")
        c3.metric("毛利率", f"{m.get('gross_margin', 0):.2f}%" if m.get("gross_margin") is not None else "-")
        c3.caption(f"净利率: {m.get('net_margin', 0):.2f}%" if m.get("net_margin") is not None else "净利率: -")
        c4.metric("负债率", f"{m.get('debt_ratio', 0):.2f}%" if m.get("debt_ratio") is not None else "-")
        c4.caption(f"ROE: {m.get('roe', 0):.2f}% | ROA: {m.get('roa', 0):.2f}%" if m.get("roe") is not None else "ROE/ROA: -")
        c5.metric("财务评分", f"{m.get('score', 0):.0f} / 100")
        c5.caption(f"等级: {m.get('grade', '-')}")

        if m.get("score_detail"):
            with st.expander("评分拆解"):
                st.json(m.get("score_detail"))

        baseline = m.get("baseline") or {}
        if baseline:
            st.subheader("行业基准对比（中位数）")
            rows = [
                {"指标": "营收", "公司": _format_money(m.get("revenue")), "行业": _format_money(baseline.get("revenue"))},
                {"指标": "净利", "公司": _format_money(m.get("net_income")), "行业": _format_money(baseline.get("net_income"))},
                {"指标": "毛利率%", "公司": f"{m.get('gross_margin', 0):.2f}" if m.get("gross_margin") is not None else "-", "行业": f"{baseline.get('gross_margin', 0):.2f}"},
                {"指标": "净利率%", "公司": f"{m.get('net_margin', 0):.2f}" if m.get("net_margin") is not None else "-", "行业": f"{baseline.get('net_margin', 0):.2f}"},
                {"指标": "ROE%", "公司": f"{m.get('roe', 0):.2f}" if m.get("roe") is not None else "-", "行业": f"{baseline.get('roe', 0):.2f}"},
                {"指标": "ROA%", "公司": f"{m.get('roa', 0):.2f}" if m.get("roa") is not None else "-", "行业": f"{baseline.get('roa', 0):.2f}"},
                {"指标": "负债率%", "公司": f"{m.get('debt_ratio', 0):.2f}" if m.get("debt_ratio") is not None else "-", "行业": f"{baseline.get('debt_ratio', 0):.2f}"},
                {"指标": "经营现金流", "公司": _format_money(m.get("ocf")), "行业": _format_money(baseline.get("ocf"))},
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

        if m.get("alerts"):
            st.warning(f"预警: {m.get('alerts')}")

        df_inc = r["income"]
        df_bs = r["balance"]
        df_cf = r["cashflow"]

        if df_inc is not None and not df_inc.empty:
            df_trend = df_inc.copy()
            df_trend = df_trend.sort_values("end_date")
            st.subheader("收入与利润趋势")
            if "total_revenue" in df_trend.columns:
                st.line_chart(df_trend.set_index("end_date")["total_revenue"], height=200)
            if "n_income" in df_trend.columns:
                st.line_chart(df_trend.set_index("end_date")["n_income"], height=200)

        if df_cf is not None and not df_cf.empty:
            df_trend_cf = df_cf.sort_values("end_date")
            st.subheader("经营现金流趋势")
            if "n_cashflow_act" in df_trend_cf.columns:
                st.line_chart(df_trend_cf.set_index("end_date")["n_cashflow_act"], height=200)

        if df_inc is not None and not df_inc.empty:
            st.subheader("利润表")
            st.dataframe(df_inc, use_container_width=True)
            st.download_button(
                "导出利润表 CSV",
                data=df_inc.to_csv(index=False),
                file_name=f"income_{r['code']}.csv",
                mime="text/csv"
            )
        if df_bs is not None and not df_bs.empty:
            st.subheader("资产负债表")
            st.dataframe(df_bs, use_container_width=True)
            st.download_button(
                "导出资产负债表 CSV",
                data=df_bs.to_csv(index=False),
                file_name=f"balance_{r['code']}.csv",
                mime="text/csv"
            )
        if df_cf is not None and not df_cf.empty:
            st.subheader("现金流量表")
            st.dataframe(df_cf, use_container_width=True)
            st.download_button(
                "导出现金流 CSV",
                data=df_cf.to_csv(index=False),
                file_name=f"cashflow_{r['code']}.csv",
                mime="text/csv"
            )

        if r["forecast"] is not None and not r["forecast"].empty:
            latest_for = r["forecast"].iloc[0]
            ftype = latest_for.get("type", "")
            st.subheader(f"最新业绩预告: {ftype}")
            st.dataframe(r["forecast"].head(5), use_container_width=True)

    with st.expander("📈 财务评分趋势(来自雷达)", expanded=False):
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
