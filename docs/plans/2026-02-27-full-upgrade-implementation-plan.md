# 全面升级与回测跑通 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一键可重跑的“系统升级 + 回测验证”管线，并在本地跑通。

**Architecture:** 新增两个核心模块：`backtest_smoke` 负责轻量回测验证，`upgrade_pipeline` 负责编排学习刷新/实验跟踪/训练/回测并统一落盘；再用 CLI 脚本执行重试与结果汇总。

**Tech Stack:** Python 3.11, unittest, pandas, existing core modules (learning_engine_v2 / experiment_tracker_v1 / strategy_trainer)

---

### Task 1: 回测烟雾测试模块（TDD）

**Files:**
- Create: `tests/test_backtest_smoke.py`
- Create: `core/backtest_smoke.py`

**Step 1: Write the failing tests**
- 覆盖场景：
  - 有数据且至少一个组合成功时返回 `ok=true`。
  - 全部空数据时返回 `ok=false` 且失败原因为 `no_data`。

**Step 2: Run test to verify it fails**
Run: `python -m unittest tests.test_backtest_smoke -v`
Expected: `ModuleNotFoundError` 或断言失败。

**Step 3: Write minimal implementation**
- 新增 `run_backtest_smoke(...)`。
- 支持注入 scanner/backtester 以便测试。
- 输出 summary + rows，并支持写入 latest/history。

**Step 4: Run test to verify it passes**
Run: `python -m unittest tests.test_backtest_smoke -v`
Expected: PASS

### Task 2: 升级编排管线（TDD）

**Files:**
- Create: `tests/test_upgrade_pipeline.py`
- Create: `core/upgrade_pipeline.py`

**Step 1: Write the failing tests**
- 覆盖场景：
  - 依赖步骤全部成功时总体 `ok=true`。
  - 某步骤失败时总体 `ok=false`，并保留其他步骤结果。

**Step 2: Run test to verify it fails**
Run: `python -m unittest tests.test_upgrade_pipeline -v`
Expected: fail

**Step 3: Write minimal implementation**
- `run_upgrade_pipeline(...)`：
  - `refresh_learning_views`
  - `refresh_experiment_tracking`
  - `run_training`（可选/轻量）
  - `run_backtest_smoke`
- 生成 `data/upgrade_pipeline_latest.json` 与 history jsonl。

**Step 4: Run test to verify it passes**
Run: `python -m unittest tests.test_upgrade_pipeline -v`
Expected: PASS

### Task 3: 一键执行器与重试

**Files:**
- Create: `tools/full_upgrade_and_backtest.py`

**Step 1: Add CLI wrapper**
- 参数：`--max-attempts`、`--days`、`--skip-training`。
- 失败时重试，成功提前退出。

**Step 2: Dry run command**
Run: `python tools/full_upgrade_and_backtest.py --max-attempts 1 --skip-training`
Expected: 生成报告文件，命令退出码 0/1 与结果一致。

### Task 4: 全量验证

**Files:**
- Modify (if needed after failures): `core/backtest_smoke.py`, `core/upgrade_pipeline.py`, `tools/full_upgrade_and_backtest.py`

**Step 1: Run all tests**
Run: `python -m unittest discover -s tests -p "test_*.py"`
Expected: 全部通过。

**Step 2: Syntax check**
Run: `python -m py_compile core/backtest_smoke.py core/upgrade_pipeline.py tools/full_upgrade_and_backtest.py`
Expected: 无错误。

**Step 3: Real pipeline run**
Run: `python tools/full_upgrade_and_backtest.py --max-attempts 3`
Expected: 至少一次成功跑通并输出报告。

**Step 4: Capture outputs**
- 读取并汇报：
  - `data/upgrade_pipeline_latest.json`
  - `data/backtest_smoke_latest.json`
