"""Journal finished transfers in the runtime and on the mounted Drive."""
import json
import os
from pathlib import Path
from threading import RLock
import time
from uuid import UUID

import workspace_store


def _history_file(task_id):
    return UUID(task_id).hex + ".json.gz"


def _load(directory):
    records = {}
    for path in directory.glob("*.json.gz"):
        try:
            raw = workspace_store._get(path.name, directory)
            if raw is None:
                continue
            record = json.loads(raw)
            if (_history_file(record["id"]) == path.name and isinstance(record["name"], str)
                    and record["status"] in ("completed", "failed", "cancelled")):
                records[record["id"]] = record
        except (ValueError, KeyError, TypeError, OSError, EOFError, AttributeError):
            continue
    return records


def _write(directory, record):
    workspace_store._put(_history_file(record["id"]), json.dumps(record, ensure_ascii=False).encode(), directory)


class TransferHistory:
    def __init__(self, drive_root):
        self.local = workspace_store.STORE / "transfer-history"
        self.drive_root = Path(drive_root) if drive_root is not None else None
        self.drive = self.drive_root / "Workflow Studio" / "transfer-history" if self.drive_root else None
        self.lock = RLock()
        self.records = _load(self.local)
        self.storage = "runtime"
        for task in workspace_store.read().get("hf_downloads", []):
            if task["id"] not in self.records:
                self._save({**task, "updated_at": 0})
        self.sync()

    def sync(self):
        with self.lock:
            if self.drive_root is None or not self.drive_root.is_dir():
                self.storage = "runtime"
                return
            try:
                self.drive.mkdir(parents=True, exist_ok=True)
                remote = _load(self.drive)
                for task_id, record in remote.items():
                    previous = self.records.get(task_id, {})
                    if record != previous and record.get("updated_at", 0) >= previous.get("updated_at", 0):
                        self.records[task_id] = record
                        _write(self.local, record)
                if not os.access(self.drive, os.W_OK):
                    self.storage = "runtime"
                    return
                for task_id, record in self.records.items():
                    if remote.get(task_id) != record:
                        _write(self.drive, record)
                self.storage = "drive"
            except (OSError, ValueError):
                self.storage = "runtime"

    def _save(self, record):
        self.records[record["id"]] = record
        local_saved = False
        try:
            _write(self.local, record)
            local_saved = True
        except (OSError, ValueError):
            pass
        if self.storage == "drive":
            try:
                _write(self.drive, record)
                return
            except (OSError, ValueError):
                pass
        self.storage = "runtime" if local_saved else "memory"

    def finish(self, task):
        with self.lock:
            now = time.time()
            self._save({**task, "finished_at": now, "updated_at": now})

    def set_deleted(self, task_id, deleted):
        with self.lock:
            record = self.records.get(task_id)
            if record is None or bool(record.get("deleted")) == deleted:
                return False
            self._save({**record, "deleted": deleted, "updated_at": time.time()})
            return True

    def visible(self):
        with self.lock:
            return [dict(record) for record in sorted(self.records.values(), key=lambda task: task.get("finished_at", 0))
                    if not record.get("deleted")]
