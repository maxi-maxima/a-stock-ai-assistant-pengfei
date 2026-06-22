import unittest

from core import metrics


class MetricsExecutionCoverageTest(unittest.TestCase):
    def test_only_buy_sell_require_execution(self):
        decisions = [
            {"decision_id": "d_hold", "payload": {"action": "HOLD", "decision_scope": "advisory"}},
            {"decision_id": "d_buy", "payload": {"action": "BUY", "decision_scope": "order"}},
            {"decision_id": "d_sell", "payload": {"action": "SELL", "decision_scope": "order"}},
        ]
        executions = [{"decision_id": "d_buy"}]

        info = metrics._calc_execution_coverage(decisions, executions)

        self.assertEqual(info["actionable_count"], 2)
        self.assertEqual(info["hold_count"], 1)
        self.assertEqual(info["missing_count"], 1)
        self.assertAlmostEqual(info["execution_rate"], 0.5)

    def test_no_actionable_decision_does_not_penalize_execution_rate(self):
        decisions = [
            {"decision_id": "d_hold_1", "payload": {"action": "HOLD"}},
            {"decision_id": "d_hold_2", "payload": {"action": "HOLD"}},
        ]
        executions = []

        info = metrics._calc_execution_coverage(decisions, executions)

        self.assertEqual(info["actionable_count"], 0)
        self.assertEqual(info["missing_count"], 0)
        self.assertAlmostEqual(info["execution_rate"], 1.0)

    def test_linked_outcome_decisions_only_count_known_decisions(self):
        decision_ids = {"d1", "d2"}
        outcome_ids = {"d1", "d2", "d3"}
        linked = metrics._count_linked_outcome_decisions(decision_ids, outcome_ids)
        self.assertEqual(linked, 2)

    def test_advisory_buy_is_not_treated_as_execution_required(self):
        decisions = [
            {
                "decision_id": "d_adv_buy",
                "source": "cognitive_graph",
                "payload": {"action": "BUY", "decision_scope": "advisory"},
            }
        ]
        executions = []

        info = metrics._calc_execution_coverage(decisions, executions)

        self.assertEqual(info["actionable_count"], 0)
        self.assertEqual(info["advisory_actionable_count"], 1)
        self.assertAlmostEqual(info["execution_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
