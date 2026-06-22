# Blindbox Paper Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一个 100% 可跑通的“盲盒测试机”最小闭环：每日自动选策略与股票、纸面买入、持有 2 个交易日后自动卖出、计算已实现盈亏、自动调低/调高策略权重，并持续写出日报与状态文件。

**Architecture:** 先不改现有多脑主链，新增一条隔离的 `blindbox` 子系统，独立完成 `选股源 -> 策略抽样 -> 下单 -> 到期平仓 -> realized pnl -> 策略调权 -> 次日继续`。实现尽量复用现有 `trade_simulator`、`event_bus`、`market calendar`、`daily bar` 数据能力，但避免依赖复杂 agent/LLM 路径，保证最小闭环稳定。

**Tech Stack:** Python 3.11, unittest, existing project modules (`skills.scanner`, `core.trade_simulator`, `core.metrics`, `core.upgrade_scheduler`), JSON/JSONL state files

---

### Task 1: 定义盲盒闭环的状态与协议

**Files:**
- Create: `core/blindbox_protocol.py`
- Create: `tests/test_blindbox_protocol.py`

**Step 1: Write the failing test**

```python
import unittest

from core.blindbox_protocol import (
    build_strategy_state,
    build_position_plan,
)


class BlindboxProtocolTest(unittest.TestCase):
    def test_build_strategy_state_has_required_fields(self):
        row = build_strategy_state("coin_flip_buy")
        self.assertEqual(row["strategy_id"], "coin_flip_buy")
        self.assertIn("weight", row)
        self.assertIn("closed_trades", row)
        self.assertIn("realized_pnl_sum", row)
        self.assertIn("status", row)

    def test_build_position_plan_has_hold_days_and_exit_date(self):
        row = build_position_plan(
            decision_id="d1",
            code="000001.SZ",
            strategy_id="coin_flip_buy",
            buy_date="2026-03-07",
            planned_exit_date="2026-03-11",
            hold_days=2,
        )
        self.assertEqual(row["decision_id"], "d1")
        self.assertEqual(row["hold_days"], 2)
        self.assertEqual(row["planned_exit_date"], "2026-03-11")
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_protocol -v`
Expected: `ModuleNotFoundError` or missing function failure

**Step 3: Write minimal implementation**

```python
def build_strategy_state(strategy_id, weight=1.0):
    return {
        "strategy_id": strategy_id,
        "weight": float(weight),
        "calls": 0,
        "buys": 0,
        "closed_trades": 0,
        "wins": 0,
        "realized_pnl_sum": 0.0,
        "avg_realized_pnl": 0.0,
        "last_realized_pnl": None,
        "status": "active",
    }


def build_position_plan(...):
    ...
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_protocol -v`
Expected: PASS

### Task 2: 实现盲盒策略池与加权抽样器

**Files:**
- Create: `core/blindbox_strategies.py`
- Create: `tests/test_blindbox_strategies.py`

**Step 1: Write the failing test**

```python
import unittest

from core.blindbox_strategies import (
    list_builtin_strategies,
    weighted_pick_strategy,
)


class BlindboxStrategiesTest(unittest.TestCase):
    def test_builtin_strategies_exist(self):
        rows = list_builtin_strategies()
        ids = {row["strategy_id"] for row in rows}
        self.assertIn("coin_flip_buy", ids)
        self.assertIn("prev_day_down_buy", ids)
        self.assertIn("above_ma5_buy", ids)

    def test_weighted_pick_skips_disabled_strategies(self):
        strategies = [
            {"strategy_id": "a", "weight": 1.0, "status": "disabled"},
            {"strategy_id": "b", "weight": 2.0, "status": "active"},
        ]
        picked = weighted_pick_strategy(strategies, rng_seed=7)
        self.assertEqual(picked["strategy_id"], "b")
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_strategies -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 内置 3-4 个纯规则策略，不用 LLM：
  - `coin_flip_buy`
  - `random_pick_hold_2d`
  - `prev_day_down_buy`
  - `above_ma5_buy`
- 只返回选股规则与持有天数，不直接负责交易
- 采样器只在 `status=active` 中按 `weight` 抽样

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_strategies -v`
Expected: PASS

