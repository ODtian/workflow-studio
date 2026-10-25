"""MOSS Base/SFT: select files from the existing Comfy model directories."""
from moss_runner import MODELS, model_files, preferred, prepare_moss, run_moss
from runtime_options import sampling_options
from size_presets import common_size_presets

_files = model_files()
_samplers, _schedulers = sampling_options()
_ready = all(_files[folder] for folder in ("diffusion_models", "text_encoders", "vae"))

SPEC = {
    "name": "MOSS-Image · Base / SFT",
    "run_label": "生成图片",
    "refresh_label": "刷新模型列表",
    "model_root": str(MODELS),
    "prepare_fields": ["model", "text_encoder", "vae", "loras"],
    "ready": _ready,
    "size_presets": common_size_presets(),
    "description": "选择目录中的模型文件，加载器自动识别模型和量化格式。" if _ready else
                   "模型目录已建立。将 DiT、TE、VAE 放入对应子目录，模型列表会自动更新。",
    "fields": [
        {"key": "model", "label": "扩散模型", "type": "select", "section": "模型文件", "area": "models",
         "options": _files["diffusion_models"], "default": preferred(_files["diffusion_models"], "moss", "sft")},
        {"key": "text_encoder", "label": "文本编码器", "type": "select", "section": "模型文件", "area": "models",
         "options": _files["text_encoders"], "default": preferred(_files["text_encoders"], "qwen3.5", "9b")},
        {"key": "vae", "label": "VAE", "type": "select", "section": "模型文件", "area": "models",
         "options": _files["vae"], "default": preferred(_files["vae"], "flux2")},
        {"key": "loras", "label": "LoRA", "type": "lora_stack", "section": "LoRA",
         "options": _files["loras"], "default": []},
        {"key": "prompt", "label": "提示词", "type": "textarea", "section": "创作", "area": "prompts", "rows": 4,
         "default": "A photograph of a white ceramic mug on a wooden table beside a small green potted plant, soft daylight, natural colors."},
        {"key": "negative_prompt", "label": "负面提示词", "type": "textarea", "section": "创作", "area": "prompts", "rows": 2, "default": ""},
        {"key": "steps", "label": "采样步数", "type": "number", "section": "采样", "default": 50, "min": 1, "step": 1},
        {"key": "cfg", "label": "CFG", "type": "number", "section": "采样", "default": 3.0, "min": 0, "step": 0.1},
        {"key": "sampler", "label": "采样器", "type": "select", "section": "采样", "default": "euler",
         "options": _samplers},
        {"key": "scheduler", "label": "调度器", "type": "select", "section": "采样", "default": "simple",
         "options": _schedulers},
        {"key": "slg_enabled", "label": "启用 SLG", "type": "boolean", "section": "SLG", "area": "advanced", "default": True},
        {"key": "slg_double_layers", "label": "Double layers", "type": "text", "section": "SLG", "area": "advanced", "default": "",
         "hint": "双流层编号，从 0 开始；多个层用逗号分隔。"},
        {"key": "slg_single_layers", "label": "Single layers", "type": "text", "section": "SLG", "area": "advanced", "default": "22",
         "hint": "单流层编号，从 0 开始；多个层用逗号分隔。"},
        {"key": "slg_start", "label": "SLG start", "type": "number", "section": "SLG", "area": "advanced", "default": 0.0,
         "min": 0, "max": 1, "step": 0.01},
        {"key": "slg_end", "label": "SLG end", "type": "number", "section": "SLG", "area": "advanced", "default": 1.0,
         "min": 0, "max": 1, "step": 0.01},
        {"key": "spectrum_enabled", "label": "Spectrum 加速", "type": "boolean", "area": "advanced", "default": True,
         "hint": "自适应预测中间特征以减少计算，画面细节可能变化。"},
        {"key": "compile_dit", "label": "编译 DiT", "type": "boolean", "area": "advanced", "default": False,
         "hint": "首次编译耗时较长，同一输入尺寸后续复用缓存。"},
        {"key": "shift", "label": "Shift", "type": "number", "section": "高级", "area": "advanced", "default": 5.0, "min": 0.1, "step": 0.1},
        {"key": "width", "label": "宽度", "type": "number", "section": "画面", "default": 1024, "min": 16, "step": 16},
        {"key": "height", "label": "高度", "type": "number", "section": "画面", "default": 1024, "min": 16, "step": 16},
        {"key": "seed", "label": "随机种子", "type": "number", "section": "画面", "default": -1, "min": -1, "step": 1},
        {"key": "batch_size", "label": "图片数量", "type": "number", "section": "画面", "default": 1, "min": 1, "step": 1},
        {"key": "preview_every", "label": "预览间隔 / 步", "type": "number", "section": "高级", "area": "advanced", "default": 1, "min": 1, "step": 1},
    ],
}


def run(params, ctx):
    return run_moss(params, ctx)


def prepare(params, ctx):
    return prepare_moss(params, ctx)
