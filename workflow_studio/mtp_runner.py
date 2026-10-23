"""Adapt the upstream llama-cpp-python MTP scheduler to Workflow Studio."""
import os
import re
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys


def prepare_mtp(ctx):
    packages = [name for name in ("openai", "pydantic", "jinja2", "safetensors")
                if importlib.util.find_spec(name) is None]
    if packages:
        ctx.status("安装 MTP 推理组件")
        installer = ["uv", "pip", "install", "--python", sys.executable] if shutil.which("uv") else [sys.executable, "-m", "pip", "install"]
        log_path = Path("/tmp/workflow-studio-mtp-install.log")
        with log_path.open("w") as log:
            result = subprocess.run([*installer, *packages], stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(log_path.read_text()[-3000:])
        importlib.invalidate_caches()


class MTPModel:
    _studio_mtp = True

    def __init__(self, path, projector, draft, params, ctx):
        prepare_mtp(ctx)
        from vendor import llama_batch_engine as engine

        self.engine = engine
        threads = max(1, (os.cpu_count() or 2) // 2)
        ctx.status("加载 GGUF 与 MTP · " + (draft.name if draft else "主模型内嵌"))
        self.model = engine.Model(
            model_path=str(path), n_ctx=int(params["n_ctx"]),
            n_gpu_layers=int(params["n_gpu_layers"]), n_batch=int(params["n_batch"]),
            n_seq_max=1, n_threads=threads, n_threads_batch=threads, flash_attn=True,
            draft_model="draft-mtp", draft_model_path=str(draft) if draft else None,
            draft_model_num_pred_tokens=2,
        )
        # The notebook owns the process-wide llama.cpp backend across model switches.
        self.model.backend_initialized = False
        try:
            if projector:
                ctx.status("加载图像投影器 · " + projector.name)
                self.model.mtmd_processor = engine.MTMDProcessor(
                    model_path=str(path), llama_model=self.model.llama_model,
                    chat_formatter=self.model.chat_formatter, tokenize=self.model.tokenize,
                    n_embd_inp=self.model.n_embd_inp, n_batch=self.model.n_batch,
                    n_ubatch=self.model.n_ubatch, n_threads_batch=self.model.n_threads_batch,
                    mmproj_path=str(projector), batch_max_tokens=self.model.n_batch,
                    embedding_cache=None, allowed_media_domains=None,
                    allowed_local_media_path=None, image_max_bytes=20 * 1024**2,
                    audio_max_bytes=100 * 1024**2, video_max_bytes=512 * 1024**2,
                    image_timeout_seconds=10.0,
                )
            self.scheduler = engine.CompletionScheduler(self.model)
            self.service = engine.CompletionService(self.scheduler)
        except Exception:
            self.model.close()
            raise
        self._studio_vision_handler = self.model.mtmd_processor
        self.template = self.model.chat_formatter
        self.channels = None
        self.chat_format = params["chat_format"]

    def configure_chat(self, options, channels):
        self.channels = channels
        if self.template:
            self.template.template_kwargs = options
            self.model.chat_formatter = self.template
            if self.model.mtmd_processor:
                self.model.mtmd_processor.chat_formatter = self.template
            return "enable_thinking" in self.template._template_text
        return False

    def tokenize(self, text, add_bos=True):
        return self.model.tokenize(text.decode() if isinstance(text, bytes) else text, add_bos=add_bos)

    def _payload(self, prompt, sampling):
        return self.engine.CreateCompletionRequest(
            prompt=prompt, max_tokens=sampling["max_tokens"],
            temperature=sampling["temperature"], top_p=sampling["top_p"],
            top_k=sampling["top_k"], min_p=sampling["min_p"],
            repeat_penalty=sampling["repeat_penalty"],
            seed=sampling["seed"] if sampling["seed"] >= 0 else None,
            stop=sampling["stop"], stream=True,
        )

    def _stream(self, stream, cancel, chat=False):
        try:
            for chunk in stream:
                if chat:
                    chunk = {**chunk, "choices": [
                        {**choice, "delta": {"content": choice.get("text", "")}}
                        for choice in chunk["choices"]]}
                yield chunk
        finally:
            cancel()
            stream.close()
            # Wait for cancellation to release scheduler state before the next turn.
            self.service.call_on_scheduler(lambda: None)

    def create_completion(self, prompt, **sampling):
        stream, cancel = self.service.submit(self._payload(prompt, sampling))
        return self._stream(stream, cancel)

    def create_chat_completion(self, messages, **sampling):
        if self.chat_format and not self.model.mtmd_processor:
            from llama_cpp.llama_chat_format import get_chat_format
            formatted = get_chat_format(self.chat_format)(messages=messages)
            prompt = formatted.prompt
            generation_prompt = prompt
            plan = self.engine.PromptPlan.from_tokens(prompt, self.model.tokenize(prompt, add_bos=False, special=True))
            stops = [formatted.stop] if isinstance(formatted.stop, str) else formatted.stop or []
        else:
            messages = [self.engine.ChatCompletionRequestMessage(**message) for message in messages]
            prompt, generation_prompt, plan, stops = self.model.build_chat_prompt(messages)
        match = re.search(r"(<think>|<analysis>|<\|channel>(?:thought|analysis))\s*$", generation_prompt)
        self.channels.prefix = match[0] if match else ""
        sampling = {**sampling, "stop": list(dict.fromkeys([*sampling["stop"], *stops]))}
        payload = self._payload(prompt, sampling)
        request = self.service.request_from_prepared(payload=payload, prompt_text=prompt, prompt_plan=plan)
        stream, cancel = self.service.submit_request(request)
        return self._stream(stream, cancel, chat=True)

    def close(self):
        self.service.close()
