import py_compile
import unittest
from pathlib import Path


class TacticsModuleCompileTest(unittest.TestCase):
    def test_tactics_module_compiles(self):
        root = Path(__file__).resolve().parents[1]
        target = root / "ui" / "modules" / "tactics.py"
        py_compile.compile(str(target), doraise=True)


if __name__ == "__main__":
    unittest.main()
