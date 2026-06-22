import unittest

from core.blindbox_strategies import list_builtin_strategies, weighted_pick_strategy


class BlindboxStrategiesTest(unittest.TestCase):
    def test_builtin_strategies_exist(self):
        rows = list_builtin_strategies()
        ids = {row["strategy_id"] for row in rows}
        self.assertIn("coin_flip_buy", ids)
        self.assertIn("prev_day_down_buy", ids)
        self.assertIn("above_ma5_buy", ids)
        self.assertIn("random_pick_hold_2d", ids)
        self.assertIn("tp10_sl10_t20", ids)

    def test_weighted_pick_skips_disabled_strategies(self):
        strategies = [
            {"strategy_id": "a", "weight": 1.0, "status": "disabled"},
            {"strategy_id": "b", "weight": 2.0, "status": "active"},
        ]
        picked = weighted_pick_strategy(strategies, rng_seed=7)
        self.assertEqual(picked["strategy_id"], "b")

    def test_weighted_pick_prefers_primary_strategy_when_all_calls_zero(self):
        strategies = [
            {"strategy_id": "coin_flip_buy", "weight": 1.0, "status": "active", "calls": 0},
            {"strategy_id": "random_pick_hold_2d", "weight": 1.0, "status": "active", "calls": 0},
            {"strategy_id": "tp10_sl10_t20", "weight": 1.2, "status": "active", "calls": 0},
        ]
        picked = weighted_pick_strategy(strategies, rng_seed=1)
        self.assertEqual(picked["strategy_id"], "tp10_sl10_t20")


if __name__ == "__main__":
    unittest.main()
