import os
import sys
import json
import time
import importlib.util
import argparse

from core.bootstrap import init_runtime
init_runtime()

# --- 颜色代码，让黑窗口好看点 ---
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

DEPENDENCY_MODULES = [
    "pandas",
    "streamlit",
    "plotly",
    "tushare",
    "akshare",
]

CRITICAL_FILES = [
    "dashboard.py",
    "ui/modules/tactics.py",
    "ui/modules/radar.py",
    "core/portfolio.py",
    "core/strategy_library.py",
    "core/memory.py",
    "skills/scanner.py",
    "skills/dealer_hunter.py",
]

DATA_FILES = [
    "data/real_portfolio.json",
    "data/paper_portfolio.json",
    "data/my_strategies.json",
    "data/knowledge_base.json",
]

MODULE_CHECKS = [
    ("core.strategy_library", "core/strategy_library.py"),
    ("skills.scanner", "skills/scanner.py"),
]

def log(status, msg):
    if status == "OK":
        print(f"[{GREEN} OK {RESET}] {msg}")
    elif status == "ERR":
        print(f"[{RED}FAIL{RESET}] {msg}")
    elif status == "WARN":
        print(f"[{YELLOW}WARN{RESET}] {msg}")
    else:
        print(f"[INFO] {msg}")

def check_file_exists(path):
    if os.path.exists(path):
        log("OK", f"文件存在: {path}")
        return True
    else:
        log("ERR", f"文件缺失: {path}")
        return False

