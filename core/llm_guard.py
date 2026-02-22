import json
import os
import re
import datetime
import ast


LOG_PATH = "data/llm_logs.jsonl"


def _ensure_dir():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


def _truncate(text, limit=2000):
    if not isinstance(text, str):
        return ""
    return text if len(text) <= limit else text[:limit] + "..."


def clean_json_text(raw):
    if not raw:
        return ""
    txt = raw.strip()
    # Extract code block
    if "```json" in txt:
        txt = txt.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in txt:
        txt = txt.split("```", 1)[0]

    # Extract first {...} block
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if m:
        return m.group(0)
    return txt


def parse_json_safe(raw):
    cleaned = clean_json_text(raw)
    if not cleaned:
        return None, cleaned
    try:
        return json.loads(cleaned), cleaned
    except Exception:
        pass
    # fallback: python literal
    try:
        obj = ast.literal_eval(cleaned)
        if isinstance(obj, dict):
            return obj, cleaned
    except Exception:
        pass
    return None, cleaned


def _sanitize_scores(scores):
    defaults = {
        "capital": 50, "technical": 50, "macro": 50, "news": 50,
        "memory": 50, "knowledge": 50, "total": 50, "reason": ""
    }
    if not isinstance(scores, dict):
        return defaults
    out = {}
    for k, v in defaults.items():
        if k == "reason":
            out[k] = str(scores.get(k, v)) if scores.get(k) is not None else v
        else:
            try:
                out[k] = float(scores.get(k, v))
            except Exception:
                out[k] = v
            out[k] = max(0, min(100, out[k]))
    return out


def _sanitize_grid(grid):
    defaults = {
        "note": "",
        "buy1_price": "", "buy1_action": "",
        "buy2_price": "", "buy2_action": "",
        "sell1_price": "", "sell1_action": "",
        "sell2_price": "", "sell2_action": ""
    }
    if not isinstance(grid, dict):
        return defaults
    out = {}
    for k, v in defaults.items():
        out[k] = grid.get(k, v)
    return out


def validate_debate(data, mode="stock"):
    if not isinstance(data, dict):
        data = {}

    if mode == "morning":
        out = {
            "core_view": data.get("core_view", ""),
            "action": data.get("action", "HOLD"),
            "risk_warning": data.get("risk_warning", ""),
            "blue_view": data.get("blue_view", ""),
            "red_view": data.get("red_view", ""),
            "final_verdict": data.get("final_verdict", ""),
            "bull_bear_power": data.get("bull_bear_power", {"bull": 50, "bear": 50})
        }
        return out

    # sanitize weights
    fw = data.get("feature_weights", {})
    if not isinstance(fw, dict):
        fw = {}
    # normalize to 100 if possible
    try:
        total = sum([float(v) for v in fw.values() if isinstance(v, (int, float))])
        if total > 0:
            fw = {k: round(float(v) / total * 100, 2) for k, v in fw.items() if isinstance(v, (int, float))}
    except Exception:
        pass

    out = {
        "scores": _sanitize_scores(data.get("scores", {})),
        "action": data.get("action", "HOLD"),
        "core_view": data.get("core_view", ""),
        "risk_warning": data.get("risk_warning", ""),
        "grid_strategy": _sanitize_grid(data.get("grid_strategy", {})),
        "scenarios": data.get("scenarios", []),
        "feature_weights": fw,
        "blue_view": data.get("blue_view", ""),
        "red_view": data.get("red_view", ""),
        "final_verdict": data.get("final_verdict", "")
    }
    return out


def log_llm(mode, model, raw, cleaned, ok=True):
    _ensure_dir()
    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "model": model,
        "ok": bool(ok),
        "raw": _truncate(raw),
        "cleaned": _truncate(cleaned)
    }
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
