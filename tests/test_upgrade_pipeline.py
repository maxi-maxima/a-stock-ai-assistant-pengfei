import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.upgrade_pipeline import run_upgrade_pipeline, run_upgrade_with_retries


class UpgradePipelineTest(unittest.TestCase):
    def test_pipeline_ok_when_all_steps_ok(self):
        with tempfile.TemporaryDirectory() as td:
            latest_path = str(Path(td) / "upgrade_latest.json")
            history_path = str(Path(td) / "upgrade_history.jsonl")

            out = run_upgrade_pipeline(
                days=30,
                apply=True,
                latest_path=latest_path,
                history_path=history_path,
                learning_runner=lambda **kwargs: {"ok": True, "sample_count": 10},
                tracking_runner=lambda **kwargs: {"ok": True, "champion_strategy": "s1"},
                training_runner=lambda config=None: {"ok": True, "strategies": {}},
                smoke_runner=lambda **kwargs: {"ok": True, "passed_cases": 3, "error_cases": 0},
            )

            self.assertTrue(out.get("ok"))
            self.assertTrue(Path(latest_path).exists())
            self.assertTrue(Path(history_path).exists())

            latest = json.loads(Path(latest_path).read_text(encoding="utf-8"))
            self.assertTrue(latest.get("ok"))
            self.assertEqual(latest.get("smoke", {}).get("passed_cases"), 3)

    def test_pipeline_fail_when_one_step_fails(self):
        out = run_upgrade_pipeline(
            days=30,
            apply=False,
            learning_runner=lambda **kwargs: {"ok": True},
            tracking_runner=lambda **kwargs: {"ok": False, "error": "track failed"},
            training_runner=lambda config=None: {"ok": True},
            smoke_runner=lambda **kwargs: {"ok": True, "passed_cases": 1, "error_cases": 0},
        )

        self.assertFalse(out.get("ok"))
        self.assertFalse(out.get("tracking", {}).get("ok"))
        self.assertTrue(out.get("learning", {}).get("ok"))

    def test_cli_help_runs(self):
        root = Path(__file__).resolve().parents[1]
        cmd = [sys.executable, "tools/full_upgrade_and_backtest.py", "--help"]
        cp = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0, msg=cp.stderr or cp.stdout)

    def test_retry_runner_stops_on_success(self):
        calls = {"n": 0}

        def fake_pipeline(**kwargs):
            calls["n"] += 1
            if calls["n"] < 2:
                return {"ok": False, "status": "fail", "smoke": {"passed_cases": 0, "error_cases": 1}}
            return {"ok": True, "status": "pass", "smoke": {"passed_cases": 3, "error_cases": 0}}

        out = run_upgrade_with_retries(
            max_attempts=3,
            pipeline_runner=fake_pipeline,
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("attempts_used"), 2)
        self.assertEqual(len(out.get("attempts", [])), 2)

    def test_retry_runner_fail_after_max_attempts(self):
        def fake_pipeline(**kwargs):
            return {"ok": False, "status": "fail", "smoke": {"passed_cases": 0, "error_cases": 2}}

        out = run_upgrade_with_retries(
            max_attempts=2,
            pipeline_runner=fake_pipeline,
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("attempts_used"), 2)
        self.assertEqual(len(out.get("attempts", [])), 2)


if __name__ == "__main__":
    unittest.main()
