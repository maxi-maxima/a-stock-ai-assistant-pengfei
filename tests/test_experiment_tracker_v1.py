import json
import os
import tempfile
import unittest
from unittest import mock

from core.experiment_tracker_v1 import load_experiment_history, refresh_experiment_tracking


class ExperimentTrackerV1Test(unittest.TestCase):
    def test_refresh_tracking_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            samples_path = os.path.join(td, "learning_samples.jsonl")
            profiles_path = os.path.join(td, "strategy_profiles.json")
            tracking_path = os.path.join(td, "experiment_tracking.jsonl")

            with open(samples_path, "w", encoding="utf-8") as f:
                for i in range(3):
                    f.write(json.dumps({"decision_id": f"d{i}", "sample_valid": True}, ensure_ascii=False) + "\n")

            payload = {
                "summary": {
                    "updated_at": "2026-02-26T10:00:00",
                    "sample_count": 3,
                    "valid_rate": 1.0,
                    "labeled_rate": 0.67,
                    "profile_count": 2,
                    "champion_strategy": "trend_up",
                    "champion_decayed_pnl_pct": 0.0123,
                    "drift_warning_count": 1,
                },
                "profiles": {
                    "trend_up": {"drift_7_vs_30": -0.0042, "labeled_count": 3},
                    "mean_revert": {"drift_7_vs_30": 0.0011, "labeled_count": 2},
                },
            }
            with open(profiles_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            out = refresh_experiment_tracking(
                apply=True,
                samples_path=samples_path,
                profiles_path=profiles_path,
                tracking_path=tracking_path,
                mlflow_enabled=False,
            )

            self.assertTrue(out.get("ok"))
            self.assertEqual(out.get("champion_strategy"), "trend_up")
            self.assertAlmostEqual(float(out.get("champion_drift_7_vs_30")), -0.0042, places=6)
            self.assertEqual(out.get("sample_count"), 3)
            self.assertTrue(os.path.exists(tracking_path))

            history = load_experiment_history(path=tracking_path)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].get("champion_strategy"), "trend_up")

    def test_refresh_tracking_mlflow_import_error_is_soft_failure(self):
        with tempfile.TemporaryDirectory() as td:
            samples_path = os.path.join(td, "learning_samples.jsonl")
            profiles_path = os.path.join(td, "strategy_profiles.json")
            tracking_path = os.path.join(td, "experiment_tracking.jsonl")
            with open(samples_path, "w", encoding="utf-8") as f:
                f.write(json.dumps({"decision_id": "d1"}, ensure_ascii=False) + "\n")
            with open(profiles_path, "w", encoding="utf-8") as f:
                json.dump({"summary": {}, "profiles": {}}, f, ensure_ascii=False)

            with mock.patch("core.experiment_tracker_v1.importlib.import_module", side_effect=ImportError("no mlflow")):
                out = refresh_experiment_tracking(
                    apply=True,
                    samples_path=samples_path,
                    profiles_path=profiles_path,
                    tracking_path=tracking_path,
                    mlflow_enabled=True,
                )

            self.assertTrue(out.get("ok"))
            self.assertFalse(out.get("mlflow_logged"))
            self.assertIn("mlflow", str(out.get("mlflow_error", "")).lower())
            self.assertTrue(os.path.exists(tracking_path))

    def test_load_history_limit(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "experiment_tracking.jsonl")
            rows = [
                {"ts": "2026-02-20T10:00:00", "champion_strategy": "a"},
                {"ts": "2026-02-21T10:00:00", "champion_strategy": "b"},
                {"ts": "2026-02-22T10:00:00", "champion_strategy": "c"},
            ]
            with open(path, "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

            out = load_experiment_history(path=path, limit=2)
            self.assertEqual(len(out), 2)
            self.assertEqual(out[0].get("champion_strategy"), "b")
            self.assertEqual(out[1].get("champion_strategy"), "c")


if __name__ == "__main__":
    unittest.main()
