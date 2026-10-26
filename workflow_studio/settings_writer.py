"""Coalesce settings snapshots and persist them on a background thread."""
from copy import deepcopy
import json
import threading
from content_store import enabled


class SettingsWriter:
    def __init__(self, path, backup, on_saved, interval=1.5):
        self.path, self.backup, self.on_saved, self.interval = path, backup, on_saved, interval
        self.condition = threading.Condition()
        self.pending = None
        self.request = None
        self.closed = False
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()

    def submit(self, settings, request=None):
        with self.condition:
            if request is not None:
                self.request = request
            self.pending = deepcopy(settings), self.request
            self.condition.notify()

    def _write(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending is not None or self.closed)
                if self.pending is None:
                    return
                self.condition.wait_for(lambda: self.closed, timeout=self.interval)
                settings, request = self.pending
                self.pending = None
            error = ''
            try:
                if not enabled():
                    self.path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
                if self.backup:
                    self.backup(settings)
            except Exception as exc:
                error = str(exc)
            self.on_saved(request, error)

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify()
