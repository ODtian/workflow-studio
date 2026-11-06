"""Strata DeepSeek inference through the official precompiled engine and pipes."""
from pathlib import Path
import json
from collections import deque
import importlib
import os
import subprocess
import sys
import threading
import time
from llama_runner import MODELS
from strata_runtime import ROOT, CONTROL, ENGINE, QWEN_ENGINE, ensure_runtime

_engine = None
_service = None
_api = None
_loaded_key = None
_output = deque(maxlen=120)


def _runtime_api():
    global _api
    if _api is None:
        ensure_runtime()
        _api = importlib.import_module("serve.server")
        _api.print = lambda *values, **kwargs: _output.append(" ".join(map(str, values)))
    return _api


def release():
    global _engine, _service, _loaded_key
    if _engine is not None:
        _engine.close()
    _engine = _service = _loaded_key = None


def _load_tokenizer(directory):
    from strata_tokenizer import Tokenizer
    vocab = json.loads((directory / "vocab.json").read_text())
    tokens = [None] * len(vocab)
    for token, index in vocab.items():
        tokens[index] = token
    config = json.loads((directory / "tokenizer.json").read_text())
    return Tokenizer(tokens, (directory / "merges.txt").read_text().split("\n"),
                     json.loads((directory / "token_type.json").read_text()),
                     config.get("pre") or "qwen35", config.get("special_ids"))


