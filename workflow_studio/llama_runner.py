"""llama.cpp inference through Python bindings in the notebook process."""
from __future__ import annotations

import gc
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from template_parameters import reasoning_field, template_options
from gguf_roles import profile as gguf_profile, validate_files

ROOT = Path(__file__).parent
MODELS = Path(os.environ.get("WORKFLOW_MODELS_DIR", "/tmp/molab-comfy-runtime/models"
                          if Path("/marimo").exists() else ROOT / "models"))
_loaded = None
_loaded_key = None
_library = None
MODEL_DIRECTORY = "Qwen3.8-27B-Uncensored-GGUF"
DEFAULT_MODEL = MODEL_DIRECTORY + "/Qwen3.8-27B-Uncensored-OrcaRouter-Q8_0.gguf"
DEFAULT_MTP = MODEL_DIRECTORY + "/MTP/Qwen3.8-27B-Uncensored-OrcaRouter-MTP-Q8_0.gguf"
DEFAULT_MMPROJ = MODEL_DIRECTORY + "/AUX/mmproj-Qwen3.8-27B-Uncensored-OrcaRouter-BF16.gguf"


def catalog():
    import workspace_store
    entries = json.loads((ROOT / "llm_models.json").read_text(encoding="utf-8"))
    entries.update(workspace_store.read().get("llm_catalog", {}))
    return entries


def ensure_files(params, ctx):
    entry = catalog().get(params["model"])
    if entry:
        directory = MODELS / "LLM" / entry["directory"]
        selected = [params["model"], params.get("mmproj"), params.get("mtp")]
        missing = [item["name"] for item in entry["files"]
                   if entry["directory"] + "/" + item["name"] in selected
                   and not (directory / item["name"]).exists()]
        if missing:
            from huggingface_hub import snapshot_download
            ctx.status("下载 GGUF 主模型及配套权重…")
            snapshot_download(repo_id=entry["download_repo"], revision=entry["revision"],
                              local_dir=directory, allow_patterns=missing, max_workers=3)


def model_files():
    directory = MODELS / "LLM"
    directory.mkdir(parents=True, exist_ok=True)
    local = {name for name, info in gguf_files() if info["role"] == "model"}
    return sorted(local | {name for name in catalog() if name.endswith(".gguf")})


def gguf_files():
    directory = MODELS / "LLM"
    return [(path.relative_to(directory).as_posix(), gguf_profile(path))
            for path in directory.rglob("*.gguf")
            if "-of-" not in path.stem or "-00001-of-" in path.stem]


def companion_files(role):
    local = {name for name, info in gguf_files()
             if info["role"] == role or role == "mtp" and info["has_mtp"]}
    return sorted(local | {DEFAULT_MTP if role == "mtp" else DEFAULT_MMPROJ})


def selected_file(params, key):
    selected = params.get(key, "")
    return MODELS / "LLM" / selected if selected else None


def prepare(ctx):
    global _library
    if _library is not None:
        return _library
    if importlib.util.find_spec("llama_cpp") is None:
        cuda = shutil.which("nvidia-smi") is not None
        release_tag = "v0.3.36-cu130" if cuda else "v0.3.36"
        platform = "win_amd64" if sys.platform == "win32" else (
            "manylinux_2_35_x86_64" if cuda else "manylinux2014_x86_64.manylinux_2_17_x86_64")
        wheel = f"https://github.com/abetlen/llama-cpp-python/releases/download/{release_tag}/llama_cpp_python-0.3.36-py3-none-{platform}.whl"
        ctx.status("下载并安装官方预编译 llama.cpp · " + ("CUDA 13.0" if cuda else "CPU"))
        installer = ["uv", "pip", "install", "--python", sys.executable] if shutil.which("uv") else [sys.executable, "-m", "pip", "install"]
        log_path = Path("/tmp/workflow-studio-llama-install.log")
        with log_path.open("w", encoding="utf-8") as log:
            installed = subprocess.run([*installer, "--only-binary=:all:", wheel],
                                       stdout=log, stderr=subprocess.STDOUT)
        if installed.returncode:
            raise RuntimeError(log_path.read_text(encoding="utf-8")[-3000:])
        importlib.invalidate_caches()
    import llama_cpp
    _library = llama_cpp
    return _library


def release():
    global _loaded, _loaded_key
    if _loaded is not None:
        _loaded.close()
        _loaded = None
        _loaded_key = None
        gc.collect()


