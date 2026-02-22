# Git 提交指南

由于当前环境未安装 Git，请按以下步骤完成代码上传：

## 方法 1: 使用 GitHub Desktop (推荐新手)

1. 下载安装 [GitHub Desktop](https://desktop.github.com/)
2. 登录你的 GitHub 账号
3. 选择 "Add existing repository"
4. 选择本文件夹 (`C:\Users\1\Desktop\KIMIstock\股票分身`)
5. 点击 "Publish repository"
6. 设置仓库名称为 `ai-trading-avatar`
7. 取消勾选 "Keep this code private" (如果要开源)
8. 点击 "Publish repository"

## 方法 2: 使用命令行

### 1. 安装 Git
下载地址: https://git-scm.com/download/win

### 2. 初始化并提交

在项目目录打开 Git Bash 或 PowerShell：

```bash
# 进入项目目录
cd "C:\Users\1\Desktop\KIMIstock\股票分身"

# 初始化 Git 仓库
git init

# 添加所有文件
git add .

# 提交
git commit -m "Initial commit: AI Trading Avatar v1.0

- 三脑决策架构 (TriBrain Council)
- 认知图谱系统 (Cognitive Graph)
- 战术指挥室、AI巡逻官、猎手雷达
- 知识库、风格学习、回测系统
- 完整文档和开源许可证"

# 连接 GitHub (替换 yourusername)
git remote add origin https://github.com/yourusername/ai-trading-avatar.git

# 推送
git branch -M main
git push -u origin main
```

## 方法 3: 手动上传 (最简单)

1. 在 GitHub 上创建新仓库：https://github.com/new
2. 仓库名: `ai-trading-avatar`
3. 选择 "Public" (公开)
4. 不要勾选初始化 README (我们已有 README)
5. 创建后，点击 "uploading an existing file"
6. 拖拽本文件夹中的所有文件到网页
7. 提交信息写: "Initial commit"
8. 点击 "Commit changes"

## 提交前检查清单

确保以下文件已准备好：

- [ ] `README.md` - 项目介绍
- [ ] `LICENSE` - MIT 许可证
- [ ] `DISCLAIMER.md` - 免责声明
- [ ] `CONTRIBUTING.md` - 贡献指南
- [ ] `.gitignore` - 忽略配置
- [ ] 所有 API 密钥已清空
- [ ] 临时文件已删除

## 首次提交后的建议

1. **创建 Release**: 在 GitHub 上创建 v1.0 标签
2. **添加 Topics**: 添加标签如 `ai`, `trading`, `a-stock`, `langchain`, `streamlit`
3. **启用 Discussions**: 开启讨论区方便交流
4. **设置 Social Preview**: 上传项目封面图

## 需要帮助？

如有问题，请参考：
- [GitHub 官方文档](https://docs.github.com/)
- [Git 教程](https://www.liaoxuefeng.com/wiki/896043488029600)
