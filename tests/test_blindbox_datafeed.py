import unittest

from core.blindbox_datafeed import calc_planned_exit_date, prefer_akshare_fallback, resolve_reference_trade_date, resolve_universe


class BlindboxDatafeedTest(unittest.TestCase):
    def test_calc_planned_exit_date_skips_non_trading_days(self):
        calendar = ["2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12"]
        out = calc_planned_exit_date("2026-03-10", hold_days=2, trading_days=calendar)
        self.assertEqual(out, "2026-03-12")

    def test_resolve_universe_prefers_watchlist_then_fallback(self):
        out = resolve_universe(watchlist=["000001.SZ"], fallback=["000002.SZ"])
        self.assertEqual(out, ["000001.SZ"])

    def test_resolve_reference_trade_date_picks_latest_non_future_date(self):
        out = resolve_reference_trade_date(
            candidate_dates=["2026-03-05", "2026-03-06", "2026-03-10"],
            today="2026-03-07",
        )
        self.assertEqual(out, "2026-03-06")

    def test_resolve_reference_trade_date_falls_back_to_previous_weekday(self):
        out = resolve_reference_trade_date(candidate_dates=[], today="2026-03-07")
        self.assertEqual(out, "2026-03-06")

    def test_prefer_akshare_fallback_disables_tushare_market_pro(self):
        class Market:
            def __init__(self):
                self.pro = object()
                self.token = "abc"

        class DataSkill:
            def __init__(self):
                self.market = Market()

        class Scanner:
            def __init__(self):
                self.data_skill = DataSkill()

        scanner = Scanner()
        meta = prefer_akshare_fallback(scanner)
        self.assertTrue(meta["akshare_only"])
        self.assertIsNone(scanner.data_skill.market.pro)
        self.assertEqual(scanner.data_skill.market.token, "")


if __name__ == "__main__":
    unittest.main()