class ResponseChannels:
    markers = re.compile(r"(<think>|</think>|<analysis>|</analysis>|<\|channel>(?:thought|analysis|final)\s*|<channel\|>)")

    def __init__(self):
        self.prefix = ""

    def split(self, text):
        answer, reasoning = [], []
        thinking = False
        for part in self.markers.split(self.prefix + text):
            if part in ("<think>", "<analysis>") or part.startswith("<|channel>thought") or part.startswith("<|channel>analysis"):
                thinking = True
            elif part in ("</think>", "</analysis>", "<channel|>") or part.startswith("<|channel>final"):
                thinking = False
            else:
                (reasoning if thinking else answer).append(part)
        return "".join(answer).strip(), "".join(reasoning).strip()


@lru_cache(maxsize=4)
def chat_formatter(template, eos, bos, stop):
    from llama_cpp.llama_chat_format import Jinja2ChatFormatter
    return Jinja2ChatFormatter(template=template, eos_token=eos, bos_token=bos, stop_token_ids=[stop])


def configure_chat(llm, params, channels):
    if getattr(llm, "_studio_mtp", False):
        return llm.configure_chat(template_options(params), channels)
    from llama_cpp.llama_chat_format import chat_formatter_to_chat_completion_handler
    template = llm.metadata.get("tokenizer.chat_template")
    options = template_options(params)
    vision_handler = getattr(llm, "_studio_vision_handler", None)
    if vision_handler:
        formatter = chat_formatter(template, llm._model.token_get_text(llm.token_eos()),
                                   llm._model.token_get_text(llm.token_bos()), llm.token_eos())

        def multimodal_messages(**kwargs):
            messages = vision_handler._get_template_messages(kwargs["messages"], "<__media__>")
            formatted = formatter(messages=messages, **options)
            match = re.search(r"(<think>|<analysis>|<\|channel>(?:thought|analysis))\s*$", formatted.prompt)
            channels.prefix = match[0] if match else ""
            return vision_handler(**kwargs, **options)

        llm.chat_handler = multimodal_messages
        return bool("enable_thinking" in template or "thinking" in template)
    llm.chat_handler = None
    if template and llm.chat_format.startswith("chat_template"):
        formatter = chat_formatter(template, llm._model.token_get_text(llm.token_eos()),
                                   llm._model.token_get_text(llm.token_bos()), llm.token_eos())

        def format_messages(**kwargs):
            response = formatter(**kwargs, **options)
            match = re.search(r"(<think>|<analysis>|<\|channel>(?:thought|analysis))\s*$", response.prompt)
            channels.prefix = match[0] if match else ""
            return response

        llm.chat_handler = chat_formatter_to_chat_completion_handler(format_messages)
    return bool(template and ("enable_thinking" in template or "thinking" in template))


def load_model(params, ctx):
    global _loaded, _loaded_key
    started = time.monotonic()
    ensure_files(params, ctx)
    path = MODELS / "LLM" / params["model"]
    projector = selected_file(params, "mmproj")
    mtp = params.get("mtp", "")
    draft = selected_file(params, "mtp") if mtp != "embedded" else None
    validate_files(path, projector, draft, embedded=mtp == "embedded")
    llama_cpp = prepare(ctx)
    ctx.metadata(运行库准备秒=round(time.monotonic() - started, 3))
    key = (str(path), path.stat().st_mtime_ns, int(params["n_ctx"]), int(params["n_gpu_layers"]),
           int(params["n_batch"]), params["chat_format"], str(projector) if projector else "", "embedded" if mtp == "embedded" else str(draft) if draft else "", int(params.get("speculative_tokens", 2)))
    if key != _loaded_key:
        release()
        if "comfy.model_management" in sys.modules:
            sys.modules["comfy.model_management"].soft_empty_cache()
        ctx.status("加载 GGUF · " + path.name)
        started = time.monotonic()
        if mtp and key[8]:
            from mtp_runner import MTPModel
            _loaded = MTPModel(path, projector, draft, params, ctx)
        else:
            handler = None
            if projector:
                from llama_cpp.llama_chat_format import MTMDChatHandler
                handler = MTMDChatHandler(clip_model_path=str(projector), verbose=False,
                                          use_gpu=int(params["n_gpu_layers"]) != 0)
            _loaded = llama_cpp.Llama(model_path=str(path), n_ctx=key[2], n_gpu_layers=key[3],
                                     n_batch=key[4], chat_format=params["chat_format"] or None,
                                     chat_handler=handler, flash_attn=True, verbose=False)
            _loaded._studio_vision_handler = handler
            if handler:
                ctx.status("加载图像投影器 · " + projector.name)
                handler._init_mtmd_context(_loaded)
        _loaded_key = key
        ctx.metadata(GGUF加载秒=round(time.monotonic() - started, 3))
    ctx.metadata(输入模态="文本 + 图片" if projector else "文本", 图像投影器=projector.name if projector else "",
                 MTP草稿头="主模型内嵌 MTP" if mtp == "embedded" else draft.name if draft else "关闭")
    return _loaded, llama_cpp