def prepare_strata(params, ctx):
    global _engine, _service, _loaded_key
    path = MODELS / "LLM" / params["model"]
    draft = params.get("dspark_file", "")
    dspark = str(MODELS / "LLM" / draft) if draft else ""
    vector = path.parent.parent / "Huihui-Qwen3.8-Flash-Next-refusal-direction-r.gguf"
    key = (str(path), int(params["n_ctx"]), float(params["strata_ram_gb"]), dspark, vector.exists())
    if _engine is not None and _engine.alive() and key == _loaded_key:
        return _service
    from model_residency import release as release_models
    release_models("llama")
    ensure_runtime(ctx)
    from gguf_reader import GGUFFile
    architecture = GGUFFile(path).metadata["general.architecture"]
    deepseek = architecture == "deepseek41"
    pack = path.parent / "strata-pack"
    inputs = {"model": str(path), "dspark": dspark, "architecture": architecture}
    marker = pack / "studio-inputs.json"
    if not marker.exists() or json.loads(marker.read_text()) != inputs:
        ctx.status("建立 Strata 模型索引…")
        if deepseek:
            shards = sorted(path.parent.glob(path.name.split("-00001-of-")[0] + "-*-of-*.gguf"))
            command = [sys.executable, str(CONTROL / "tools/dsv41/pack_gguf.py"),
                       "--model", str(path.parent), "--shards", *[p.name for p in shards],
                       "--engram", str(path.parent / "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf"),
                       "--engram-meta", str(ROOT / "metadata/UD-Q8_K_XL/DeepSeek-V4.1-Flash-1017-UD-Q8_K_XL-00001-of-00009.gguf"),
                       "--out", str(pack)]
            if dspark:
                command += ["--dspark-gguf", dspark, "--dspark-noise-token", "128799",
                            "--dspark-markov-rank", "256"]
            projector = path.parent / "mmproj-BF16.gguf"
            if projector.exists():
                command += ["--mmproj", str(projector)]
        else:
            command = [sys.executable, str(CONTROL / "tools/iq_pack.py"),
                       "--gguf", str(path), "--out", str(pack)]
        log = ROOT / ("deepseek-pack.log" if deepseek else "qwen-pack.log")
        with log.open("w") as output:
            result = subprocess.run(command, cwd=CONTROL, stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(log.read_text()[-5000:])
        marker.write_text(json.dumps(inputs))
    api = _runtime_api()
    from strata_control.dsv41_engine import start_env
    exe = ENGINE if deepseek else QWEN_ENGINE
    env = start_env(exe)
    env.update(CUDA_VISIBLE_DEVICES="0", CUDA_DEVICE_ORDER="PCI_BUS_ID")
    if deepseek:
        args = ["--pack", str(pack), "--max-context", str(key[1]), "--eos", "1",
                "--dspark", "auto" if dspark else "none"]
        if key[2] >= 0:
            args += ["--ssd-cache", str(key[2])]
    else:
        args = ["--pack", str(pack), "--native", str(path),
                "--ple-gguf", str(path.with_name(path.name.replace("-00001-", "-00002-"))),
                "--expert-profile", str(CONTROL / "data/expert-profile.bin"),
                "--expert-cache", "auto", "--prefill", "auto", "--spec", "4", "--spec-min-p", "0.5",
                "--max-context", str(key[1])]
        if vector.exists():
            args += ["--control-vector-scaled", str(vector) + ":1.0",
                     "--control-vector-layer-range", "4", "44", "--cvec-mode", "project", "--cvec-dir", "per-layer"]
    ctx.status("加载 Strata · CUDA 13")
    _engine = api.StrataEngine(str(exe), args, cwd=str(CONTROL),
                              log=str(ROOT / ("deepseek-engine.log" if deepseek else "qwen-engine.log")), env=env)
    tokenizer = _load_tokenizer(pack / "tokenizer")
    template = pack / "tokenizer/chat_template.jinja"
    if deepseek:
        from serve.dsml import pick_template
        template, _ = pick_template(template)
    _service = api.Service(_engine, tokenizer, api.ChatTemplate(template), model_name=path.stem,
                           sampling_defaults={"experimental_speed_projection": True} if vector.exists() else None)
    _service.model_arch = architecture
    _service.set_family("deepseek41" if deepseek else None)
    _loaded_key = key
    ctx.metadata(引擎="Strata", 版本="0.1.56", 架构=architecture, 后端="CUDA 13", 通信="stdin/stdout")
    ctx.status("Strata 模型已就绪")
    return _service


def run_strata(params, ctx):
    service = prepare_strata(params, ctx)
    effort = params.get('reasoning_effort') or ('high' if params.get('thinking') == 'on' else 'none')
    request = {'model': service.model, 'messages': params['messages'],
        'max_tokens': int(params['max_tokens']), 'temperature': float(params['temperature']),
        'top_p': float(params['top_p']), 'top_k': int(params['top_k']),
        'min_p': float(params['min_p']), 'repetition_penalty': float(params['repeat_penalty']),
        'seed': int(params['seed']), 'reasoning_effort': effort}
    if params.get('tools'):
        request['tools'] = params['tools']
    if params.get('stop'):
        request['stop'] = params['stop'].splitlines()
    request.update(service.sampling_defaults)
    api = _runtime_api()
    messages, tools, options = api.openai_to_messages(request)
    cancel = ctx.cancel
    ids, thinking, max_new = service.prepare(messages, tools, options, request['max_tokens'], cancel=cancel)
    request.update(options)
    ctx.metadata(引擎='Strata', 模型=params['model'], 后端='CUDA', 通信='stdin/stdout', reasoning_effort=effort)
    text, reasoning, calls = '', '', {}
    first = None
    first_answer = None
    started = time.monotonic()
    stream = api.openai_chunks(service, request, ids, thinking, tools, max_new, cancel)
    try:
        for record in stream:
            ctx.check_cancelled()
            if record is None:
                continue
            usage = record.get('usage')
            if usage:
                ctx.metadata(输入tokens=usage['prompt_tokens'], 输出tokens=usage['completion_tokens'])
            timings = record.get('timings')
            if timings:
                ctx.metadata(每秒tokens=timings['predicted_per_second'],
                             提示词每秒tokens=timings['prompt_per_second'])
            for choice in record.get('choices', []):
                delta = choice.get('delta', {})
                answer = delta.get('content') or ''
                thought = delta.get('reasoning_content') or ''
                text += answer
                reasoning += thought
                for item in delta.get('tool_calls', []):
                    call = calls.setdefault(item['index'], {'id': '', 'name': '', 'arguments': ''})
                    call['id'] += item.get('id') or ''
                    function = item.get('function', {})
                    call['name'] += function.get('name') or ''
                    call['arguments'] += function.get('arguments') or ''
                if first is None and (answer or thought or calls):
                    first = time.monotonic()
                    ctx.metadata(首字秒=round(first - started, 3))
                if first_answer is None and answer:
                    first_answer = time.monotonic()
                    ctx.metadata(正文首字秒=round(first_answer - started, 3))
                ctx.response(text, reasoning)
        ctx.check_cancelled()
        if calls:
            ctx.tool_calls([{**call, 'arguments': json.loads(call['arguments'])}
                            for call in calls.values()])
        ctx.response(text, reasoning, final=True)
        return text
    finally:
        stream.close()
        if params['residency'] == 'release':
            release()
