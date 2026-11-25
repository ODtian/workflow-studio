"""Run downloads that were requested in the Studio file panel."""
from pathlib import Path
import threading
import time
import uuid
import re
from urllib.parse import urlsplit, unquote

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

    def download(self, recipe):
        from huggingface_hub import snapshot_download

        local_dir = recipe["local_path"]
        for source in recipe["hf_sources"]:
            files = snapshot_download(**source, local_dir=local_dir, dry_run=True, max_workers=2)
            if not files:
                raise ValueError("没有找到符合文件范围的 Hugging Face 文件。")
            for file in files:
                options = {"repo_id": source["repo_id"], "revision": file.commit_hash,
                           "filename": file.filename, "local_dir": local_dir}
                self.controller.transfers.submit(self.run, options).result()

    def save(self):
        with self.controller.lock:
            history = [dict(task) for task in self.controller.tasks
                       if task.get("source") == "huggingface"
                       and task["status"] in ("completed", "failed", "cancelled")][-64:]
        self.bridge.store.edit(lambda state: state.update(hf_downloads=history))

    def run(self, options, task_id=None):
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import tqdm
        from transfer_core import Cancelled
        controller = self.controller
        if task_id is None:
            task_id = uuid.uuid4().hex
            task = {
                "id": task_id, "name": "Hugging Face · " + options["repo_id"] + "/" + options["filename"],
                "source": "huggingface", "kind": "file", "direction": "download",
                "status": "queued", "bytes": 0, "total": 0, "speed": 0, "error": "",
                "retryable": True,
            }
            cancel = threading.Event()
            with controller.lock:
                self.operations[task_id] = (options, task, cancel)
                controller.tasks.append(task)
        else:
            options, task, cancel = self.operations[task_id]
        with controller.lock:
            task.update(status="running", bytes=0, error="")
        controller._publish()
        last_publish = [0.0]

        class TransferProgress(tqdm):
            def __init__(self, *args, **options):
                self.downloaded = options.get("initial", 0)
                self.download_total = options.get("total", 0)
                options["disable"] = True
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
            if cancel.is_set() or controller.closed:
                raise Cancelled("Hugging Face 下载已停止")
            result = hf_hub_download(**options, tqdm_class=TransferProgress)
            path = Path(result)
            size = path.stat().st_size
            with controller.lock:
                task.update(status="completed", bytes=size, total=size, local_path=str(path), speed=0)
                self.operations.pop(task_id, None)
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
        with self.controller.lock:
            operation = self.operations.get(task_id)
            if operation is None:
                return False
            options, task, cancel = operation
            if command["action"] == "cancel":
                cancel.set()
            elif command["action"] == "retry":
                if task["status"] in ("failed", "cancelled"):
                    cancel.clear()
                    task.update(status="queued", error="")
                    self.controller.transfers.submit(self.run, options, task_id)
            else:
                return False
        return True

    def close(self):
        with self.controller.lock:
            for _, _, cancel in self.operations.values():
                cancel.set()
