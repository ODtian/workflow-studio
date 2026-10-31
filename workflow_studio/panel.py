"""Compose Python workflow panels inside one marimo widget."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import mimetypes
from pathlib import Path
import secrets
import threading
import time
import traceback

import anywidget
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import traitlets
from chat_tree import ChatTree
from image_history import ImageHistory
from preview_transport import WidgetTransport, jpeg
from settings_writer import SettingsWriter, configuration_parameters
from content_store import enabled, read_bytes, read_text, write_text, open_image, save_image

ROOT = Path(__file__).parent
INFERENCE_LOCK = threading.Lock()
CHATS = {}


class Cancelled(Exception):
    pass


def image_bytes(image, *, preview=False):
    return jpeg(image, final=not preview)


class RunContext:
    def __init__(self, session, cancel):
        self.panel = session
        self.cancel = cancel
        self.output_dir = session.owner.output_dir
        self.last_preview = 0
        self.last_text = 0

    def check_cancelled(self):
        if self.cancel.is_set() or getattr(threading.current_thread(), "should_exit", False):
            raise Cancelled()

    def status(self, message):
        self.check_cancelled()
        self.panel.update(message=str(message))

    def metadata(self, **values):
        self.panel.update(metadata={**self.panel.state["metadata"], **values})

    def image(self, value):
        if value.startswith("data:"):
            return Image.open(io.BytesIO(base64.b64decode(value.split(",", 1)[1])))
        return open_image(value)

    def text(self, value, *, final=False):
        self.check_cancelled()
        now = time.monotonic()
        if final or now - self.last_text >= 0.05:
            self.last_text = now
            if self.panel.chat:
                node = self.panel.chat.response(str(value))
                if self.panel.chat_visible:
                    self.panel.owner.send({"type": "chat_delta", "id": self.panel.id, "node": node})
            else:
                self.panel.owner.set_payload("texts", self.panel.id, str(value))

    def response(self, content, reasoning="", *, final=False):
        self.check_cancelled()
        now = time.monotonic()
        if final or now - self.last_text >= 0.05:
            self.last_text = now
            if self.panel.chat:
                node = self.panel.chat.response(content, reasoning)
                if self.panel.chat_visible:
                    self.panel.owner.send({"type": "chat_delta", "id": self.panel.id, "node": node})
            else:
                self.panel.owner.set_payload("texts", self.panel.id, content)

    def progress(self, step, total, preview=None, message=None):
        self.check_cancelled()
        progress = {"step": int(step), "total": int(total), "message": message or f"执行 {step} / {total}"}
        self.panel.state = {**self.panel.state, **progress}
        self.panel.owner.send({"type": "image_progress", "id": self.panel.id,
                               "run_id": self.panel.state["run_id"], **progress})
        now = time.monotonic()
        if preview is not None and (step == total or now - self.last_preview >= 0.5):
            self.last_preview = now
            self.panel.owner.transport.preview(self.panel.id, preview, run_id=self.panel.state["run_id"])


class PrepareContext(RunContext):
    def status(self, message):
        self.check_cancelled()
        self.panel.update(initialization=str(message))


class WorkflowSession:
    def __init__(self, owner, workflow_id, params=None, session_id=None):
        self.owner = owner
        self.id = session_id or secrets.token_hex(4)
        self.cancel = threading.Event()
        self.published_at = 0
        self.prepare_guard = threading.Lock()
        self.prepare_pending = None
        self.prepare_running = False
        self.prepared_signature = None
        spec = owner.load(workflow_id).SPEC
        defaults = {field["key"]: field.get("default", "") for field in spec["fields"]}
        self.params = {**defaults, **configuration_parameters(spec['fields'], params or {})}
        if spec.get("model_binding_fields"):
            self.params.update(owner.model_bindings.get(self.params["model"], {}))
        self.state = {"id": self.id, "selected": workflow_id, "spec": spec,
                      "params": self.params, "busy": False, "phase": "idle",
                      "message": "工作流已就绪", "step": 0, "total": 0, "elapsed": 0, "metadata": {},
                      "initializing": False, "initialization": ""}
        self.chat = None
        self.chat_visible = False
        if spec.get("chat") and spec.get("chat_engine") != "pi":
            key = (str(owner.workflow_dir), self.id)
            if key not in CHATS:
                CHATS[key] = ChatTree()
            self.chat = CHATS[key]
            self.publish_chat()

    def publish_chat(self):
        self.owner.set_payload("chats", self.id, self.chat.snapshot())

    def chat_action(self, action, content):
        if action == "chat_select":
            self.chat.select(content["node"])
        elif action == "chat_new":
            self.chat.new()
        else:
            if action == "chat_send":
                self.chat.send(content["text"], content.get("images", []))
            elif action == "chat_edit":
                self.chat.edit(content["node"], content["text"])
            elif action == "chat_retry":
                self.chat.retry(content["node"])
            self.publish_chat()
            self.start({**content["params"], "messages": self.chat.messages()})
            return
        self.publish_chat()

    def update(self, **values):
        self.state = {**self.state, **values}
        self.owner.publish()

    def prepare(self, values):
        module = self.owner.load(self.state["selected"])
        params = {**self.params, **values}
        signature = json.dumps({key: params[key] for key in module.SPEC["prepare_fields"]}, sort_keys=True)
        with self.prepare_guard:
            if signature == self.prepared_signature:
                return
            self.prepare_pending = (signature, module, params)
            if self.prepare_running:
                return
            self.prepare_running = True
        self.update(initializing=True, initialization="准备模型…")
        import marimo as mo
        self.prepare_worker = mo.Thread(target=self.prepare_models, daemon=True)
        self.prepare_worker.start()

    def prepare_models(self):
        while True:
            with self.prepare_guard:
                if self.prepare_pending is None:
                    self.prepare_running = False
                    self.update(initializing=False)
                    return
            try:
                with INFERENCE_LOCK:
                    with self.prepare_guard:
                        signature, module, params = self.prepare_pending
                        self.prepare_pending = None
                    context = PrepareContext(self, threading.Event())
                    module.prepare(params, context)
                    self.prepared_signature = signature
                    self.update(initialization="模型已就绪")
            except Exception as exc:
                with self.prepare_guard:
                    self.prepare_pending = None
                    self.prepare_running = False
                self.update(initializing=False, initialization=f"{type(exc).__name__}: {exc}")
                return

    def start(self, values, *, run_id=None):
        self.started_at = time.monotonic()
        module = self.owner.load(self.state["selected"])
        params = {**self.params, **values}
        self.params = {key: value for key, value in params.items() if key != "messages"}
        self.state["params"] = {field["key"]: params[field["key"]] for field in module.SPEC["fields"]}
        self.owner.save_settings()
        self.cancel = threading.Event()
        self.owner.set_payload("results", self.id, [])
        self.owner.set_payload("texts", self.id, "")
        self.update(busy=True, phase="queued", message="等待推理资源…", step=0,
                    total=0, elapsed=0, display_ms=0, delivery_ms=0, end_to_end_ms=0,
                    run_id=run_id or secrets.token_hex(8), metadata={})
        self.owner.send({"type":"preview_reset", "id":self.id, "run_id":self.state['run_id']})
        import marimo as mo
        self.worker = mo.Thread(target=self.execute, args=(module, params, self.cancel), daemon=True)
        self.worker.start()

    def execute(self, module, params, cancel):
        started = self.started_at
        context = RunContext(self, cancel)
        acquired = False
        try:
            while not acquired:
                context.check_cancelled()
                acquired = INFERENCE_LOCK.acquire(timeout=0.2)
            context.check_cancelled()
            self.update(phase="running", message="准备工作流…",
                        metadata={**self.state["metadata"], "排队秒": round(time.monotonic() - started, 3)})
            result = module.run(params, context)
            context.check_cancelled()
            if module.SPEC.get("output") == "text":
                context.text(result, final=True)
                if not module.SPEC.get("chat"):
                    filename = time.strftime("%Y%m%d-%H%M%S") + f"-{self.id}.txt"
                    path = self.owner.output_dir / filename
                    self.owner.write_text_result(path, result)
                    self.owner.set_payload("results", self.id,
                                           [{"name": filename, "kind": "text", "bytes": path.stat().st_size}])
                self.update(phase="complete", message="文本生成完成", step=self.state["total"])
            elif isinstance(result, dict) and result.get("kind") == "video":
                self.publish_video(result, params, module.SPEC)
            else:
                self.publish_images(result, params, module.SPEC)
        except Cancelled:
            self.update(phase="cancelled", message="任务已停止，当前结果已保留。")
        except Exception as exc:
            self.update(phase="error", message=f"{type(exc).__name__}: {exc}")
            if not self.chat:
                self.state['error_detail'] = traceback.format_exc()
        finally:
            if acquired:
                INFERENCE_LOCK.release()
            if self.chat:
                self.chat.finish(self.state["phase"])
                self.publish_chat()
                self.owner.set_payload("texts", self.id, "")
            self.update(busy=False, elapsed=round(time.monotonic() - started, 2))

    def publish_images(self, images, params, spec):
        if isinstance(images, (Image.Image, str, Path)):
            images = [images]
        images = [open_image(image) if isinstance(image, (str, Path)) else image for image in images]
        self.update(phase="publishing", message="显示结果…")
        image_fields = {field["key"] for field in spec["fields"]
                        if field["type"] in ("image", "media_list", "keyframe_list")}
        metadata = {"workflow": self.state["selected"], "params": {
            key: value for key, value in params.items() if key not in image_fields}}
        metadata["run_info"] = dict(self.state["metadata"])
        if "Seed" in metadata["run_info"]:
            metadata["params"]["seed"] = metadata["run_info"]["Seed"]
        results = []
        for index, image in enumerate(images):
            filename = time.strftime("%Y%m%d-%H%M%S") + f"-{self.id}-{secrets.token_hex(2)}-{index+1}.png"
            path = self.owner.output_dir / filename
            png_info = PngInfo()
            png_info.add_text("workflow_studio", json.dumps(metadata, ensure_ascii=False))
            save_image(image, path, "PNG", pnginfo=png_info, compress_level=1)
            self.owner.history_store.add(path, metadata)
            results.append({"name": filename, "kind": "image", "width": image.width,
                            "height": image.height, "bytes": path.stat().st_size})
        self.owner.history_store.save()
        self.owner.transport.attribute("histories", self.owner.history_store.snapshot())
        self.owner.set_payload("results", self.id, results)
        self.update(phase="complete", message=f"完成 · {len(results)} 张图片", step=self.state["total"])
        if images:
            self.published_at = time.monotonic()
            self.owner.transport.preview(self.id, images[0], final=True,
                                         run_id=self.state["run_id"], started=self.started_at)

    def publish_video(self, video, params, spec):
        path = Path(video["path"])
        media_fields = {field["key"] for field in spec["fields"]
                        if field["type"] in ("image", "media_list", "keyframe_list")}
        metadata = {"workflow": self.state["selected"], "params": {
            key: value for key, value in params.items() if key not in media_fields},
                    "run_info": dict(self.state["metadata"])}
        if "Seed" in metadata["run_info"]:
            metadata["params"]["seed"] = metadata["run_info"]["Seed"]
        entry = self.owner.history_store.add_video(path, video, metadata)
        self.owner.history_store.save()
        self.owner.transport.attribute("histories", self.owner.history_store.snapshot())
        self.owner.set_payload("results", self.id, [entry])
        self.update(phase="complete", message=f"完成 · {video['duration']:.1f} 秒视频", step=self.state["total"])
        self.published_at = time.monotonic()
        self.owner.transport.preview(self.id, path, video=True, final=True,
                                     run_id=self.state["run_id"], started=self.started_at)


class WorkflowPanel(anywidget.AnyWidget):
    state = traitlets.Dict()
    previews = traitlets.Dict()
    texts = traitlets.Dict()
    results = traitlets.Dict()
    chats = traitlets.Dict()
    files = traitlets.Dict()
    histories = traitlets.Dict()

    @traitlets.observe('state', 'previews', 'texts', 'results', 'chats', 'files', 'histories')
    def runtime_changed(self, change):
        self.send({'type': 'runtime_state', 'name': change['name'], 'value': change['new']})

    def __init__(self, workflow_dir=None, output_dir=None, initial=None, settings_backup=None):
        super().__init__(_esm=("const GRADIO_COMPONENT_CSS = " + json.dumps((ROOT / "assets/components.css").read_text(encoding="utf-8"))
                             + ";\n" + (ROOT / "assets/view.js").read_text(encoding="utf-8")))
        self.transport = WidgetTransport(self)
        self.workflow_dir = Path(workflow_dir or ROOT / "workflows").resolve()
        self.output_dir = Path(output_dir or ROOT / "generated").resolve()
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.history_store = ImageHistory(self.output_dir if enabled() else self.workflow_dir.parent / "studio_history")
        self.history_store.import_directory(self.output_dir)
        self.histories = self.history_store.snapshot()
        self.settings_path = self.workflow_dir.parent / "studio_settings.json"
        self.settings_backup = settings_backup
        if enabled():
            from workspace_store import read
            saved = read().get('studio_settings', {})
        else:
            saved = json.loads(read_text(self.settings_path)) if self.settings_path.exists() else {}
        self.settings_writer = SettingsWriter(self.settings_path, self.settings_backup, self.settings_saved)
        self.model_bindings = saved.get("model_bindings", {})
        self.playback = saved.get("playback", {"volume": 0.25, "muted": False})
        self._modules = {}
        self.sessions = {}
        self.state = {"workflows": [], "panels": [], "message": "", "active": saved.get("active", ""), "model_bindings": self.model_bindings, "playback": self.playback}
        self.on_msg(self._message)
        self.refresh()
        available = {item["id"] for item in self.state["workflows"]}
        if initial is None:
            initial = saved.get("panels")
        if initial is None:
            initial = [{"workflow": name} for name in ("moss_image.py", "minimax_h3.py", "llama_cpp.py") if name in available]
        if not initial and available:
            initial = [{"workflow": self.state["workflows"][0]["id"]}]
        for item in initial:
            self.add(item["workflow"], item.get("params"), session_id=item.get("id"), activate=False)
        self.files_bridge = None
        if importlib.util.find_spec("transfer_core") is not None:
            self.files_bridge = self.create_files_bridge()

    def create_files_bridge(self):
        from files_bridge import FilesBridge
        return FilesBridge(self)

    def _send_widget_message(self, content, buffers=None):
        anywidget.AnyWidget.send(self, content, buffers=buffers)

    def save_settings(self, panels=None, active=None, model_bindings=None, request=None, playback=None):
        if model_bindings is not None:
            self.model_bindings = model_bindings
        if playback is not None:
            self.playback = playback
        for item in panels or []:
            session = self.sessions[item["id"]]
            session.params = {**session.params, **item["params"]}
            session.state["params"] = {f["key"]: session.params[f["key"]] for f in session.state["spec"]["fields"]}
        if active is not None:
            self.state = {**self.state, "active": active}
        for session in self.sessions.values():
            keys = session.state["spec"].get("model_binding_fields")
            if keys and session.params.get("model"):
                self.model_bindings[session.params["model"]] = {key: session.params.get(key, "") for key in keys}
        self.state = {**self.state, "model_bindings": self.model_bindings, "playback": self.playback}
        saved = {"active": self.state["active"], "model_bindings": self.model_bindings, "playback": self.playback, "panels": [
            {"id": session.id, "workflow": session.state["selected"],
             "params": configuration_parameters(session.state['spec']['fields'], session.params)}
            for session in self.sessions.values()]}
        self.settings_writer.submit(saved, request)

    def settings_saved(self, request, error):
        self.send({"type":"settings_saved", "request":request, "error":error})

    def publish(self):
        self.transport.payload("state", "panels", [session.state for session in self.sessions.values()])

    def send(self, content, buffers=None):
        self.transport.send(content, buffers)

    def set_payload(self, name, panel_id, value):
        self.transport.payload(name, panel_id, value)

    def write_text_result(self, path, text):
        write_text(path, text)

    def unload_models(self, panel_id=None):
        from model_residency import release, workflow_group

        group = workflow_group(self.sessions[panel_id].state['selected']) if panel_id else 'all'
        with INFERENCE_LOCK:
            release(group)
            for session in self.sessions.values():
                if group == 'all' or workflow_group(session.state['selected']) == group:
                    session.prepared_signature = None
                    session.update(message='模型已卸载', metadata={**session.state['metadata'], '模型驻留':'已卸载'})
        self.state = {**self.state, 'message':'全部模型已卸载' if group == 'all' else '当前工作流模型已卸载'}

    def image_path(self, name):
        archived = self.history_store.original(name)
        return archived if archived.exists() else self.output_dir / name

    def load(self, workflow_id):
        path = self.workflow_dir / workflow_id
        stamp = path.stat().st_mtime_ns
        cached = self._modules.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
        module_spec = importlib.util.spec_from_file_location("studio_flow_" + path.stem, path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        self._modules[path] = stamp, module
        return module

    def model_entries(self):
        roots = {Path(module.SPEC["model_root"]) for _, module in self._modules.values()
                 if module.SPEC.get("model_root")}
        return sorted(str(path) for root in roots for path in root.rglob("*")
                      if path.is_file() and path.suffix.lower() in (".safetensors", ".gguf", ".pth"))

    def refresh_models(self):
        if self.model_entries() != self._model_entries:
            self.refresh()

    def refresh(self):
        self._modules.clear()
        workflows = []
        for path in sorted(self.workflow_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            spec = self.load(path.name).SPEC
            workflows.append({"id": path.name, "name": spec["name"], "description": spec.get("description", "")})
        self.state = {**self.state, "workflows": workflows}
        for session in self.sessions.values():
            spec = self.load(session.state["selected"]).SPEC
            for field in spec["fields"]:
                key = field["key"]
                session.params.setdefault(key, field.get("default", ""))
                if field.get("area") == "models" and field["type"] == "select" and not session.params[key]:
                    session.params[key] = field.get("default", "")
            session.state = {**session.state, "spec": spec,
                             "params": {field["key"]: session.params[field["key"]] for field in spec["fields"]}}
        self._model_entries = self.model_entries()
        self.publish()

    def add(self, workflow_id, params=None, session_id=None, activate=True):
        session = WorkflowSession(self, workflow_id, params, session_id=session_id)
        self.sessions[session.id] = session
        if activate or not self.state["active"]:
            self.state = {**self.state, "active": session.id}
        self.save_settings()
        self.publish()
        return session

    def _message(self, widget, content, buffers):
        try:
            action = content["action"]
            if action == 'sync':
                self.send({'type': 'runtime_snapshot', 'values': {name: getattr(self, name)
                           for name in ('state', 'previews', 'texts', 'results', 'chats', 'files', 'histories')}})
                return
            if action == "files":
                self.files_bridge.receive(content["command"])
                return
            if action == "settings":
                self.save_settings(content["panels"], content["active"], content.get("model_bindings"), content.get("request"), playback=content.get("playback"))
                return
            if action == "chat_visibility":
                for item in content["panels"]:
                    session = self.sessions[item["id"]]
                    session.chat_visible = item["visible"]
                    if item["visible"] and session.chat:
                        session.publish_chat()
                        self.send({"type": "chat_snapshot", "id": session.id, "chat": self.chats[session.id]})
                return
            if action == "add":
                self.add(content["workflow"])
                return
            if action == "refresh":
                self.refresh()
                return
            if action == "scan_models":
                self.refresh_models()
                return
            if action == "unload_models":
                import marimo as mo
                mo.Thread(target=self.unload_models, args=(content.get('id'),), daemon=True).start()
                return
            if action == "import":
                path = self.workflow_dir / Path(content["name"]).name
                if path.suffix != ".py":
                    raise ValueError("请选择 Python 工作流文件（.py）。")
                path.write_text(content["source"], encoding="utf-8")
                self.refresh()
                self.add(path.name)
                return
            session = self.sessions[content["id"]]
            if action == "pi":
                command = content["command"]
                if command["action"] in ("prompt", "compact"):
                    if not session.state["busy"]:
                        session.start({**content["params"], "pi_request":command})
                else:
                    import marimo as mo
                    import pi_runner
                    mo.Thread(target=pi_runner.control, args=(session, command, content.get("params")), daemon=True).start()
            elif action == "prepare":
                session.prepare(content["params"])
            elif action == "cancel":
                session.cancel.set()
                session.update(message="正在结束当前步骤…")
            elif action == "remove" and not session.state["busy"]:
                self.sessions.pop(session.id)
                if session.chat:
                    CHATS.pop((str(self.workflow_dir), session.id)).close()
                if self.state["active"] == session.id:
                    self.state = {**self.state, "active": next(iter(self.sessions), "")}
                for name in ("previews", "texts", "results", "chats"):
                    setattr(self, name, {key: value for key, value in getattr(self, name).items() if key != session.id})
                self.publish()
                self.save_settings()
            elif action == "run" and not session.state["busy"]:
                session.start(content["params"], run_id=content.get("run_id"))
            elif action == "chat_export" and not session.state["busy"]:
                self.send({"type": "download", "id": session.id, "name": "conversation.json", "mime": "application/json"},
                          buffers=[memoryview(session.chat.export())])
            elif action == "chat_sync":
                if session.chat:
                    session.publish_chat()
                    self.send({"type": "chat_snapshot", "id": session.id, "chat": self.chats[session.id]})
            elif action.startswith("chat_") and not session.state["busy"]:
                session.chat_action(action, content)
            elif action == "displayed":
                if content.get("run_id") and content["run_id"] == session.state.get("run_id"):
                    session.update(display_ms=content["ms"], end_to_end_ms=content["end_to_end_ms"],
                                   delivery_ms=max(0, content["end_to_end_ms"] - content["server_ms"]))
            elif action == "download":
                path = self.image_path(content["name"])
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send({"type": "download", "id": session.id, "name": path.name, "mime": mime},
                          buffers=[memoryview(read_bytes(path))])
            elif action == "image_detail":
                path = self.image_path(content["name"])
                self.send({"type": "image_detail", "id": session.id, "name": path.name,
                           "request": content["request"], "mime": mimetypes.guess_type(path.name)[0]},
                          buffers=[memoryview(read_bytes(path))])
            elif action == "image_thumbnail":
                path = self.history_store.thumbnail(content["name"])
                self.send({"type": "image_thumbnail", "id": session.id, "name": content["name"],
                           "request": content["request"]}, buffers=[memoryview(read_bytes(path))])
            elif action == "image_preview":
                source = self.image_path(content["name"])
                self.transport.preview(session.id, source, video=source.suffix == ".mp4", final=True,
                    response={"type":"image_preview", "name":content["name"], "request":content["request"]})
            elif action == "show_result":
                if session.state['busy']:
                    return
                path = self.image_path(content["name"])
                self.transport.preview(session.id, path, video=path.suffix == ".mp4", final=True,
                                       run_id=session.state.get('run_id'))
            elif action == "export":
                path = self.workflow_dir / session.state["selected"]
                self.send({"type": "workflow", "name": path.name, "source": path.read_text(encoding="utf-8")})
        except Exception as exc:
            self.state = {**self.state, "message": str(exc)}
            if content.get("action") == "settings":
                self.state = {**self.state, "settings_result": {"request": content.get("request"), "error": str(exc)}}

    def close(self):
        if hasattr(self, "settings_writer"):
            self.settings_writer.close()
        if hasattr(self, "transport"):
            self.transport.close()
        if getattr(self, "files_bridge", None):
            self.files_bridge.close()
            self.files_bridge = None
        super().close()


def get_panel(workflow_dir=None, output_dir=None, initial=None, settings_backup=None):
    return WorkflowPanel(workflow_dir=workflow_dir, output_dir=output_dir, initial=initial, settings_backup=settings_backup)
