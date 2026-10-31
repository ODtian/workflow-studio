"""Adapt the existing Drive transfer queue to the Studio component UI."""
import sys
import os
from pathlib import Path
import threading
import uuid
from content_store import enabled


def connect_drive():
    from persistent_drive_auth import connect_from_secrets, has_persistent_secret
    if not has_persistent_secret():
        return None
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build
    from transfer_core import GoogleDriveProvider

    def service(credentials):
        return build("drive", "v3", http=AuthorizedHttp(credentials, http=httplib2.Http(timeout=30)),
                     cache_discovery=False)
    value = connect_from_secrets(service_factory=service)
    return GoogleDriveProvider(value) if value is not None else None


class FilesBridge:
    def __init__(self, owner, controller=None, store=None, provider_factory=None, authorization_factory=None):
        self.owner = owner
        if store is None:
            import workspace_store as store
        self.store = store
        if controller is None:
            from transfer_core import TransferController
            session = getattr(sys.modules.get("transfer_widget"), "_SESSION", None)
            controller = session.controller if session and not session.controller.closed else None
            if controller is None:
                from transfer_core import LOCAL_ROOTS
                roots = {**LOCAL_ROOTS, 'output':Path(os.environ['WORKFLOW_OUTPUT_DIR'])} if enabled() else None
                controller = TransferController(None, local_roots=roots, provider_factory=provider_factory or connect_drive)
        self.controller = controller
        self.authorization_factory = authorization_factory
        self.hidden_tasks = getattr(controller, "studio_hidden_tasks", set())
        self.undo = getattr(controller, "studio_undo", [])
        controller.studio_hidden_tasks = self.hidden_tasks
        controller.studio_undo = self.undo
        self.message = ""
        self.drive_setup = None
        self.drive_auth = {'phase': 'idle', 'url': '', 'error': ''}
        if not hasattr(controller, "tools_listeners"):
            controller.tools_listeners = []
        controller.tools_listeners.append(self.publish)
        self.publish()
        if not any(self.controller.state["panes"][name].get("entries") for name in ("drive", "local")):
            self.controller.start()

    def publish(self):
        value = self.controller.snapshot()
        saved = self.store.read()
        value.update(recipes=saved["copies"], message=self.message, drive_auth=dict(self.drive_auth),
                     can_undo=bool(self.undo or saved.get("copy_trash")))
        value['drive_auth']['storage_description'] = getattr(self.owner, 'authorization_storage',
            '首次授权保存在本 Notebook 的 Secrets，后续打开自动重连。')
        value["tasks"] = [task for task in value["tasks"] if task["id"] not in self.hidden_tasks]
        self.owner.files = value

    def receive(self, command):
        self.message = ""
        action = command["action"]
        if action == 'drive_connect':
            from persistent_drive_auth import DriveAuthorization
            self.drive_setup = (self.authorization_factory or DriveAuthorization)()
            self.drive_auth = {'phase': 'pending', 'url': self.drive_setup.begin(), 'error': ''}
        elif action == 'drive_authorize':
            self.drive_auth = {'phase': 'working', 'url': '', 'error': ''}
            threading.Thread(target=self.authorize_drive, args=(command['code'],), daemon=True).start()
        elif action == "save_recipe":
            from copy_registry import save_recipe
            save_recipe(command["recipe"])
            self.message = "快捷操作已保存。"
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
        from persistent_drive_auth import DriveAuthError
        try:
            self.drive_setup.complete(code)
            self.controller.provider = None
            self.drive_auth = {'phase': 'complete', 'url': '', 'error': ''}
            self.message = 'Drive 授权已保存，正在读取目录。'
            self.controller.handle({'action': 'root', 'pane': 'drive', 'root': 'root', 'request_id': uuid.uuid4().hex})
        except DriveAuthError as exc:
            self.drive_auth = {'phase': 'error', 'url': '', 'error': str(exc)}
        finally:
            self.drive_setup = None
            self.publish()

    def replay(self, ids):
        from copy_registry import resolve
        try:
            for record in self.store.read()["copies"]:
                if record["id"] in ids:
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
        self.controller.tools_listeners.remove(self.publish)
