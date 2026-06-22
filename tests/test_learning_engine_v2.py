import unittest

from core.learning_engine_v2 import build_learning_views_from_events


class LearningEngineV2Test(unittest.TestCase):
    def test_build_learning_views_dedup_and_pick_realized_outcome(self):
        events = [
            {
                "event": "decision",
                "ts": "2026-02-20T09:30:00",
                "code": "000001.SZ",
                "decision_id": "d1",
                "payload": {
                    "action": "BUY",
                    "suggested_action": "BUY",
                    "decision_sample": {
                        "thesis": "旧观点",
                        "risk_points": ["波动风险"],
                        "confidence": 0.7,
                        "strategy_tags": ["s1"],
                        "timeframe": "swing_3_10d",
                    },
                },
            },
            {
                "event": "decision",
                "ts": "2026-02-20T09:31:00",
                "code": "000001.SZ",
                "decision_id": "d1",
                "payload": {
                    "action": "BUY",
                    "suggested_action": "BUY",
                    "decision_sample": {
                        "thesis": "新观点",
                        "risk_points": ["波动风险"],
                        "confidence": 0.8,
                        "strategy_tags": ["s1"],
                        "timeframe": "swing_3_10d",
                    },
                },
            },
            {
                "event": "decision",
                "ts": "2026-02-20T10:00:00",
                "code": "000002.SZ",
                "decision_id": "d2",
                "payload": {
                    "action": "HOLD",
                    "suggested_action": "HOLD",
                    "decision_sample": {
                        "thesis": "观察等待",
                        "risk_points": ["确认不足"],
                        "confidence": 0.5,
                        "strategy_tags": ["s2"],
                        "timeframe": "watchlist",
                    },
                },
            },
            {
                "event": "outcome",
                "ts": "2026-02-21T10:00:00",
                "code": "000001.SZ",
                "decision_id": "d1",
                "payload": {"eval_type": "mark_to_market", "pnl_pct": 0.01, "eval_date": "2026-02-21"},
            },
            {
                "event": "outcome",
                "ts": "2026-02-22T10:00:00",
                "code": "000001.SZ",
                "decision_id": "d1",
                "payload": {"eval_type": "sell_realized", "pnl_pct": -0.03, "eval_date": "2026-02-22"},
            },
        ]

        out = build_learning_views_from_events(events)
        samples = out.get("samples", [])
        summary = out.get("summary", {})
        profiles = out.get("profiles", {})

        self.assertEqual(len(samples), 2)
        self.assertEqual(summary.get("decision_count"), 2)
        self.assertEqual(summary.get("labeled_count"), 1)

        sample_d1 = next(s for s in samples if s.get("decision_id") == "d1")
        self.assertEqual(sample_d1.get("thesis"), "新观点")
        self.assertEqual(sample_d1.get("outcome_eval_type"), "sell_realized")
        self.assertAlmostEqual(float(sample_d1.get("outcome_pnl_pct")), -0.03, places=6)

        s1 = profiles.get("s1", {})
        self.assertEqual(s1.get("sample_count"), 1)
        self.assertEqual(s1.get("labeled_count"), 1)
        self.assertAlmostEqual(float(s1.get("avg_pnl_pct")), -0.03, places=6)


if __name__ == "__main__":
    unittest.main()
