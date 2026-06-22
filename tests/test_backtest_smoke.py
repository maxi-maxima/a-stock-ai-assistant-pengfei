import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.backtest_smoke import run_backtest_smoke


class _FakeDataSkill:
    def __init__(self, data_map):
        self._data_map = data_map

    def get_history(self, code, days=240):
        return self._data_map.get(code, pd.DataFrame())


class _FakeScanner:
    def __init__(self, data_map, strategies=None):
        self.data_skill = _FakeDataSkill(data_map)
        self._strategies = strategies or ["Standard (放量突破)"]

    def get_strategy_list(self):
        return list(self._strategies)


class _FakeBacktester:
    def run(self, df, strategy_name, **kwargs):
        return {
            "return_pct": 6.2,
            "max_drawdown": -0.05,
            "sharpe": 1.12,
            "score": 8.1,
            "trades": [{"action": "BUY"}, {"action": "SELL"}],
        }


def _make_df(n=140):
    base = pd.Timestamp("2025-01-01")
    rows = []
    close = 10.0
    for i in range(n):
        close = close * 1.001
        rows.append(
            {
                "date": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": close * 0.995,
                "high": close * 1.005,
                "low": close * 0.99,
                "close": close,
                "vol": 100000 + i,
                "pct_chg": 0.1,
            }
        )
    return pd.DataFrame(rows)


class BacktestSmokeTest(unittest.TestCase):
    def test_smoke_ok_with_at_least_one_success_case(self):
        df = _make_df()
        scanner = _FakeScanner({"000001.SZ": df}, strategies=["Standard (放量突破)"])
        backtester = _FakeBacktester()

        with tempfile.TemporaryDirectory() as td:
            latest = str(Path(td) / "latest.json")
            history = str(Path(td) / "history.jsonl")
            out = run_backtest_smoke(
                codes=["000001.SZ"],
                strategies=["Standard (放量突破)"],
                scanner=scanner,
                backtester=backtester,
                apply=True,
                latest_path=latest,
                history_path=history,
            )

        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("passed_cases"), 1)
        self.assertEqual(out.get("no_data_cases"), 0)
        self.assertEqual(out.get("error_cases"), 0)

    def test_smoke_fail_when_all_no_data(self):
        scanner = _FakeScanner({}, strategies=["Standard (放量突破)"])
        backtester = _FakeBacktester()
        out = run_backtest_smoke(
            codes=["000001.SZ"],
            strategies=["Standard (放量突破)"],
            scanner=scanner,
            backtester=backtester,
            apply=False,
        )

        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("passed_cases"), 0)
        self.assertEqual(out.get("no_data_cases"), 1)
        self.assertEqual(out.get("error_cases"), 0)
        self.assertEqual(out.get("status"), "fail")


if __name__ == "__main__":
    unittest.main()
