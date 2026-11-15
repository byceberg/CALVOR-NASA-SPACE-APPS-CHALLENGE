from collections import defaultdict
from threading import RLock

class EventBus:
    def __init__(self, logger=None):
        self.subscribers, self.lock, self.logger = defaultdict(list), RLock(), logger

    def subscribe(self, name, callback):
        with self.lock:
            self.subscribers[name].append(callback)
        return callback

    def unsubscribe(self, name, callback):
        with self.lock:
            if callback in self.subscribers[name]:
                self.subscribers[name].remove(callback)

    def publish(self, name, payload=None):
        with self.lock:
            callbacks = list(self.subscribers[name])
        for callback in callbacks:
            try:
                callback(payload or {})
            except Exception:
                if self.logger:
                    self.logger.exception("Event callback failed: %s", name)
