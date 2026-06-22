import unittest
import tempfile
import os
import json

from core.decision_sample import build_decision_sample, ensure_decision_sample
from core.protocols import validate_decision_payload


class DecisionSampleProtocolTest(unittest.TestCase):
    def test_build_decision_sample_contains_required_fields(self):
        debate = {
            "core_view": "趋势偏强，等待确认后分批介入。",
            "risk_warning": "量能不足；题材分化；高位波动",
            "scores": {"total": 72},
        }
        signal_source = {
            "strategy": "trend_follow",
            "strategies": ["trend_follow", "breakout"],
            "strategy_votes": [{"strategy": "trend_follow", "weight": 0.8}],
        }

        sample = build_decision_sample(
            debate=debate,
            action="BUY",
            suggested_action="BUY",
            signal_source=signal_source,
            context_tags=["趋势", "放量"],
            policy_notes=["below_buy_threshold"],
        )

        self.assertIn("thesis", sample)
        self.assertIn("risk_points", sample)
        self.assertIn("confidence", sample)
        self.assertIn("strategy_tags", sample)
        self.assertIn("timeframe", sample)
        self.assertTrue(sample["thesis"])
        self.assertIsInstance(sample["risk_points"], list)
        self.assertGreaterEqual(sample["confidence"], 0.0)
        self.assertLessEqual(sample["confidence"], 1.0)
        self.assertIn("trend_follow", sample["strategy_tags"])

    def test_ensure_decision_sample_fills_missing(self):
        payload = {"action": "HOLD", "suggested_action": "HOLD"}

        out = ensure_decision_sample(payload)

        sample = out.get("decision_sample")
        self.assertIsInstance(sample, dict)
        for key in ("thesis", "risk_points", "confidence", "strategy_tags", "timeframe"):
            self.assertIn(key, sample)
        self.assertEqual(sample["timeframe"], "watchlist")

    def test_validate_decision_payload_checks_required_sample_fields(self):
        spec = {
            "version": "1.1",
            "decision": {
                "required": ["action", "suggested_action", "scores", "feature_weights", "decision_sample"],
                "required_sample": ["thesis", "risk_points", "confidence", "strategy_tags", "timeframe"],
                "allowed_actions": ["BUY", "SELL", "HOLD"],
            },
        }
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(spec, f, ensure_ascii=False, indent=2)

            ok1, errs1 = validate_decision_payload(
                {"action": "BUY", "suggested_action": "BUY", "scores": {}, "feature_weights": {}},
                path=path,
            )
            self.assertFalse(ok1)
            self.assertIn("decision_missing_decision_sample", errs1)

            ok2, errs2 = validate_decision_payload(
                {
                    "action": "BUY",
                    "suggested_action": "BUY",
                    "scores": {},
                    "feature_weights": {},
                    "decision_sample": {"thesis": "x", "risk_points": [], "strategy_tags": [], "timeframe": "watchlist"},
                },
                path=path,
            )
            self.assertFalse(ok2)
            self.assertIn("decision_sample_missing_confidence", errs2)
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
