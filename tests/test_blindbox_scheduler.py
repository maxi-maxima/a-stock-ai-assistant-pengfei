import unittest

from core.blindbox_scheduler import (
    build_schtasks_create_args,
    build_task_script_content,
    build_task_command,
    create_windows_task,
)


class BlindboxSchedulerTest(unittest.TestCase):
    def test_build_task_script_contains_runner_and_log(self):
        content = build_task_script_content(
            project_root=r"C:\Repo\gemini",
            python_executable=r"C:\Python\python.exe",
        )
        self.assertIn("blindbox_daily_runner.py\" --once", content)
        self.assertIn(r"logs\blindbox_task.log", content)
        self.assertIn(r"C:\Repo\gemini", content)

    def test_build_task_command_returns_wrapper_path(self):
        cmd = build_task_command(
            project_root=r"C:\Repo\gemini",
            python_executable=r"C:\Python\python.exe",
        )
        self.assertIn(r"run_blindbox_task.bat", cmd)

    def test_build_schtasks_create_args_contains_name_and_time(self):
        args = build_schtasks_create_args(
            task_name="Blindbox",
            start_time="15:20",
            project_root=r"C:\Repo\gemini",
            python_executable=r"C:\Python\python.exe",
        )
        self.assertEqual(args[0], "schtasks")
        self.assertIn("/Create", args)
        self.assertIn("Blindbox", args)
        self.assertIn("15:20", args)

    def test_create_windows_task_uses_runner(self):
        called = {}

        def fake_runner(args, capture_output, text, check):
            called["args"] = args

            class Result:
                returncode = 0
                stdout = "SUCCESS"
                stderr = ""

            return Result()

        out = create_windows_task(
            task_name="Blindbox",
            start_time="15:20",
            project_root=r"C:\Repo\gemini",
            python_executable=r"C:\Python\python.exe",
            runner=fake_runner,
        )
        self.assertTrue(out["ok"])
        self.assertIn("/Create", called["args"])


if __name__ == "__main__":
    unittest.main()
