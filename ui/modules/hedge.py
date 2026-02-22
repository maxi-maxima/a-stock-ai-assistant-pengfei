import os
import json
import streamlit as st
import pandas as pd
from core.stock_name import display_name
from core.hedge_engine import HedgeEngine
from core.learning_log import log_event


PLAN_PATH = "data/hedge_plan.json"


def _init_legs():
    if "hedge_legs" not in st.session_state:
        st.session_state["hedge_legs"] = []


def _save_legs(legs):
    os.makedirs(os.path.dirname(PLAN_PATH), exist_ok=True)
    try:
        with open(PLAN_PATH, "w", encoding="utf-8") as f:
            json.dump(legs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_legs():
    if not os.path.exists(PLAN_PATH):
        return []
    try:
        with open(PLAN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def render(scanner, real_portfolio):
    st.header("🛡️ 多策略对冲模块")
    st.caption("组合级对冲建议：指数 + 行业 + 事件多腿对冲（手动执行/纸面模拟）。")

    _init_legs()
    engine = HedgeEngine(scanner.data_skill)

    price_cache = {}
    total_val, per_code, price_cache = engine.portfolio_value(real_portfolio, price_cache=price_cache)
    st.metric("当前组合市值", f"¥{total_val:,.0f}")
    finfo = real_portfolio.get_fund_info()
    exposure = 0.0
    try:
        invested = float(finfo.get("invested", 0))
        principal = float(finfo.get("principal", 1))
        exposure = invested / principal if principal > 0 else 0.0
    except Exception:
        exposure = 0.0
    st.caption(f"组合仓位暴露: {exposure*100:.1f}%")
    by_industry, top_ratio, top_ind = engine.industry_exposure(real_portfolio)
    if top_ratio > 0:
        st.caption(f"行业集中度: {top_ind} {top_ratio*100:.1f}%")

    with st.expander("📌 持仓估值明细", expanded=False):
        rows = []
        for code, info in per_code.items():
            rows.append({
                "股票": display_name(code, with_code=True),
                "估值": f"{info['value']:.0f}",
                "价格": info.get("price")
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("暂无持仓")

    st.divider()
    st.subheader("⚡ 自动对冲方案")
    st.caption("根据仓位暴露与行业集中度，自动生成指数/行业对冲腿。")

    a1, a2, a3 = st.columns(3)
    with a1:
        exp_th = st.slider("仓位暴露阈值", 0.1, 0.9, 0.5, step=0.05)
    with a2:
        ind_th = st.slider("行业集中度阈值", 0.1, 0.9, 0.35, step=0.05)
    with a3:
        target_cov = st.slider("目标对冲覆盖率", 0.1, 1.0, 0.6, step=0.05)

    overwrite = st.checkbox("覆盖现有对冲腿", value=False)
    if st.button("一键生成自动对冲方案"):
        auto_legs = []
        if exposure >= exp_th:
            auto_legs.append(engine.suggest_index_hedge(exposure))
        if top_ratio >= ind_th:
            auto_legs.extend(engine.suggest_industry_hedge(real_portfolio, top_n=2))

        # scale weights to target coverage
        total_weight = sum(float(l.get("weight", 0)) * float(l.get("ratio", 1)) for l in auto_legs)
        if total_weight > 0:
            scale = min(1.0, float(target_cov) / total_weight)
            for leg in auto_legs:
                leg["weight"] = float(leg.get("weight", 0)) * scale

        if overwrite:
            st.session_state["hedge_legs"] = auto_legs
        else:
            st.session_state["hedge_legs"].extend(auto_legs)
        for leg in auto_legs:
            log_event("hedge_plan_add", leg)
        log_event("hedge_auto_plan", {
            "exposure": exposure,
            "industry_ratio": top_ratio,
            "target_coverage": target_cov,
            "legs": auto_legs
        })
        if auto_legs:
            st.success(f"已生成 {len(auto_legs)} 条对冲腿")
        else:
            st.info("未触发阈值，未生成对冲腿")

    st.divider()
    st.subheader("⚡ 一键对冲建议")
    cA, cB, cC = st.columns([2, 1, 1])
    with cA:
        st.caption("根据当前仓位暴露，提供指数对冲默认方案。")
    with cB:
        if st.button("一键添加指数对冲"):
            leg = engine.suggest_index_hedge(exposure)
            st.session_state["hedge_legs"].append(leg)
            log_event("hedge_plan_add", leg)
            st.success("已添加指数对冲腿")
    with cC:
        if st.button("一键添加行业对冲"):
            legs = engine.suggest_industry_hedge(real_portfolio, top_n=2)
            if legs:
                st.session_state["hedge_legs"].extend(legs)
                for leg in legs:
                    log_event("hedge_plan_add", leg)
                st.success("已添加行业对冲腿")
            else:
                st.info("未检测到行业集中度")

    st.divider()
    st.subheader("➕ 添加对冲腿")
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    strategy = c1.selectbox("策略类型", ["指数对冲", "行业对冲", "事件对冲"])
    hedge_code = c2.text_input("对冲标的代码", "510300.SH")
    weight = c3.number_input("权重", min_value=0.0, max_value=1.0, value=0.5, step=0.05)
    ratio = c4.number_input("对冲比例", min_value=0.1, max_value=2.0, value=1.0, step=0.1)

    if st.button("添加对冲腿"):
        if hedge_code:
            st.session_state["hedge_legs"].append({
                "strategy": strategy,
                "code": hedge_code.strip(),
                "weight": float(weight),
                "ratio": float(ratio)
            })
            log_event("hedge_plan_add", {"strategy": strategy, "code": hedge_code, "weight": weight, "ratio": ratio})
            st.success("已添加")

    st.divider()
    st.subheader("📊 对冲建议")
    legs = st.session_state.get("hedge_legs", [])
    if not legs:
        st.info("尚未添加对冲腿")
        return

    rows = []
    total_hedge = 0.0
    for i, leg in enumerate(legs):
        code = leg.get("code")
        price = engine.get_latest_price(code)
        name = engine.get_name(code)
        shares = engine.hedge_shares(total_val, price, weight=leg.get("weight", 0), hedge_ratio=leg.get("ratio", 1))
        hedge_cash = total_val * leg.get("weight", 0) * leg.get("ratio", 1)
        total_hedge += hedge_cash
        rows.append({
            "策略": leg.get("strategy"),
            "标的": f"{name} ({code})",
            "价格": price,
            "权重": leg.get("weight"),
            "比例": leg.get("ratio"),
            "对冲金额": f"{hedge_cash:.0f}",
            "建议股数": shares
        })

    df_hedge = pd.DataFrame(rows)
    st.dataframe(df_hedge, use_container_width=True)
    st.metric("对冲覆盖率", f"{(total_hedge / total_val * 100) if total_val > 0 else 0:.1f}%")

    # 对冲效果估算
    if total_val > 0:
        st.subheader("📉 对冲效果估算")
        # 简化估算：对冲覆盖率 * 暴露
        try:
            exposure_effect = exposure * (total_hedge / total_val)
        except Exception:
            exposure_effect = 0.0
        st.caption(f"预计净敞口下降约 {exposure_effect*100:.1f}%（简化估算）")

    c3, c4 = st.columns(2)
    with c3:
        if st.button("保存对冲方案"):
            _save_legs(legs)
            st.success("已保存")
    with c4:
        if st.button("加载对冲方案"):
            st.session_state["hedge_legs"] = _load_legs()
            st.success("已加载")

    if st.button("清空对冲腿"):
        st.session_state["hedge_legs"] = []
        st.success("已清空")
