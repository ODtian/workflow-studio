"""Encrypted text-workflow probe using Studio's existing widget and runner.

Public framework assets and an RSA public key are synchronized. Workflow source,
parameters, input images, logs, and text results cross the widget as AES-GCM
envelopes. Keys and decrypted workflow modules stay in the kernel's memory.
"""
from __future__ import annotations

import base64
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import secrets
import threading
from types import ModuleType

import anywidget
import traitlets
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from panel import ROOT, WorkflowSession


PROTOCOL = b"workflow-studio/private-probe/v1"
MAGIC = b"WFS1"
PASSWORD_ITERATIONS = 600_000


def b64(value):
    return base64.b64encode(value).decode("ascii")


class EncryptedStore:
    def __init__(self, root, key, cache=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._cipher = AESGCM(key)
        self.cache = cache

    def write(self, name, value):
        nonce = secrets.token_bytes(12)
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = MAGIC + nonce + self._cipher.encrypt(nonce, value, name.encode())
        path.write_bytes(blob)
        if self.cache is not None:
            self.cache.put('workflow-studio/private-probe/' + name, blob)

    def read(self, name):
        data = (self.root / name).read_bytes()
        return self._cipher.decrypt(data[4:16], data[16:], name.encode())


class PrivateWorkflowSession(WorkflowSession):
    def execute(self, module, params, cancel):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            super().execute(module, params, cancel)
        self.owner.store.write("logs.bin", output.getvalue().encode())


class PrivateStudioProbe(anywidget.AnyWidget):
    public_key = traitlets.Unicode().tag(sync=True)
    protocol = traitlets.Unicode(PROTOCOL.decode()).tag(sync=True)
    password_salt = traitlets.Unicode().tag(sync=True)
    password_iterations = traitlets.Int(PASSWORD_ITERATIONS).tag(sync=True)
    password_setup = traitlets.Bool().tag(sync=True)

    def __init__(self, directory, cache=None, legacy_key=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.cache = cache
        if cache is not None:
            for name in ('state.wfs', 'password.json'):
                saved = cache.get('workflow-studio/private-probe/' + name)
                if saved is not None:
                    (self.directory / name).write_bytes(saved)
        password_path = self.directory / 'password.json'
        self._password_config = json.loads(password_path.read_text()) if password_path.exists() else {
            'salt': b64(secrets.token_bytes(16)), 'iterations': PASSWORD_ITERATIONS}
        self._legacy_key = legacy_key
        self._rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.clients = {}
        self._key = None
        self._sources = {}
        self._modules = {}
        self.sessions = {}
        self.model_bindings = {}
        self.state = {"workflows": [], "panels": [], "message": "", "active": "",
                      "model_bindings": {}, "playback": {"volume": 0.25, "muted": False}}
        self.previews, self.texts, self.results = {}, {}, {}
        self.chats, self.files, self.histories = {}, {}, {}
        self.output_dir = self.directory / "results"
        self.output_dir.mkdir(exist_ok=True)
        self._lock = threading.RLock()
        studio_source = "const GRADIO_COMPONENT_CSS = " + json.dumps(
            (ROOT / "assets/components.css").read_text(encoding="utf-8"))
        studio_source += ";\n" + (ROOT / "assets/view.js").read_text(encoding="utf-8")
        adapter = (ROOT / "private_probe_view.js").read_text(encoding="utf-8")
        super().__init__(_esm="const STUDIO_SOURCE = " + json.dumps(studio_source) + ";\n" + adapter)
        self.public_key = b64(self._rsa.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.password_salt = self._password_config['salt']
        self.password_iterations = self._password_config['iterations']
        self.password_setup = 'wrapped_key' not in self._password_config
        self.on_msg(self._receive)

    def _save_password_config(self, password_key, content_key):
        nonce = secrets.token_bytes(12)
        self._password_config.update(nonce=b64(nonce), wrapped_key=b64(
            AESGCM(password_key).encrypt(nonce, content_key, PROTOCOL + b':content-key')))
        blob = json.dumps(self._password_config).encode()
        (self.directory / 'password.json').write_bytes(blob)
        if self.cache is not None:
            self.cache.put('workflow-studio/private-probe/password.json', blob)
        self.password_setup = False

    def _record_wire(self, packet):
        with self._lock:
            with (self.directory / "wire.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(packet) + "\n")

    def _packet(self, client, message, buffers=()):
        nonce = secrets.token_bytes(12)
        raw = json.dumps({"content": message, "buffers": [b64(bytes(x)) for x in buffers]},
                         ensure_ascii=False).encode()
        aad = PROTOCOL + b":" + client.encode() + b":s2c"
        return {"type": "sealed", "client": client, "nonce": b64(nonce),
                "data": b64(AESGCM(self.clients[client]).encrypt(nonce, raw, aad))}

    def _emit(self, packet):
        self._record_wire(packet)
        anywidget.AnyWidget.send(self, packet)

    def send(self, content, buffers=()):
        for client in list(self.clients):
            self._emit(self._packet(client, content, buffers or ()))

    def _unlock(self, packet):
        client = packet["client"]
        keys = self._rsa.decrypt(base64.b64decode(packet["wrapped"]), padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        password_key, session_key = keys[:32], keys[32:]
        if self.password_setup:
            vault_key = self._legacy_key or secrets.token_bytes(32)
        else:
            vault_key = AESGCM(password_key).decrypt(
                base64.b64decode(self._password_config['nonce']),
                base64.b64decode(self._password_config['wrapped_key']), PROTOCOL + b':content-key')
        store = EncryptedStore(self.directory, vault_key, self.cache)
        if (self.directory / "state.wfs").exists():
            saved = json.loads(store.read("state.wfs"))
        else:
            saved = {"workflows": {}, "panels": [], "active": ""}
            store.write("state.wfs", json.dumps(saved).encode())
        if self.password_setup:
            self._save_password_config(password_key, vault_key)
            self._legacy_key = None
        self.clients[client] = session_key
        if self._key is None:
            self._key, self.store = vault_key, store
            self._sources = saved["workflows"]
            for name, source in self._sources.items():
                self._load_source(name, source)
            self._refresh()
            for item in saved["panels"]:
                self._add(item["workflow"], item.get("params"), item["id"])
            self.state["active"] = saved["active"] or self.state["active"]
        self._emit(self._packet(client, {"type": "unlocked"}))

    def _receive(self, widget, packet, buffers):
        self._record_wire(packet)
        try:
            if packet.get("type") == "unlock":
                self._unlock(packet)
                return
            if packet.get("type") != "sealed" or packet.get("client") not in self.clients:
                return
            client = packet["client"]
            aad = PROTOCOL + b":" + client.encode() + b":c2s"
            raw = AESGCM(self.clients[client]).decrypt(base64.b64decode(packet["nonce"]),
                    base64.b64decode(packet["data"]), aad)
            try:
                self._dispatch(json.loads(raw))
            except Exception as error:
                self.state['message'] = f'{type(error).__name__}: {error}'
                self.publish()
        except (InvalidTag, ValueError, KeyError):
            self._emit({"type": "locked", "client": packet.get("client"),
                        "message": "请输入正确密码"})

    def _load_source(self, name, source):
        module = ModuleType("private_workflow")
        exec(compile(source, "<private-workflow>", "exec"), module.__dict__)
        self._modules[name] = module

    def load(self, name):
        return self._modules[name]

    def _refresh(self):
        self.state["workflows"] = [{"id": name, "name": module.SPEC["name"],
            "description": module.SPEC.get("description", "")}
            for name, module in self._modules.items()]

    def _add(self, name, params=None, session_id=None):
        session = PrivateWorkflowSession(self, name, params, session_id)
        self.sessions[session.id] = session
        self.state["active"] = session.id
        self.publish()
        return session

    def publish(self):
        self.state["panels"] = [session.state for session in self.sessions.values()]
        self.send({"type": "runtime_state", "name": "state", "value": self.state})

    def set_payload(self, name, panel_id, value):
        values = {**getattr(self, name), panel_id: value}
        setattr(self, name, values)
        self.send({"type": "runtime_state", "name": name, "value": values})

    def write_text_result(self, path, text):
        self.store.write(path.relative_to(self.directory).as_posix(), text.encode())

    def save_settings(self):
        with self._lock:
            saved = {"workflows": self._sources, "active": self.state["active"], "panels": [
                {"id": s.id, "workflow": s.state["selected"], "params": s.params}
                for s in self.sessions.values()]}
            self.store.write("state.wfs", json.dumps(saved, ensure_ascii=False).encode())

    def _dispatch(self, content):
        action = content["action"]
        if action == "sync":
            self.publish()
            self.send({"type": "runtime_snapshot", "values": {name: getattr(self, name)
                for name in ("state", "previews", "texts", "results", "chats", "files", "histories")}})
        elif action == "import":
            name = Path(content["name"]).name
            self._load_source(name, content["source"])
            self._sources[name] = content["source"]
            self._refresh()
            self._add(name)
            self.save_settings()
        elif action == "add":
            self._add(content["workflow"])
            self.save_settings()
        elif action == "settings":
            for item in content["panels"]:
                session = self.sessions[item["id"]]
                session.params.update(item["params"])
                session.state["params"] = dict(session.params)
            self.state["active"] = content["active"]
            self.save_settings()
            self.send({"type": "settings_saved", "request": content.get("request"), "error": ""})
        elif action == "run":
            session = self.sessions[content["id"]]
            if not session.state["busy"]:
                session.start(content["params"], run_id=content.get("run_id"))
        elif action == "cancel":
            self.sessions[content["id"]].cancel.set()
        elif action == "export":
            name = self.sessions[content["id"]].state["selected"]
            self.send({"type": "workflow", "name": name, "source": self._sources[name]})
        elif action == "download":
            name = Path(content["name"]).name
            self.send({"type": "download", "name": name, "mime": "text/plain"},
                      [self.store.read("results/" + name)])
        elif action == "remove":
            self.sessions.pop(content["id"])
            self.state["active"] = next(iter(self.sessions), "")
            self.publish()
            self.save_settings()
        elif action == "refresh":
            self._refresh()
            self.publish()

