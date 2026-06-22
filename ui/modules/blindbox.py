import json
import os

import pandas as pd
import streamlit as st

from core.blindbox_report import (
    build_blindbox_control_panel,
    build_blindbox_cumulative_series,
    build_blindbox_scorecard,
    load_blindbox_health_snapshot,
)
from core.blindbox_scheduler import create_windows_task, delete_windows_task, load_scheduler_config, query_windows_task, save_scheduler_config
from core.blindbox_view import _format_position_rows, _format_report_rows, _format_strategy_rows, _parse_task_query_summary
from tools.blindbox_daily_runner import run_once


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def render():
    st.header("盲盒实验机")
    st.caption("最小闭环实验引擎：自动抽策略、纸面交易、自动平仓，并根据已实现盈亏自动调权。")

    snap = load_blindbox_health_snapshot()
    scorecard = build_blindbox_scorecard(snap)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最近交易日", snap.get("last_trade_date") or "-")
    c2.metric("当前持仓数", int(snap.get("open_positions", 0) or 0))
    c3.metric("活跃策略数", int(snap.get("active_strategies", 0) or 0))
    c4.metric("最近已实现盈亏", f"{float(snap.get('realized_pnl_sum', 0.0) or 0.0):.2f}")

    st.subheader("首页结论")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("当前结论", scorecard.get("conclusion", ""))
    s2.metric("主策略综合分", f"{float(scorecard.get('primary_score', 0.0) or 0.0):.2f}")
    s3.metric("对照组综合分", f"{float(scorecard.get('control_score', 0.0) or 0.0):.2f}")
    s4.metric("可信度", scorecard.get("confidence", ""))
    st.caption(f"分差：{float(scorecard.get('score_diff', 0.0) or 0.0):+.2f}")
    contrib = scorecard.get("contributions", {}) if isinstance(scorecard.get("contributions", {}), dict) else {}
    st.caption(
        f"贡献拆解：累计收益 {float(contrib.get('累计收益', 0.0) or 0.0):.2f} | "
        f"平均单笔收益 {float(contrib.get('平均单笔收益', 0.0) or 0.0):.2f} | "
        f"最大回撤 {float(contrib.get('最大回撤', 0.0) or 0.0):.2f} | "
        f"样本量 {float(contrib.get('样本量', 0.0) or 0.0):.2f}"
    )

    panel = build_blindbox_control_panel(snap)
    st.subheader("主策略 vs 随机对照组")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("主策略编号", panel["primary"]["strategy_id"] or "-")
    p2.metric("主策略权重", f"{float(panel['primary']['weight'] or 0.0):.2f}")
    p3.metric("主策略调用数", int(panel["primary"]["calls"] or 0))
    p4.metric("主策略已平仓数", int(panel["primary"]["closed_trades"] or 0))

    p5, p6 = st.columns(2)
    p5.metric("主策略平均已实现收益率", f"{float(panel['primary']['avg_realized_pnl'] or 0.0)*100:.2f}%")
    p6.metric("随机对照组平均已实现收益率", f"{float(panel['control']['avg_realized_pnl'] or 0.0)*100:.2f}%")

    c8, c9 = st.columns(2)
    c8.metric("随机对照组调用数", int(panel["control"]["calls"] or 0))
    c9.metric("随机对照组已平仓数", int(panel["control"]["closed_trades"] or 0))

    st.subheader("本地自动运行")
    cfg = load_scheduler_config()
    time_val = st.text_input("每日运行时间", value=str(cfg.get("start_time", "15:05")), key="blindbox_schedule_time")
    c5, c6, c7 = st.columns(3)
    if c5.button("立即运行一次", use_container_width=True):
        latest = _load_json("data/blindbox_runner_latest.json", {})
        run_once(latest=latest, save=True)
        st.success("盲盒实验机已运行一次")
        st.rerun()
    if c6.button("安装本地定时任务", use_container_width=True):
        save_scheduler_config({"start_time": time_val})
        st.session_state["blindbox_schedule_install"] = create_windows_task(start_time=time_val)
    if c7.button("删除本地定时任务", use_container_width=True):
        st.session_state["blindbox_schedule_delete"] = delete_windows_task()

    query = query_windows_task()
    if query.get("ok"):
        st.success("本地定时任务已安装")
        with st.expander("任务详情", expanded=False):
            rows = _parse_task_query_summary(query.get("stdout", ""))
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.text(query.get("stdout", ""))
    else:
        st.info("当前未检测到盲盒实验机定时任务")

    install_out = st.session_state.get("blindbox_schedule_install")
    if isinstance(install_out, dict):
        if install_out.get("ok"):
            st.success("定时任务安装成功")
        else:
            st.error(install_out.get("stderr") or install_out.get("stdout") or "定时任务安装失败")

    delete_out = st.session_state.get("blindbox_schedule_delete")
    if isinstance(delete_out, dict):
        if delete_out.get("ok"):
            st.success("定时任务已删除")
        else:
            st.warning(delete_out.get("stderr") or delete_out.get("stdout") or "删除失败或任务不存在")

    with st.expander("策略状态", expanded=True):
        strategies = _load_json("data/blindbox_strategy_state.json", [])
        if strategies:
            st.dataframe(pd.DataFrame(_format_strategy_rows(strategies)), use_container_width=True, hide_index=True)
        else:
            st.info("暂无盲盒策略状态")

    with st.expander("当前持仓", expanded=True):
        positions = _load_json("data/blindbox_positions.json", [])
        if positions:
            st.dataframe(pd.DataFrame(_format_position_rows(positions)), use_container_width=True, hide_index=True)
        else:
            st.info("暂无盲盒持仓")

    with st.expander("最近日报", expanded=False):
        reports = []
        path = "data/blindbox_daily_report.jsonl"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        reports.append(json.loads(line))
                    except Exception:
                        continue
        if reports:
            st.dataframe(pd.DataFrame(_format_report_rows(reports[-20:])), use_container_width=True, hide_index=True)
            curve_rows = build_blindbox_cumulative_series(reports)
            if curve_rows:
                st.caption("累计已实现盈亏对比")
                st.line_chart(pd.DataFrame(curve_rows).set_index("交易日期"))
        else:
            st.info("暂无盲盒日报")
