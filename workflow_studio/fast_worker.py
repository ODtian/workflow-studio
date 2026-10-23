"""Serve the notebook's Transformers runtime over a local streaming connection."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

STARTED = time.monotonic()

import torch
from transformers import (
    AutoModelForImageTextToText, AutoProcessor, FineGrainedFP8Config,
    StoppingCriteria, TextIteratorStreamer,
)

IMPORT_SECONDS = time.monotonic() - STARTED
parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--port", type=int, default=8787)
args = parser.parse_args()
torch.set_num_threads(4)
load_started = time.monotonic()
processor = AutoProcessor.from_pretrained(args.model, local_files_only=True)
model = AutoModelForImageTextToText.from_pretrained(
    args.model, device_map="cuda:0", dtype=torch.bfloat16,
    quantization_config=FineGrainedFP8Config(dequantize=True),
    attn_implementation="sdpa", local_files_only=True,
).eval()
READY = {
    "导入运行库秒": round(IMPORT_SECONDS, 3),
    "模型加载秒": round(time.monotonic() - load_started, 3),
    "运行精度": "BF16 · 从 FP8 权重加载",
}


class StopGeneration(StoppingCriteria):
    def __init__(self, event):
        self.event = event

    def __call__(self, input_ids, scores, **kwargs):
        return self.event.is_set()


def messages_for_processor(messages):
    result = []
    for message in messages:
        content = message["content"]
        if isinstance(content, list):
            content = [
                {"type": "image", "url": item["image_url"]["url"]}
                if item["type"] == "image_url" else item
                for item in content
            ]
        result.append({**message, "content": content})
    return result


def response_parts(raw, thinking):
    raw = raw.removeprefix("<think>")
    if "</think>" in raw:
        reasoning, _, answer = raw.partition("</think>")
        return answer.lstrip(), reasoning.strip()
    return ("", raw) if thinking else (raw, "")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = json.dumps(READY, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def event(self, payload):
        self.wfile.write(("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode())
        self.wfile.flush()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        template = body.get("chat_template_kwargs", {})
        inputs = processor.apply_chat_template(
            messages_for_processor(body["messages"]), tokenize=True,
            add_generation_prompt=True, return_dict=True, return_tensors="pt", **template,
        ).to("cuda")
        streamer = TextIteratorStreamer(processor.tokenizer, skip_prompt=True, skip_special_tokens=True)
        cancel = threading.Event()
        generation = {
            **inputs, "max_new_tokens": body["max_tokens"],
            "do_sample": body["temperature"] > 0,
            "repetition_penalty": body["repetition_penalty"],
            "streamer": streamer, "stopping_criteria": [StopGeneration(cancel)],
        }
        if generation["do_sample"]:
            generation.update({key: body[key] for key in ("temperature", "top_p", "top_k", "min_p")})
        if body.get("stop"):
            generation.update(stop_strings=body["stop"], tokenizer=processor.tokenizer)
        if "seed" in body:
            torch.manual_seed(body["seed"])
        outcome = {}

        def generate():
            try:
                with torch.inference_mode():
                    outcome["tokens"] = model.generate(**generation).shape[-1] - inputs["input_ids"].shape[-1]
            except Exception as exc:
                outcome["error"] = str(exc)
                streamer.end()

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        worker = threading.Thread(target=generate, daemon=True)
        worker.start()
        raw = ""
        try:
            for text in streamer:
                raw += text
                answer, reasoning = response_parts(raw, template.get("enable_thinking", True))
                self.event({"studio_response": {"content": answer, "reasoning": reasoning}})
            worker.join()
            if "error" in outcome:
                self.event({"error": outcome["error"]})
            else:
                self.event({"usage": {"completion_tokens": outcome["tokens"]}})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            cancel.set()


ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
