import json
from threading import RLock

class Config:
    def __init__(self, path):
        self.path, self.lock, self.data = path, RLock(), {}
        self.load()

    def load(self):
        with self.lock:
            if self.path.exists():
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            else:
                self.data = {"server": {"host": "127.0.0.1", "port": 8765}}
                self.save()

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def get(self, key, default=None):
        with self.lock:
            value = self.data
            for part in key.split("."):
                if not isinstance(value, dict) or part not in value:
                    return default
                value = value[part]
            return value

    def set(self, key, value):
        with self.lock:
            target = self.data
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
            self.save()
