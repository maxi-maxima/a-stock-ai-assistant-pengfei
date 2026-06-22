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
        os.getenv("COMPOSIO_API_KEY"),
        secure.get("composio_api_key"),
        secure.get("COMPOSIO_API_KEY")
    )


def _normalize_list(val):
    if val is None:
        return None
    if isinstance(val, (list, tuple, set)):
        return [str(v).strip() for v in val if str(v).strip()]
    text = str(val).strip()
    return [text] if text else None


def _tool_to_dict(tool):
    if isinstance(tool, dict):
        return tool
    if hasattr(tool, "model_dump"):
        try:
            return tool.model_dump()
        except Exception:
            pass
    if hasattr(tool, "dict"):
        try:
            return tool.dict()
        except Exception:
            pass
    name = getattr(tool, "name", None) or getattr(tool, "tool_name", None)
    if name:
        return {"name": str(name)}
    return {"raw": str(tool)}


def get_composio_client(api_key=None, toolkit_versions=None, skip_version_check=None):
    try:
        from composio import Composio
    except Exception as exc:
        return None, f"composio_import_failed:{exc}"
    key = _resolve_api_key(api_key)
    try:
        kwargs = {}
        if toolkit_versions and isinstance(toolkit_versions, dict):
            kwargs["toolkit_versions"] = toolkit_versions
        if skip_version_check is not None:
            kwargs["dangerously_skip_version_check"] = bool(skip_version_check)
        if key:
            return Composio(api_key=key, **kwargs), ""
        return Composio(**kwargs), ""
    except Exception as exc:
        return None, f"composio_init_failed:{exc}"


def composio_list_tools(args=None):
    args = args if isinstance(args, dict) else {}
    client, err = get_composio_client(
        args.get("api_key"),
        toolkit_versions=args.get("toolkit_versions"),
        skip_version_check=args.get("skip_version_check")
    )
    if not client:
        return {"ok": False, "error": err}
    user_id = str(args.get("user_id") or "default").strip()
    toolkits = _normalize_list(args.get("toolkits"))
    tools = _normalize_list(args.get("tools"))
    search = args.get("search")
    limit = args.get("limit")
    try:
        kwargs = {"user_id": user_id}
        if toolkits:
            kwargs["toolkits"] = toolkits
        if tools:
            kwargs["tools"] = tools
        if search:
            kwargs["search"] = str(search)
        if limit is not None:
            try:
                kwargs["limit"] = int(limit)
            except Exception:
                pass
        result = client.tools.get(**kwargs)
    except Exception as exc:
        exception("composio.list_failed", exc)
        return {"ok": False, "error": str(exc)}
    items = []
    if isinstance(result, (list, tuple)):
        for t in result:
            items.append(_tool_to_dict(t))
    elif result is not None:
        items.append(_tool_to_dict(result))
    return {"ok": True, "user_id": user_id, "count": len(items), "tools": items}


def composio_execute(args=None):
    args = args if isinstance(args, dict) else {}
    client, err = get_composio_client(
        args.get("api_key"),
        toolkit_versions=args.get("toolkit_versions"),
        skip_version_check=args.get("skip_version_check")
    )
    if not client:
        return {"ok": False, "error": err}
    tool_name = (
        args.get("tool")
        or args.get("tool_name")
        or args.get("name")
    )
    if not tool_name:
        return {"ok": False, "error": "missing_tool_name"}
    user_id = str(args.get("user_id") or "default").strip()
    arguments = args.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    try:
        result = client.tools.execute(tool_name, arguments, user_id=user_id)
    except Exception as exc:
        exception("composio.execute_failed", exc)
        return {"ok": False, "error": str(exc)}
    if isinstance(result, dict):
        return {"ok": True, "user_id": user_id, "result": result}
    return {"ok": True, "user_id": user_id, "result": {"raw": str(result)}}


def register_composio_tools(registry=None):
    registry = registry or get_registry()
    registry.register(
        "composio_list_tools",
        composio_list_tools,
        meta={
            "kind": "composio",
            "description": "List tools from Composio (filters: toolkits/tools)."
        }
    )
    registry.register(
        "composio_execute",
        composio_execute,
        meta={
            "kind": "composio",
            "description": "Execute a Composio tool by name with arguments."
        }
    )
    return registry
