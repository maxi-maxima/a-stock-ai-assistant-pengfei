import json
import os
from collections import Counter, deque

import pandas as pd
import streamlit as st


EVENT_BUS_PATH = "data/event_bus.jsonl"
DEFAULT_LIGHTNING_REPORT = "data/agent_lightning_report.jsonl"


def _load_agent_lightning_api():
    try:
        from core import agent_lightning_adapter as ala

        return ala, ""
    except Exception as exc:
        return None, str(exc)


def _load_agent_reports(max_lines=5000):
    if not os.path.exists(EVENT_BUS_PATH):
        return []
    try:
        with open(EVENT_BUS_PATH, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=max_lines)
    except Exception:
        return []

    reports = []
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
        reports.append({
            "ts": rec.get("ts") or payload.get("ts"),
            "agent_id": payload.get("agent_id"),
            "agent_type": payload.get("agent_type"),
            "status": payload.get("status"),
            "summary": payload.get("summary"),
            "run_id": payload.get("run_id"),
            "version": payload.get("version"),
            "duration_ms": payload.get("duration_ms"),
            "source": rec.get("source"),
            "details": payload.get("details"),
            "metrics": payload.get("metrics"),
            "recommendations": payload.get("recommendations"),
            "tags": payload.get("tags"),
        })
    return reports


def _build_label(rec):
    ts = rec.get("ts") or ""
    agent = rec.get("agent_id") or rec.get("agent_type") or "unknown"
    status = rec.get("status") or "idle"
    return f"{ts} | {agent} | {status}"


def _render_timeline():
    st.subheader("智能体时间线")

    max_lines = int(st.number_input("Read last N lines from event bus", min_value=200, max_value=20000, value=5000, step=200))
    reports = _load_agent_reports(max_lines=max_lines)

    if not reports:
        st.info("事件总线里还没有智能体报告。")
        return

    agent_ids = sorted({r.get("agent_id") for r in reports if r.get("agent_id")})
    statuses = ["ok", "warn", "fail", "idle"]

    cols = st.columns(2)
    with cols[0]:
        agent_filter = st.multiselect("智能体筛选", agent_ids, default=agent_ids)
    with cols[1]:
        status_filter = st.multiselect("状态筛选", statuses, default=statuses)

    filtered = []
    for r in reports:
        if agent_filter and r.get("agent_id") not in agent_filter:
            continue
        if status_filter and r.get("status") not in status_filter:
            continue
        filtered.append(r)

    if not filtered:
        st.warning("当前筛选条件下没有记录。")
        return

    status_counts = Counter([r.get("status") for r in filtered])
    st.caption("状态统计：" + ", ".join([f"{k}:{v}" for k, v in status_counts.items()]))

    df = pd.DataFrame([{
        "时间": r.get("ts"),
        "智能体": r.get("agent_id"),
        "状态": r.get("status"),
        "摘要": r.get("summary"),
        "运行编号": r.get("run_id"),
        "耗时毫秒": r.get("duration_ms"),
        "来源": r.get("source")
    } for r in filtered])

    st.dataframe(df, use_container_width=True)

    options = [_build_label(r) for r in filtered]
    selected = st.selectbox("查看详情", options, index=0)
    idx = options.index(selected)
    rec = filtered[idx]

    st.markdown("**摘要**")
    st.write(rec.get("summary") or "")

    st.markdown("**指标**")
    st.json(rec.get("metrics") or {})

    st.markdown("**详情**")
    st.json(rec.get("details") or {})

    st.markdown("**建议**")
    st.write(rec.get("recommendations") or [])

    st.markdown("**标签**")
    st.write(rec.get("tags") or [])


