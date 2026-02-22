import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
SRC_STAGE = BUILD / "src"
OBF_DIR = BUILD / "obf"
ASSETS_DIR = BUILD / "assets"
PYI_WORK = BUILD / "pyi_build"
PYI_SPEC = BUILD / "pyi_spec"
DIST_DIR = ROOT / "dist"
OBF_MODE = os.getenv("OBF_MODE", "none").strip().lower()
BUILD_CONSOLE = os.getenv("BUILD_CONSOLE", "0").strip() == "1"


def run(cmd, cwd=None):
    print(">", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, cwd=cwd)


def clean_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copytree(src: Path, dst: Path):
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def stage_sources():
    clean_dir(SRC_STAGE)
    for name in ["core", "ui", "modules", "skills"]:
        copytree(ROOT / name, SRC_STAGE / name)

    for fname in ["dashboard.py", "run_app.py", "__init__.py"]:
        src = ROOT / fname
        if src.exists():
            shutil.copy2(src, SRC_STAGE / fname)


def stage_assets():
    clean_dir(ASSETS_DIR)

    cfg_src = ROOT / "config"
    cfg_dst = ASSETS_DIR / "config"
    copytree(cfg_src, cfg_dst)

    lic_path = cfg_dst / "license.json"
    if lic_path.exists():
        lic_path.unlink()

    data_dst = ASSETS_DIR / "data"
    data_dst.mkdir(parents=True, exist_ok=True)
    (data_dst / "__init__.py").write_text("", encoding="utf-8")
    (data_dst / "cache").mkdir(parents=True, exist_ok=True)
    (data_dst / "chroma_db").mkdir(parents=True, exist_ok=True)


def _find_pyarmor_cli():
    candidates = []
    if os.name == "nt":
        candidates += [
            Path(sys.executable).with_name("pyarmor.exe"),
            Path(sys.executable).with_name("pyarmor.cmd"),
            Path(sys.executable).with_name("pyarmor.bat"),
        ]
    else:
        candidates.append(Path(sys.executable).with_name("pyarmor"))
    for c in candidates:
        if c.exists():
            return str(c)
    which = shutil.which("pyarmor")
    if which:
        return which
    return None


def obfuscate():
    clean_dir(OBF_DIR)
    cli = _find_pyarmor_cli()
    if cli:
        cmd = [cli, "gen", "-O", str(OBF_DIR), "-r", str(SRC_STAGE)]
    else:
        cmd = [
            sys.executable,
            "-m",
            "pyarmor.cli",
            "gen",
            "-O",
            str(OBF_DIR),
            "-r",
            str(SRC_STAGE),
        ]
    run(cmd)


def prepare_code_root():
    if OBF_MODE == "pyarmor":
        obfuscate()
        return OBF_DIR / SRC_STAGE.name
    return SRC_STAGE


def build_exe(code_root: Path):
    clean_dir(PYI_WORK)
    clean_dir(PYI_SPEC)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    def add_data(src: Path, dest: str):
        sep = ";" if os.name == "nt" else ":"
        return f"{src}{sep}{dest}"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console" if BUILD_CONSOLE else "--noconsole",
        "--clean",
        "--name",
        "KIMIstock",
        "--workpath",
        str(PYI_WORK),
        "--specpath",
        str(PYI_SPEC),
        "--distpath",
        str(DIST_DIR),
        "--paths",
        str(code_root),
        "--add-data",
        add_data(code_root, "."),
        "--add-data",
        add_data(ASSETS_DIR / "config", "config"),
        "--add-data",
        add_data(ASSETS_DIR / "data", "data"),
    ]

    env_file = ROOT / ".env"
    if env_file.exists():
        cmd += ["--add-data", add_data(env_file, ".")]

    env_example = ROOT / ".env.example"
    if env_example.exists():
        cmd += ["--add-data", add_data(env_example, ".")]

    for pkg in [
        "streamlit",
        "altair",
        "plotly",
        "chromadb",
        "sentence_transformers",
        "langgraph",
        "akshare",
        "tushare",
    ]:
        cmd += ["--collect-all", pkg]

    cmd.append(str(code_root / "run_app.py"))
    run(cmd)


def main():
    stage_sources()
    stage_assets()
    code_root = prepare_code_root()
    build_exe(code_root)
    print("Build finished:", DIST_DIR / "KIMIstock.exe")


if __name__ == "__main__":
    main()
