import datetime
import json
import tempfile
import unittest
from pathlib import Path

from core.upgrade_scheduler import load_scheduler_config, run_scheduled_upgrade_once, save_scheduler_config


class UpgradeSchedulerTest(unittest.TestCase):
    def test_load_scheduler_config_with_defaults(self):
        cfg = load_scheduler_config(path="non_exists_upgrade_scheduler.json")
        self.assertIn("enabled", cfg)
        self.assertIn("schedule_time", cfg)
        self.assertIn("max_attempts", cfg)

    def test_save_and_load_scheduler_config(self):
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "upgrade_scheduler.json")
            ok = save_scheduler_config({"enabled": False, "schedule_time": "03:15"}, path=path)
            self.assertTrue(ok)
            cfg = load_scheduler_config(path=path)
            self.assertFalse(cfg.get("enabled"))
            self.assertEqual(cfg.get("schedule_time"), "03:15")

    def test_run_once_skips_weekend(self):
        row = run_scheduled_upgrade_once(
            config={
                "enabled": True,
                "skip_weekends": True,
            },
            apply=False,
            now=datetime.datetime(2026, 2, 28, 9, 0, 0),  # Saturday
            retry_runner=lambda **kwargs: {"ok": True, "attempts_used": 1, "final_report": {}},
        )
        self.assertTrue(row.get("skipped"))
        self.assertEqual(row.get("reason"), "weekend")

    def test_run_once_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            latest = str(Path(td) / "scheduler_latest.json")
            history = str(Path(td) / "scheduler_history.jsonl")
            row = run_scheduled_upgrade_once(
                config={
                    "enabled": True,
                    "skip_weekends": False,
                    "days": 180,
                    "max_attempts": 2,
                    "training_enabled": False,
                    "training_mode": "light",
                },
                apply=True,
                latest_path=latest,
                history_path=history,
                now=datetime.datetime(2026, 2, 27, 9, 0, 0),
                retry_runner=lambda **kwargs: {
                    "ok": True,
                    "attempts_used": 1,
                    "final_report": {"status": "pass"},
                },
            )
            self.assertTrue(row.get("ok"))
            self.assertTrue(Path(latest).exists())
            self.assertTrue(Path(history).exists())
            payload = json.loads(Path(latest).read_text(encoding="utf-8"))
            self.assertTrue(payload.get("ok"))


if __name__ == "__main__":
    unittest.main()
