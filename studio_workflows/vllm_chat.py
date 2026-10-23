"""Streaming local text and image chat with vLLM and MTP."""
from vllm_runner import MODELS, model_files, prepare_vllm, run_vllm

_models = model_files()
SPEC = {
    "name": "vLLM · 对话", "output": "text", "chat": True, "images": True,
    "run_label": "发送", "refresh_label": "刷新模型列表", "model_root": str(MODELS / "LLM"),
    "model_binding_fields": ["thinking", "reasoning_effort", "speculative_tokens"],
    "prepare_fields": ["model", "n_ctx", "n_batch", "gpu_memory_utilization", "speculative_tokens"],
    "ready": bool(_models), "description": "FP8 GPU 推理，支持视觉输入、流式对话和 MTP 加速。",
    "fields": [
        {"key": "model", "label": "LLM 模型", "type": "select", "area": "models", "options": _models,
         "default": "Qwen3.8-27B-Uncensored-FP8"},
        {"key": "system_prompt", "label": "系统提示词", "type": "textarea", "area": "prompts", "persist": True,
         "rows": 2, "default": "You are a helpful assistant."},
        {"key": "thinking", "label": "Thinking · enable_thinking", "type": "select", "section": "生成",
         "default": "auto", "options": [{"label": "模型默认", "value": "auto"},
                    {"label": "开启", "value": "on"}, {"label": "关闭", "value": "off"}]},
        {"key": "reasoning_effort", "label": "推理强度 · reasoning_effort", "type": "text",
         "section": "生成", "default": "", "placeholder": "模型默认",
         "hint": "原值传入模型自带模板，随模型保存。"},
        {"key": "max_tokens", "label": "最大输出 tokens", "type": "number", "section": "生成",
         "default": 2048, "min": 1, "step": 64},
        {"key": "temperature", "label": "Temperature", "type": "number", "section": "生成",
         "default": 0.7, "min": 0, "step": 0.05},
        {"key": "top_p", "label": "Top P", "type": "number", "section": "采样",
         "default": 0.95, "min": 0, "max": 1, "step": 0.01},
        {"key": "top_k", "label": "Top K", "type": "number", "section": "采样",
         "default": 20, "min": 0, "step": 1},
        {"key": "min_p", "label": "Min P", "type": "number", "section": "采样",
         "default": 0.0, "min": 0, "max": 1, "step": 0.01},
        {"key": "repeat_penalty", "label": "重复惩罚", "type": "number", "section": "采样",
         "default": 1.0, "min": 0, "step": 0.05},
        {"key": "seed", "label": "随机种子", "type": "number", "section": "采样",
         "default": -1, "min": -1, "step": 1},
        {"key": "residency", "label": "模型驻留", "type": "select", "section": "加载", "default": "keep",
         "options": [{"label": "保留模型，加快下轮对话", "value": "keep"},
                     {"label": "生成后释放显存", "value": "release"}]},
        {"key": "speculative_tokens", "label": "MTP 预测步数", "type": "number", "section": "加载",
         "default": 2, "min": 0, "max": 4, "step": 1, "hint": "0 关闭；当前模型推荐 2。"},
        {"key": "n_ctx", "label": "上下文长度", "type": "number", "area": "advanced",
         "default": 32768, "min": 512, "step": 1024},
        {"key": "n_batch", "label": "输入批处理 tokens", "type": "number", "area": "advanced",
         "default": 2048, "min": 512, "step": 512},
        {"key": "gpu_memory_utilization", "label": "显存使用比例", "type": "number", "area": "advanced",
         "default": 0.6, "min": 0.4, "max": 0.95, "step": 0.05},
        {"key": "stop", "label": "停止词（每行一个）", "type": "textarea", "area": "advanced",
         "default": "", "rows": 2},
    ],
}


def run(params, ctx):
    return run_vllm(params, ctx)


def prepare(params, ctx):
    return prepare_vllm(params, ctx)
