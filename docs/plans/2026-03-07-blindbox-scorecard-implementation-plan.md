# Blindbox Scorecard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 blindbox 实验平台新增“主策略是否跑赢随机对照组”的综合评分结论，并在首页显示可解释的胜负与可信度。

**Architecture:** 在 `core/blindbox_report.py` 中新增 scorecard 评分器，基于主策略与随机对照组的累计收益、平均单笔收益、最大回撤、样本量生成比较分与结论；在 `ui/modules/blindbox.py` 中新增首页结论卡和贡献拆解区。

**Tech Stack:** Python 3.11, unittest, existing `blindbox_report.py`, `blindbox.py`, JSON state files

---

### Task 1: 报告层评分器

**Files:**
- Modify: `core/blindbox_report.py`
- Modify: `tests/test_blindbox_report.py`

**Step 1: Write the failing test**
- 增加：
  - 主策略收益领先时 `winner=primary`
  - 样本太少时 `confidence=样本不足`

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_report -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 新增：
  - `build_blindbox_scorecard(...)`
- 输出：
  - `primary_score`
  - `control_score`
  - `score_diff`
  - `winner`
  - `conclusion`
  - `confidence`
  - contribution breakdown

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_report -v`
Expected: PASS

### Task 2: 首页结论展示

**Files:**
- Modify: `ui/modules/blindbox.py`
- Test: `tests/test_blindbox_report.py`

**Step 1: Extend test inputs**
- 要求 blindbox 页依赖的快照与 scorecard 数据字段完整

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_report -v`
Expected: FAIL or missing fields

**Step 3: Write minimal implementation**
- 在 blindbox 页新增：
  - 当前结论
  - 主策略综合分
  - 对照组综合分
  - 分差
  - 可信度
- 再显示：
  - 收益贡献
  - 单笔收益贡献
  - 回撤贡献
  - 样本量贡献

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_report -v`
Expected: PASS

### Task 3: 全量回归与实跑

**Files:**
- Verify only

**Step 1: Run full suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: 全部通过

**Step 2: Run blindbox once**

Run: `python tools/blindbox_daily_runner.py --once`
Expected: 正常运行或正常 skip

**Step 3: Verify page still boots**

Run: `python -m streamlit run dashboard.py --server.headless true --server.port 8515`
Expected: HTTP 200
