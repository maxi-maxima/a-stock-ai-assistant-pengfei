# Blindbox Milestone 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 清理 blindbox 的未来日期脏数据，禁止未来日期再次写入，并新增 `10%止盈 / 10%止损 / 20天强平` 基准策略作为赛马主策略。

**Architecture:** 新增一个 blindbox 维护模块负责状态清理与未来日期保护；扩展 blindbox 策略与引擎以支持 `tp10_sl10_t20` 规则；保持现有随机策略作为对照组。所有展示层继续只做中文映射，不修改内部主键。

**Tech Stack:** Python 3.11, unittest, existing `blindbox_*` modules, JSON/JSONL state files, existing `PaperBroker`

---

> Note: 当前目录不是 git 仓库，因此计划里省略 commit 步骤，专注于 TDD 与验证命令。

### Task 1: 未来日期清理工具

**Files:**
- Create: `core/blindbox_maintenance.py`
- Create: `tests/test_blindbox_maintenance.py`

**Step 1: Write the failing test**

```python
def test_sanitize_future_state_removes_future_rows():
    payload = sanitize_future_state(...)
    assert payload["removed_reports"] == 2
    assert payload["removed_positions"] == 1
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_maintenance -v`
Expected: `ModuleNotFoundError`

**Step 3: Write minimal implementation**
- 读取 blindbox 状态文件
- 移除晚于参考交易日的记录
- 返回清理统计

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_maintenance -v`
Expected: PASS

### Task 2: Runner 禁止未来日期

**Files:**
- Modify: `tools/blindbox_daily_runner.py`
- Modify: `tests/test_blindbox_runner.py`

**Step 1: Write the failing test**

```python
def test_run_once_rejects_future_trade_date():
    row = run_once(target_dates=["2026-03-20"], latest={}, save=False, max_allowed_date="2026-03-07")
    assert row["ok"] is False
    assert row["reason"] == "future_trade_date"
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_runner -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 增加 `max_allowed_date`
- 超过时直接拒绝
- `--once` 默认使用最近交易日

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_runner -v`
Expected: PASS

### Task 3: 新增 10/10/20 主策略

**Files:**
- Modify: `core/blindbox_strategies.py`
- Modify: `core/blindbox_engine.py`
- Modify: `core/strategy_display.py`
- Modify: `tests/test_blindbox_strategies.py`
- Modify: `tests/test_blindbox_engine.py`

**Step 1: Write the failing test**

```python
def test_builtin_strategies_include_tp10_sl10_t20():
    ids = {row["strategy_id"] for row in list_builtin_strategies()}
    assert "tp10_sl10_t20" in ids

def test_due_position_hits_stop_loss_first_when_same_day_both_hit():
    result = run_blindbox_day(...)
    assert result["closed_count"] == 1
    assert updated["last_realized_pnl"] < 0
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_strategies tests.test_blindbox_engine -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 新增 `tp10_sl10_t20`
- 使用日线 OHLC 判断止盈/止损/强平
- 同日双命中时优先止损

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_strategies tests.test_blindbox_engine -v`
Expected: PASS

### Task 4: 启动前自动清理 blindbox 脏状态

**Files:**
- Modify: `tools/blindbox_daily_runner.py`
- Modify: `core/blindbox_report.py`
- Test: `tests/test_blindbox_maintenance.py`

**Step 1: Write the failing test**
- 要求：runner 在正式执行前先清理 future-dated 状态

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_maintenance tests.test_blindbox_runner -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- runner 启动前调用维护工具
- `blindbox_runner_latest.json` 不再保留未来日期

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_maintenance tests.test_blindbox_runner -v`
Expected: PASS

### Task 5: 回归与实跑验证

**Files:**
- Modify: `tests/test_ui_modules_compile.py`（如需纳入新文件）
- Verify only: `data/blindbox_*`

**Step 1: Run targeted tests**

Run:
- `python -m unittest tests.test_blindbox_maintenance tests.test_blindbox_runner tests.test_blindbox_engine tests.test_blindbox_strategies -v`

Expected: PASS

**Step 2: Run full suite**

Run:
- `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: 全部通过

**Step 3: Real run**

Run:
- `python tools/blindbox_daily_runner.py --once`

Expected:
- 不再写入未来日期
- 状态文件时间线不晚于最近交易日
- blindbox 页面可正常显示
