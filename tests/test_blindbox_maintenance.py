import json
import tempfile
import unittest
from pathlib import Path

from core.blindbox_maintenance import sanitize_future_state


class BlindboxMaintenanceTest(unittest.TestCase):
    def test_sanitize_future_state_removes_future_rows(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            positions_path = td / "positions.json"
            report_path = td / "report.jsonl"
            history_path = td / "history.jsonl"
            latest_path = td / "latest.json"
            trades_path = td / "trades.jsonl"
            event_bus_path = td / "event_bus.jsonl"
            experience_path = td / "experience.jsonl"
            strategy_state_path = td / "strategy_state.json"

            positions_path.write_text(
                json.dumps(
                    [
                        {"decision_id": "blindbox_20260306_keep", "buy_date": "2026-03-06", "status": "open"},
                        {"decision_id": "blindbox_20260312_drop", "buy_date": "2026-03-12", "status": "open"},
                        {"decision_id": "blindbox_20260306_pending", "signal_date": "2026-03-06", "planned_buy_date": "2026-03-10", "status": "pending_entry"},
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            report_path.write_text(
                "\n".join(
                    [
                        json.dumps({"trade_date": "2026-03-06", "chosen_strategy_id": "coin_flip_buy", "opened_count": 1, "closed_count": 0}),
                        json.dumps({"trade_date": "2026-03-12", "chosen_strategy_id": "random_pick_hold_2d", "opened_count": 1, "closed_count": 0}),
                    ]
                ),
                encoding="utf-8",
            )
            history_path.write_text(
                "\n".join(
                    [
                        json.dumps({"last_trade_date": "2026-03-06", "results": [{"trade_date": "2026-03-06", "chosen_strategy_id": "coin_flip_buy", "opened_count": 1}]}),
                        json.dumps({"last_trade_date": "2026-03-12", "results": [{"trade_date": "2026-03-12", "chosen_strategy_id": "random_pick_hold_2d", "opened_count": 1}]}),
                    ]
                ),
                encoding="utf-8",
            )
            latest_path.write_text(
                json.dumps({"last_trade_date": "2026-03-12", "results": [{"trade_date": "2026-03-12", "chosen_strategy_id": "random_pick_hold_2d", "opened_count": 1}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            trades_path.write_text(
                "\n".join(
                    [
                        json.dumps({"action": "BUY", "decision_id": "blindbox_20260306_keep"}),
                        json.dumps({"action": "BUY", "decision_id": "blindbox_20260312_drop"}),
                    ]
                ),
                encoding="utf-8",
            )
            event_bus_path.write_text(
                "\n".join(
                    [
                        json.dumps({"event": "outcome", "decision_id": "blindbox_20260306_keep", "payload": {"pnl_pct": 0.01, "signal_source": {"strategy": "coin_flip_buy"}}}),
                        json.dumps({"event": "outcome", "decision_id": "blindbox_20260312_drop", "payload": {"pnl_pct": -0.02, "signal_source": {"strategy": "random_pick_hold_2d"}}}),
                    ]
                ),
                encoding="utf-8",
            )
            experience_path.write_text(
                "\n".join(
                    [
                        json.dumps({"event": "decision", "payload": {"decision_id": "blindbox_20260306_keep"}}),
                        json.dumps({"event": "decision", "payload": {"decision_id": "blindbox_20260312_drop"}}),
                    ]
                ),
                encoding="utf-8",
            )
            strategy_state_path.write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")

            out = sanitize_future_state(
                reference_trade_date="2026-03-07",
                positions_path=str(positions_path),
                report_path=str(report_path),
                history_path=str(history_path),
                latest_path=str(latest_path),
                trades_path=str(trades_path),
                event_bus_path=str(event_bus_path),
                experience_path=str(experience_path),
                strategy_state_path=str(strategy_state_path),
            )

            self.assertEqual(out["removed_positions"], 1)
            self.assertEqual(out["removed_reports"], 1)
            self.assertEqual(out["removed_history"], 1)
            self.assertEqual(out["removed_trades"], 1)
            self.assertEqual(out["removed_events"], 1)
            self.assertEqual(out["removed_experience"], 1)

            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(latest["last_trade_date"], "2026-03-06")

            strategies = json.loads(strategy_state_path.read_text(encoding="utf-8"))
            coin = next(row for row in strategies if row["strategy_id"] == "coin_flip_buy")
            self.assertEqual(coin["calls"], 1)


if __name__ == "__main__":
    unittest.main()
