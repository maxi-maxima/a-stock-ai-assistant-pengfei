import os
import time
import importlib.util

class SystemDoctor:
    def __init__(self):
        self.root_dir = os.getcwd()

    def run_full_diagnosis(self):
        """运行全系统诊断"""
        report = []
        
        # 1. 核心文件检查
        core_files = {
            "core/tri_brain.py": "三脑决策核心",
            "core/memory.py": "记忆存储系统",
            "core/portfolio.py": "资产管理核心",
            "core/cognitive_graph.py": "认知决策流",
            "skills/scanner.py": "市场扫描雷达",
            "skills/data_factory.py": "数据工厂接口",
            "dashboard.py": "主控台入口"
        }
        
        for path, desc in core_files.items():
            full_path = os.path.join(self.root_dir, path)
            if os.path.exists(full_path):
                report.append({"module": desc, "status": "OK", "message": f"文件存在: {path}"})
            else:
                report.append({"module": desc, "status": "ERROR", "message": f"❌ 缺失关键文件: {path}"})

        # 2. 目录结构检查
        dirs = ["data", "config", "skills", "core", "ui/modules"]
        for d in dirs:
            if os.path.exists(os.path.join(self.root_dir, d)):
                report.append({"module": f"目录-{d}", "status": "OK", "message": "目录结构正常"})
            else:
                report.append({"module": f"目录-{d}", "status": "WARNING", "message": "目录缺失，建议新建"})

        # 3. 依赖库检查 (模拟)
        libs = ["streamlit", "pandas", "tushare", "plotly", "openai"]
        for lib in libs:
            if importlib.util.find_spec(lib):
                report.append({"module": f"依赖库-{lib}", "status": "OK", "message": "已安装"})
            else:
                report.append({"module": f"依赖库-{lib}", "status": "WARNING", "message": "未检测到库，可能导致运行报错"})

        return report