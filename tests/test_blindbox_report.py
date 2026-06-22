import unittest
import tempfile
from pathlib import Path

from core.blindbox_report import (
    build_blindbox_control_panel,
    build_blindbox_cumulative_series,
    build_blindbox_report,
    build_blindbox_scorecard,
    load_blindbox_health_snapshot,
)


class BlindboxReportTest(unittest.TestCase):
    def test_report_contains_core_summary_fields(self):
        row = build_blindbox_report(
            latest_day={"trade_date": "2026-03-10", "opened_count": 1, "closed_count": 1, "realized_pnl_sum": -123.4},
            strategies=[
                {"strategy_id": "a", "weight": 0.8, "status": "watch", "avg_realized_pnl": -0.03},
                {"strategy_id": "b", "weight": 1.2, "status": "active", "avg_realized_pnl": 0.05},
            ],
        )
        self.assertEqual(row["opened_count"], 1)
        self.assertEqual(row["closed_count"], 1)
        self.assertIn("top_strategies", row)
        self.assertIn("weak_strategies", row)

    def test_load_health_snapshot_summarizes_files(self):
        with tempfile.TemporaryDirectory() as td:
            latest = Path(td) / "latest.json"
            strategies = Path(td) / "strategies.json"
            positions = Path(td) / "positions.json"

            latest.write_text(
                '{"last_trade_date":"2026-03-10","processed_days":1,"results":[{"opened_count":1,"closed_count":1,"realized_pnl_sum":12.3}]}',
                encoding="utf-8",
            )
            strategies.write_text(
                '[{"strategy_id":"tp10_sl10_t20","status":"active","weight":1.2,"calls":3,"closed_trades":2,"realized_pnl_sum":0.06,"avg_realized_pnl":0.03},'
                '{"strategy_id":"coin_flip_buy","status":"active","weight":0.7,"calls":4,"closed_trades":2,"realized_pnl_sum":-0.02,"avg_realized_pnl":-0.01},'
                '{"strategy_id":"random_pick_hold_2d","status":"active","weight":0.8,"calls":2,"closed_trades":1,"realized_pnl_sum":0.0,"avg_realized_pnl":0.0}]',
                encoding="utf-8",
            )
            positions.write_text(
                '[{"decision_id":"d1","status":"open"},{"decision_id":"d2","status":"closed"}]',
                encoding="utf-8",
            )

            row = load_blindbox_health_snapshot(
                latest_path=str(latest),
                strategies_path=str(strategies),
                positions_path=str(positions),
            )

            self.assertEqual(row["last_trade_date"], "2026-03-10")
            self.assertEqual(row["open_positions"], 1)
            self.assertEqual(row["active_strategies"], 3)
            self.assertEqual(row["top_strategy_id"], "tp10_sl10_t20")
            self.assertEqual(row["primary_strategy_id"], "tp10_sl10_t20")
            self.assertEqual(row["control_calls"], 6)
            self.assertEqual(row["control_closed_trades"], 3)

    def test_build_control_panel_compares_primary_vs_control(self):
        panel = build_blindbox_control_panel(
            {
                "primary_strategy_id": "tp10_sl10_t20",
                "primary_weight": 1.2,
                "primary_calls": 3,
                "primary_closed_trades": 2,
                "primary_avg_realized_pnl": 0.03,
                "control_calls": 6,
                "control_closed_trades": 3,
                "control_avg_realized_pnl": -0.01,
            }
        )
        self.assertEqual(panel["primary"]["strategy_id"], "tp10_sl10_t20")
        self.assertEqual(panel["primary"]["closed_trades"], 2)
        self.assertEqual(panel["control"]["closed_trades"], 3)

    def test_build_cumulative_series_accumulates_primary_and_control(self):
        rows = build_blindbox_cumulative_series(
            [
                {"trade_date": "2026-03-03", "chosen_strategy_id": "coin_flip_buy", "realized_pnl_sum": -10},
                {"trade_date": "2026-03-04", "chosen_strategy_id": "tp10_sl10_t20", "realized_pnl_sum": 30},
                {"trade_date": "2026-03-05", "chosen_strategy_id": "random_pick_hold_2d", "realized_pnl_sum": 20},
            ]
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["主策略累计已实现盈亏"], 30.0)
        self.assertEqual(rows[-1]["随机对照组累计已实现盈亏"], 10.0)

    def test_build_scorecard_marks_primary_ahead_when_profit_dominates(self):
        scorecard = build_blindbox_scorecard(
            {
                "primary_strategy_id": "tp10_sl10_t20",
                "primary_closed_trades": 8,
                "primary_avg_realized_pnl": 0.03,
                "primary_realized_pnl_sum": 0.24,
                "primary_max_drawdown": 0.04,
                "control_closed_trades": 10,
                "control_avg_realized_pnl": 0.005,
                "control_realized_pnl_sum": 0.05,
                "control_max_drawdown": 0.08,
            }
        )
        self.assertEqual(scorecard["winner"], "primary")
        self.assertEqual(scorecard["conclusion"], "主策略跑赢随机对照组")
        self.assertEqual(scorecard["confidence"], "初步可信")
        self.assertGreater(scorecard["primary_score"], scorecard["control_score"])

    def test_build_scorecard_returns_insufficient_when_samples_too_small(self):
        scorecard = build_blindbox_scorecard(
            {
                "primary_strategy_id": "tp10_sl10_t20",
                "primary_closed_trades": 2,
                "primary_avg_realized_pnl": 0.02,
                "primary_realized_pnl_sum": 0.04,
                "primary_max_drawdown": 0.03,
                "control_closed_trades": 1,
                "control_avg_realized_pnl": 0.01,
                "control_realized_pnl_sum": 0.01,
                "control_max_drawdown": 0.02,
            }
        )
        self.assertEqual(scorecard["conclusion"], "样本不足，暂不下结论")
        self.assertEqual(scorecard["confidence"], "样本不足")


if __name__ == "__main__":
    unittest.main()
