import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.blindbox_engine import JsonBlindboxStateStore, run_blindbox_day


class FakeScanner:
    def __init__(self, history_map):
        self.history_map = history_map

    def get_history(self, code, days=120):
        return self.history_map[code]


class FakeSimulator:
    def __init__(self):
        self.buys = []
        self.sells = []

    def buy(self, code, price, target_cash, reason="", decision_id=None, signal_source=None, **kwargs):
        self.buys.append(
            {
                "code": code,
                "price": price,
                "target_cash": target_cash,
                "reason": reason,
                "decision_id": decision_id,
                "signal_source": signal_source or {},
            }
        )
        return True, "ok"

    def sell(self, code, price, shares=None, reason="", decision_id=None, signal_source=None, **kwargs):
        self.sells.append(
            {
                "code": code,
                "price": price,
                "shares": shares,
                "reason": reason,
                "decision_id": decision_id,
                "signal_source": signal_source or {},
            }
        )
        return True, "ok"


class MemoryStateStore(JsonBlindboxStateStore):
    def __init__(self, data=None):
        self.data = data or {}

    def load(self):
        return self.data or {}

    def save(self, payload):
        self.data = payload
        return payload


class BlindboxEngineTest(unittest.TestCase):
    def test_tp10_sl10_t20_creates_pending_entry_on_signal_day(self):
        scanner = FakeScanner(
            {
                "000001.SZ": [
                    {"date": "2026-03-07", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1},
                    {"date": "2026-03-10", "open": 10.3, "high": 10.5, "low": 10.0, "close": 10.4},
                ]
            }
        )
        simulator = FakeSimulator()
        store = MemoryStateStore()

        with tempfile.TemporaryDirectory() as td:
            report_path = str(Path(td) / "blindbox_daily_report.jsonl")
            result = run_blindbox_day(
                trade_date="2026-03-07",
                universe=["000001.SZ"],
                scanner=scanner,
                simulator=simulator,
                state_store=store,
                strategy_rows=[
                    {"strategy_id": "coin_flip_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "random_pick_hold_2d", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "prev_day_down_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "above_ma5_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "tp10_sl10_t20", "weight": 2.0, "status": "active", "tp_pct": 0.1, "sl_pct": 0.1, "hold_days": 20, "entry_mode": "next_open"},
                ],
                rng_seed=7,
                apply=True,
                report_path=report_path,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["opened_count"], 0)
        self.assertEqual(len(simulator.buys), 0)
        positions = store.load().get("positions", [])
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["status"], "pending_entry")
        self.assertEqual(positions[0]["signal_date"], "2026-03-07")
        self.assertEqual(positions[0]["planned_buy_date"], "2026-03-10")

    def test_pending_entry_executes_on_next_trade_day_open(self):
        scanner = FakeScanner(
            {
                "000001.SZ": [
                    {"date": "2026-03-07", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1},
                    {"date": "2026-03-10", "open": 10.3, "high": 10.5, "low": 10.0, "close": 10.4},
                ]
            }
        )
        simulator = FakeSimulator()
        store = MemoryStateStore(
            {
                "strategies": [
                    {
                        "strategy_id": "tp10_sl10_t20",
                        "weight": 2.0,
                        "hold_days": 20,
                        "entry_mode": "next_open",
                        "tp_pct": 0.1,
                        "sl_pct": 0.1,
                        "status": "active",
                    }
                ],
                "positions": [
                    {
                        "decision_id": "blindbox_20260307_x1",
                        "code": "000001.SZ",
                        "strategy_id": "tp10_sl10_t20",
                        "signal_date": "2026-03-07",
                        "planned_buy_date": "2026-03-10",
                        "buy_date": "",
                        "planned_exit_date": "2026-04-07",
                        "hold_days": 20,
                        "buy_price": None,
                        "shares": None,
                        "status": "pending_entry",
                    }
                ],
            }
        )

        with tempfile.TemporaryDirectory() as td:
            report_path = str(Path(td) / "blindbox_daily_report.jsonl")
            result = run_blindbox_day(
                trade_date="2026-03-10",
                universe=["000001.SZ"],
                scanner=scanner,
                simulator=simulator,
                state_store=store,
                strategy_rows=[
                    {"strategy_id": "coin_flip_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "random_pick_hold_2d", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "prev_day_down_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "above_ma5_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "tp10_sl10_t20", "weight": 2.0, "status": "active", "tp_pct": 0.1, "sl_pct": 0.1, "hold_days": 20, "entry_mode": "next_open"},
                ],
                rng_seed=7,
                apply=True,
                report_path=report_path,
                allow_new_positions=False,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["opened_count"], 1)
        self.assertEqual(len(simulator.buys), 1)
        self.assertAlmostEqual(float(simulator.buys[0]["price"]), 10.3, places=6)
        positions = store.load().get("positions", [])
        self.assertEqual(positions[0]["status"], "open")
        self.assertEqual(positions[0]["buy_date"], "2026-03-10")
        self.assertAlmostEqual(float(positions[0]["buy_price"]), 10.3, places=6)

    def test_tp10_sl10_t20_stop_loss_wins_if_same_day_both_hit(self):
        scanner = FakeScanner(
            {
                "000001.SZ": [
                    {"date": "2026-03-10", "open": 100.0, "high": 112.0, "low": 89.0, "close": 105.0},
                ]
            }
        )
        simulator = FakeSimulator()
        store = MemoryStateStore(
            {
                "strategies": [
                    {
                        "strategy_id": "tp10_sl10_t20",
                        "weight": 1.0,
                        "closed_trades": 0,
                        "wins": 0,
                        "realized_pnl_sum": 0.0,
                        "avg_realized_pnl": 0.0,
                        "status": "active",
                        "tp_pct": 0.1,
                        "sl_pct": 0.1,
                        "hold_days": 20,
                    }
                ],
                "positions": [
                    {
                        "decision_id": "d1",
                        "code": "000001.SZ",
                        "strategy_id": "tp10_sl10_t20",
                        "buy_date": "2026-03-03",
                        "planned_exit_date": "2026-03-31",
                        "hold_days": 20,
                        "buy_price": 100.0,
                        "shares": 100,
                        "status": "open",
                    }
                ],
            }
        )

        with tempfile.TemporaryDirectory() as td:
            report_path = str(Path(td) / "blindbox_daily_report.jsonl")
            result = run_blindbox_day(
                trade_date="2026-03-10",
                universe=["000001.SZ"],
                scanner=scanner,
                simulator=simulator,
                state_store=store,
                strategy_rows=[{"strategy_id": "tp10_sl10_t20", "weight": 1.0, "status": "active", "tp_pct": 0.1, "sl_pct": 0.1, "hold_days": 20}],
                rng_seed=3,
                apply=True,
                allow_new_positions=False,
                report_path=report_path,
            )
        self.assertEqual(result["closed_count"], 1)
        self.assertEqual(len(simulator.sells), 1)
        self.assertAlmostEqual(float(simulator.sells[0]["price"]), 90.0, places=6)

    def test_run_day_builds_isolated_paper_broker_by_default(self):
        scanner = FakeScanner({})
        store = MemoryStateStore()

        with patch("core.trade_simulator.PaperBroker") as paper_broker_cls:
            broker = paper_broker_cls.return_value
            broker.buy.return_value = (False, "skip")
            broker.sell.return_value = (False, "skip")

            run_blindbox_day(
                trade_date="2026-03-10",
                universe=[],
                scanner=scanner,
                simulator=None,
                state_store=store,
                apply=False,
                allow_new_positions=False,
            )

            _, kwargs = paper_broker_cls.call_args
            self.assertEqual(kwargs["portfolio_path"], "data/blindbox_paper_portfolio.json")
            self.assertEqual(kwargs["trade_log_path"], "data/blindbox_trades.jsonl")
            self.assertEqual(kwargs["event_bus_path"], "data/blindbox_event_bus.jsonl")
            self.assertEqual(kwargs["experience_path"], "data/blindbox_experience_log.jsonl")
            self.assertFalse(kwargs["log_learning"])
            self.assertFalse(kwargs["log_memory"])
            self.assertFalse(kwargs["update_registry"])

    def test_run_day_can_open_position(self):
        scanner = FakeScanner(
            {
                "000001.SZ": [
                    {"date": "2026-03-09", "close": 10.0, "open": 10.0},
                    {"date": "2026-03-10", "close": 10.5, "open": 10.4},
                ]
            }
        )
        simulator = FakeSimulator()
        store = MemoryStateStore()

        with tempfile.TemporaryDirectory() as td:
            report_path = str(Path(td) / "blindbox_daily_report.jsonl")
            result = run_blindbox_day(
                trade_date="2026-03-10",
                universe=["000001.SZ"],
                scanner=scanner,
                simulator=simulator,
                state_store=store,
                strategy_rows=[
                    {"strategy_id": "coin_flip_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "prev_day_down_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "above_ma5_buy", "weight": 1.0, "status": "disabled"},
                    {"strategy_id": "tp10_sl10_t20", "weight": 1.2, "status": "disabled", "tp_pct": 0.1, "sl_pct": 0.1, "hold_days": 20, "entry_mode": "next_open"},
                    {"strategy_id": "random_pick_hold_2d", "weight": 1.0, "status": "active"},
                ],
                rng_seed=7,
                apply=True,
                report_path=report_path,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["opened_count"], 1)
        self.assertEqual(len(simulator.buys), 1)
        self.assertEqual(len(store.load().get("positions", [])), 1)

    def test_run_day_can_close_due_position_and_apply_reward(self):
        scanner = FakeScanner(
            {
                "000001.SZ": [
                    {"date": "2026-03-10", "close": 10.0, "open": 10.0},
                    {"date": "2026-03-11", "close": 10.1, "open": 10.0},
                    {"date": "2026-03-12", "close": 10.4, "open": 10.3},
                ]
            }
        )
        simulator = FakeSimulator()
        store = MemoryStateStore(
            {
                "strategies": [
                    {
                        "strategy_id": "random_pick_hold_2d",
                        "weight": 1.0,
                        "closed_trades": 0,
                        "wins": 0,
                        "realized_pnl_sum": 0.0,
                        "avg_realized_pnl": 0.0,
                        "status": "active",
                    }
                ],
                "positions": [
                    {
                        "decision_id": "d1",
                        "code": "000001.SZ",
                        "strategy_id": "random_pick_hold_2d",
                        "buy_date": "2026-03-10",
                        "planned_exit_date": "2026-03-12",
                        "hold_days": 2,
                        "buy_price": 10.0,
                        "shares": 100,
                        "status": "open",
                    }
                ],
            }
        )

        with tempfile.TemporaryDirectory() as td:
            report_path = str(Path(td) / "blindbox_daily_report.jsonl")
            result = run_blindbox_day(
                trade_date="2026-03-12",
                universe=["000001.SZ"],
                scanner=scanner,
                simulator=simulator,
                state_store=store,
                strategy_rows=[{"strategy_id": "random_pick_hold_2d", "weight": 1.0, "status": "active"}],
                rng_seed=3,
                apply=True,
                allow_new_positions=False,
                report_path=report_path,
            )
        self.assertEqual(result["closed_count"], 1)
        self.assertEqual(result["reward_updates"], 1)
        self.assertEqual(len(simulator.sells), 1)
        updated = next(row for row in store.load()["strategies"] if row.get("strategy_id") == "random_pick_hold_2d")
        self.assertGreater(updated["weight"], 1.0)


if __name__ == "__main__":
    unittest.main()
