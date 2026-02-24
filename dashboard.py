import streamlit as st
import os
import sys

from core.bootstrap import init_runtime

init_runtime()

st.set_page_config(page_title="AI 交易分身", page_icon="🧠", layout="wide")
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path: sys.path.append(current_dir)

from skills.scanner import MarketScanner
from skills.style_learner import StyleLearner
from core.portfolio import VirtualPortfolio
from core.memory import MemoryManager
from core.knowledge_base import KnowledgeBase
from skills.chart_plotter import ChartPlotter
from skills.backtester import Backtester
from ui.modules import tactics, radar, backtest, style, history, rules, library, workshop, patrol, broker_recommend, financial, behavior, hedge, system_check, replay, luck, metrics, watchlist, agents, llm_keys

if 'scanner' not in st.session_state: st.session_state.scanner = MarketScanner("tushare")
if 'real_portfolio' not in st.session_state: st.session_state.real_portfolio = VirtualPortfolio("data/real_portfolio.json")
if 'paper_portfolio' not in st.session_state: st.session_state.paper_portfolio = VirtualPortfolio("data/paper_portfolio.json")
if 'plotter' not in st.session_state: st.session_state.plotter = ChartPlotter()
if 'memory' not in st.session_state: st.session_state.memory = MemoryManager()
if 'kb' not in st.session_state: st.session_state.kb = KnowledgeBase()
if 'learner' not in st.session_state: st.session_state.learner = StyleLearner()
if 'backtester' not in st.session_state: st.session_state.backtester = Backtester()

if 'current_page' not in st.session_state: st.session_state.current_page = "🧘 战术指挥室"

with st.sidebar:
    st.title("🧠 AI 交易分身")
    NAV_OPTIONS = ['🧘 战术指挥室', '👮 AI 巡逻官', '📈 系统KPI', '📊 财务透视', '🏆 券商金股', '🔭 猎手雷达', '👀 观察池', '🛠️ 技能工坊', '⏳ 时光回测', '🔁 决策回放', '🎲 纯运气', '📚 知识库', '🧬 风格实验室', '🧭 行为画像', '🛡️ 对冲模块', '📜 历史军情', '🔑 三脑API Key', '⚖️ 家规与系统', 'Agents', 'System Check']
    st.session_state.current_page = st.radio("系统导航", NAV_OPTIONS, index=0)
    st.divider()
    if st.button("🔄 刷新系统"): st.rerun()

page = st.session_state.current_page
if "战术指挥室" in page:
    tactics.render(st.session_state.scanner, st.session_state.real_portfolio, st.session_state.paper_portfolio, st.session_state.plotter, st.session_state.memory, st.session_state.kb, st.session_state.learner)
elif "AI 巡逻官" in page: patrol.render(st.session_state.scanner, st.session_state.real_portfolio)
elif "系统KPI" in page: metrics.render()
elif "财务透视" in page: financial.render()
elif "券商金股" in page: broker_recommend.render()
elif "猎手雷达" in page: radar.render(st.session_state.scanner, st.session_state.plotter)
elif "观察池" in page: watchlist.render()
elif "技能工坊" in page: workshop.render()
elif "时光回测" in page: backtest.render(st.session_state.backtester)
elif "决策回放" in page: replay.render()
elif "纯运气" in page: luck.render()
elif "知识库" in page: library.render(st.session_state.kb)
elif "风格实验室" in page: style.render(st.session_state.learner, st.session_state.memory)
elif "行为画像" in page: behavior.render()
elif "对冲模块" in page: hedge.render(st.session_state.scanner, st.session_state.real_portfolio)
elif "历史军情" in page: history.render(st.session_state.memory)
elif "三脑API Key" in page: llm_keys.render()
elif "Agents" in page: agents.render()
elif "System Check" in page: system_check.render(st.session_state.scanner, st.session_state.real_portfolio, st.session_state.memory, st.session_state.kb)
elif "家规与系统" in page: rules.render(st.session_state.memory, st.session_state.scanner)
