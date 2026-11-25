"""Connect the Studio file panel to its transfer queue."""
from pathlib import Path
import threading
from studio_paths import model_directory
from transfer_core import TransferController
from transfer_history import TransferHistory


class FilesBridge:
    def __init__(self, owner, drive_directory):
        import workspace_store
        from hf_downloads import HuggingFaceDownloads

        self.owner = owner
        self.store = workspace_store
        self.models = model_directory()
        roots = {"root": Path(self.models.anchor), "models": self.models,
                 "input": owner.workflow_dir.parent / "input", "output": owner.output_dir}
        self.history = TransferHistory(drive_directory)
        self.controller = TransferController(drive_directory, local_roots=roots, on_change=self.publish,
                                             on_finish=self.history.finish)
        self.undo = []
        self.message = ""
        self.hf_downloads = HuggingFaceDownloads(self.controller)
        self.publish()
        self.controller.start()

    def publish(self, value=None):
        if value is None:
            value = self.controller.snapshot()
        saved = self.store.read()
        value.update(recipes=saved["copies"], message=self.message,
                     drive_directory=str(self.controller.drive_directory or ''),
                     model_directory=str(self.models), can_undo=bool(self.undo or saved.get("copy_trash")),
                     history_storage=self.history.storage)
        live = {task["id"]: task for task in value["tasks"]}
        active = [task for task in live.values() if task["status"] in ("queued", "running")]
        active_ids = {task["id"] for task in active}
        value["tasks"] = [
            {**task, "retryable": task["id"] in live and live[task["id"]].get("retryable", True)}
            for task in self.history.visible() if task["id"] not in active_ids
        ] + active
        self.owner.files = value

    def receive(self, command):
        self.message = ""
        action = command["action"]
        if self.hf_downloads.receive(command):
            self.publish()
            return
        if action == "save_recipe":
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
            if self.history.set_deleted(command["id"], True):
                self.undo.append(("task", command["id"]))
                self.message = "传输记录已删除。"
        elif action == "undo" and (self.undo or self.store.read().get("copy_trash")):
            kind, value = self.undo.pop() if self.undo else ("recipe", self.store.read()["copy_trash"][-1]["id"])
            if kind == "task":
                self.history.set_deleted(value, False)
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
            if action == "refresh" and command.get("pane") == "drive":
                self.history.sync()
            self.controller.handle({**command, "save_shortcut": action == "transfer"})
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
                    self.controller._enqueue({"entry_ids": [self.controller._register(source)],
                                              "target_id": self.controller._register(target)})
                    self.message = "已加入复制队列。"
        except Exception as exc:
            self.message = str(exc)
        self.publish()

    def close(self):
        self.hf_downloads.close()
        self.controller.close()
