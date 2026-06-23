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


if __name__ == "__main__":
    unittest.main()
