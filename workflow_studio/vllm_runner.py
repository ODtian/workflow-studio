"""GPU text and vision chat through a local vLLM server."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import requests

from template_parameters import template_options

ROOT = Path(__file__).parent
MODELS = Path(os.environ.get("WORKFLOW_MODELS_DIR", "/tmp/molab-comfy-runtime/models"))
RUNTIME = Path("/tmp/workflow-studio-vllm")
VERSION = "0.32.0"
ENDPOINT = "http://127.0.0.1:8787"
LOG = Path("/tmp/workflow-studio-vllm.log")
_process = None
_server_key = None


def catalog():
    import workspace_store
    models = json.loads((ROOT / "llm_models.json").read_text(encoding="utf-8"))
    models.update(workspace_store.read().get("llm_catalog", {}))
    return models


def model_files():
    directory = MODELS / "LLM"
    directory.mkdir(parents=True, exist_ok=True)
    local = {path.parent.relative_to(directory).as_posix()
             for path in directory.rglob("config.json") if ".cache" not in path.parts}
    return sorted(local | set(catalog()))


def ensure_model(name, ctx):
    directory = MODELS / "LLM" / name
    entry = catalog().get(name)
    if entry is None:
        return directory
    missing = [item for item in entry["files"]
               if not (directory / item["name"]).exists()
               or (directory / item["name"]).stat().st_size != item["size"]]
    if missing:
        directory.mkdir(parents=True, exist_ok=True)
        if "drive_id" not in missing[0]:
            from huggingface_hub import snapshot_download
            ctx.status("从 Hugging Face 加载模型…")
            snapshot_download(repo_id=entry["download_repo"], revision=entry["revision"],
                              local_dir=directory, allow_patterns=[item["name"] for item in missing],
                              max_workers=3)
            return directory
        from files_bridge import connect_drive
        provider = connect_drive()

        def download(item):
            ctx.status("从 Drive 加载模型 · " + item["name"])
            with (directory / item["name"]).open("wb") as stream:
                provider.download(item["drive_id"], stream, item["size"],
                                  lambda amount: ctx.check_cancelled(), ctx.cancel)

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(download, missing))
    return directory


def ensure_runtime(ctx):
    executable = RUNTIME / "bin/vllm"
    if executable.exists():
        return executable
    ctx.status("准备 vLLM GPU 运行环境…")
    with Path("/tmp/workflow-studio-vllm-install.log").open("w") as log:
        subprocess.run(["uv", "venv", "--python", sys.executable, str(RUNTIME)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(["uv", "pip", "install", "--python", str(RUNTIME / "bin/python"),
                        "vllm==" + VERSION, "--torch-backend=auto"],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([str(executable), "download-kernels"],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    return executable


def release():
    global _process, _server_key
    if _process is not None:
        if _process.poll() is None:
            _process.terminate()
            _process.wait(timeout=30)
        _process = None
        _server_key = None


def start_server(params, ctx):
    global _process, _server_key
    path = ensure_model(params["model"], ctx)
    key = (str(path), int(params["n_ctx"]), int(params["n_batch"]),
           float(params["gpu_memory_utilization"]), int(params["speculative_tokens"]))
    if _process is not None and _process.poll() is None and key == _server_key:
        return
    release()
    if "fast_runner" in sys.modules:
        sys.modules["fast_runner"].release()
    import llama_runner
    llama_runner.release()
    if "comfy.model_management" in sys.modules:
        sys.modules["comfy.model_management"].soft_empty_cache()
    executable = ensure_runtime(ctx)
    command = [str(executable), "serve", str(path), "--host", "127.0.0.1", "--port", "8787",
               "--served-model-name", "studio-llm", "--max-model-len", str(key[1]),
               "--max-num-batched-tokens", str(key[2]), "--max-num-seqs", "1",
               "--gpu-memory-utilization", str(key[3]),
               "--reasoning-parser", "qwen3", "--enable-auto-tool-choice",
               "--tool-call-parser", "qwen3_coder", "--limit-mm-per-prompt",
               json.dumps({"image": 8, "video": 0})]
    if key[4]:
        command += ["--speculative-config", json.dumps({"method": "mtp", "num_speculative_tokens": key[4]})]
    environment = {**os.environ, "VLLM_USE_FLASHINFER_SAMPLER": "0",
                   "VLLM_NO_USAGE_STATS": "1", "HF_HUB_OFFLINE": "1",
                   "OMP_NUM_THREADS": "1", "TORCHINDUCTOR_COMPILE_THREADS": "2"}
    ctx.status("加载 vLLM · FP8 + MTP…")
    started = time.monotonic()
    with LOG.open("w") as log:
        _process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                    env=environment, start_new_session=True)
    _server_key = key
    while True:
        ctx.check_cancelled()
        if _process.poll() is not None:
            raise RuntimeError(LOG.read_text(encoding="utf-8")[-5000:])
        try:
            response = requests.get(ENDPOINT + "/health", timeout=2)
            if response.status_code == 200:
                break
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
    ctx.metadata(引擎="vLLM · FP8 + MTP", 模型=params["model"],
                 上下文长度=key[1], MTP预测步数=key[4],
                 服务启动秒=round(time.monotonic() - started, 2), 输入模态="文本 + 图片")


def prepare_vllm(params, ctx):
    start_server(params, ctx)


def run_vllm(params, ctx):
    start_server(params, ctx)
    messages = []
    if params["system_prompt"].strip():
        messages.append({"role": "system", "content": params["system_prompt"]})
    messages.extend(params.get("messages") or [{"role": "user", "content": params["prompt"]}])
    body = {"model": "studio-llm", "messages": messages, "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": int(params["max_tokens"]), "temperature": float(params["temperature"]),
            "top_p": float(params["top_p"]), "top_k": int(params["top_k"]),
            "min_p": float(params["min_p"]), "repetition_penalty": float(params["repeat_penalty"]),
            "chat_template_kwargs": template_options(params),
            "stop": [line for line in params["stop"].splitlines() if line]}
    if int(params["seed"]) >= 0:
        body["seed"] = int(params["seed"])
    ctx.metadata(引擎="vLLM · FP8 + MTP", 模型=params["model"],
                 MTP预测步数=int(params["speculative_tokens"]), 上下文消息=len(messages))
    ctx.status("生成中…")
    started = time.monotonic()
    first_token = None
    answer, reasoning = "", ""
    usage = {}
    try:
        with requests.post(ENDPOINT + "/v1/chat/completions", json=body,
                           stream=True, timeout=(10, 600)) as response:
            response.raise_for_status()
            for line in response.iter_lines(chunk_size=1024):
                ctx.check_cancelled()
                if not line.startswith(b"data: "):
                    continue
                data = line[6:]
                if data == b"[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                if not chunk.get("choices"):
                    continue
                delta = chunk["choices"][0]["delta"]
                text = delta.get("content") or ""
                thought = delta.get("reasoning") or delta.get("reasoning_content") or ""
                if text or thought:
                    if first_token is None:
                        first_token = time.monotonic()
                        ctx.metadata(首字秒=round(first_token - started, 3))
                    answer += text
                    reasoning += thought
                    ctx.response(answer, reasoning)
        ctx.response(answer, reasoning, final=True)
        count = usage.get("completion_tokens", 0)
        ctx.metadata(输出tokens=count,
                     每秒tokens=round(count / max(time.monotonic() - (first_token or started), 0.001), 1))
        return answer
    finally:
        if params["residency"] == "release":
            release()
