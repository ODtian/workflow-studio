"""Send Hugging Face file downloads through Studio's existing transfer history."""
from functools import wraps
from pathlib import Path
import threading
import time
import uuid
import re
from urllib.parse import urlsplit, unquote

_active = None


def source_from_recipe(recipe):
    address = recipe.get("hf_url", recipe.get("repo_id", "")).strip()
    revision = recipe.get("hf_revision", "main").strip() or "main"
    patterns = [part.strip() for part in re.split(r"[,\n]", recipe.get("hf_patterns", "")) if part.strip()]
    if "://" in address:
        url = urlsplit(address)
        if url.hostname not in ("huggingface.co", "hf.co"):
            raise ValueError("请填写 Hugging Face 仓库或文件链接。")
        parts = unquote(url.path).strip("/").split("/")
    else:
        parts = address.strip("/").split("/")
    repo_id = "/".join(parts[:2])
    from huggingface_hub.utils import validate_repo_id
    validate_repo_id(repo_id)
    if len(parts) > 2:
        kind, revision = parts[2:4]
        selected = "/".join(parts[4:])
        if kind in ("resolve", "blob"):
            patterns = [selected]
        elif kind == "tree" and selected:
            patterns = patterns or [selected.rstrip("/") + "/*"]
    source = {"repo_id": repo_id, "revision": revision}
    if patterns:
        source["allow_patterns"] = patterns
    return source


def replay_recipe(recipe):
    from huggingface_hub import snapshot_download
    for source in recipe["hf_sources"]:
        snapshot_download(**{"local_dir": recipe["local_path"], "max_workers": 2, **source})


class HuggingFaceDownloads:
    def __init__(self, bridge):
        self.bridge = bridge
        self.controller = bridge.controller
        self.operations = {}
        with self.controller.lock:
            known = {task["id"] for task in self.controller.tasks}
            self.controller.tasks.extend(
                {**task, "retryable": False}
                for task in bridge.store.read().get("hf_downloads", [])
                if task["id"] not in known
            )
        self.controller._publish()

    def save(self):
        with self.controller.lock:
            history = [dict(task) for task in self.controller.tasks
                       if task.get("source") == "huggingface"
                       and task["status"] in ("completed", "failed", "cancelled")][-64:]
        self.bridge.store.edit(lambda state: state.update(hf_downloads=history))

    def run(self, original, kwargs, task_id=None):
        from huggingface_hub.utils import tqdm
        from transfer_core import Cancelled
        controller = self.controller
        if task_id is None:
            task_id = uuid.uuid4().hex
            task = {
                "id": task_id, "name": "Hugging Face · " + kwargs["repo_id"] + "/" + kwargs["filename"],
                "source": "huggingface", "kind": "file", "direction": "download",
                "status": "queued", "bytes": 0, "total": 0, "speed": 0, "error": "",
                "retryable": True, "repo_id": kwargs["repo_id"], "filename": kwargs["filename"],
            }
            cancel = threading.Event()
            self.operations[task_id] = (original, dict(kwargs), task, cancel)
            with controller.lock:
                controller.tasks.append(task)
        else:
            original, kwargs, task, cancel = self.operations[task_id]
            cancel.clear()
        task.update(status="running", bytes=0, error="")
        controller._publish()
        base = kwargs.get("tqdm_class") or tqdm
        last_publish = [0.0]

        class TransferProgress(base):
            def __init__(self, *args, **options):
                self.downloaded = options.get("initial", 0)
                self.download_total = options.get("total", 0)
                super().__init__(*args, **options)
                self.report()

            def report(self):
                if cancel.is_set():
                    raise Cancelled("Hugging Face 下载已停止")
                with controller.lock:
                    task.update(bytes=max(task["bytes"], int(self.downloaded)), total=int(self.download_total or 0))
                now = time.monotonic()
                if now - last_publish[0] >= 0.25:
                    last_publish[0] = now
                    controller._publish()

            def update(self, amount=1):
                result = super().update(amount)
                self.downloaded += amount or 0
                self.report()
                return result

        try:
            result = original(**{**kwargs, "tqdm_class": TransferProgress})
            path = Path(result)
            size = path.stat().st_size
            with controller.lock:
                task.update(status="completed", bytes=size, total=size, local_path=str(path), speed=0)
            return result
        except Exception as error:
            with controller.lock:
                task.update(status="cancelled" if cancel.is_set() else "failed", error=str(error), speed=0)
            raise
        finally:
            controller._publish()
            self.save()

    def receive(self, command):
        task_id = command.get("task_id")
        if task_id not in self.operations:
            return False
        original, kwargs, task, cancel = self.operations[task_id]
        if command["action"] == "cancel":
            cancel.set()
        elif command["action"] == "retry":
            self.controller.transfers.submit(self.run, original, kwargs, task_id)
        else:
            return False
        return True


def bind(bridge):
    global _active
    install()
    manager = getattr(bridge.controller, "hf_downloads", None)
    if manager is None:
        manager = HuggingFaceDownloads(bridge)
        bridge.controller.hf_downloads = manager
    _active = manager
    return manager


def install():
    import huggingface_hub.file_download as downloads
    if getattr(downloads._hf_hub_download_to_local_dir, "_workflow_studio_history", False):
        return
    def tracked(original):
        @wraps(original)
        def download(**kwargs):
            if _active is None or kwargs.get("dry_run"):
                return original(**kwargs)
            return _active.run(original, kwargs)
        download._workflow_studio_history = True
        return download
    for name in ("_hf_hub_download_to_local_dir", "_hf_hub_download_to_cache_dir"):
        setattr(downloads, name, tracked(getattr(downloads, name)))
