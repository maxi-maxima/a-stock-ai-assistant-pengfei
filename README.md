# 🧠 AI 交易分身 (AI Trading Avatar)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.28+-red.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 最新版本：v1.1.0

本次升级同步了 `C:\Users\1\Desktop\KIMIstock\gemini` 中的最新项目版本，并清理掉不应发布的本地密钥、缓存、日志和运行态数据。

重点更新：
- 新增 Blindbox 实验引擎、日报维护流程、调度器和 UI 模块。
- 新增完整升级/回测流水线、升级调度器和命令行运行工具。
- 新增 AutoGen/AG2、Composio、browser-use、Letta、Agent Lightning 能力适配与注册。
- 增强循环健康度、执行覆盖率、策略展示和日常维护报告。
- 新增测试套件，并移除旧的本地授权/机器码门控脚本。

验证命令：

```bash
python -m unittest discover -s tests -v
python -m compileall -q core modules skills ui tests tools dashboard.py doctor.py
```

Quick health report for issues and automation:

```bash
python doctor.py --json
python doctor.py --markdown
```

The JSON output supports automation. The Markdown output summarizes missing dependencies, missing core files, data-file warnings, and module-load failures in a GitHub issue-ready format.

> ⚠️ **免责声明**: 本系统仅供**教育和研究**目的，**不构成投资建议**。使用本系统进行交易的风险由用户自行承担。

---

## 🎯 项目简介

**AI 交易分身** 是一个面向A股市场的智能交易辅助系统，采用创新的**三脑决策架构**（策略脑 + 战术脑 + 法官脑），结合认知图谱和多智能体协作，为个人投资者提供数据驱动的决策支持。

### 核心特色

- 🧠 **三脑决策架构**: 策略脑(DeepSeek) + 战术脑(Qwen) + 法官脑(Kimi) 协同决策
- 🎯 **战术指挥室**: 交互式交易决策界面，支持多维度分析
- 👮 **AI 巡逻官**: 自动监控持仓和市场异常，及时预警
- 📚 **知识库系统**: 基于向量存储的投资知识和经验积累
- 🧬 **风格学习**: 自适应学习用户交易风格，个性化建议
- ⏳ **时光回测**: 策略历史回测验证
- 🔭 **猎手雷达**: 市场扫描和机会发现

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Windows/Linux/macOS
- API密钥（DeepSeek/Qwen/Kimi/Tushare）

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/maxi-maxima/a-stock-ai-assistant-pengfei.git
cd a-stock-ai-assistant-pengfei

# 2. 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 API 密钥
cp .env.example .env
# 编辑 .env 填入你的 API 密钥

# 5. 启动系统
streamlit run dashboard.py
```

### 配置说明

在 `.env` 文件中配置以下 API 密钥：

```env
# 三脑 API 密钥
BLUE_BRAIN_API_KEY=your_deepseek_key
RED_BRAIN_API_KEY=your_qwen_key
GREEN_BRAIN_API_KEY=your_kimi_key

# 数据源
TUSHARE_TOKEN=your_tushare_token
```

---

## 📁 项目结构

```
a-stock-ai-assistant-pengfei/
├── core/                   # 核心框架
│   ├── tri_brain.py       # 三脑决策核心
│   ├── cognitive_graph.py # 认知图谱(LangGraph)
│   ├── knowledge_base.py  # 知识库系统
│   └── memory.py          # 记忆管理
├── skills/                 # 技能模块
│   ├── scanner.py         # 市场扫描
│   ├── chip_analyst.py    # 筹码分析
│   ├── sentiment_engine.py # 情绪分析
│   └── backtester.py      # 回测系统
├── ui/                     # 用户界面
│   └── modules/           # 各功能模块
├── config/                 # 配置文件
├── data/                   # 数据存储
└── dashboard.py           # 主入口
```

---

## 🎮 功能模块

### 1. 战术指挥室 🧘
核心交易决策界面，集成：
- 多维度技术分析
- 基本面数据透视
- 新闻情绪分析
- 智能买卖点推荐
- 仓位管理建议

### 2. AI 巡逻官 👮
自动监控功能：
- 持仓股票实时监控
- 市场异常波动预警
- 止损止盈提醒
- 盘前策略生成

### 3. 猎手雷达 🔭
市场机会发现：
- 多维度股票筛选
- 技术指标扫描
- 资金流向分析
- 热点板块追踪

### 4. 知识库 📚
投资知识管理：
- 向量化的投资笔记
- 历史案例分析
- 策略文档存储
- 智能问答支持

### 5. 时光回测 ⏳
策略验证工具：
- 历史数据回测
- 多策略对比
- 收益曲线分析
- 风险指标计算

---

## ⚠️ 风险提示

**使用本项目前，请务必阅读 [DISCLAIMER.md](DISCLAIMER.md)**

1. **非投资建议**: 本系统提供的所有分析和建议仅供学习研究，不构成任何投资建议
2. **风险自担**: 用户使用本系统进行交易的风险和损失由用户自行承担
3. **无收益承诺**: 不保证任何投资收益，过往表现不代表未来结果
4. **合规要求**: 请遵守所在地区的证券法律法规

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。

这意味着你可以：
- ✅ 商业使用
- ✅ 修改源码
- ✅ 分发副本
- ✅ 私人使用

但必须：
- ⚠️ 保留版权声明
- ⚠️ 包含许可证副本

---

## 🙏 致谢

- [LangChain](https://github.com/hwchase17/langchain) - AI 应用框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - 智能体工作流
- [Streamlit](https://streamlit.io/) - UI 框架
- [Tushare](https://tushare.pro/) - A股数据源
- [DeepSeek](https://deepseek.com/) / [Qwen](https://tongyi.aliyun.com/) / [Kimi](https://kimi.moonshot.cn/) - 大语言模型支持

---

## 📞 联系方式

- 项目主页: https://github.com/maxi-maxima/a-stock-ai-assistant-pengfei
- 问题反馈: [GitHub Issues](https://github.com/maxi-maxima/a-stock-ai-assistant-pengfei/issues)

---

**Made with ❤️ for A股投资者**
