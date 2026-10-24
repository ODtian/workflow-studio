"""Pi sessions over JSONL pipes, backed by the kernel's resident llama.cpp model."""
import atexit
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time

import llama_runner

ROOT = Path(__file__).parent / "pi_bridge"
_client = None


class PiClient:
    def __init__(self, ctx):
        package = ROOT / "node_modules/@earendil-works/pi-coding-agent/package.json"
        if not package.exists():
            ctx.status("安装 Pi 对话运行库…")
            subprocess.run([shutil.which("npm"), "install", "--prefix", str(ROOT), "--omit=dev",
                            "--ignore-scripts", "--no-audit", "--no-fund"], check=True, capture_output=True, text=True)
        self.log_path = Path(tempfile.gettempdir()) / "workflow-studio-pi.log"
        self.log = self.log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [shutil.which("node"), str(ROOT / "worker.mjs")], cwd=os.environ.get("WORKFLOW_WORKSPACE", os.getcwd()),
            env={**os.environ, "PI_OFFLINE":"1", "WORKFLOW_PI_DIR":str(self.log_path.with_suffix(""))},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, encoding="utf-8", bufsize=1)
        self.events = queue.Queue()
        threading.Thread(target=self.read, daemon=True).start()
        atexit.register(self.close)

    def read(self):
        for line in self.process.stdout:
            self.events.put(json.loads(line))
        self.events.put({"type":"result", "error":self.log_path.read_text(encoding="utf-8")})

    def send(self, value):
        self.process.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.log.close()


def prepare_pi(ctx):
    global _client
    if _client is None or _client.process.poll() is not None:
        _client = PiClient(ctx)
    return _client


class NativeContext:
    def __init__(self, client, request, ctx):
        self.client, self.request, self.ctx = client, request, ctx
        self.panel = ctx.panel
        self.values = {}

    def check_cancelled(self):
        self.ctx.check_cancelled()

    def status(self, message):
        self.ctx.status(message)

    def metadata(self, **values):
        self.values.update(values)
        self.ctx.metadata(**{("模型首字秒" if key == "首字秒" else key):value for key,value in values.items()})

    def response(self, content, reasoning="", *, final=False):
        self.client.send({"type":"model_delta", "id":self.request, "content":content, "reasoning":reasoning})


def run_pi(params, ctx):
    started = time.monotonic()
    client = prepare_pi(ctx)
    messages = params.get("messages") or [{"role":"user", "content":params["prompt"]}]
    nodes = list(ctx.panel.chat.snapshot()["nodes"])
    client.send({"type":"prompt", "config":{key:value for key,value in params.items() if key != "messages"},
                 "messages":messages, "nodes":nodes, "conversationId":nodes[0]})
    ctx.metadata(对话层="Pi 1.4.0", 通信="JSONL 进程管道", Pi状态="准备")
    reasoning = ""
    first = None
    worker = None

    def generate(record):
        native = NativeContext(client, record["id"], ctx)
        try:
            llama_runner.run_llama({**params, "system_prompt":"", "messages":record["messages"]}, native)
            client.send({"type":"model_done", "id":record["id"], "outputTokens":native.values.get("输出tokens",0)})
        except Exception as exc:
            client.send({"type":"model_error", "id":record["id"], "error":str(exc)})

    try:
        while True:
            ctx.check_cancelled()
            try:
                record = client.events.get(timeout=0.1)
            except queue.Empty:
                continue
            kind = record["type"]
            if kind == "model_request":
                import marimo as mo
                worker = mo.Thread(target=generate, args=(record,), daemon=True)
                worker.start()
            elif kind == "session":
                ctx.metadata(Pi会话=record["id"])
            elif kind == "event":
                event = record["event"]
                if event["type"] == "message_update":
                    partial = event["assistantMessageEvent"].get("partial")
                    if partial:
                        answer = "".join(item["text"] for item in partial["content"] if item["type"] == "text")
                        reasoning = "".join(item["thinking"] for item in partial["content"] if item["type"] == "thinking")
                        if first is None and (answer or reasoning):
                            first = time.monotonic()
                            ctx.metadata(首字秒=round(first - started, 3))
                        ctx.response(answer, reasoning)
                elif event["type"] == "agent_start":
                    ctx.metadata(Pi状态="生成中")
                elif event["type"] == "auto_compaction_start":
                    ctx.metadata(Pi状态="整理上下文")
            elif kind == "result":
                if record.get("error"):
                    raise RuntimeError(record["error"])
                ctx.metadata(Pi状态="完成")
                ctx.response(record["content"], reasoning, final=True)
                return record["content"]
    except Exception:
        ctx.cancel.set()
        if worker is not None:
            worker.join()
        client.close()
        raise
