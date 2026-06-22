import unittest

from core.blindbox_protocol import build_position_plan, build_strategy_state


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


if __name__ == "__main__":
    unittest.main()
