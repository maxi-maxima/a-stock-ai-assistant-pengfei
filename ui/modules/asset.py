import streamlit as st
import pandas as pd
from core.stock_name import display_name

def render(real_portfolio, paper_portfolio, scanner):
    st.header("💼 资产管理中心 (Asset Center)")
    
    tab1, tab2 = st.tabs(["🔴 实盘账户 (Real)", "🔵 模拟账户 (Paper)"])
    
    # --- 实盘账户逻辑 ---
    with tab1:
        st.caption("请在此录入您的真实券商账户资金与持仓，以便 AI 做出符合您仓位的决策。")
        
        # 1. 资金设置
        funds = real_portfolio.get_fund_info()
        c1, c2 = st.columns([2, 1])
        with c1:
            # 安全获取 principal
            current_fund = float(funds.get('principal', 100000))
            new_fund = st.number_input("实盘可用资金 (Cash)", value=current_fund, step=1000.0, key="real_fund_in")
        with c2:
            st.write("")
            st.write("")
            if st.button("💾 更新资金", key="btn_upd_fund"):
                real_portfolio.update_fund(new_fund)
                st.success("资金已更新")
                st.rerun()

        st.divider()

        # 2. 持仓管理
        with st.expander("➕ 录入/更新持仓", expanded=False):
            with st.form("add_pos_form"):
                f1, f2, f3 = st.columns(3)
                p_code = f1.text_input("代码 (如 000001.SZ)")
                p_cost = f2.number_input("成本价", min_value=0.0, step=0.1)
                p_vol = f3.number_input("持仓股数", min_value=0, step=100)
                if st.form_submit_button("提交录入"):
                    if p_code and p_vol > 0:
                        real_portfolio.update_position(p_code, p_vol, p_cost)
                        st.success(f"{display_name(p_code, with_code=True)} 已录入")
                        st.rerun()

        # 3. 持仓列表
        st.subheader("📜 实盘持仓明细")
        positions = real_portfolio.get_all_positions()
        
        if not positions:
            st.info("目前显示空仓。请在上方录入持仓。")
        else:
            h1, h2, h3, h4, h5 = st.columns([2, 2, 2, 2, 1])
            h1.markdown("**股票**")
            h2.markdown("**代码**")
            h3.markdown("**成本**")
            h4.markdown("**股数**")
            h5.markdown("**操作**")
            st.markdown("---")
            
            # 🔥 遍历持仓，增加 try-except 保护
            for code, info in positions.items():
                if not isinstance(info, dict): continue # 跳过异常数据

                stock_name = display_name(code)

                # 🔥 核心修复：使用 .get() 提供默认值，防止报错
                cost = info.get('cost', 0.0)
                volume = info.get('volume', 0)
                # 兼容旧版本键名 (如果存在)
                if volume == 0: volume = info.get('vol', 0)
                
                r1, r2, r3, r4, r5 = st.columns([2, 2, 2, 2, 1])
                r1.write(f"**{stock_name}**")
                r2.write(code)
                r3.write(f"¥{cost}")
                r4.write(f"{volume}股")
                
                if r5.button("🗑️", key=f"del_real_{code}", help=f"删除 {stock_name}"):
                    real_portfolio.remove_position(code)
                    st.toast(f"已删除 {stock_name}", icon="🗑️")
                    st.rerun()

    with tab2:
        st.info("模拟盘数据独立存储，用于测试激进策略。")
        p_funds = paper_portfolio.get_fund_info()
        st.metric("模拟盘资金", f"¥{p_funds.get('principal', 100000):,.0f}")
        p_positions = paper_portfolio.get_all_positions()
        if p_positions:
            rows = []
            for code, info in p_positions.items():
                if not isinstance(info, dict):
                    continue
                rows.append({
                    "股票": display_name(code),
                    "代码": code,
                    "成本": info.get("cost", 0),
                    "股数": info.get("volume", info.get("vol", 0))
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True)
            else:
                st.json(p_positions)
        else:
            st.caption("模拟盘空仓")