def _render_lightning():
    st.subheader("智能体强化调优")
    api, api_err = _load_agent_lightning_api()
    if not api:
        st.error(f"加载 AgentLightning 模块失败: {api_err}")
        return

    cfg = api.load_config()
    current_buy = float(cfg.get("buy_threshold", 62.0) or 62.0)
    current_sell = float(cfg.get("sell_threshold", 50.0) or 50.0)
    report_path = st.text_input("报告文件路径", value=str(cfg.get("report_path") or DEFAULT_LIGHTNING_REPORT))
    compare_limit = int(st.number_input("对比最近 run 数量", min_value=1, max_value=100, value=20, step=1))

    st.caption(
        f"当前阈值: buy={current_buy:.1f}, sell={current_sell:.1f} | "
        f"reward_mode={cfg.get('reward_mode')} | risk_level_mode={cfg.get('risk_level_mode')}"
    )

    comp = api.compare_agent_lightning_runs(path=report_path, limit=compare_limit)
    runs = comp.get("runs", []) if isinstance(comp, dict) else []
    if runs:
        df_runs = pd.DataFrame(
            [
                {
                    "运行编号": r.get("run_id"),
                    "任务数": r.get("tasks"),
                    "平均奖励": round(float(r.get("avg_reward", 0.0)), 6),
                    "平均总分": round(float(r.get("avg_score_total", 0.0)), 4),
                    "动作分布": " / ".join(
                        [f"{k}:{v}" for k, v in (r.get("actions", {}) if isinstance(r.get("actions"), dict) else {}).items()]
                    ),
                    "错误数": r.get("errors", 0),
                    "开始时间": r.get("ts_first"),
                    "结束时间": r.get("ts_last"),
                }
                for r in runs
            ]
        )
        st.dataframe(df_runs, use_container_width=True)
    else:
        st.info("当前报告里没有可对比的 run 记录。")

    run_options = ["全部"] + [str(r.get("run_id")) for r in runs if r.get("run_id")]
    selected_run = st.selectbox("调优数据范围", options=run_options, index=0)
    tune_run_id = None if selected_run == "全部" else selected_run

    c1, c2, c3 = st.columns(3)
    with c1:
        buy_min = int(st.number_input("buy 最小值", min_value=1, max_value=99, value=55, step=1))
        buy_max = int(st.number_input("buy 最大值", min_value=1, max_value=99, value=75, step=1))
    with c2:
        sell_min = int(st.number_input("sell 最小值", min_value=1, max_value=99, value=40, step=1))
        sell_max = int(st.number_input("sell 最大值", min_value=1, max_value=99, value=60, step=1))
    with c3:
        min_gap = int(st.number_input("buy-sell 最小间隔", min_value=1, max_value=50, value=5, step=1))
        trade_penalty = float(st.number_input("交易惩罚", min_value=0.0, max_value=1.0, value=0.02, step=0.01, format="%.2f"))
        high_risk_buy_penalty = float(
            st.number_input("高风险买入惩罚", min_value=0.0, max_value=1.0, value=0.08, step=0.01, format="%.2f")
        )
    with st.expander("均衡交易风格目标", expanded=True):
        balance_enabled = st.checkbox("启用均衡目标（抑制全 HOLD）", value=True)
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            target_trade_ratio = float(
                st.number_input("目标交易占比", min_value=0.0, max_value=1.0, value=0.35, step=0.05, format="%.2f")
            )
            trade_ratio_weight = float(
                st.number_input("交易占比权重", min_value=0.0, max_value=2.0, value=0.25, step=0.05, format="%.2f")
            )
        with bc2:
            max_hold_ratio = float(
                st.number_input("最大 HOLD 占比", min_value=0.0, max_value=1.0, value=0.80, step=0.05, format="%.2f")
            )
            hold_excess_weight = float(
                st.number_input("超额 HOLD 惩罚", min_value=0.0, max_value=2.0, value=0.35, step=0.05, format="%.2f")
            )
        with bc3:
            min_buy_ratio = float(
                st.number_input("最小 BUY 占比", min_value=0.0, max_value=1.0, value=0.10, step=0.05, format="%.2f")
            )
            buy_shortfall_weight = float(
                st.number_input("BUY 不足惩罚", min_value=0.0, max_value=2.0, value=0.25, step=0.05, format="%.2f")
            )

    if st.button("开始调优", type="primary"):
        tune = api.tune_thresholds_from_report(
            path=report_path,
            run_id=tune_run_id,
            reward_mode=str(cfg.get("reward_mode") or "score_risk_adjusted"),
            buy_min=buy_min,
            buy_max=buy_max,
            sell_min=sell_min,
            sell_max=sell_max,
            min_gap=min_gap,
            trade_penalty=trade_penalty,
            high_risk_buy_penalty=high_risk_buy_penalty,
            balance_mode="balanced" if balance_enabled else "none",
            target_trade_ratio=target_trade_ratio,
            trade_ratio_weight=trade_ratio_weight,
            max_hold_ratio=max_hold_ratio,
            hold_excess_weight=hold_excess_weight,
            min_buy_ratio=min_buy_ratio,
            buy_shortfall_weight=buy_shortfall_weight,
        )
        st.session_state["al_tune_result"] = tune
        st.session_state["al_tune_report_path"] = report_path

    tune_result = st.session_state.get("al_tune_result")
    if not isinstance(tune_result, dict):
        return
    if not tune_result.get("ok"):
        st.error(f"调优失败: {tune_result.get('error', 'unknown')}")
        return

    best = tune_result.get("best", {}) if isinstance(tune_result.get("best"), dict) else {}
    best_buy = float(best.get("buy_threshold", current_buy) or current_buy)
    best_sell = float(best.get("sell_threshold", current_sell) or current_sell)
    best_util = float(best.get("avg_utility", 0.0) or 0.0)
    best_obj = float(best.get("objective", best_util) or best_util)
    best_penalty = float(best.get("style_penalty", 0.0) or 0.0)
    best_ratios = best.get("ratios", {}) if isinstance(best.get("ratios"), dict) else {}
    best_actions = best.get("actions", {}) if isinstance(best.get("actions"), dict) else {}
    st.success(
        f"最佳阈值: buy={best_buy:.1f}, sell={best_sell:.1f}, objective={best_obj:.6f}, "
        f"avg_utility={best_util:.6f}, style_penalty={best_penalty:.6f}, "
        f"actions={best_actions}"
    )
    if best_ratios:
        st.caption(
            "占比: "
            f"BUY={float(best_ratios.get('buy', 0.0)):.1%}, "
            f"SELL={float(best_ratios.get('sell', 0.0)):.1%}, "
            f"HOLD={float(best_ratios.get('hold', 0.0)):.1%}, "
            f"TRADE={float(best_ratios.get('trade', 0.0)):.1%}"
        )

    top = tune_result.get("top_candidates", []) if isinstance(tune_result.get("top_candidates"), list) else []
    if top:
        df_top = pd.DataFrame(
            [
                {
                    "buy_threshold": float(x.get("buy_threshold", 0.0)),
                    "sell_threshold": float(x.get("sell_threshold", 0.0)),
                    "objective": round(float(x.get("objective", x.get("avg_utility", 0.0))), 6),
                    "avg_utility": round(float(x.get("avg_utility", 0.0)), 6),
                    "style_penalty": round(float(x.get("style_penalty", 0.0)), 6),
                    "hold_ratio": round(float((x.get("ratios", {}) if isinstance(x.get("ratios"), dict) else {}).get("hold", 0.0)), 4),
                    "trade_ratio": round(float((x.get("ratios", {}) if isinstance(x.get("ratios"), dict) else {}).get("trade", 0.0)), 4),
                    "actions": " / ".join(
                        [f"{k}:{v}" for k, v in (x.get("actions", {}) if isinstance(x.get("actions"), dict) else {}).items()]
                    ),
                }
                for x in top
            ]
        )
        st.dataframe(df_top, use_container_width=True)

    if st.button("应用最佳阈值到配置"):
        new_cfg = dict(cfg) if isinstance(cfg, dict) else {}
        new_cfg["buy_threshold"] = best_buy
        new_cfg["sell_threshold"] = best_sell
        new_cfg["report_path"] = str(st.session_state.get("al_tune_report_path") or report_path)
        if api.save_config(new_cfg):
            st.success("已写入 config/agent_lightning.json。重启后生效。")
        else:
            st.error("写入配置失败。")


def render():
    tab_timeline, tab_lightning = st.tabs(["智能体时间线", "AgentLightning 调优"])
    with tab_timeline:
        _render_timeline()
    with tab_lightning:
        _render_lightning()
