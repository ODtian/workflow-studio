"""Pi tools, resources and sessions over pipes to the resident native model."""
import atexit
import json
import io
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import uuid
import llama_runner
import workspace_store
from content_store import enabled

ROOT = Path(__file__).parent / "pi_bridge"
_client = None
_client_lock = threading.Lock()


class PiClient:
    def __init__(self, ctx):
        if not (ROOT / "node_modules/@earendil-works/pi-coding-agent/package.json").exists():
            ctx.status("安装 Pi 运行库…")
            subprocess.run([shutil.which("npm"), "install", "--prefix", str(ROOT), "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund"], check=True, capture_output=True, text=True)
        workspace = Path(os.environ.get("WORKFLOW_WORKSPACE", os.getcwd()))
        self.log = io.StringIO()
        self.process = subprocess.Popen([shutil.which("node"), str(ROOT / "worker.mjs")], cwd=workspace,
            env={**os.environ, "PI_OFFLINE":"1", "WORKFLOW_PI_DIR":str(workspace / ".pi" / "agent")},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self.read_errors, daemon=True).start()
        self.pending = {}
        self.write_lock = threading.Lock()
        self.model_events = None
        threading.Thread(target=self.read, daemon=True).start()
        atexit.register(self.close)

    def read(self):
        for line in self.process.stdout:
            record = json.loads(line)
            target = self.model_events if record["type"] == "model_request" else self.pending.get(record.get("request"))
            if target is not None:
                target.put(record)
        for target in list(self.pending.values()):
            target.put({"type":"result", "error":self.log.getvalue()})

    def read_errors(self):
        for line in self.process.stderr:
            self.log.write(line)

    def send(self, value):
        with self.write_lock:
            self.process.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
            self.process.stdin.flush()

    def request(self, panel, params, command, *, inference=False):
        request = uuid.uuid4().hex
        events = self.pending[request] = queue.Queue()
        if inference:
            self.model_events = events
        config = {k:v for k,v in params.items() if k not in ("messages", "pi_request")}
        config.update(workspace_store.read().get("pi_preferences", {}).get(panel.id, {}))
        self.send({"type":"command", "panel":panel.id, "config":config,
                   "request":request, **command})
        return request, events

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()


def prepare_pi(ctx):
    global _client
    with _client_lock:
        if _client is None or _client.process.poll() is not None:
            _client = PiClient(ctx)
    return _client


def apply_record(panel, record):
    if record["type"] == "result" and record.get("snapshot"):
        snapshot = record["snapshot"]
        session_file = Path(snapshot["file"]) if snapshot["file"] else None
        saved_session = str(session_file) if session_file is not None and session_file.is_file() else None
        workspace_store.edit(lambda state: state.setdefault("pi_preferences", {}).update({
            panel.id: {"saved_tools": snapshot["activeTools"], "saved_session": saved_session}}))
        workspace = Path(os.environ["WORKFLOW_WORKSPACE"])
        resources = [path for directory in (".pi/skills", ".pi/prompts", ".pi/agent/skills", ".pi/agent/prompts")
                     for path in (workspace / directory).rglob("*") if path.is_file()]
        if saved_session:
            resources.append(session_file)
        workspace_store.save_files(resources)
        panel.update(pi=record["snapshot"])
    elif record["type"] in ("skill", "export"):
        panel.owner.send({**record, "type":"pi_" + record["type"], "id":panel.id})


def control(panel, command, params=None):
    from panel import RunContext
    ctx = RunContext(panel, threading.Event())
    client = prepare_pi(ctx)
    request, events = client.request(panel, params or panel.params, command)
    try:
        while True:
            record = events.get()
            apply_record(panel, record)
            if record["type"] == "result":
                if command["action"] == "save_skill":
                    panel.owner.send({"type":"pi_skill_saved", "id":panel.id, "error":record.get("error", "")})
                if record.get("error"):
                    panel.update(message=record["error"])
                return
    finally:
        client.pending.pop(request)


class NativeContext:
    def __init__(self, client, request, ctx):
        self.client, self.request, self.ctx = client, request, ctx
        self.panel, self.values, self.calls = ctx.panel, {}, []

    def check_cancelled(self):
        self.ctx.check_cancelled()

    def status(self, message):
        self.ctx.status(message)

    def metadata(self, **values):
        self.values.update(values)
        self.ctx.metadata(**{("模型首字秒" if k == "首字秒" else k):v for k,v in values.items()})

    def response(self, content, reasoning="", *, final=False):
        self.client.send({"type":"model_delta", "id":self.request, "content":content, "reasoning":reasoning})

    def tool_calls(self, calls):
        self.calls = calls


def run_pi(params, ctx):
    started = time.monotonic()
    client = prepare_pi(ctx)
    request, events = client.request(ctx.panel, params, params["pi_request"], inference=True)
    ctx.metadata(对话层="Pi 1.4.0", 通信="JSONL 进程管道", Pi状态="运行中")
    first = None
    worker = None

    def generate(record):
        native = NativeContext(client, record["id"], ctx)
        try:
            llama_runner.run_llama({**params, "system_prompt":"", "messages":record["messages"], "tools":record["tools"]}, native)
            client.send({"type":"model_done", "id":record["id"], "calls":native.calls,
                         "outputTokens":native.values.get("输出tokens",0), "inputTokens":native.values.get("输入tokens",0)})
        except Exception as exc:
            client.send({"type":"model_error", "id":record["id"], "error":str(exc)})
    try:
        while True:
            ctx.check_cancelled()
            try:
                record = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if record["type"] == "model_request":
                import marimo as mo
                worker = mo.Thread(target=generate, args=(record,), daemon=True)
                worker.start()
            elif record["type"] == "event":
                event = record["event"]
                ctx.panel.owner.send({"type":"pi_event", "id":ctx.panel.id, "event":event})
                if event["type"] == "message_update" and first is None:
                    first = time.monotonic()
                    ctx.metadata(首字秒=round(first-started,3))
                if event["type"] == "tool_execution_start":
                    ctx.status("执行工具 · " + event["toolName"])
                elif event["type"] == "turn_start":
                    ctx.status("Pi 正在生成…")
            elif record["type"] == "result":
                apply_record(ctx.panel, record)
                if record.get("error"):
                    raise RuntimeError(record["error"])
                ctx.metadata(Pi状态="完成", Pi会话=record["snapshot"]["id"])
                return record["content"]
    except Exception:
        ctx.cancel.set()
        if worker is not None:
            worker.join()
        client.close()
        raise
    finally:
        client.model_events = None
        client.pending.pop(request)
