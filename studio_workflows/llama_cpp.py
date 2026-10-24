"""In-process llama.cpp text and image chat with GGUF and MTP."""
from llama_runner import (MODELS, DEFAULT_MODEL, DEFAULT_MTP, DEFAULT_MMPROJ,
                          model_files, companion_files, prepare_llama, run_llama, reasoning_control)

_models = model_files()
SPEC = {
    "name": "llama.cpp · 对话", "output": "text", "chat": True, "images": True,
    "run_label": "发送", "refresh_label": "刷新模型列表", "model_root": str(MODELS / "LLM"),
    "model_binding_fields": ["thinking", "reasoning_effort", "mmproj", "mtp", "speculative_tokens"],
    "prepare_fields": ["model", "mmproj", "mtp", "n_ctx", "n_gpu_layers", "n_batch", "chat_format", "speculative_tokens"],
    "ready": bool(_models), "description": "进程内 GGUF 推理，支持图片输入、Thinking 和 MTP 加速。",
    "fields": [
        {"key": "model", "label": "GGUF 模型", "type": "select", "area": "models", "options": _models,
         "default": DEFAULT_MODEL},
        {"key": "system_prompt", "label": "系统提示词", "type": "textarea", "area": "prompts", "persist": True,
         "rows": 2, "default": "You are a helpful assistant."},
        {"key": "thinking", "label": "Thinking · enable_thinking", "type": "select", "section": "生成",
         "default": "off", "options": [{"label": "模型默认", "value": "auto"},
                    {"label": "开启", "value": "on"}, {"label": "关闭", "value": "off"}]},
        reasoning_control(),
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
        {"key": "mmproj", "label": "图像投影器 mmproj", "type": "select", "section": "加载",
         "default": DEFAULT_MMPROJ, "hint": "按 GGUF 元数据筛选图像投影器；手动选择后随主模型保存。",
         "options": [{"label": "关闭", "value": ""}] + companion_files("mmproj")},
        {"key": "mtp", "label": "MTP 草稿头", "type": "select", "section": "加载",
         "default": DEFAULT_MTP, "hint": "按 GGUF 元数据筛选含 MTP 权重的文件；主模型自带 MTP 时选择内嵌。",
         "options": [{"label": "关闭", "value": ""},
                     {"label": "使用主模型内嵌 MTP", "value": "embedded"}] + companion_files("mtp")},
        {"key": "speculative_tokens", "label": "MTP 预测步数", "type": "number", "section": "加载",
         "default": 2, "min": 0, "max": 4, "step": 1, "hint": "0 关闭；当前模型推荐 2。"},
        {"key": "n_ctx", "label": "上下文长度", "type": "number", "area": "advanced",
         "default": 32768, "min": 512, "step": 1024},
        {"key": "n_batch", "label": "输入批处理 tokens", "type": "number", "area": "advanced",
         "default": 2048, "min": 512, "step": 512},
        {"key": "n_gpu_layers", "label": "GPU 层数", "type": "number", "area": "advanced",
         "default": 999, "min": -1, "step": 1},
        {"key": "chat_format", "label": "对话模板覆盖", "type": "text", "area": "advanced",
         "default": "", "placeholder": "GGUF 内置模板"},
        {"key": "stop", "label": "停止词（每行一个）", "type": "textarea", "area": "advanced",
         "default": "", "rows": 2},
    ],
}


def run(params, ctx):
    return run_llama(params, ctx)


def prepare(params, ctx):
    return prepare_llama(params, ctx)
