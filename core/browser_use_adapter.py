import asyncio
import json
import os

from core.env_loader import load_env, is_placeholder_value
from core.logger import exception
from core.tool_registry import get_registry


def _load_secure_settings():
    path = "data/secure_settings.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _pick_value(*vals):
    for v in vals:
        if v is None:
            continue
        try:
            text = str(v).strip()
        except Exception:
            continue
        if not text:
            continue
        if is_placeholder_value(text):
            continue
        return text
    return ""


def _resolve_api_key(explicit=None):
    load_env()
    secure = _load_secure_settings()
    return _pick_value(
        explicit,
        os.getenv("BROWSER_USE_API_KEY"),
        secure.get("browser_use_api_key"),
        secure.get("BROWSER_USE_API_KEY")
    )


async def _run_agent(task, api_key=None, max_steps=60, headless=True, use_cloud=False):
    try:
        from browser_use import Agent, Browser, ChatBrowserUse
    except Exception as exc:
        return {"ok": False, "error": f"browser_use_import_failed:{exc}"}

    key = _resolve_api_key(api_key)
    try:
        llm = ChatBrowserUse(api_key=key) if key else ChatBrowserUse()
    except Exception as exc:
        return {"ok": False, "error": f"browser_use_llm_init_failed:{exc}"}

    try:
        browser = Browser(use_cloud=bool(use_cloud), headless=bool(headless))
    except Exception as exc:
        return {"ok": False, "error": f"browser_use_browser_init_failed:{exc}"}

    agent = Agent(task=task, llm=llm, browser=browser, max_steps=int(max_steps or 60))
    try:
        history = await agent.run()
    except Exception as exc:
        exception("browser_use.run_failed", exc)
        return {"ok": False, "error": str(exc)}

    # Try to summarize output into text
    output = ""
    try:
        final_result = None
        if hasattr(history, "final_result"):
            final_result = history.final_result
            if callable(final_result):
                final_result = final_result()
        elif isinstance(history, dict) and history.get("final_result") is not None:
            final_result = history.get("final_result")
        if final_result:
            output = str(final_result)
        elif isinstance(history, dict) and history.get("result") is not None:
            output = str(history.get("result"))
        elif isinstance(history, list) and history:
            output = str(history[-1])
        else:
            output = str(history)
    except Exception:
        output = str(history)

    return {"ok": True, "output": output, "history": history}


def browser_use_run(args=None):
    args = args if isinstance(args, dict) else {}
    task = str(args.get("task") or args.get("prompt") or "").strip()
    if not task:
        return {"ok": False, "error": "missing_task"}
    max_steps = args.get("max_steps", 60)
    headless = args.get("headless", True)
    use_cloud = args.get("use_cloud", False)
    api_key = args.get("api_key")

    try:
        result = asyncio.run(_run_agent(
            task=task,
            api_key=api_key,
            max_steps=max_steps,
            headless=headless,
            use_cloud=use_cloud
        ))
    except RuntimeError:
        # If we're already in an event loop, fallback
        result = asyncio.get_event_loop().run_until_complete(_run_agent(
            task=task,
            api_key=api_key,
            max_steps=max_steps,
            headless=headless,
            use_cloud=use_cloud
        ))
    return result


def register_browser_use_tool(registry=None):
    registry = registry or get_registry()
    registry.register(
        "browser_use_run",
        browser_use_run,
        meta={
            "kind": "browser_use",
            "description": "Run a browser-use agent task with optional cloud/headless settings."
        }
    )
    return registry
