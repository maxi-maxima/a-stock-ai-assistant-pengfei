import streamlit as st
import pandas as pd
import datetime
from core.cognitive_graph import build_cognitive_graph
from core.tri_brain import TriBrainCouncil
from skills.data_factory import TushareMaster
from skills.dealer_hunter import DealerHunter
from skills.news_verifier import NewsVerifier
from skills.smart_grid import SmartGrid
from skills.liquidity_guard import LiquidityGuard
from skills.chip_analyst import ChipAnalyst
from skills.sentiment_engine import SentimentEngine
from skills.cycle_compass import CycleCompass # 🔥 新引入
from core.stock_name import display_name

tm = TushareMaster()
council = TriBrainCouncil()
hunter = DealerHunter()
verifier = NewsVerifier()
smart_grid = SmartGrid()
liq_guard = LiquidityGuard()
chip_analyst = ChipAnalyst()
sentiment = SentimentEngine()
compass = CycleCompass() # 🔥 初始化罗盘

def render_morning_briefing(portfolio):
    # (省略)
    with st.expander("🌅 早盘金典 (Morning Briefing)", expanded=False):
        if st.button("🔮 生成推演"): st.success("已生成")

def render(scanner, real_portfolio, paper_portfolio, plotter, memory, kb):
    st.header("🧘 战术指挥室 (Tactical Room)")
    
    # 1. 市场天气
    weather_report = sentiment.get_weather_report()
    st.markdown(f"""
    <div style="background-color: {weather_report['bg_color']}; padding: 10px; border-radius: 10px; border: 1px solid #ddd; margin-bottom: 20px;">
        <h3 style="margin:0; color: #333;">{weather_report['icon']} 市场温度: {weather_report['temperature']}°C | {weather_report['weather']}</h3>
    </div>
    """, unsafe_allow_html=True)
    
    render_morning_briefing(real_portfolio)
    st.divider()
    
    c1, c2 = st.columns([3, 1])
    with c1: stock_code = st.text_input("输入代码", "000001.SZ")
    with c2: 
        st.write("")
        st.write("")
        btn = st.button("🚀 部署战术", type="primary")

    if btn:
        stock_label = display_name(stock_code, with_code=True)
        st.toast(f"锁定目标 {stock_label}...", icon="🎯")
        with st.spinner("正在调取 K 线与资金数据..."):
            df_chart = scanner.data_skill.get_history(stock_code, days=250)
            
            # 运行所有技能
            dealer_check = hunter.analyze(df_chart)
            news_check = verifier.check_divergence(df_chart)
            grid_data = smart_grid.calculate(df_chart)
            liq_report = liq_guard.check(df_chart)
            chip_data = chip_analyst.analyze(df_chart)
            # 🔥 6. 生命周期检测
            cycle_data = compass.detect_phase(df_chart)
            
            my_pos = real_portfolio.get_specific_position(stock_code)

            if not df_chart.empty:
                fig = plotter.plot_kline(df_chart, title=stock_label)
                # 绘图辅助线
                if chip_data: fig.add_hline(y=chip_data['peak_price'], line_dash="solid", line_color="gold", annotation_text=f"主力筹码:{chip_data['peak_price']}")
                if grid_data: fig.add_hline(y=grid_data['stop_loss'], line_dash="dot", line_color="purple", annotation_text=f"防扫止损:{grid_data['stop_loss']}")
                st.plotly_chart(fig, use_container_width=True)
            else: st.error("K线缺失")

        app = build_cognitive_graph()
        with st.status("🧠 六维全息评分引擎启动...", expanded=True) as status:
            try:
                # ... 上下文构建 ...
                morning_guidance = "无早盘指导"
                try: all_knowledge = kb.get_all_knowledge()
                except: all_knowledge = []
                k_context = "知识库为空" if not all_knowledge else str(len(all_knowledge)) + "条战法"
                
                hunter_context = f"庄家风险:{dealer_check['risk_level']}"
                news_context = f"消息背离:{news_check['status']}"
                pos_context = "无持仓" if not my_pos else f"持仓成本{my_pos['cost']}"
                grid_context = "" if not grid_data else f"ATR:{grid_data['atr']}"
                liq_context = f"流动性:{liq_report['status']}"
                chip_context = "筹码不明" if not chip_data else f"筹码状态:{chip_data['status']}"
                macro_context = f"市场环境:{weather_report['weather']}"
                
                # 🔥 注入生命周期情报
                cycle_context = f"生命周期:{cycle_data['phase']}, 描述:{cycle_data['desc']}"
                if cycle_data['score_impact'] == -100:
                    cycle_context += " !!!警告:处于主跌浪(冬天), 必须空仓!!!"

                final_prompt = f"{morning_guidance}|{hunter_context}|{news_context}|{pos_context}|{grid_context}|{liq_context}|{chip_context}|{macro_context}|{cycle_context}"
                
                res = app.invoke({
                    "stock_code": stock_code, 
                    "messages": [],
                    "morning_strategy": final_prompt,
                    "knowledge_context": k_context
                })
                status.update(label="评分完成", state="complete")
                
                sig = res['trading_signal']
                tactics = sig.get('details', {})
                act = sig.get('action', 'HOLD')
                m_data = res.get('market_data', {})
                scores = tactics.get('scores', {})
                
                # --- 渲染界面 ---
                st.divider()
                
                # 🔥🔥🔥 新增：生命周期状态栏 🔥🔥🔥
                st.markdown(f"""
                <div style="background-color:rgba(0,0,0,0.03); padding:15px; border-radius:10px; margin-bottom: 20px; text-align: center;">
                    <h2 style="margin:0;">{cycle_data['icon']} {cycle_data['phase']}</h2>
                    <p style="color:gray; margin-top:5px;">{cycle_data['desc']}</p>
                </div>
                """, unsafe_allow_html=True)
                # ------------------------------------

                # 流动性、庄家、消息预警
                l1, l2, l3 = st.columns([1, 1, 3])
                with l1: st.metric("💧 日均成交额", liq_report['value_str'])
                with l2: 
                    if liq_report['is_zombie']: st.error("⛔ 僵尸股")
                    else: st.info(f"✅ {liq_report['status']}")
                
                if dealer_check['risk_score'] > 0: st.error(f"⚠️ 庄家风险: {dealer_check['risk_level']}")
                if news_check['divergence_score'] != 0: st.info(f"📰 消息面: {news_check['status']}")

                st.divider()
                title_name = m_data.get('stock_name') or display_name(stock_code, with_code=True)
                st.title(title_name)

                st.subheader("📊 六维全息体检报告")
                
                # 综合算分
                final_total_score = scores.get('total', 50) + news_check['divergence_score']
                if chip_data: final_total_score += chip_data['score_impact']
                # 🔥 周期修正
                final_total_score += cycle_data['score_impact']
                
                # 僵尸股否决
                if liq_report['is_zombie']: final_total_score = min(30, final_total_score)
                # 主跌浪否决
                if cycle_data['score_impact'] == -100: 
                    final_total_score = 0
                    st.toast("⛔ 处于主跌浪严冬，AI 拒绝评分", icon="❄️")
                
                final_total_score = max(0, min(100, final_total_score))
                
                st.progress(final_total_score)
                st.caption(f"综合得分: {final_total_score}")

                st.divider()

                # 交易按钮区 (保持不变)
                mc1, mc2 = st.columns([1, 3])
                with mc1:
                    color = "red" if act == "BUY" and final_total_score > 60 else "green" if act == "SELL" else "gray"
                    st.markdown(f"<div style='text-align:center; border:4px solid {color}; padding:15px; border-radius:15px'><h1 style='color:{color}; margin:0'>{act}</h1></div>", unsafe_allow_html=True)
                    # 按钮代码省略...

                with mc2:
                    st.info(f"📢 **指挥官批示**: {tactics.get('core_view')}")
                    
                st.divider()
                # 筹码 & 网格
                if chip_data:
                    cc1, cc2 = st.columns(2)
                    with cc1: st.metric("🏔️ 主力筹码峰", f"¥{chip_data['peak_price']}")
                    with cc2: st.metric("🏆 获利盘", f"{chip_data['winner_ratio']}%")
                
                if grid_data:
                    st.caption(f"🛡️ 智能止损位: ¥{grid_data['stop_loss']} (ATR: {grid_data['atr']})")

            except Exception as e:
                st.error(f"分析出错: {e}")
