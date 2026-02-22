import json
import os


class PluginManager:
    def __init__(self, path="config/module_status.json"):
        self.path = path
        self._ensure_store()

    def _ensure_store(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def _save(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_all_status(self):
        return self._load()

    def set_status(self, key, enabled):
        data = self._load()
        data[key] = bool(enabled)
        self._save(data)
