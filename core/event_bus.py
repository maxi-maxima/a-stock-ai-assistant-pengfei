import datetime
import json
import os
import uuid

from core.event_schema import normalize_event, validate_event
from core.logger import warn, exception


EVENT_BUS_PATH = "data/event_bus.jsonl"
EVENT_BUS_ERROR_PATH = "data/event_bus_errors.jsonl"


class EventBus:
    """
    Unified event stream for decisions/executions/outcomes.
    JSONL format for append-only durability.
    """
    def __init__(self, path=EVENT_BUS_PATH):
        self.path = path
        self._ensure_dir()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def _now(self):
        return datetime.datetime.now().isoformat(timespec="seconds")

    def _new_id(self):
        return uuid.uuid4().hex

    def log(self, event_type, payload=None, code=None, decision_id=None, source=None):
        record = normalize_event(event_type, payload=payload, code=code, decision_id=decision_id, source=source, ts=self._now())
        # keep event id stable if caller wants to set it
        if not record.get("event_id"):
            record["event_id"] = self._new_id()
        ok, errors = validate_event(record)
        if not ok:
            try:
                warn("event_bus.validation_failed", {"errors": errors, "event": record.get("event")})
                with open(EVENT_BUS_ERROR_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": self._now(), "errors": errors, "record": record}, ensure_ascii=False) + "\n")
            except Exception as e:
                exception("event_bus.validation_log_failed", e)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            exception("event_bus.write_failed", e)
        return record.get("event_id")
