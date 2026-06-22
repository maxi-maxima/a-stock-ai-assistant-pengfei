import json
import os
import subprocess
import sys


DEFAULT_TASK_NAME = "BlindboxPaperLoop"
DEFAULT_START_TIME = "15:05"
DEFAULT_CONFIG_PATH = "config/blindbox_scheduler.json"
DEFAULT_TASK_SCRIPT_PATH = "tools/run_blindbox_task.bat"
DEFAULT_LOG_PATH = "logs/blindbox_task.log"


def load_scheduler_config(path=DEFAULT_CONFIG_PATH):
    default = {"task_name": DEFAULT_TASK_NAME, "start_time": DEFAULT_START_TIME, "enabled": True}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            default.update(data)
    except Exception:
        pass
    return default


def save_scheduler_config(config, path=DEFAULT_CONFIG_PATH):
    payload = load_scheduler_config(path)
    if isinstance(config, dict):
        payload.update(config)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def build_task_script_content(project_root=None, python_executable=None, log_path=None):
    project_root = os.path.abspath(project_root or os.getcwd())
    python_executable = os.path.abspath(python_executable or sys.executable)
    log_path = os.path.abspath(log_path or os.path.join(project_root, DEFAULT_LOG_PATH))
    runner_path = os.path.abspath(os.path.join(project_root, "tools", "blindbox_daily_runner.py"))
    return "\n".join(
        [
            "@echo off",
            "setlocal",
            f'cd /d "{project_root}"',
            "set PYTHONIOENCODING=utf-8",
            f'"{python_executable}" "{runner_path}" --once >> "{log_path}" 2>&1',
            "endlocal",
            "",
        ]
    )


def ensure_task_script(project_root=None, python_executable=None, script_path=None, log_path=None):
    project_root = os.path.abspath(project_root or os.getcwd())
    script_path = os.path.abspath(script_path or os.path.join(project_root, DEFAULT_TASK_SCRIPT_PATH))
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(log_path or os.path.join(project_root, DEFAULT_LOG_PATH))), exist_ok=True)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(build_task_script_content(project_root=project_root, python_executable=python_executable, log_path=log_path))
    return script_path


def build_task_command(project_root=None, python_executable=None, task_script_path=None, log_path=None):
    project_root = os.path.abspath(project_root or os.getcwd())
    task_script_path = os.path.abspath(task_script_path or os.path.join(project_root, DEFAULT_TASK_SCRIPT_PATH))
    if not os.path.exists(task_script_path):
        ensure_task_script(project_root=project_root, python_executable=python_executable, script_path=task_script_path, log_path=log_path)
    return f'"{task_script_path}"'


def build_schtasks_create_args(task_name=DEFAULT_TASK_NAME, start_time=DEFAULT_START_TIME, project_root=None, python_executable=None, task_script_path=None, log_path=None):
    command = build_task_command(project_root=project_root, python_executable=python_executable, task_script_path=task_script_path, log_path=log_path)
    return ["schtasks", "/Create", "/SC", "DAILY", "/TN", str(task_name), "/TR", command, "/ST", str(start_time), "/F"]


def create_windows_task(task_name=DEFAULT_TASK_NAME, start_time=DEFAULT_START_TIME, project_root=None, python_executable=None, task_script_path=None, log_path=None, runner=None):
    runner = runner or subprocess.run
    args = build_schtasks_create_args(task_name=task_name, start_time=start_time, project_root=project_root, python_executable=python_executable, task_script_path=task_script_path, log_path=log_path)
    result = runner(args, capture_output=True, text=True, check=False)
    return {"ok": int(getattr(result, "returncode", 1) or 0) == 0, "returncode": int(getattr(result, "returncode", 1) or 0), "stdout": getattr(result, "stdout", "") or "", "stderr": getattr(result, "stderr", "") or "", "args": args}


def delete_windows_task(task_name=DEFAULT_TASK_NAME, runner=None):
    runner = runner or subprocess.run
    args = ["schtasks", "/Delete", "/TN", str(task_name), "/F"]
    result = runner(args, capture_output=True, text=True, check=False)
    return {"ok": int(getattr(result, "returncode", 1) or 0) == 0, "returncode": int(getattr(result, "returncode", 1) or 0), "stdout": getattr(result, "stdout", "") or "", "stderr": getattr(result, "stderr", "") or "", "args": args}


def query_windows_task(task_name=DEFAULT_TASK_NAME, runner=None):
    runner = runner or subprocess.run
    args = ["schtasks", "/Query", "/TN", str(task_name), "/FO", "LIST", "/V"]
    result = runner(args, capture_output=True, text=True, check=False)
    return {"ok": int(getattr(result, "returncode", 1) or 0) == 0, "returncode": int(getattr(result, "returncode", 1) or 0), "stdout": getattr(result, "stdout", "") or "", "stderr": getattr(result, "stderr", "") or "", "args": args}
