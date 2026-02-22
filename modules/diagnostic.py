import streamlit as st
import pandas as pd
import time
from skills.diagnostic import SystemDoctor

def render():
    st.header("🏥 系统自检中心 (System Health Center)")
    st.caption("一键检测 AI 交易分身的所有神经链路、数据管道和外部接口。")
    
    st.divider()
    
    c1, c2 = st.columns([1, 3])
    
    with c1:
        st.info("检测项目：\n1. 核心数据文件\n2. 资产账户接口\n3. 策略库同步\n4. 记忆存取\n5. 行情网络连接\n6. 庄家克星算法")
        if st.button("🚀 开始全面体检", type="primary"):
            doc = SystemDoctor()
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 模拟进度动画，提升体验
            status_text.text("正在扫描本地文件系统...")
            progress_bar.progress(20)
            time.sleep(0.3)
            
            status_text.text("正在测试资产与策略链路...")
            progress_bar.progress(50)
            time.sleep(0.3)
            
            status_text.text("正在连接交易所测试网络延时...")
            progress_bar.progress(80)
            
            # 执行真实检查
            report = doc.run_full_diagnosis()
            
            progress_bar.progress(100)
            status_text.text("✅ 体检完成！")
            
            st.session_state['diag_report'] = report
            st.rerun()

    with c2:
        st.subheader("📋 体检报告")
        
        if 'diag_report' in st.session_state:
            report = st.session_state['diag_report']
            
            # 统计
            errors = len([r for r in report if r['status'] == 'ERROR'])
            warnings = len([r for r in report if r['status'] == 'WARNING'])
            
            if errors == 0 and warnings == 0:
                st.success("🎉 系统极度健康！所有链路运作正常。")
            elif errors > 0:
                st.error(f"⚠️ 发现 {errors} 个致命故障，请查看详情！")
            else:
                st.warning(f"发现 {warnings} 个潜在隐患。")
            
            # 渲染详细列表
            for item in report:
                icon = "✅"
                color = "green"
                if item['status'] == "ERROR":
                    icon = "❌"
                    color = "red"
                elif item['status'] == "WARNING":
                    icon = "⚠️"
                    color = "orange"
                
                st.markdown(f"""
                <div style="border-left: 5px solid {color}; padding-left: 10px; margin-bottom: 10px; background-color: rgba(0,0,0,0.02)">
                    <strong style="font-size:16px">{icon} {item['module']}</strong>
                    <br>
                    <span style="color:gray">{item['message']}</span>
                </div>
                """, unsafe_allow_html=True)
                
        else:
            st.info("等待启动检测...")