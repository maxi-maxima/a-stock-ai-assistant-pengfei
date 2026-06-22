from core.env_loader import load_env
from core.utf8 import ensure_utf8
from core.capability_registry import get_capability


def init_runtime():
    # Load .env first so model keys are available early.
    load_env()
    ensure_utf8()
    try:
        cap = get_capability("tools", "composio")
        if isinstance(cap, dict) and cap.get("enabled"):
            from core.composio_adapter import register_composio_tools
            register_composio_tools()
    except Exception:
        pass
    try:
        cap = get_capability("tools", "browser_use")
        if isinstance(cap, dict) and cap.get("enabled"):
            from core.browser_use_adapter import register_browser_use_tool
            register_browser_use_tool()
    except Exception:
        pass
    try:
        cap = get_capability("orchestrators", "autogen")
        if isinstance(cap, dict) and cap.get("enabled"):
            from core.autogen_orchestrator import register_autogen_tool
            register_autogen_tool()
    except Exception:
        pass
    try:
        cap = get_capability("optimizers", "agent_lightning")
        if isinstance(cap, dict) and cap.get("enabled"):
            from core.agent_lightning_adapter import register_agent_lightning_tool
            register_agent_lightning_tool()
    except Exception:
        pass
