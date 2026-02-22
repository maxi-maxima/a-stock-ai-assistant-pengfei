import streamlit as st
import pandas as pd

from skills.decision_replay import DecisionReplayer


def _summarize(results):
    if not results:
        return {}
    horizons = set()
    for r in results:
        fr = r.get("forward_returns", {}) if isinstance(r.get("forward_returns", {}), dict) else {}
        horizons.update(fr.keys())
    summary = {"total": len(results), "hit_rate": {}}
    for h in horizons:
        hits = 0
        total = 0
        for r in results:
            hit = r.get("hit", {}).get(h)
            if hit is None:
                continue
            total += 1
            if hit:
                hits += 1
        if total:
            summary["hit_rate"][h] = hits / total * 100
    return summary


def render():
    st.header("🔁 决策回放与评估")

    col1, col2, col3 = st.columns(3)
    with col1:
        limit = st.slider("回放样本数", 20, 500, 100, step=20)
    with col2:
        horizons = st.multiselect("前瞻周期(天)", [1, 3, 5, 10, 20], default=[1, 5, 10])
    with col3:
        save = st.checkbox("保存回放结果", value=True)

    if st.button("运行回放", type="primary"):
        replayer = DecisionReplayer()
        res = replayer.replay(limit=limit, horizons=tuple(horizons), save=save)
        st.session_state["replay_results"] = res

    results = st.session_state.get("replay_results", [])
    if not results:
        st.info("暂无回放结果。点击上方按钮运行。")
        return

    summary = _summarize(results)
    st.subheader("概要")
    st.write(f"样本总数: {summary.get('total', 0)}")
    hit_rate = summary.get("hit_rate", {})
    if hit_rate:
        for k, v in hit_rate.items():
            st.write(f"{k} 日命中率: {v:.1f}%")

    st.subheader("明细")
    rows = []
    for r in results:
        row = {
            "ts": r.get("ts"),
            "code": r.get("code"),
            "action": r.get("action"),
            "decision_id": r.get("decision_id")
        }
        fr = r.get("forward_returns", {}) if isinstance(r.get("forward_returns", {}), dict) else {}
        for h, v in fr.items():
            row[f"ret_{h}d(%)"] = None if v is None else round(v, 2)
        rows.append(row)
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
