import copy
import datetime
import json
import os

from core.logger import exception


CONFIG_PATH = "config/news_fetch.json"


def _now_date():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def _default_config():
    return {
        "enabled": False,
        "mode": "composio",
        "tool": "",
        "toolkit_slug": "",
        "toolkit_version": "",
        "toolkit_versions": {},
        "user_id": "default",
        "query_template": "{name} {code} 新闻",
        "query_key": "query",
        "limit_key": "limit",
        "limit": 5,
        "min_items": 2,
        "max_items": 5,
        "merge": "prepend",
        "arguments": {}
    }


def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        return _default_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_config()
        merged = _default_config()
        merged.update(data)
        return merged
    except Exception as exc:
        exception("news_fetch.config_load_failed", exc, {"path": path})
        return _default_config()


def _render_str(text, ctx):
    if not isinstance(text, str):
        return text
    out = text
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _render_args(obj, ctx):
    if isinstance(obj, dict):
        return {k: _render_args(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_render_args(v, ctx) for v in obj]
    if isinstance(obj, tuple):
        return [_render_args(v, ctx) for v in obj]
    return _render_str(obj, ctx)


def should_fetch(state, cfg=None):
    cfg = cfg or load_config()
    if not cfg.get("enabled"):
        return False
    min_items = cfg.get("min_items", 0)
    news = state.get("news_data") if isinstance(state, dict) else None
    if isinstance(news, list) and len(news) >= int(min_items or 0):
        return False
    return True


def build_news_tool_tasks(state, cfg=None):
    cfg = cfg or load_config()
    if not cfg.get("enabled"):
        return []
    if str(cfg.get("mode") or "").lower() != "composio":
        return []
    tool_name = str(cfg.get("tool") or "").strip()
    if not tool_name:
        return []

    market = state.get("market_data", {}) if isinstance(state, dict) else {}
    code = str(state.get("stock_code") or "").strip()
    name = str(market.get("stock_name") or "").strip()
    query = str(cfg.get("query_template") or "{name} {code} 新闻")
    ctx = {
        "code": code,
        "name": name,
        "query": query,
        "date": _now_date()
    }
    query = _render_str(query, ctx)
    args = copy.deepcopy(cfg.get("arguments") or {})
    qk = str(cfg.get("query_key") or "").strip()
    if qk and qk not in args:
        args[qk] = query
    lk = str(cfg.get("limit_key") or "").strip()
    if lk and lk not in args and cfg.get("limit") is not None:
        args[lk] = cfg.get("limit")
    args = _render_args(args, ctx)
    toolkit_versions = cfg.get("toolkit_versions")
    if not isinstance(toolkit_versions, dict):
        toolkit_versions = {}
    toolkit_slug = str(cfg.get("toolkit_slug") or "").strip()
    toolkit_version = str(cfg.get("toolkit_version") or "").strip()
    if toolkit_slug and toolkit_version:
        toolkit_versions = dict(toolkit_versions)
        toolkit_versions[toolkit_slug] = toolkit_version

    task = {
        "tool": "composio_execute",
        "args": {
            "tool": tool_name,
            "arguments": args,
            "user_id": cfg.get("user_id"),
            "toolkit_versions": toolkit_versions if toolkit_versions else None
        },
        "map_to": "news_data",
        "max_items": cfg.get("max_items", cfg.get("limit", 5)),
        "merge": cfg.get("merge", "prepend"),
        "kind": "composio",
        "purpose": "news"
    }
    return [task]


def _extract_text_from_item(item):
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()
    for k in ["title", "headline", "name"]:
        if item.get(k):
            title = str(item.get(k)).strip()
            break
    else:
        title = ""
    for k in ["summary", "description", "snippet", "content"]:
        if item.get(k):
            desc = str(item.get(k)).strip()
            break
    else:
        desc = ""
    if title and desc:
        return f"{title} | {desc}"
    if title:
        return title
    if desc:
        return desc
    # fallback to any string fields
    for k, v in item.items():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def extract_news_items(data, max_items=None):
    items = []
    raw = data
    if isinstance(raw, dict) and "data" in raw and isinstance(raw.get("data"), dict):
        raw = raw.get("data")
    if isinstance(raw, dict):
        for key in ["result", "results", "articles", "items", "news", "news_results", "data"]:
            if key in raw:
                raw = raw.get(key)
                break
    if isinstance(raw, list):
        for it in raw:
            text = _extract_text_from_item(it)
            if text:
                items.append(text)
    elif isinstance(raw, dict):
        text = _extract_text_from_item(raw)
        if text:
            items.append(text)
    elif isinstance(raw, str):
        items.append(raw.strip())
    else:
        items.append(str(raw))

    # dedup + limit
    seen = set()
    out = []
    for it in items:
        if not it:
            continue
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
        if max_items and len(out) >= int(max_items):
            break
    return out


def merge_news(existing, incoming, mode="prepend", max_items=None):
    existing = existing if isinstance(existing, list) else []
    incoming = incoming if isinstance(incoming, list) else []
    if mode == "append":
        merged = existing + incoming
    else:
        merged = incoming + existing
    # dedup
    seen = set()
    out = []
    for it in merged:
        if not it or it in seen:
            continue
        seen.add(it)
        out.append(it)
        if max_items and len(out) >= int(max_items):
            break
    return out
