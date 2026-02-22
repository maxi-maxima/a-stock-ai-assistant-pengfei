import streamlit as st
from core.plugin_manager import PluginManager

pm = PluginManager()

def render():
    st.header("⚙️ 系统中枢设置 (System Kernel Settings)")
    st.caption("在此处挂载或卸载功能模块。关闭的模块将从导航栏消失，但数据不会丢失。")
    
    st.divider()
    
    # 获取当前状态
    current_status = pm.get_all_status()
    
    # 模块名称映射 (ID -> 中文名)
    name_map = {
        "tactics": "🧘 战术指挥室 (Tactics)",
        "patrol": "👮 AI 巡逻官 (Patrol)",
        "financial": "📊 财务透视 (Financial)",
        "broker": "🏆 券商金股 (Broker)",
        "radar": "🔭 猎手雷达 (Radar)",
        "asset": "💼 资产管理 (Asset)",
        "workshop": "🛠️ 技能工坊 (Workshop)",
        "backtest": "⏳ 时光回测 (Backtest)",
        "library": "📚 知识库 (Library)",
        "style": "🧬 风格实验室 (Style)",
        "history": "📜 历史军情 (History)",
        "rules": "⚖️ 家规与系统 (Rules)"
    }
    
    st.subheader("🧩 功能模块热插拔")
    
    # 使用列布局，更美观
    col1, col2 = st.columns(2)
    
    keys = list(name_map.keys())
    half = len(keys) // 2
    
    with col1:
        for key in keys[:half]:
            is_on = current_status.get(key, True)
            # 使用 checkbox，当状态改变时直接保存
            new_state = st.toggle(name_map[key], value=is_on, key=f"tog_{key}")
            if new_state != is_on:
                pm.set_status(key, new_state)
                st.toast(f"模块已{'启用' if new_state else '禁用'}，请刷新生效", icon="🔄")
                
    with col2:
        for key in keys[half:]:
            is_on = current_status.get(key, True)
            new_state = st.toggle(name_map[key], value=is_on, key=f"tog_{key}")
            if new_state != is_on:
                pm.set_status(key, new_state)
                st.toast(f"模块已{'启用' if new_state else '禁用'}，请刷新生效", icon="🔄")

    st.divider()
    
    if st.button("🔄 保存并刷新系统", type="primary"):
        st.rerun()