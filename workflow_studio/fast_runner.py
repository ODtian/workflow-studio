"""Start the existing notebook runtime and stream text or vision chat."""
import json
from pathlib import Path
import subprocess
import sys
import time

import requests

from template_parameters import template_options
from vllm_runner import MODELS, ensure_model, model_files

ENDPOINT = "http://127.0.0.1:8787"
LOG = Path("/tmp/workflow-studio-fast.log")
_process = None
_model = None
_startup = {}


def release():
    global _process, _model
    if _process is not None:
        if _process.poll() is None:
            _process.terminate()
            _process.wait(timeout=30)
        _process = None
        _model = None


def prepare_fast(params, ctx):
    global _process, _model, _startup
    if _process is not None and _process.poll() is None and params["model"] == _model:
        ctx.metadata(**_startup)
        return
    started = time.monotonic()
    path = ensure_model(params["model"], ctx)
    release()
    import vllm_runner
    vllm_runner.release()
    import llama_runner
    llama_runner.release()
    if "comfy.model_management" in sys.modules:
        sys.modules["comfy.model_management"].soft_empty_cache()
    ctx.status("用 notebook 运行库加载模型…")
    command = [sys.executable, str(Path(__file__).with_name("fast_worker.py")), "--model", str(path)]
    with LOG.open("w") as log:
        _process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    _model = params["model"]
    while True:
        ctx.check_cancelled()
        if _process.poll() is not None:
            raise RuntimeError(LOG.read_text(encoding="utf-8")[-5000:])
        try:
            response = requests.get(ENDPOINT + "/health", timeout=2)
            if response.status_code == 200:
                _startup = {"引擎": "Transformers · 快速启动", "模型": _model,
                            "环境安装秒": 0, "输入模态": "文本 + 图片", **response.json(),
                            "初始化合计秒": round(time.monotonic() - started, 3)}
                ctx.metadata(**_startup)
                return
        except requests.ConnectionError:
            pass
        time.sleep(0.2)


def run_fast(params, ctx):
    prepare_fast(params, ctx)
    messages = []
    if params["system_prompt"].strip():
        messages.append({"role": "system", "content": params["system_prompt"]})
    messages.extend(params.get("messages") or [{"role": "user", "content": params["prompt"]}])
    ctx.metadata(上下文消息=len(messages))
    body = {"messages": messages, "max_tokens": int(params["max_tokens"]),
            "temperature": float(params["temperature"]), "top_p": float(params["top_p"]),
            "top_k": int(params["top_k"]), "min_p": float(params["min_p"]),
            "repetition_penalty": float(params["repeat_penalty"]),
            "chat_template_kwargs": template_options(params),
            "stop": [line for line in params["stop"].splitlines() if line]}
    if int(params["seed"]) >= 0:
        body["seed"] = int(params["seed"])
    ctx.status("生成中…")
    started = time.monotonic()
    first = None
    usage = {}
    answer, reasoning = "", ""
    try:
        with requests.post(ENDPOINT + "/chat", json=body, stream=True, timeout=(10, 600)) as response:
            response.raise_for_status()
            for line in response.iter_lines(chunk_size=1):
                ctx.check_cancelled()
                if not line.startswith(b"data: "):
                    continue
                data = line[6:]
                if data == b"[DONE]":
                    break
                chunk = json.loads(data)
                if "error" in chunk:
                    raise RuntimeError(chunk["error"])
                if "usage" in chunk:
                    usage = chunk["usage"]
                if "studio_response" in chunk:
                    answer = chunk["studio_response"]["content"]
                    reasoning = chunk["studio_response"]["reasoning"]
                    if (answer or reasoning) and first is None:
                        first = time.monotonic()
                        cold_first = _startup.setdefault("首次初始化及首字秒",
                            round(_startup["初始化合计秒"] + first - started, 3))
                        ctx.metadata(请求首字秒=round(first - started, 3),
                                     首次初始化及首字秒=cold_first)
                    ctx.response(answer, reasoning)
        ctx.response(answer, reasoning, final=True)
        count = usage.get("completion_tokens", 0)
        ctx.metadata(输出tokens=count, 每秒tokens=round(count / (time.monotonic() - (first or started)), 1))
        return answer
    finally:
        if params["residency"] == "release":
            release()
