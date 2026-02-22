import os
import sys
import shutil
import multiprocessing as mp
import socket
import threading
import time
import traceback
import webbrowser
import io
import urllib.request
import urllib.error


def _is_frozen():
    return bool(getattr(sys, "frozen", False))


def _bundle_root():
    if _is_frozen() and hasattr(sys, "_MEIPASS"):
        return os.path.abspath(sys._MEIPASS)
    return os.path.dirname(os.path.abspath(__file__))


def _app_root():
    env_root = os.getenv("APP_HOME")
    if env_root:
        return os.path.abspath(env_root)
    if _is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _fallback_root():
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "KIMIstock", "stock_agent")


def _is_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return True
    except Exception:
        return False


def _select_app_root():
    primary = _app_root()
    if _is_writable(primary):
        return primary
    fallback = _fallback_root()
    if _is_writable(fallback):
        return fallback
    return primary


def _same_path(a, b):
    try:
        return os.path.abspath(a) == os.path.abspath(b)
    except Exception:
        return False


def _copytree_if_missing(src, dst):
    if not os.path.exists(src):
        return
    if os.path.exists(dst):
        return
    shutil.copytree(src, dst)


def _copyfile_if_missing(src, dst):
    if not os.path.exists(src):
        return
    if os.path.exists(dst):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def _prepare_app_home():
    bundle_root = _bundle_root()
    app_root = _select_app_root()
    os.makedirs(app_root, exist_ok=True)
    os.environ["APP_HOME"] = app_root

    for name in ("config", "data"):
        src = os.path.join(bundle_root, name)
        dst = os.path.join(app_root, name)
        if _same_path(src, dst):
            continue
        _copytree_if_missing(src, dst)

    os.makedirs(os.path.join(app_root, "config"), exist_ok=True)
    os.makedirs(os.path.join(app_root, "data"), exist_ok=True)

    for name in (".env", ".env.example"):
        src = os.path.join(bundle_root, name)
        dst = os.path.join(app_root, name)
        if _same_path(src, dst):
            continue
        _copyfile_if_missing(src, dst)

    return app_root, bundle_root


def _log_path(app_root):
    return os.path.join(app_root, "startup.log")


def _log(app_root, msg):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(_log_path(app_root), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


class _Tee(io.TextIOBase):
    def __init__(self, *streams):
        self._streams = [s for s in streams if s]
        self.encoding = getattr(self._streams[0], "encoding", "utf-8") if self._streams else "utf-8"

    def write(self, s):
        for stream in self._streams:
            try:
                stream.write(s)
                stream.flush()
            except Exception:
                pass
        return len(s)

    def flush(self):
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:
                pass


def _pick_port(start=8501, end=8515):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _open_browser_later(url, delay=1.5):
    def _open():
        try:
            webbrowser.open(url)
        except Exception:
            pass
    t = threading.Timer(delay, _open)
    t.daemon = True
    t.start()


def _is_port_open(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except Exception:
        return False


def _is_streamlit_alive(port):
    try:
        url = f"http://127.0.0.1:{port}/_stcore/health"
        with urllib.request.urlopen(url, timeout=0.6) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ensure_streamlit_config(app_root, port):
    cfg_dir = os.path.join(app_root, ".streamlit")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_path = os.path.join(cfg_dir, "config.toml")
    cfg = [
        "[global]",
        "developmentMode = false",
        "",
        "[server]",
        "headless = true",
        f"port = {int(port)}",
        "",
        "[browser]",
        "gatherUsageStats = false",
        "",
    ]
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("\n".join(cfg))
        return cfg_path
    except Exception:
        return ""


def main():
    app_root, bundle_root = _prepare_app_home()

    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("STREAMLIT_LOG_LEVEL", "debug")

    os.chdir(app_root)
    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    if bundle_root not in sys.path:
        sys.path.insert(0, bundle_root)

    import streamlit.web.cli as stcli

    target = os.path.join(bundle_root, "dashboard.py") if _is_frozen() else os.path.join(app_root, "dashboard.py")
    env_port = os.getenv("APP_PORT") or os.getenv("STREAMLIT_PORT")
    port = int(env_port) if env_port and env_port.isdigit() else 8501
    open_browser = os.getenv("APP_OPEN_BROWSER", "1") != "0"
    log_path = _log_path(app_root)
    try:
        log_file = open(log_path, "a", encoding="utf-8")
        sys.stdout = _Tee(sys.stdout, log_file)
        sys.stderr = _Tee(sys.stderr, log_file)
    except Exception:
        log_file = None

    _log(app_root, f"bundle_root={bundle_root}")
    _log(app_root, f"app_root={app_root}")
    _log(app_root, f"target={target}")
    _log(app_root, f"port={port}")
    _log(app_root, f"frozen={_is_frozen()}")

    # If an instance is already running on the target port, just open browser and exit.
    if _is_port_open(port) and _is_streamlit_alive(port):
        _log(app_root, f"existing_instance=1 port={port}")
        _open_browser_later(f"http://localhost:{port}", delay=0.5)
        return

    # If port is occupied but not healthy, try another port.
    if _is_port_open(port) and not _is_streamlit_alive(port):
        new_port = _pick_port(start=8502, end=8515)
        _log(app_root, f"port_in_use=1 fallback_port={new_port}")
        port = new_port

    cfg_path = _ensure_streamlit_config(app_root, port)
    if cfg_path:
        _log(app_root, f"config={cfg_path}")
    _log(app_root, f"target_exists={os.path.exists(target)}")

    sys.argv = [
        "streamlit",
        "run",
        target,
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--logger.level",
        "debug",
    ]

    if open_browser:
        _open_browser_later(f"http://localhost:{port}")

    try:
        stcli.main()
    except SystemExit as e:
        _log(app_root, f"SystemExit: {e}")
        raise
    except Exception:
        _log(app_root, "Exception in streamlit:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    mp.freeze_support()
    try:
        main()
    except Exception:
        try:
            app_root = os.getenv("APP_HOME") or os.path.dirname(os.path.abspath(sys.executable))
            _log(app_root, "Fatal error:\n" + traceback.format_exc())
        except Exception:
            pass
        raise
