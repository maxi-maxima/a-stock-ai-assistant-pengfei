import streamlit as st
import datetime
from core.threshold_profiles import (
    load_profiles,
    list_profile_names,
    get_profile,
    get_active_profile_name,
    set_active_profile_name,
    PROFILE_DESC,
)

def render(memory, scanner):
    st.header("⚖️ 委员会家规设置")
    st.caption("在此定义 AI 的最高宪法与人设。")
    
    curr = memory.get_rules()
    constraints = curr.get("constraints", {})

    profiles = load_profiles()
    profile_names = list_profile_names(profiles)
    active_profile = get_active_profile_name(profiles)
    if active_profile not in profiles:
        active_profile = profile_names[0]

    st.markdown("#### 🧭 阈值方案")
    idx = profile_names.index(active_profile) if active_profile in profile_names else 0
    profile_name = st.selectbox("选择方案", profile_names, index=idx, key="rules_profile_select")
    desc = PROFILE_DESC.get(profile_name)
    if desc:
        st.caption(desc)
    if st.button("一键套用到家规", key="rules_profile_apply"):
        profile = get_profile(profile_name, profiles)
        rules_pack = profile.get("rules", {}) if isinstance(profile, dict) else {}
        cons = rules_pack.get("constraints", {}) if isinstance(rules_pack, dict) else {}
        if not cons and isinstance(profile, dict):
            cons = profile.get("constraints", {}) or {}
        if isinstance(cons, dict) and cons:
            new_rules = dict(curr)
            new_constraints = dict(curr.get("constraints", {}))
            new_constraints.update(cons)
            new_rules["constraints"] = new_constraints
            memory.update_rules(new_rules)
            set_active_profile_name(profile_name)
            st.success("已应用家规阈值方案")
            st.rerun()
        else:
            st.warning("该方案未配置家规阈值")
    
    with st.form("rules"):
        st.subheader("📜 核心家规 (General Rules)")
        r_gen = st.text_area("最高宪法 (AI必须无条件遵守)", curr.get('general'))
        
        st.subheader("🎭 三脑人设 (Personas)")
        c1, c2, c3 = st.columns(3)
        r_b = c1.text_area("🔵 蓝军 (进攻)", curr.get('blue'), height=150)
        r_r = c2.text_area("🔴 红军 (风控)", curr.get('red'), height=150)
        r_g = c3.text_area("🟢 绿军 (裁决)", curr.get('green'), height=150)

        st.subheader("🧱 硬性约束 (Structure)")
        d1, d2, d3 = st.columns(3)
        max_single = d1.number_input("单票最大仓位(%)", min_value=1.0, max_value=100.0,
                                     value=float(constraints.get("max_single_position", 0.3))*100, step=1.0)
        max_ind = d2.number_input("行业集中度(%)", min_value=1.0, max_value=100.0,
                                  value=float(constraints.get("max_industry_concentration", 0.35))*100, step=1.0)
        max_dd = d3.number_input("最大回撤(%)", min_value=1.0, max_value=100.0,
                                 value=float(constraints.get("max_drawdown", 0.2))*100, step=1.0)

        d4, d5, d6 = st.columns(3)
        max_trades = d4.number_input("日内最大交易次数", min_value=1, max_value=50,
                                     value=int(constraints.get("max_daily_trades", 6)), step=1)
        stop_loss = d5.number_input("止损幅度(%)", min_value=0.5, max_value=50.0,
                                    value=float(constraints.get("stop_loss_pct", 0.06))*100, step=0.5)
        take_profit = d6.number_input("止盈幅度(%)", min_value=1.0, max_value=200.0,
                                      value=float(constraints.get("take_profit_pct", 0.15))*100, step=1.0)
        allow_chase = st.checkbox("允许追高", value=bool(constraints.get("allow_chase", False)))

        d7, d8 = st.columns(2)
        max_positions = d7.number_input("最大持仓数量", min_value=1, max_value=100,
                                        value=int(constraints.get("max_open_positions", 6)), step=1)
        daily_loss = d8.number_input("日内最大亏损(%)", min_value=0.5, max_value=50.0,
                                     value=float(constraints.get("daily_loss_pct", 0.03))*100, step=0.5)
        
        if st.form_submit_button("💾 保存全套家规"):
            new_r = {
                "general": r_gen,
                "blue": r_b,
                "red": r_r,
                "green": r_g,
                "constraints": {
                    "max_single_position": float(max_single)/100.0,
                    "max_industry_concentration": float(max_ind)/100.0,
                    "max_drawdown": float(max_dd)/100.0,
                    "max_daily_trades": int(max_trades),
                    "stop_loss_pct": float(stop_loss)/100.0,
                    "take_profit_pct": float(take_profit)/100.0,
                    "allow_chase": bool(allow_chase),
                    "max_open_positions": int(max_positions),
                    "daily_loss_pct": float(daily_loss)/100.0
                }
            }
            memory.update_rules(new_r)
            st.success("已更新。下次分析时生效。")
            
    st.divider()
    st.subheader("🧪 系统状态")
    st.caption(f"Data Source: {scanner.data_skill.source_name}")
    try:
        last_trade = scanner.data_skill.get_last_trade_date()
    except Exception:
        last_trade = None
    st.write(f"- 最新交易日: {last_trade if last_trade else '未知'}")
    st.write(f"- 规则更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
