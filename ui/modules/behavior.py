import os
import json
import streamlit as st
import pandas as pd
import altair as alt
from core.learning_log import load_events, summarize_behavior
from skills.factor_attribution import summarize_factor_effects, split_factor_stats
from skills.data_factory import DataSkillFactory
from skills.risk_budget import max_drawdown
from core.stock_name import display_name


def _load_style_profile():
    path = "config/style_profile.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def render():
    st.header("🧭 行为画像 (Behavior Profile)")
    events = load_events(2000)
    summary = summarize_behavior(events)
    profile = _load_style_profile()
    data_skill = DataSkillFactory.get_skill("tushare")

    c1, c2, c3 = st.columns(3)
    c1.metric("风险偏好", summary.get("risk_appetite", "平衡"))
    c2.metric("持仓偏好", summary.get("holding_preference", "中性"))
    c3.metric("活跃度", summary.get("activity_level", "低"))

    st.caption(f"累计事件: {summary.get('total_events', 0)}")

    if profile:
        with st.expander("🧬 DNA 档案", expanded=False):
            st.json(profile)

    if not events:
        st.info("暂无行为数据，先进行回测/分析/教学即可生成画像。")
        return

    df = pd.DataFrame(events)
    df["date"] = df["ts"].astype(str).str.slice(0, 10)

    st.subheader("📊 事件分布")
    by_type = df.groupby("event").size().reset_index(name="count").sort_values("count", ascending=False)
    st.bar_chart(by_type.set_index("event"))

    st.subheader("📈 活跃度趋势")
    by_day = df.groupby("date").size().reset_index(name="count")
    st.line_chart(by_day.set_index("date"))

    st.subheader("🧠 分析行为")
    if "payload" in df.columns:
        def _get(d, k):
            return d.get(k) if isinstance(d, dict) else None
        df["action"] = df["payload"].apply(lambda x: _get(x, "action"))
        df["score"] = df["payload"].apply(lambda x: _get(x, "score"))
        df["code"] = df["payload"].apply(lambda x: _get(x, "code"))

        an = df[df["event"] == "analysis_run"]
        if not an.empty:
            a1, a2, a3 = st.columns(3)
            a1.metric("分析次数", len(an))
            a2.metric("平均评分", f"{an['score'].dropna().mean():.1f}" if an["score"].notna().any() else "N/A")
            a3.metric("偏好动作", an["action"].mode().iloc[0] if an["action"].notna().any() else "N/A")

            act_cnt = an.groupby("action").size().reset_index(name="count").sort_values("count", ascending=False)
            st.bar_chart(act_cnt.set_index("action"))
        else:
            st.caption("暂无分析记录")

    st.subheader("🧪 回测偏好")
    bt = df[df["event"] == "backtest_run"]
    if not bt.empty:
        bt["tp"] = bt["payload"].apply(lambda x: x.get("take_profit") if isinstance(x, dict) else None)
        bt["sl"] = bt["payload"].apply(lambda x: x.get("stop_loss") if isinstance(x, dict) else None)
        bt["days"] = bt["payload"].apply(lambda x: x.get("max_days") if isinstance(x, dict) else None)
        b1, b2, b3 = st.columns(3)
        b1.metric("平均止盈", f"{bt['tp'].dropna().mean()*100:.1f}%" if bt["tp"].notna().any() else "N/A")
        b2.metric("平均止损", f"{bt['sl'].dropna().mean()*100:.1f}%" if bt["sl"].notna().any() else "N/A")
        b3.metric("平均持仓", f"{bt['days'].dropna().mean():.0f}天" if bt["days"].notna().any() else "N/A")
    else:
        st.caption("暂无回测记录")

    st.subheader("🧾 最近事件")
    def _flatten(ev):
        payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
        return {
            "时间": ev.get("ts"),
            "事件": ev.get("event"),
            "股票": display_name(payload.get("code"), with_code=True),
            "动作": payload.get("action"),
            "评分": payload.get("score")
        }
    recent = [ _flatten(e) for e in events[-20:] ]
    st.dataframe(pd.DataFrame(recent), use_container_width=True)

    # 纸面交易统计
    trades = df[df["event"] == "paper_trade"]
    if not trades.empty:
        st.subheader("💰 纸面交易统计")
        trades["pnl"] = trades["payload"].apply(lambda x: x.get("pnl") if isinstance(x, dict) else None)
        trades["action"] = trades["payload"].apply(lambda x: x.get("action") if isinstance(x, dict) else None)
        trades["equity"] = trades["payload"].apply(lambda x: x.get("equity") if isinstance(x, dict) else None)
        sells = trades[trades["action"] == "SELL"]
        if not sells.empty:
            total_pnl = sells["pnl"].dropna().sum()
            win = (sells["pnl"] > 0).sum()
            total = sells["pnl"].notna().sum()
            win_rate = win / total * 100 if total > 0 else 0
            c1, c2, c3 = st.columns(3)
            c1.metric("卖出次数", int(total))
            c2.metric("胜率", f"{win_rate:.1f}%")
            c3.metric("累计盈亏", f"{total_pnl:.0f}")

        # equity curve
        eq = trades["equity"].dropna()
        if not eq.empty:
            st.subheader("📈 纸面资金曲线")
            st.line_chart(eq.reset_index(drop=True))

        # per-stock pnl bar chart
        if not sells.empty:
            st.subheader("📊 买卖盈亏柱状图")
            # resolve names
            name_cache = st.session_state.get("name_cache", {})
            def _name(code):
                if code in name_cache:
                    return name_cache[code]
                try:
                    info = data_skill.get_stock_basic_info(code)
                    name = info.get("name", code) if isinstance(info, dict) else code
                except Exception:
                    name = code
                name_cache[code] = name
                st.session_state["name_cache"] = name_cache
                return name

            agg = sells.groupby(sells["payload"].apply(lambda x: x.get("code") if isinstance(x, dict) else None))["pnl"].sum()
            rows = []
            for code, pnl in agg.items():
                if code is None:
                    continue
                rows.append({
                    "code": code,
                    "name": _name(code),
                    "pnl": float(pnl),
                    "abs_pnl": abs(float(pnl))
                })
            if rows:
                pdf = pd.DataFrame(rows)
                chart = alt.Chart(pdf).mark_bar().encode(
                    x=alt.X("name:N", sort="-y", title="股票"),
                    y=alt.Y("abs_pnl:Q", title="盈亏幅度（绝对值）"),
                    color=alt.condition(
                        alt.datum.pnl >= 0,
                        alt.value("#e53935"),
                        alt.value("#43a047")
                    ),
                    tooltip=["name", "pnl"]
                )
                st.altair_chart(chart, use_container_width=True)

            # summary metrics
            total_profit = float(total_pnl) if "total_pnl" in locals() else 0.0
            eq_series = eq.tolist()
            mdd = max_drawdown(eq_series) if eq_series else 0.0
            s1, s2 = st.columns(2)
            s1.metric("最大回撤", f"{mdd*100:.2f}%")
            s2.metric("累计盈利", f"{total_profit:.0f}")

    # 风险预算
    rb = df[df["event"] == "risk_budget"]
    if not rb.empty:
        last = rb.iloc[-1]
        payload = last.get("payload", {}) if isinstance(last.get("payload"), dict) else {}
        st.subheader("🧯 组合风险预算")
        r1, r2, r3 = st.columns(3)
        r1.metric("最大回撤", f"{float(payload.get('mdd', 0))*100:.2f}%")
        r2.metric("VaR(95%)", f"{float(payload.get('var', 0))*100:.2f}%")
        r3.metric("风险等级", payload.get("level", "N/A"))

    # 因子权重趋势
    fw = df[df["event"] == "feature_weights"]
    if not fw.empty:
        st.subheader("⚖️ 因子权重趋势")
        try:
            weights = fw["payload"].apply(lambda x: x.get("weights") if isinstance(x, dict) else {})
            rows = []
            for w in weights:
                if not isinstance(w, dict):
                    continue
                rows.append(w)
            if rows:
                wdf = pd.DataFrame(rows)
                st.line_chart(wdf)
        except Exception:
            pass

    # 因子归因
    with st.expander("📌 因子有效性 (简易相关性)", expanded=False):
        corr = summarize_factor_effects()
        if corr is not None and not corr.empty:
            st.dataframe(corr, use_container_width=True)
        else:
            st.caption("暂无足够交易数据用于统计")

    with st.expander("📊 因子分层统计 (盈利 vs 亏损)", expanded=False):
        win, lose = split_factor_stats()
        if win is not None and lose is not None:
            st.markdown("**盈利样本**")
            st.dataframe(win, use_container_width=True)
            st.markdown("**亏损样本**")
            st.dataframe(lose, use_container_width=True)
        else:
            st.caption("暂无足够交易数据用于统计")
