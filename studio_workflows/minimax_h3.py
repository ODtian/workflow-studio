"""MiniMax H3: images, multimodal references and a segmented video timeline."""
from h3_runner import MODELS, h3_files, preferred, run_h3
from runtime_options import sampling_options
from size_presets import common_size_presets

_files = h3_files()
_samplers, _schedulers = sampling_options()
_video_vaes = [name for name in _files["vae"] if "video" in name.lower()]
_audio_vaes = [name for name in _files["vae"] if "audio" in name.lower()]
_sizes = common_size_presets(base=768, step=32)

SPEC = {
    "name": "MiniMax H3 · 图片 / 视频", "tab_name": "H3", "run_label": "生成",
    "output": "media", "model_root": str(MODELS), "size_presets": _sizes,
    "ready": all((_files["diffusion_models"], _files["text_encoders"], _video_vaes, _audio_vaes)),
    "fields": [
        {"key": "model", "label": "H3 模型", "type": "select", "area": "models",
         "options": _files["diffusion_models"], "default": preferred(_files["diffusion_models"], "hybrid")},
        {"key": "text_encoder", "label": "文本编码器", "type": "select", "area": "models",
         "options": _files["text_encoders"], "default": preferred(_files["text_encoders"], "32b")},
        {"key": "vae", "label": "视频 VAE", "type": "select", "area": "models",
         "options": _video_vaes, "default": preferred(_video_vaes, "convrot")},
        {"key": "audio_vae", "label": "音频 VAE", "type": "select", "area": "models",
         "options": _audio_vaes, "default": preferred(_audio_vaes, "fp32")},
        {"key": "output_type", "label": "输出", "type": "select", "section": "生成",
         "options": [{"label": "图片", "value": "image"}, {"label": "视频", "value": "video"}], "default": "image"},
        {"key": "prompt", "label": "提示词", "type": "textarea", "area": "prompts", "rows": 3, "default": "一个土豆"},
        {"key": "negative_prompt", "label": "负面提示词", "type": "textarea", "area": "prompts", "rows": 1, "default": ""},
        {"key": "timeline", "label": "时间轴", "type": "h3_timeline", "area": "timeline", "default": {}, "persist": True},
        {"key": "references", "label": "参考素材", "type": "media_list", "section": "参考", "persist": True,
         "default": [], "hint": "图片、视频与音频；提示词中可用 <Picture 1>、<Video 1>、<Audio 1> 指代。"},
        {"key": "first_frame", "label": "首帧", "type": "image", "section": "关键帧", "default": "", "persist": True},
        {"key": "last_frame", "label": "尾帧", "type": "image", "section": "关键帧", "default": "", "persist": True,
         "when": {"output_type": "video"}},
        {"key": "guides", "label": "时间轴关键帧", "type": "keyframe_list", "section": "关键帧",
         "default": [], "persist": True, "when": {"output_type": "video"},
         "hint": "按整段视频的时间放置图片、视频片段或音频。"},
        {"key": "loras", "label": "LoRA", "type": "lora_stack", "section": "LoRA",
         "options": _files["loras"], "default": []},
        {"key": "duration", "label": "总时长 / 秒", "type": "number", "section": "视频",
         "default": 5, "min": 0.25, "step": 1, "when": {"output_type": "video"}},
        {"key": "long_video", "label": "生成方式", "type": "select", "section": "视频", "default": "motion",
         "when": {"output_type": "video"}, "options": [
             {"label": "运动上下文续写", "value": "motion"},
             {"label": "末帧续写", "value": "tail_frame"},
             {"label": "上下文续写 + 淡化衔接", "value": "overlap"},
             {"label": "分镜串联", "value": "shots"},
             {"label": "最长单段（15 秒）", "value": "single"}]},
        {"key": "segment_seconds", "label": "每段时长 / 秒", "type": "number", "section": "视频",
         "default": 5, "min": 1, "max": 15, "step": 1,
         "when": {"output_type": "video", "long_video": ["motion", "tail_frame", "overlap", "shots"]}},
        {"key": "shot_prompts", "label": "分镜提示词", "type": "textarea", "section": "视频", "persist": False,
         "rows": 3, "default": "", "when": {"output_type": "video", "long_video": "shots"},
         "placeholder": "每个分镜一段，段落之间留一空行"},
        {"key": "audio", "label": "生成声音", "type": "boolean", "section": "视频",
         "default": True, "when": {"output_type": "video"}},
        {"key": "steps", "label": "采样步数", "type": "number", "section": "采样", "default": 20, "min": 1, "step": 1},
        {"key": "cfg", "label": "CFG", "type": "number", "section": "采样", "default": 1, "min": 0, "step": 0.1},
        {"key": "sampler", "label": "采样器", "type": "select", "section": "采样", "options": _samplers, "default": "euler"},
        {"key": "scheduler", "label": "调度器", "type": "select", "section": "采样", "options": _schedulers, "default": "simple"},
        {"key": "width", "label": "宽度", "type": "number", "section": "画面", "default": 768, "min": 32, "step": 32},
        {"key": "height", "label": "高度", "type": "number", "section": "画面", "default": 768, "min": 32, "step": 32},
        {"key": "seed", "label": "随机种子", "type": "number", "section": "画面", "default": -1, "min": -1, "step": 1},
        {"key": "shift", "label": "视频 Shift", "type": "number", "area": "advanced", "default": 12, "min": 0.01, "step": 0.1},
        {"key": "attention", "label": "注意力加速", "type": "select", "area": "advanced", "default": "auto",
         "options": [{"label": "自动", "value": "auto"}, {"label": "Sol 稀疏", "value": "sol"},
                     {"label": "INT8", "value": "int8"}, {"label": "PyTorch", "value": "pytorch"}],
         "hint": "Sol 保留参考与音频条件的精确注意力。"},
        {"key": "audio_shift", "label": "音频 Shift", "type": "number", "area": "advanced", "default": 3, "min": 0.01, "step": 0.1},
        {"key": "ref_image_size", "label": "参考图尺寸", "type": "select", "area": "advanced", "default": "match",
         "options": [{"label": "匹配输出尺寸", "value": "match"}, {"label": "原生参考尺寸", "value": "max"}]},
        {"key": "context_frames", "label": "运动上下文 / 帧", "type": "select", "area": "advanced", "default": "22",
         "options": ["5", "22", "39", "56"], "when": {"output_type": "video", "long_video": ["motion", "overlap"]}},
        {"key": "audio_context_frames", "label": "音频上下文 / 帧", "type": "number", "area": "advanced",
         "default": 18, "min": 0, "step": 3, "when": {"output_type": "video", "long_video": ["motion", "overlap"]}},
    ],
}


def run(params, ctx):
    return run_h3(params, ctx)