### Task 3: 实现策略进化器（纯数值反馈）

**Files:**
- Create: `core/blindbox_evolution.py`
- Create: `tests/test_blindbox_evolution.py`

**Step 1: Write the failing test**

```python
import unittest

from core.blindbox_evolution import apply_realized_reward


class BlindboxEvolutionTest(unittest.TestCase):
    def test_negative_reward_reduces_weight(self):
        state = {
            "strategy_id": "coin_flip_buy",
            "weight": 1.0,
            "closed_trades": 0,
            "wins": 0,
            "realized_pnl_sum": 0.0,
            "avg_realized_pnl": 0.0,
            "status": "active",
        }
        updated = apply_realized_reward(state, pnl_pct=-0.03)
        self.assertLess(updated["weight"], 1.0)
        self.assertEqual(updated["closed_trades"], 1)

    def test_positive_reward_increases_weight(self):
        state = {
            "strategy_id": "coin_flip_buy",
            "weight": 1.0,
            "closed_trades": 0,
            "wins": 0,
            "realized_pnl_sum": 0.0,
            "avg_realized_pnl": 0.0,
            "status": "active",
        }
        updated = apply_realized_reward(state, pnl_pct=0.05)
        self.assertGreater(updated["weight"], 1.0)
        self.assertEqual(updated["wins"], 1)
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_evolution -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 用 realized pnl 做乘法或线性调权
- 只更新：
  - `weight`
  - `closed_trades`
  - `wins`
  - `realized_pnl_sum`
  - `avg_realized_pnl`
  - `last_realized_pnl`
- 先不让 LLM 改代码或生成新策略

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_evolution -v`
Expected: PASS

### Task 4: 实现股票源与交易日驱动器

**Files:**
- Create: `core/blindbox_datafeed.py`
- Create: `tests/test_blindbox_datafeed.py`

**Step 1: Write the failing test**

```python
import unittest

from core.blindbox_datafeed import (
    resolve_universe,
    calc_planned_exit_date,
)


class BlindboxDatafeedTest(unittest.TestCase):
    def test_calc_planned_exit_date_skips_non_trading_days(self):
        calendar = ["2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12"]
        out = calc_planned_exit_date("2026-03-10", hold_days=2, trading_days=calendar)
        self.assertEqual(out, "2026-03-12")

    def test_resolve_universe_prefers_watchlist_then_fallback(self):
        out = resolve_universe(watchlist=["000001.SZ"], fallback=["000002.SZ"])
        self.assertEqual(out, ["000001.SZ"])
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_datafeed -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 股票源优先级：
  1. `data/watchlist.json`
  2. 配置里的 fallback symbols
- 交易日只用现有日历/数据能力，不引入实时行情
- 第一版统一按**收盘价**做 paper 买入和 paper 卖出，避免 intraday 依赖

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_datafeed -v`
Expected: PASS

### Task 5: 实现最小盲盒执行引擎

**Files:**
- Create: `core/blindbox_engine.py`
- Create: `tests/test_blindbox_engine.py`

**Step 1: Write the failing test**

```python
import unittest

from core.blindbox_engine import run_blindbox_day


class BlindboxEngineTest(unittest.TestCase):
    def test_run_day_can_open_position(self):
        result = run_blindbox_day(
            trade_date="2026-03-10",
            universe=["000001.SZ"],
            scanner=FakeScanner(...),
            simulator=FakeSimulator(...),
            state_store=FakeStateStore(...),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["opened_count"], 1)

    def test_run_day_can_close_due_position_and_apply_reward(self):
        result = run_blindbox_day(
            trade_date="2026-03-12",
            universe=["000001.SZ"],
            scanner=FakeScanner(...),
            simulator=FakeSimulator(...),
            state_store=FakeStateStore(with_due_position=True),
        )
        self.assertEqual(result["closed_count"], 1)
        self.assertEqual(result["reward_updates"], 1)
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_engine -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 每日顺序固定：
  1. 先卖出今天到期的纸面仓位
  2. 结算 realized pnl
  3. 把 pnl 回写到策略权重
  4. 再抽样一个策略 + 一个股票开新仓
- 新增状态文件：
  - `data/blindbox_strategy_state.json`
  - `data/blindbox_positions.json`
  - `data/blindbox_daily_report.jsonl`
- 优先复用 `core.trade_simulator.TradeSimulator`

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_engine -v`
Expected: PASS