def check_json_valid(path):
    if not os.path.exists(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            json.load(f)
        log("OK", f"数据格式正常: {path}")
        return True
    except json.JSONDecodeError:
        log("ERR", f"数据文件损坏 (JSON格式错误): {path}")
        return False
    except Exception as e:
        log("ERR", f"无法读取文件 {path}: {e}")
        return False

def check_import(module_name, file_path=None):
    try:
        # 如果指定了路径，尝试动态加载文件
        if file_path:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                log("OK", f"模块加载成功: {module_name} ({file_path})")
                return True
            else:
                log("ERR", f"无法找到模块规范: {file_path}")
                return False
        else:
            # 普通 import
            __import__(module_name)
            log("OK", f"库已安装: {module_name}")
            return True
    except ImportError:
        log("ERR", f"缺少依赖库: {module_name} (请运行 pip install {module_name})")
        return False
    except Exception as e:
        log("ERR", f"模块代码有错 {module_name}: {e}")
        return False

def collect_diagnostics(
    root=None,
    dependency_modules=None,
    critical_files=None,
    data_files=None,
    module_checks=None,
):
    root = os.fspath(root or os.getcwd())
    dependency_modules = dependency_modules if dependency_modules is not None else DEPENDENCY_MODULES
    critical_files = critical_files if critical_files is not None else CRITICAL_FILES
    data_files = data_files if data_files is not None else DATA_FILES
    module_checks = module_checks if module_checks is not None else MODULE_CHECKS

    checks = []
    checks.extend(_dependency_check(module_name) for module_name in dependency_modules)
    checks.extend(_file_check(root, file_path) for file_path in critical_files)
    checks.extend(_data_file_check(root, file_path) for file_path in data_files)
    checks.extend(_module_file_check(root, module_name, file_path) for module_name, file_path in module_checks)

    summary = {
        "total": len(checks),
        "passed": sum(1 for check in checks if check["status"] == "ok"),
        "failed": sum(1 for check in checks if check["status"] == "fail"),
        "warnings": sum(1 for check in checks if check["status"] == "warn"),
        "missing_files": sum(1 for check in checks if check.get("kind") == "file" and check.get("reason") == "missing"),
        "missing_dependencies": sum(1 for check in checks if check.get("kind") == "dependency" and check.get("reason") == "missing"),
    }
    return {
        "ok": summary["failed"] == 0,
        "summary": summary,
        "checks": checks,
    }


def render_markdown_report(report):
    summary = report["summary"]
    status = "PASS" if report["ok"] else "FAIL"
    lines = [
        "# AI Trading Avatar Doctor Report",
        "",
        f"Status: **{status}**",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total | {summary['total']} |",
        f"| Passed | {summary['passed']} |",
        f"| Failed | {summary['failed']} |",
        f"| Warnings | {summary['warnings']} |",
        f"| Missing files | {summary['missing_files']} |",
        f"| Missing dependencies | {summary['missing_dependencies']} |",
        "",
        "## Checks",
        "",
        "| Kind | Target | Status | Reason |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        target = check.get("path") or check.get("name") or "-"
        reason = check.get("reason") or "-"
        lines.append(f"| {check['kind']} | {target} | {check['status']} | {reason} |")
    lines.extend([
        "",
        "_Generated by `python doctor.py --markdown`._",
        "",
    ])
    return "\n".join(lines)


def _dependency_check(module_name):
    try:
        __import__(module_name)
        return {"kind": "dependency", "name": module_name, "status": "ok"}
    except ImportError as exc:
        return {"kind": "dependency", "name": module_name, "status": "fail", "reason": "missing", "message": str(exc)}
    except Exception as exc:
        return {"kind": "dependency", "name": module_name, "status": "fail", "reason": "error", "message": str(exc)}


def _file_check(root, file_path):
    exists = os.path.exists(os.path.join(root, file_path))
    return {
        "kind": "file",
        "path": file_path,
        "status": "ok" if exists else "fail",
        "reason": "exists" if exists else "missing",
    }


def _data_file_check(root, file_path):
    full_path = os.path.join(root, file_path)
    if not os.path.exists(full_path):
        return {
            "kind": "data_file",
            "path": file_path,
            "status": "warn",
            "reason": "not_created",
        }
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            json.load(f)
        return {"kind": "data_file", "path": file_path, "status": "ok"}
    except json.JSONDecodeError as exc:
        return {"kind": "data_file", "path": file_path, "status": "fail", "reason": "invalid_json", "message": str(exc)}
    except Exception as exc:
        return {"kind": "data_file", "path": file_path, "status": "fail", "reason": "read_error", "message": str(exc)}


def _module_file_check(root, module_name, file_path):
    full_path = os.path.join(root, file_path)
    try:
        spec = importlib.util.spec_from_file_location(module_name, full_path)
        if not spec or not spec.loader:
            return {"kind": "module", "name": module_name, "path": file_path, "status": "fail", "reason": "missing_spec"}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {"kind": "module", "name": module_name, "path": file_path, "status": "ok"}
    except ImportError as exc:
        return {"kind": "module", "name": module_name, "path": file_path, "status": "fail", "reason": "missing_import", "message": str(exc)}
    except Exception as exc:
        return {"kind": "module", "name": module_name, "path": file_path, "status": "fail", "reason": "error", "message": str(exc)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run project health checks.")
    parser.add_argument("--json", action="store_true", help="write a machine-readable diagnostic report")
    parser.add_argument("--markdown", action="store_true", help="write a GitHub issue-ready diagnostic report")
    args = parser.parse_args(argv)

    if args.json:
        report = collect_diagnostics()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    if args.markdown:
        report = collect_diagnostics()
        print(render_markdown_report(report))
        return 0 if report["ok"] else 1

    print("="*50)
    print(" AI 系统独立急救医生 (Standalone Doctor)")
    print("="*50)
    print("正在进行尸检级扫描...\n")

    # 1. 环境检查
    print(f"{YELLOW}--- 1. Python 环境检查 ---{RESET}")
    check_import("pandas")
    check_import("streamlit")
    check_import("plotly")
    check_import("tushare")
    check_import("akshare")

    # 2. 核心文件结构检查
    print(f"\n{YELLOW}--- 2. 核心骨架检查 ---{RESET}")
    critical_files = [
        "dashboard.py",
        "ui/modules/tactics.py",
        "ui/modules/radar.py",
        "core/portfolio.py",
        "core/strategy_library.py",
        "core/memory.py",
        "skills/scanner.py",
        "skills/dealer_hunter.py"
    ]
    
    missing_count = 0
    for f in critical_files:
        if not check_file_exists(f):
            missing_count += 1
            
    # 3. 数据健康度检查
    print(f"\n{YELLOW}--- 3. 数据血液检查 ---{RESET}")
    data_files = [
        "data/real_portfolio.json",
        "data/paper_portfolio.json",
        "data/my_strategies.json", # 策略库
        "data/knowledge_base.json"
    ]
    for f in data_files:
        if os.path.exists(f):
            check_json_valid(f)
        else:
            log("WARN", f"数据文件未生成 (系统运行后会自动创建): {f}")

    # 4. 代码逻辑试运行 (沙盒测试)
    print(f"\n{YELLOW}--- 4. 核心逻辑试运行 ---{RESET}")
    # 尝试加载几个容易报错的模块
    check_import("core.strategy_library", "core/strategy_library.py")
    check_import("skills.scanner", "skills/scanner.py")

    print("="*50)
    if missing_count == 0:
        print(f"{GREEN}诊断结论: 系统骨架完整。如果无法启动，请检查报错截图。{RESET}")
    else:
        print(f"{RED}诊断结论: 发现 {missing_count} 个核心文件缺失！系统肯定无法启动。{RESET}")
    print("="*50)
    try:
        if sys.stdin.isatty():
            input("按回车键退出...")
    except EOFError:
        pass
    return 0 if missing_count == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
