"""Connect the Studio file panel to its transfer queue."""
from pathlib import Path
import threading
import uuid
from studio_paths import model_directory
from transfer_core import TransferController, TransferError


class FilesBridge:
    def __init__(self, owner):
        import workspace_store
        from hf_downloads import HuggingFaceDownloads

        self.owner = owner
        self.store = workspace_store
        self.models = model_directory()
        roots = {"root": Path(self.models.anchor), "models": self.models,
                 "input": owner.workflow_dir.parent / "input", "output": owner.output_dir}
        self.controller = TransferController(None, local_roots=roots, on_change=self.publish)
        self.hidden_tasks = set()
        self.undo = []
        self.message = ""
        self.drive_setup = None
        self.drive_auth = {'phase': 'idle', 'url': '', 'error': ''}
        self.hf_downloads = HuggingFaceDownloads(self)
        self.publish()
        self.controller.start()

    def publish(self, value=None):
        if value is None:
            value = self.controller.snapshot()
        saved = self.store.read()
        value.update(recipes=saved["copies"], message=self.message, drive_auth=dict(self.drive_auth),
                     model_directory=str(self.models), can_undo=bool(self.undo or saved.get("copy_trash")))
        value["tasks"] = [task for task in value["tasks"] if task["id"] not in self.hidden_tasks]
        self.owner.files = value

    def receive(self, command):
        self.message = ""
        action = command["action"]
        if self.hf_downloads.receive(command):
            self.publish()
            return
        if action == 'drive_connect':
            from drive_auth import DriveAuthorization
            if self.drive_auth['phase'] == 'working':
                return
            try:
                self.drive_setup = DriveAuthorization()
                self.drive_auth = {'phase': 'pending', 'url': self.drive_setup.begin(), 'error': ''}
            except Exception:
                self.drive_setup = None
                self.drive_auth = {'phase': 'error', 'url': '', 'error': '无法生成 Google Drive 授权链接，请重试。'}
        elif action == 'drive_authorize':
            if self.drive_setup is None or self.drive_auth['phase'] != 'pending':
                return
            self.drive_auth = {'phase': 'working', 'url': '', 'error': ''}
            threading.Thread(target=self.authorize_drive, args=(command['code'],), daemon=True).start()
        elif action == "save_recipe":
            from copy_registry import save_recipe
            recipe_id = save_recipe(command["recipe"])
            self.message = "快捷操作已保存。"
            if command.get("replay"):
                threading.Thread(target=self.replay, args=([recipe_id],), daemon=True).start()
        elif action == "delete_recipe":
            def remove(state):
                record = next(record for record in state["copies"] if record["id"] == command["id"])
                state["copies"].remove(record)
                state.setdefault("copy_trash", []).append(record)
            self.store.edit(remove)
            self.undo.append(("recipe", command["id"]))
            self.message = "快捷操作已删除。"
        elif action == "delete_task":
            self.hidden_tasks.add(command["id"])
            self.undo.append(("task", command["id"]))
            self.message = "传输记录已删除。"
        elif action == "undo":
            kind, value = self.undo.pop() if self.undo else ("recipe", self.store.read()["copy_trash"][-1]["id"])
            if kind == "task":
                self.hidden_tasks.remove(value)
            else:
                def restore(state):
                    record = next(record for record in state["copy_trash"] if record["id"] == value)
                    state["copy_trash"].remove(record)
                    state["copies"].append(record)
                self.store.edit(restore)
            self.message = "已恢复删除项。"
        elif action == "replay":
            threading.Thread(target=self.replay, args=(command["ids"],), daemon=True).start()
        else:
            self.controller.handle({**command, "request_id": uuid.uuid4().hex})
        self.publish()

    def authorize_drive(self, code):
        try:
            self.controller.connect(self.drive_setup.complete(code))
            self.drive_auth = {'phase': 'complete', 'url': '', 'error': ''}
            self.message = 'Drive 已连接，正在读取目录。'
        except TransferError as exc:
            self.drive_auth = {'phase': 'error', 'url': '', 'error': str(exc)}
        except Exception:
            self.drive_auth = {'phase': 'error', 'url': '', 'error': '授权未完成，请重新获取授权链接。'}
        finally:
            self.drive_setup = None
            self.publish()

    def replay(self, ids):
        from copy_registry import resolve
        try:
            for record in self.store.read()["copies"]:
                if record["id"] in ids:
                    if record.get("source_provider") == "huggingface":
                        self.message = "正在从 Hugging Face 复制到 " + record["local_path"]
                        self.publish()
                        self.hf_downloads.download(record)
                        self.message = "复制完成：" + record["local_path"]
                        self.controller._schedule_navigation("local", self.controller.positions["local"])
                        self.publish()
                        continue
                    source, target = resolve(self.controller, record)
                    path = self.controller.local_roots["root"].joinpath(*target.parts, source.name)
                    if source.kind == "file" and record["direction"] == "download" and path.exists() and path.stat().st_size == source.size:
                        self.message = "已复用目录中的现有文件。"
                        continue
                    self.controller._enqueue({"entry_ids": [self.controller._register(source)],
                                              "target_id": self.controller._register(target)})
                    self.message = "已加入复制队列。"
        except Exception as exc:
            self.message = str(exc)
        self.publish()

    def close(self):
        self.hf_downloads.close()
        self.controller.close()