### Task 6: 接入现有项目数据与模拟交易器

**Files:**
- Modify: `core/trade_simulator.py`
- Modify: `core/portfolio.py`
- Test: `tests/test_blindbox_engine.py`

**Step 1: Write the failing integration test**
- 覆盖 blindbox 调用现有 paper broker 时：
  - BUY 写入 `trades.jsonl`
  - SELL 写入 `trades.jsonl`
  - `decision_id` / `origin_decision_id` 保持可追溯

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_engine -v`
Expected: FAIL on missing trade linkage

**Step 3: Write minimal implementation**
- 只加 blindbox 所需的最小兼容层
- 不重构现有复杂交易逻辑
- 确保 blindbox 的 BUY/SELL 都能形成 realized outcome 所需字段

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_engine -v`
Expected: PASS

### Task 7: 实现调度器与补跑机制

**Files:**
- Create: `tools/blindbox_daily_runner.py`
- Create: `tests/test_blindbox_runner.py`

**Step 1: Write the failing test**

```python
import unittest

from tools.blindbox_daily_runner import run_once


class BlindboxRunnerTest(unittest.TestCase):
    def test_run_once_skips_when_same_trade_day_already_done(self):
        row = run_once(..., already_done=True)
        self.assertTrue(row["skipped"])

    def test_run_once_backfills_missed_trade_days(self):
        row = run_once(..., missed_days=["2026-03-10", "2026-03-11"])
        self.assertEqual(row["processed_days"], 2)
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_runner -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 支持：
  - `--once`
  - `--date`
  - 自动判断最近已处理交易日
  - 补跑缺失交易日
- 第一版只写本地脚本，云端部署后复用同一入口

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_runner -v`
Expected: PASS

### Task 8: 输出最小日报与体检页

**Files:**
- Create: `core/blindbox_report.py`
- Modify: `ui/modules/system_check.py`
- Modify: `dashboard.py`
- Create: `tests/test_blindbox_report.py`

**Step 1: Write the failing test**
- 报表至少包含：
  - 今日买入数
  - 今日卖出数
  - 已实现 pnl
  - 当前策略权重排名
  - 最近失败策略

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blindbox_report -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 新增日报汇总函数
- 在 `System Check` 中增加 blindbox 健康摘要
- 不做复杂新页面，先把系统体检里看得见

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blindbox_report -v`
Expected: PASS

### Task 9: 全量验证与云端前准备

**Files:**
- Modify: `docs/plans/2026-03-07-blindbox-paper-loop.md`（必要时补充真实命令）
- Modify: `README.md`

**Step 1: Run all tests**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: 全部通过

**Step 2: Run doctor**

Run: `python doctor.py`
Expected: 通过，且 blindbox 新文件存在

**Step 3: Run blindbox locally**

Run: `python tools/blindbox_daily_runner.py --once`
Expected: 生成：
- `data/blindbox_strategy_state.json`
- `data/blindbox_positions.json`
- `data/blindbox_daily_report.jsonl`

**Step 4: Verify closed-loop artifacts**

Run:
- `python -c "import json;print(json.load(open('data/blindbox_strategy_state.json','r',encoding='utf-8')))"`
- `python -c "print(open('data/blindbox_daily_report.jsonl','r',encoding='utf-8').read().splitlines()[-1])"`

Expected:
- 至少 1 个策略 state
- 日报存在 `opened_count` / `closed_count` / `realized_pnl`

**Step 5: Update README**
- 记录本地运行方式
- 记录之后上云的唯一入口命令：
  - `python tools/blindbox_daily_runner.py --once`
