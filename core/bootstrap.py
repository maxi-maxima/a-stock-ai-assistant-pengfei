from core.env_loader import load_env
from core.utf8 import ensure_utf8


def init_runtime():
    # Load .env first so model keys are available early.
    load_env()
    ensure_utf8()
