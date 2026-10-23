"""Text and vision chat using the notebook runtime."""
from fast_runner import MODELS, model_files, prepare_fast, run_fast

_models = model_files()
SPEC = {
    "name": "LLM · 对话", "output": "text", "chat": True, "images": True,
    "run_label": "发送", "refresh_label": "刷新模型列表", "model_root": str(MODELS / "LLM"),
    "model_binding_fields": ["thinking", "reasoning_effort"],
    "prepare_fields": ["model"],
    "ready": bool(_models), "description": "使用 notebook 现有环境，快速启动文本与图片对话。",
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
        {"key": "stop", "label": "停止词（每行一个）", "type": "textarea", "area": "advanced",
         "default": "", "rows": 2},
    ],
}


def run(params, ctx):
    return run_fast(params, ctx)


def prepare(params, ctx):
    return prepare_fast(params, ctx)
