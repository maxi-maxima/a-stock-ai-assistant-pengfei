import unittest

from tools.blindbox_daily_runner import run_once


class BlindboxRunnerTest(unittest.TestCase):
    def test_run_once_rejects_future_trade_date(self):
        row = run_once(
            target_dates=["2026-03-20"],
            latest={},
            save=False,
            max_allowed_date="2026-03-07",
        )
        self.assertFalse(row["ok"])
        self.assertEqual(row["reason"], "future_trade_date")

    def test_run_once_skips_when_same_trade_day_already_done(self):
        row = run_once(
            target_dates=["2026-03-10"],
            latest={"last_trade_date": "2026-03-10"},
            day_runner=lambda **kwargs: {"ok": True},
            save=False,
        )
        self.assertTrue(row["skipped"])

    def test_run_once_backfills_missed_trade_days(self):
        calls = []

        def fake_day_runner(**kwargs):
            calls.append(kwargs["trade_date"])
            return {"ok": True, "opened_count": 0, "closed_count": 0}

        row = run_once(
            target_dates=["2026-03-10", "2026-03-11"],
            latest={"last_trade_date": "2026-03-09"},
            day_runner=fake_day_runner,
            save=False,
        )
        self.assertEqual(row["processed_days"], 2)
        self.assertEqual(calls, ["2026-03-10", "2026-03-11"])

    def test_run_once_passes_prepared_scanner(self):
        captured = {}

        def fake_day_runner(**kwargs):
            captured["scanner"] = kwargs.get("scanner")
            return {"ok": True, "opened_count": 0, "closed_count": 0}

        row = run_once(
            target_dates=["2026-03-10"],
            latest={},
            day_runner=fake_day_runner,
            save=False,
            scanner="prepared-scanner",
        )
        self.assertTrue(row["ok"])
        self.assertEqual(captured["scanner"], "prepared-scanner")


if __name__ == "__main__":
    unittest.main()
