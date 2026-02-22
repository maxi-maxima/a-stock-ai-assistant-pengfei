import datetime
import json
import os
import uuid


EXPERIMENT_PATH = "data/experiments.jsonl"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _ensure_dir():
    os.makedirs(os.path.dirname(EXPERIMENT_PATH), exist_ok=True)


def log_experiment(kind, config=None, data_meta=None, result=None, tags=None):
    record = {
        "id": uuid.uuid4().hex,
        "ts": _now(),
        "kind": str(kind or "").strip(),
        "config": config if isinstance(config, dict) else {},
        "data": data_meta if isinstance(data_meta, dict) else {},
        "result": result if isinstance(result, dict) else {},
        "tags": tags if isinstance(tags, list) else []
    }
    _ensure_dir()
    try:
        with open(EXPERIMENT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return record
