import os
import sys
import json
import time
import importlib.util

from core.bootstrap import init_runtime
init_runtime()

# --- 颜色代码，让黑窗口好看点 ---
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

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

def main():
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

if __name__ == "__main__":
    main()
