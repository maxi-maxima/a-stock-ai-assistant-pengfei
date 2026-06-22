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


if __name__ == "__main__":
    unittest.main()
