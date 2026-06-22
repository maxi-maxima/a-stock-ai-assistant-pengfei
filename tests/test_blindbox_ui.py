import unittest

from core.blindbox_view import (
    _format_position_rows,
    _format_report_rows,
    _format_strategy_rows,
    _parse_task_query_summary,
    _translate_status,
)


class BlindboxUiTest(unittest.TestCase):
    def test_translate_status_maps_to_chinese(self):
        self.assertEqual(_translate_status("active"), "启用")
        self.assertEqual(_translate_status("watch"), "观察")
        self.assertEqual(_translate_status("disabled"), "停用")
        self.assertEqual(_translate_status("open"), "持有中")

    def test_format_strategy_rows_renames_columns(self):
        rows = _format_strategy_rows(
            [
                {
                    "strategy_id": "coin_flip_buy",
                    "weight": 1.2,
                    "status": "active",
                    "calls": 3,
                    "buys": 2,
                    "closed_trades": 1,
                    "wins": 1,
                    "avg_realized_pnl": 0.03,
                }
            ]
        )
        row = rows[0]
        self.assertIn("策略编号", row)
        self.assertIn("当前权重", row)
        self.assertEqual(row["状态"], "启用")

    def test_format_position_rows_renames_columns(self):
        rows = _format_position_rows(
            [
                {
                    "decision_id": "d1",
                    "code": "000001.SZ",
                    "strategy_id": "coin_flip_buy",
                    "buy_date": "2026-03-10",
                    "planned_exit_date": "2026-03-12",
                    "status": "open",
                }
            ]
        )
        row = rows[0]
        self.assertIn("决策编号", row)
        self.assertIn("股票代码", row)
        self.assertEqual(row["状态"], "持有中")

    def test_format_report_rows_renames_columns(self):
        rows = _format_report_rows(
            [
                {
                    "trade_date": "2026-03-10",
                    "opened_count": 1,
                    "closed_count": 1,
                    "reward_updates": 1,
                    "realized_pnl_sum": -12.3,
                    "chosen_strategy_id": "coin_flip_buy",
                    "selected_code": "000001.SZ",
                    "ok": True,
                }
            ]
        )
        row = rows[0]
        self.assertIn("交易日期", row)
        self.assertIn("新开仓数", row)
        self.assertEqual(row["执行结果"], "成功")

    def test_parse_task_query_summary_picks_core_fields(self):
        text = "\n".join(
            [
                "TaskName: \\\\BlindboxPaperLoop",
                "Next Run Time: 2026/3/8 15:05:00",
                "Last Run Time: 2026/3/7 16:41:00",
                "Last Result: 0",
                "Status: Ready",
            ]
        )
        rows = _parse_task_query_summary(text)
        labels = {row["项目"] for row in rows}
        self.assertIn("任务名称", labels)
        self.assertIn("下次运行时间", labels)
        self.assertIn("最近执行结果", labels)


if __name__ == "__main__":
    unittest.main()
