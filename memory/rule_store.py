from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from models.schemas import EditorialRule


@dataclass
class RuleStore:
    path: Path

    def load(self) -> List[EditorialRule]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [EditorialRule.model_validate(item) for item in data]

    def save(self, rules: List[EditorialRule]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [rule.model_dump(mode="json") for rule in rules]
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def add_rule(self, rule: EditorialRule) -> None:
        rules = self.load()
        rules.append(rule)
        self.save(rules)

    def remove_rule(self, index: int) -> None:
        rules = self.load()
        if 0 <= index < len(rules):
            rules.pop(index)
            self.save(rules)
