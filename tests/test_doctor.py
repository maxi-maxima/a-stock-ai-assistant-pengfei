import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import doctor


class DoctorTest(unittest.TestCase):
    def test_collect_diagnostics_counts_missing_core_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "dashboard.py").write_text("", encoding="utf-8")

            report = doctor.collect_diagnostics(
                root=root,
                critical_files=["dashboard.py", "core/missing.py"],
                dependency_modules=[],
                data_files=[],
                module_checks=[],
            )

            self.assertFalse(report["ok"])
            self.assertEqual(report["summary"]["missing_files"], 1)
            self.assertEqual(report["checks"][1]["status"], "fail")
            self.assertEqual(report["checks"][1]["path"], "core/missing.py")

    def test_collect_diagnostics_tracks_missing_dependencies_separately(self):
        report = doctor.collect_diagnostics(
            critical_files=[],
            dependency_modules=["definitely_missing_package_for_doctor_test"],
            data_files=[],
            module_checks=[],
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["summary"]["missing_files"], 0)
        self.assertEqual(report["summary"]["missing_dependencies"], 1)

    def test_main_json_outputs_machine_readable_report(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            code = doctor.main(["--json"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0 if payload["ok"] else 1)
        self.assertIn("summary", payload)
        self.assertIn("checks", payload)
        self.assertIsInstance(payload["ok"], bool)

    def test_render_markdown_report_creates_issue_ready_summary(self):
        report = {
            "ok": False,
            "summary": {
                "total": 3,
                "passed": 1,
                "failed": 1,
                "warnings": 1,
                "missing_files": 1,
                "missing_dependencies": 0,
            },
            "checks": [
                {"kind": "dependency", "name": "pandas", "status": "ok"},
                {"kind": "file", "path": "dashboard.py", "status": "fail", "reason": "missing"},
                {"kind": "data_file", "path": "data/my_strategies.json", "status": "warn", "reason": "not_created"},
            ],
        }

        markdown = doctor.render_markdown_report(report)

        self.assertIn("# AI Trading Avatar Doctor Report", markdown)
        self.assertIn("Status: **FAIL**", markdown)
        self.assertIn("| Failed | 1 |", markdown)
        self.assertIn("| Kind | Target | Status | Reason | Message |", markdown)
        self.assertIn("| file | dashboard.py | fail | missing | - |", markdown)
        self.assertIn("| data_file | data/my_strategies.json | warn | not_created | - |", markdown)

    def test_render_markdown_report_escapes_table_cells(self):
        report = {
            "ok": False,
            "summary": {
                "total": 1,
                "passed": 0,
                "failed": 1,
                "warnings": 0,
                "missing_files": 0,
                "missing_dependencies": 0,
            },
            "checks": [
                {
                    "kind": "module",
                    "path": "core/a|b.py",
                    "status": "fail",
                    "reason": "error",
                    "message": "bad | import\nsecond line",
                },
            ],
        }

        markdown = doctor.render_markdown_report(report)

        self.assertIn("| module | core/a\\|b.py | fail | error | bad \\| import second line |", markdown)

    def test_main_markdown_outputs_issue_ready_report(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            code = doctor.main(["--markdown"])

        markdown = stdout.getvalue()

        self.assertIn("# AI Trading Avatar Doctor Report", markdown)
        self.assertIn("| Total |", markdown)
        self.assertEqual(code, 0 if "Status: **PASS**" in markdown else 1)


if __name__ == "__main__":
    unittest.main()
