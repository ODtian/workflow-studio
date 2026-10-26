"""Helpers used by the bundled diffusion workflows; the panel is engine-agnostic."""
from __future__ import annotations

import gc
import importlib.util
from pathlib import Path
import secrets
import subprocess
import sys

_cache_key = None
_pipeline = None


def fields(family):
    return [
        {"key": "model", "label": "本地模型目录 / checkpoint", "type": "text", "section": "模型",
         "default": "", "required": True, "hint": "填写本地 Diffusers 模型目录或该架构的 checkpoint 文件路径。"},
        {"key": "prompt", "label": "提示词", "type": "textarea", "section": "创作", "rows": 5,
         "default": "A small ceramic house in a moss garden, soft morning light, macro photography", "required": True},
        {"key": "negative_prompt", "label": "负面提示词", "type": "textarea", "section": "创作", "rows": 2, "default": ""},
        {"key": "steps", "label": "采样步数", "type": "number", "section": "采样参数", "default": 24, "min": 1, "max": 150, "step": 1},
        {"key": "cfg", "label": "CFG", "type": "number", "section": "采样参数", "default": 6, "min": 0, "max": 30, "step": 0.5},
        {"key": "sampler", "label": "采样器", "type": "select", "section": "采样参数", "default": "dpmpp_2m",
         "options": [{"value": "euler", "label": "Euler"}, {"value": "dpmpp_2m", "label": "DPM++ 2M"}, {"value": "dpmpp_2m_sde", "label": "DPM++ 2M SDE"}]},
        {"key": "scheduler", "label": "噪声调度", "type": "select", "section": "采样参数", "default": "karras", "options": ["normal", "karras"]},
        {"key": "width", "label": "宽度", "type": "number", "section": "画面", "default": 1024 if family == "sdxl" else 512, "min": 64, "step": 64},
        {"key": "height", "label": "高度", "type": "number", "section": "画面", "default": 1024 if family == "sdxl" else 512, "min": 64, "step": 64},
        {"key": "seed", "label": "随机种子", "type": "number", "section": "画面", "default": -1, "min": -1, "step": 1, "hint": "-1 表示每次随机。"},
        {"key": "batch_size", "label": "图片数量", "type": "number", "section": "画面", "default": 1, "min": 1, "max": 8, "step": 1},
        {"key": "preview_every", "label": "预览间隔 / 步", "type": "number", "section": "预览与图生图", "default": 4, "min": 1, "step": 1},
        {"key": "denoise", "label": "Denoise / 重绘幅度", "type": "number", "section": "预览与图生图", "default": 1, "min": 0.01, "max": 1, "step": 0.01,
         "hint": "初始图用于图生图，denoise 控制重绘幅度；文生图使用 1。"},
        {"key": "init_image", "label": "初始图（可选）", "type": "image", "section": "预览与图生图", "default": ""},
    ]


def run_diffusion(family, params, ctx):
    model = params["model"].strip()
    if not model or not Path(model).exists():
        raise FileNotFoundError("缺少本地模型文件或目录：" + model)
    if any(importlib.util.find_spec(name) is None for name in ("diffusers", "accelerate")):
        ctx.status("准备此工作流的 Diffusers 依赖…")
        subprocess.run(["uv", "pip", "install", "--no-deps", "--python", sys.executable,
                        "diffusers==0.41.0", "accelerate"], check=True)
    import torch
    from PIL import Image
    from diffusers import (
        AutoPipelineForImage2Image,
        DPMSolverMultistepScheduler,
        EulerDiscreteScheduler,
        StableDiffusionPipeline,
        StableDiffusionXLPipeline,
    )

    global _cache_key, _pipeline
    key = family, model
    ctx.check_cancelled()
    if key != _cache_key:
        ctx.status("加载模型 · " + model)
        _pipeline = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        cls = StableDiffusionXLPipeline if family == "sdxl" else StableDiffusionPipeline
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        loader = cls.from_single_file if Path(model).is_file() else cls.from_pretrained
        _pipeline = loader(model, torch_dtype=dtype, local_files_only=True)
        _pipeline.to("cuda" if torch.cuda.is_available() else "cpu")
        _pipeline.set_progress_bar_config(disable=True)
        _cache_key = key
    pipe = _pipeline
    params["seed"] = int(params["seed"])
    if params["seed"] < 0:
        params["seed"] = secrets.randbelow(2**32)
    ctx.metadata(Seed=params["seed"], 引擎="Diffusers")
    sampler = params["sampler"]
    scheduler_args = {"use_karras_sigmas": params["scheduler"] == "karras"}
    if sampler == "euler":
        pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, **scheduler_args)
    else:
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            pipe.scheduler.config, solver_order=2,
            algorithm_type="sde-dpmsolver++" if sampler == "dpmpp_2m_sde" else "dpmsolver++",
            **scheduler_args)
    call = dict(prompt=params["prompt"], negative_prompt=params["negative_prompt"],
                num_inference_steps=int(params["steps"]), guidance_scale=float(params["cfg"]),
                height=int(params["height"]), width=int(params["width"]),
                num_images_per_prompt=int(params["batch_size"]),
                generator=torch.Generator(device=pipe.device).manual_seed(params["seed"]))
    if params.get("init_image"):
        pipe = AutoPipelineForImage2Image.from_pipe(pipe)
        image = ctx.image(params["init_image"]).convert("RGB")
        call["image"] = image.resize((call["width"], call["height"]), Image.Resampling.LANCZOS)
        call["strength"] = float(params["denoise"])
    elif float(params["denoise"]) != 1:
        raise ValueError("请载入初始图以使用 Denoise 重绘参数；文生图请设置为 1。")
    interval = int(params["preview_every"])

    def on_step(pipeline, step, timestep, callback_kwargs):
        ctx.check_cancelled()
        total = pipeline.num_timesteps
        preview = None
        if (step + 1) % interval == 0 or step == 0:
            latent = callback_kwargs["latents"][:1].to(pipeline.vae.dtype)
            scale = min(1.0, 64 / max(latent.shape[-2:]))
            if scale < 1:
                latent = torch.nn.functional.interpolate(latent, scale_factor=scale, mode="bilinear", align_corners=False)
            decoded = pipeline.vae.decode(latent / pipeline.vae.config.scaling_factor, return_dict=False)[0]
            preview = pipeline.image_processor.postprocess(decoded, output_type="pil")[0]
        ctx.progress(step + 1, total, preview, f"采样 {step + 1} / {total}")
        return callback_kwargs

    ctx.status("模型就绪，开始采样…")
    with torch.inference_mode():
        images = pipe(**call, callback_on_step_end=on_step,
                      callback_on_step_end_tensor_inputs=["latents"]).images
    ctx.check_cancelled()
    return images
