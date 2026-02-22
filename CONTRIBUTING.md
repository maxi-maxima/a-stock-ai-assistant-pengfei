# 贡献指南 / Contributing Guide

感谢您对 AI 交易分身项目的关注！我们欢迎各种形式的贡献。

## 如何贡献

### 报告问题 (Bug Reports)

如果您发现了问题，请通过 [GitHub Issues](https://github.com/yourusername/ai-trading-avatar/issues) 提交，并包含以下信息：

- 问题的详细描述
- 复现步骤
- 期望行为 vs 实际行为
- 系统环境（Python版本、操作系统等）
- 相关日志或截图

### 功能建议 (Feature Requests)

我们欢迎新功能的建议！请描述：

- 功能的具体用途
- 为什么这个功能对项目有价值
- 可能的技术实现思路（可选）

### 提交代码 (Pull Requests)

1. **Fork** 本仓库
2. **创建分支**: `git checkout -b feature/your-feature-name`
3. **提交更改**: `git commit -m 'Add some feature'`
4. **推送分支**: `git push origin feature/your-feature-name`
5. **创建 PR**: 在 GitHub 上提交 Pull Request

#### 代码规范

- 遵循 PEP 8 Python 代码规范
- 添加适当的注释和文档字符串
- 确保代码通过基础测试
- 更新相关的 README 文档

### 文档改进

文档改进也是非常宝贵的贡献！包括：

- 修正拼写错误
- 改进文档清晰度
- 添加使用示例
- 翻译（目前主要支持中文和英文）

## 开发环境设置

```bash
# 克隆您的 Fork
git clone https://github.com/your-username/ai-trading-avatar.git
cd ai-trading-avatar

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装开发依赖
pip install -r requirements.txt

# 启动开发服务器
streamlit run dashboard.py
```

## 代码审查流程

- 所有 PR 都需要至少一个审查者的批准
- 确保 CI 检查通过（如果有设置）
- 保持与主分支的同步
- 积极回应审查者的反馈

## 行为准则

- 保持尊重和专业的态度
- 欢迎新手，耐心解答问题
- 专注于建设性讨论
- 尊重不同的观点和经验

## 问题联系

如有任何问题，欢迎通过以下方式联系：

- GitHub Issues: [提交问题](https://github.com/yourusername/ai-trading-avatar/issues)
- 项目邮箱: your.email@example.com

再次感谢您的贡献！
