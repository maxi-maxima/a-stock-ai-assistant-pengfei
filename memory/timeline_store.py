from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


@dataclass
class TimelineStore:
    path: Path

    def load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, entries: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries, ensure_ascii=True, indent=2), encoding="utf-8")

    def add_events(self, chapter_number: int, events: List[str]) -> None:
        if not events:
            return
        entries = self.load()
        entries.append(
            {
                "chapter_number": chapter_number,
                "events": [e for e in events if e],
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        self.save(entries)

    def recent_events(self, limit: int = 5) -> List[str]:
        entries = self.load()
        recent = entries[-limit:] if limit > 0 else entries
        events: List[str] = []
        for item in recent:
            events.extend(item.get("events", []))
        return events
