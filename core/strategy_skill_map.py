import json
import os

from core.knowledge_base import KnowledgeBase

MAP_PATH = "config/strategy_skill_map.json"
TAG_PATH = "config/strategy_skill_tags.json"

DEFAULT_SKILL_STRATEGY_MAP = {
    "trend": ["skill_trend_system"],
    "oscillator": ["skill_oscillator_combo"],
    "volume": ["skill_volume_confirm"],
    "pattern": ["skill_pattern_breakout"],
    "multi-timeframe": ["skill_multi_timeframe_proxy"],
    "risk": ["skill_risk_guard"]
}


def _normalize_map(mapping):
    out = {}
    if not isinstance(mapping, dict):
        return dict(DEFAULT_SKILL_STRATEGY_MAP)
    for k, v in mapping.items():
        key = str(k).strip()
        if not key:
            continue
        items = []
        if isinstance(v, list):
            items = [str(x).strip() for x in v if str(x).strip()]
        elif isinstance(v, str):
            items = [x.strip() for x in v.split(",") if x.strip()]
        if items:
            out[key] = items
    if not out:
        out = dict(DEFAULT_SKILL_STRATEGY_MAP)
    return out


def load_skill_strategy_map(path=MAP_PATH):
    if not os.path.exists(path):
        return dict(DEFAULT_SKILL_STRATEGY_MAP)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _normalize_map(data)
    except Exception:
        return dict(DEFAULT_SKILL_STRATEGY_MAP)


def save_skill_strategy_map(mapping, path=MAP_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_normalize_map(mapping), f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_skill_tags(path=TAG_PATH):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            tags = data.get("active_tags", [])
        else:
            tags = data
        if isinstance(tags, list):
            return [str(t).strip() for t in tags if str(t).strip()]
    except Exception:
        return []
    return []


def save_skill_tags(tags, path=TAG_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        payload = {"active_tags": [str(t).strip() for t in (tags or []) if str(t).strip()]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _tags_to_list(tags):
    if tags is None:
        return []
    if isinstance(tags, (list, tuple, set)):
        return [str(t).strip() for t in tags if str(t).strip()]
    text = str(tags)
    for sep in [",", ";", "|", "/", " ", "\uFF0C", "\uFF1B", "\u3001"]:
        text = text.replace(sep, ",")
    return [t.strip() for t in text.split(",") if t.strip()]


def get_skill_tags_from_kb():
    mapping = load_skill_strategy_map()
    allowed = set(mapping.keys())
    try:
        kb = KnowledgeBase()
        items = kb.get_all_knowledge()
    except Exception:
        return []
    tags = []
    for item in items:
        tag_list = _tags_to_list(item.get("tags"))
        if "skill_summary" not in tag_list:
            continue
        for t in tag_list:
            if t in allowed:
                tags.append(t)
    # de-dup
    out = []
    seen = set()
    for t in tags:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def resolve_active_tags():
    tags = load_skill_tags()
    if tags:
        return tags
    tags = get_skill_tags_from_kb()
    if tags:
        return tags
    return list(load_skill_strategy_map().keys())


def strategies_from_tags(tags, mapping=None):
    mapping = mapping if mapping is not None else load_skill_strategy_map()
    if not tags:
        return []
    out = []
    seen = set()
    for t in tags:
        for s in mapping.get(t, []) or []:
            name = str(s).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
    return out
