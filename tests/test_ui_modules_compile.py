import py_compile
import unittest
from pathlib import Path


class UiModulesCompileTest(unittest.TestCase):
    def test_high_risk_ui_modules_compile(self):
        root = Path(__file__).resolve().parents[1]
        targets = [
            root / "ui" / "modules" / "tactics.py",
            root / "ui" / "modules" / "patrol.py",
            root / "ui" / "modules" / "broker_recommend.py",
            root / "ui" / "modules" / "metrics.py",
            root / "ui" / "modules" / "backtest.py",
            root / "ui" / "modules" / "radar.py",
            root / "ui" / "modules" / "system_check.py",
            root / "ui" / "modules" / "llm_keys.py",
            root / "ui" / "modules" / "blindbox.py",
            root / "dashboard.py",
        ]
        for target in targets:
            with self.subTest(target=target.name):
                py_compile.compile(str(target), doraise=True)


if __name__ == "__main__":
    unittest.main()
