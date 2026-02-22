import os
import json
import datetime
import uuid


EXPERIENCE_LOG = "data/experience_log.jsonl"


class ExperienceStore:
    def __init__(self, path=EXPERIENCE_LOG):
        self.path = path
        self._ensure_dir()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def _now(self):
        return datetime.datetime.now().isoformat(timespec="seconds")

    def _write(self, record):
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def log_event(self, event_type, payload=None):
        rec = {
            "ts": self._now(),
            "event": str(event_type),
            "payload": payload or {}
        }
        self._write(rec)
        return rec

    def _gen_decision_id(self, code=None):
        base = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        if code:
            code = str(code).strip().upper().replace(".", "")
            return f"{code}_{base}_{uuid.uuid4().hex[:6]}"
        return f"DEC_{base}_{uuid.uuid4().hex[:6]}"

    def log_decision(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        decision_id = payload.get("decision_id")
        if not decision_id:
            decision_id = self._gen_decision_id(payload.get("code"))
        payload = dict(payload)
        payload["decision_id"] = decision_id
        self.log_event("decision", payload)
        return decision_id

    def log_execution(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        self.log_event("execution", payload)

    def log_outcome(self, decision_id, outcome):
        payload = outcome if isinstance(outcome, dict) else {}
        payload = dict(payload)
        if decision_id:
            payload["decision_id"] = decision_id
        self.log_event("outcome", payload)

    def load_events(self, limit=1000):
        if not os.path.exists(self.path):
            return []
        events = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            return []
        if limit and len(events) > limit:
            return events[-limit:]
        return events
