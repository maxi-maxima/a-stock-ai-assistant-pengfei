import time

from core.event_bus import EventBus
from core.logger import exception
from core.tool_protocol import build_tool_call, build_tool_result, new_trace_id


class ToolRegistry:
    def __init__(self, emit_bus=True):
        self._tools = {}
        self.emit_bus = bool(emit_bus)

    def register(self, name, handler, meta=None):
        if not name or not callable(handler):
            raise ValueError("tool name and handler are required")
        key = str(name).strip()
        self._tools[key] = {"handler": handler, "meta": meta if isinstance(meta, dict) else {}}
        return self._tools[key]

    def has_tool(self, name):
        return str(name or "").strip() in self._tools

    def list_tools(self):
        return [
            {"name": name, **(item.get("meta") or {})}
            for name, item in sorted(self._tools.items(), key=lambda kv: kv[0])
        ]

    def call(
        self,
        name,
        args=None,
        caller=None,
        trace_id=None,
        dry_run=False,
        timeout_s=None,
        tags=None,
        emit_bus=None
    ):
        tool_name = str(name or "").strip()
        trace_id = trace_id or new_trace_id()
        bus = EventBus()
        emit = self.emit_bus if emit_bus is None else bool(emit_bus)
        call_payload = build_tool_call(
            tool=tool_name,
            args=args,
            caller=caller,
            trace_id=trace_id,
            timeout_s=timeout_s,
            dry_run=dry_run,
            tags=tags
        )
        if emit:
            bus.log("tool_call", payload=call_payload, source=caller or "tool_registry")

        start = time.time()
        ok = False
        error = ""
        data = {}
        try:
            entry = self._tools.get(tool_name)
            if not entry:
                raise KeyError(f"tool_not_found:{tool_name}")
            handler = entry.get("handler")
            if dry_run:
                data = {"dry_run": True}
            else:
                result = handler(args if isinstance(args, dict) else {})
                if isinstance(result, dict):
                    data = result
                else:
                    data = {"result": result}
            ok = True
        except Exception as exc:
            error = str(exc)
            exception("tool_registry.call_failed", exc, {"tool": tool_name})

        latency_ms = int((time.time() - start) * 1000)
        result_payload = build_tool_result(
            tool=tool_name,
            ok=ok,
            data=data,
            error=error,
            caller=caller,
            trace_id=trace_id,
            latency_ms=latency_ms
        )
        if emit:
            bus.log("tool_result", payload=result_payload, source=caller or "tool_registry")
        return result_payload


_DEFAULT_REGISTRY = None


def get_registry():
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ToolRegistry()
    return _DEFAULT_REGISTRY


def register_tool(name, handler, meta=None):
    return get_registry().register(name, handler, meta=meta)


def call_tool(name, args=None, caller=None, **kwargs):
    return get_registry().call(name, args=args, caller=caller, **kwargs)