def reasoning_control():
    return reasoning_field(_loaded)


def publish_template_controls(llm, ctx):
    session = ctx.panel
    spec = session.state["spec"]
    field = reasoning_field(llm)
    fields = [field if item["key"] == "reasoning_effort" else item for item in spec["fields"]]
    if fields != spec["fields"]:
        session.update(spec={**spec, "fields": fields})


def prepare_llama(params, ctx):
    started = time.monotonic()
    llm, _ = load_model(params, ctx)
    publish_template_controls(llm, ctx)
    ctx.metadata(预载秒=round(time.monotonic() - started, 3))


def run_llama(params, ctx):
    llm, llama_cpp = load_model(params, ctx)
    publish_template_controls(llm, ctx)
    channels = ResponseChannels()
    supports_thinking = configure_chat(llm, params, channels)
    ctx.metadata(引擎="llama.cpp · notebook 进程内", 模型=params["model"],
                 后端="GPU" if llama_cpp.llama_supports_gpu_offload() and int(params["n_gpu_layers"]) != 0 else "CPU",
                 Thinking模板="可控制" if supports_thinking else "模型默认",
                 对话模板="GGUF tokenizer.chat_template", reasoning_effort=params.get("reasoning_effort", "") or "模型默认")
    sampling = dict(max_tokens=int(params["max_tokens"]), temperature=float(params["temperature"]),
                    top_p=float(params["top_p"]), top_k=int(params["top_k"]),
                    min_p=float(params["min_p"]), repeat_penalty=float(params["repeat_penalty"]),
                    seed=int(params["seed"]), stream=True,
                    stop=[line for line in params["stop"].splitlines() if line])
    ctx.status("处理输入，准备生成…")
    started = time.monotonic()
    text = ""
    reasoning_delta = ""
    answer = ""
    reasoning = ""
    first_token = None
    completion = params.get("mode") == "completion"
    if completion:
        stream = llm.create_completion(prompt=params["prompt"], **sampling)
    else:
        messages = []
        if params["system_prompt"].strip():
            messages.append({"role": "system", "content": params["system_prompt"]})
        messages.extend(params.get("messages") or [{"role": "user", "content": params["prompt"]}])
        image_count = sum(1 for message in messages if isinstance(message["content"], list)
                          for item in message["content"] if item["type"] == "image_url")
        if image_count and not getattr(llm, "_studio_vision_handler", None):
            raise ValueError("请在对话设置中选择与 GGUF 配套的 mmproj 图像投影器。")
        if image_count:
            ctx.metadata(上下文图片=image_count)
        ctx.metadata(上下文消息=len(messages))
        stream = llm.create_chat_completion(messages=messages, **sampling)
    try:
        for chunk in stream:
            ctx.check_cancelled()
            choice = chunk["choices"][0]
            delta = choice.get("delta", {})
            piece = choice.get("text", "") if completion else delta.get("content", "") or ""
            thought = delta.get("reasoning_content", "") or ""
            if piece or thought:
                if first_token is None:
                    first_token = time.monotonic()
                    ctx.metadata(首字秒=round(first_token - started, 2))
                text += piece
                reasoning_delta += thought
                answer, reasoning = channels.split(text)
                ctx.response(answer, reasoning_delta + reasoning)
        if getattr(llm, "_studio_mtp", False):
            stats = llm.scheduler.speculative_stats
            ctx.metadata(MTP预测tokens=stats["draft_tokens_proposed"], MTP接受tokens=stats["draft_tokens_accepted"])
        ctx.response(answer, reasoning_delta + reasoning, final=True)
        count = len(llm.tokenize((text + reasoning_delta).encode(), add_bos=False))
        ctx.metadata(输出tokens=count, 每秒tokens=round(count / max(time.monotonic() - (first_token or started), 0.001), 1))
        return answer
    finally:
        stream.close()
        if params["residency"] == "release":
            release()


