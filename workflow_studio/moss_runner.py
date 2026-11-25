"""MOSS workflows using Comfy's native file loaders and sampler in the notebook."""
from __future__ import annotations

import importlib.util
from importlib.metadata import version
import os
from pathlib import Path
from studio_paths import model_directory
import secrets
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).parent
CORE_VERSION = '0.42.0'
MODELS = model_directory()
CORE = Path(os.environ.get("WORKFLOW_COMFY_ROOT", ROOT / f"runtime/comfy-core-{CORE_VERSION}"))
_loaded = None
_loaded_key = None
_dit_sources = {}
_adapted = None
_adapted_key = None
_compiled = None
_compiled_key = None
_core_ready = False
_conditioning = {}


def model_files():
    files = {}
    for folder in ("diffusion_models", "text_encoders", "vae", "loras", "embeddings", "vae_approx", "latent_upscale_models"):
        directory = MODELS / folder
        directory.mkdir(parents=True, exist_ok=True)
        files[folder] = sorted(p.relative_to(directory).as_posix()
                               for p in directory.rglob("*.safetensors") if p.is_file())
    return files


def prepare_core(ctx, *, spark=False):
    from packaging.requirements import Requirement
    global _core_ready
    if _core_ready:
        if spark:
            from h3_spark import prepare_backend
            prepare_backend(ctx)
        return
    if not (CORE / "comfy/sd.py").exists():
        ctx.status("准备模型加载模块…")
        CORE.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", f"v{CORE_VERSION}",
                        "https://github.com/Comfy-Org/ComfyUI.git", str(CORE)], check=True)
    dependencies = {
        "torchsde": "torchsde", "trampoline": "trampoline", "einops": "einops", "scipy": "scipy",
        "sentencepiece": "sentencepiece", "av": "av>=17", "simpleeval": "simpleeval>=1",
        "blake3": "blake3", "safetensors": "safetensors", "psutil": "psutil", "tqdm": "tqdm",
    }
    for line in (CORE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith(("comfy-kitchen", "comfy-aimdo")):
            requirement = Requirement(line)
            dependencies[requirement.name.replace("-", "_")] = str(requirement)
    missing = []
    for module, package in dependencies.items():
        requirement = Requirement(package)
        if importlib.util.find_spec(module) is None or version(requirement.name) not in requirement.specifier:
            missing.append(package)
    if missing:
        ctx.status("准备模型加载依赖…")
        installer = ["uv", "pip", "install", "--python", sys.executable] if shutil.which("uv") else [sys.executable, "-m", "pip", "install"]
        subprocess.run([*installer, "--no-deps", *missing], check=True)
    if spark:
        from h3_spark import prepare_backend
        prepare_backend(ctx)
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    import folder_paths
    for folder in ("diffusion_models", "text_encoders", "vae", "loras", "embeddings", "vae_approx", "latent_upscale_models"):
        folder_paths.add_model_folder_path(folder, str(MODELS / folder), is_default=True)
    _core_ready = True


def _diffusion_selection(params):
    base = MODELS / "diffusion_models" / params["model"]
    if not params.get("mix_enabled"):
        return (base,), 0.0
    try:
        weight = float(params.get("mix_weight", 0.5))
    except (TypeError, ValueError):
        raise ValueError("第二模型权重应在 0 到 1 之间") from None
    if not 0.0 <= weight <= 1.0:
        raise ValueError("第二模型权重应在 0 到 1 之间")
    if weight == 0.0:
        return (base,), weight
    selection = params.get("mix_model")
    if not selection:
        raise ValueError("请在模型配置中选择第二个扩散模型")
    secondary = MODELS / "diffusion_models" / selection
    if weight == 1.0:
        return (secondary,), weight
    if base.resolve() == secondary.resolve():
        raise ValueError("请选择两个不同的扩散模型")
    return (base, secondary), weight


def _merge_diffusion_models(base, secondary, weight):
    if type(base.model) is not type(secondary.model):
        raise ValueError("两个扩散模型的架构不匹配")
    source = secondary.clone()
    state_dict = source.model_state_dict
    tensors = {name for name, _ in source.model.named_parameters(remove_duplicate=False)}
    tensors.update(name for name, _ in source.model.named_buffers(remove_duplicate=False))

    def tensor_state_dict(filter_prefix=None):
        # Quantized state dicts can include serialized keys with no live tensor attribute.
        return {name: value for name, value in state_dict(filter_prefix).items() if name in tensors}

    source.model_state_dict = tensor_state_dict
    mixed = base.clone()
    applied = mixed.add_patches(source.get_key_patches("diffusion_model."), weight, 1.0 - weight)
    if not applied:
        raise ValueError("没有可融合的扩散模型张量")
    return mixed


def load_models(params, ctx):
    global _loaded, _loaded_key, _adapted, _adapted_key, _compiled, _compiled_key
    dit_paths, mix_weight = _diffusion_selection(params)
    te_path = MODELS / "text_encoders" / params["text_encoder"]
    vae_path = MODELS / "vae" / params["vae"]
    selected = [*dit_paths, te_path, vae_path,
                *(MODELS / "loras" / item["name"] for item in params.get("loras", []) if item["strength"])]
    missing = [str(path) for path in selected if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少本地模型文件：\n" + "\n".join(missing))
    started = time.monotonic()
    prepare_core(ctx)
    import comfy.sd
    import comfy.utils
    import comfy.model_management
    ctx.metadata(运行库准备秒=round(time.monotonic() - started, 3))

    dit_keys = tuple((path, path.stat().st_mtime_ns) for path in dit_paths)
    dit_key = (dit_keys, mix_weight if len(dit_keys) == 2 else 0.0)
    key = (dit_key, (te_path, te_path.stat().st_mtime_ns), (vae_path, vae_path.stat().st_mtime_ns))
    if _loaded_key != key:
        parts = list(_loaded or (None, None, None))
        cached_keys = list(_loaded_key or (None, None, None))
        _adapted, _adapted_key = None, None
        _compiled, _compiled_key = None, None
        _conditioning.clear()
        for index, label in enumerate(("DiT", "TE", "VAE")):
            if cached_keys[index] == key[index] and parts[index] is not None:
                continue
            parts[index] = None
            cached_keys[index] = None
            _loaded = tuple(parts)
            _loaded_key = tuple(cached_keys)
            comfy.model_management.cleanup_models()
            started = time.monotonic()
            if index == 0:
                for cached in tuple(_dit_sources):
                    if cached not in dit_keys:
                        del _dit_sources[cached]
                for source_key in dit_keys:
                    if source_key not in _dit_sources:
                        path, _ = source_key
                        ctx.status("加载 DiT · " + path.name)
                        dit = comfy.sd.load_diffusion_model(str(path))
                        if dit is None:
                            raise ValueError(f"无法识别扩散模型：{path.name}")
                        _dit_sources[source_key] = dit
                parts[index] = _dit_sources[dit_keys[0]]
                if len(dit_keys) == 2:
                    ctx.status("正在融合两个扩散模型…")
                    parts[index] = _merge_diffusion_models(parts[index], _dit_sources[dit_keys[1]], mix_weight)
            elif index == 1:
                ctx.status("加载 TE · " + te_path.name)
                parts[index] = comfy.sd.load_clip([str(te_path)], clip_type=comfy.sd.CLIPType.MOSS_IMAGE,
                                                 embedding_directory=[str(MODELS / "embeddings")])
            else:
                ctx.status("加载 VAE · " + vae_path.name)
                state, metadata = comfy.utils.load_torch_file(str(vae_path), return_metadata=True)
                parts[index] = comfy.sd.VAE(sd=state, metadata=metadata)
            cached_keys[index] = key[index]
            _loaded = tuple(parts)
            _loaded_key = tuple(cached_keys)
            ctx.metadata(**{label + "加载秒": round(time.monotonic() - started, 3)})
    if params.get("mix_enabled"):
        ctx.metadata(第二扩散模型=params.get("mix_model", ""), 第二模型权重=mix_weight)
    return _loaded


def apply_loras(model, clip, loras, ctx):
    global _adapted, _adapted_key
    import comfy.sd
    import comfy.utils

    enabled = [(MODELS / "loras" / item["name"], float(item["strength"]))
               for item in loras if float(item["strength"]) != 0]
    key = (_loaded_key, tuple((str(path), path.stat().st_mtime_ns, strength) for path, strength in enabled))
    if key != _adapted_key:
        _conditioning.clear()
        for path, strength in enabled:
            ctx.status("加载 LoRA · " + path.name)
            weights = comfy.utils.load_torch_file(str(path), safe_load=True)
            model, clip = comfy.sd.load_lora_for_models(model, clip, weights, strength, strength)
        _adapted, _adapted_key = (model, clip), key
    if enabled:
        ctx.metadata(LoRA=" · ".join(f"{path.name}: {strength:g}" for path, strength in enabled))
    return _adapted


def encode_prompt(clip, text):
    key = (id(clip), text)
    if key not in _conditioning:
        if len(_conditioning) == 4:
            _conditioning.pop(next(iter(_conditioning)))
        _conditioning[key] = clip.encode_from_tokens_scheduled(clip.tokenize(text))
    return _conditioning[key]


def compile_dit(model, ctx):
    global _compiled, _compiled_key
    import torch
    import comfy.ops
    from comfy_api.torch_helpers import set_torch_compile_wrapper
    from comfy.ldm.moss_image import model as moss_model

    if _compiled_key != _adapted_key:
        cache = Path(os.environ.get("WORKFLOW_WORKSPACE", ROOT.parent)) / ".cache"
        os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", str(cache / "torchinductor"))
        os.environ.setdefault("TRITON_CACHE_DIR", str(cache / "triton"))
        os.environ.setdefault("TORCHINDUCTOR_COMPILE_THREADS", "2")
        ctx.status("准备 DiT 编译…")
        # These fused INT8 kernels pass real CUDA tensors through DLPack.
        moss_model.attention = torch.compiler.disable(moss_model.attention)
        comfy.ops.linear_input_act = torch.compiler.disable(comfy.ops.linear_input_act)
        compiled = model.clone(disable_dynamic=True)
        set_torch_compile_wrapper(compiled, backend="inductor", dynamic=False)
        _compiled, _compiled_key = compiled, _adapted_key
    ctx.metadata(DiT编译="Inductor")
    return _compiled


def prepare_moss(params, ctx):
    import torch
    started = time.monotonic()
    model, clip, vae = load_models(params, ctx)
    model, clip = apply_loras(model, clip, params.get("loras", []), ctx)
    ctx.status("准备负面提示词编码…")
    with torch.no_grad():
        encode_prompt(clip, params.get("negative_prompt", ""))
    ctx.metadata(预载秒=round(time.monotonic() - started, 3))


def run_moss(params, ctx):
    import torch
    from PIL import Image
    model, clip, vae = load_models(params, ctx)
    model, clip = apply_loras(model, clip, params.get("loras", []), ctx)
    if params.get("compile_dit", False):
        model = compile_dit(model, ctx)
    import comfy.sample
    import comfy.samplers
    import comfy.model_management
    import latent_preview
    from comfy.cli_args import args, LatentPreviewMethod
    from comfy_extras.nodes_slg import SkipLayerGuidanceDiTSimple

    seed = int(params["seed"])
    if seed == -1:
        seed = secrets.randbelow(2**32)
    ctx.metadata(Seed=seed, 模型=params["model"], TE=params["text_encoder"], 引擎="Comfy 模型加载模块")
    ctx.status("编码提示词…")
    started = time.monotonic()
    with torch.no_grad():
        positive = encode_prompt(clip, params["prompt"])
        negative = encode_prompt(clip, params["negative_prompt"])
    ctx.metadata(提示词编码秒=round(time.monotonic() - started, 3))
    ctx.check_cancelled()

    model = model.clone()
    sampling = type(model.get_model_object("model_sampling"))(model.model.model_config)
    sampling.set_parameters(shift=float(params["shift"]), multiplier=1.0)
    model.add_object_patch("model_sampling", sampling)
    if params["slg_enabled"]:
        model = SkipLayerGuidanceDiTSimple.execute(
            model, start_percent=float(params["slg_start"]), end_percent=float(params["slg_end"]),
            double_layers=params["slg_double_layers"], single_layers=params["slg_single_layers"])[0]
    spectrum = None
    if params.get("spectrum_enabled", True):
        from comfy.patcher_extension import WrappersMP
        from vendor.spectrum_moss.nodes import SpectrumConfig, apply_spectrum_moss, WRAPPER_KEY

        model = apply_spectrum_moss(model, SpectrumConfig(
            mode="adaptive", flex_window=0.5,
            warmup_steps=int(params.get("spectrum_warmup_steps", 8)),
            error_tolerance=float(params.get("spectrum_error_tolerance", 1.0)),
            cache_device=params.get("spectrum_cache_device", "main_device"),
        ))
        spectrum = model.model_options["transformer_options"]["wrappers"][WrappersMP.DIFFUSION_MODEL][WRAPPER_KEY][0].root_state
        ctx.metadata(Spectrum="Adaptive")
    args.preview_method = LatentPreviewMethod.Latent2RGB
    previewer = latent_preview.get_previewer(model.load_device, model.model.latent_format)
    steps = int(params["steps"])
    every = int(params["preview_every"])

    def callback(step, x0, x, total):
        preview = previewer.decode_latent_to_preview(x0) if step == 0 or (step + 1) % every == 0 or step + 1 == total else None
        ctx.progress(step + 1, total, preview, f"采样 · {step + 1} / {total}")

    shape = (int(params["batch_size"]), 128, int(params["height"]) // 16, int(params["width"]) // 16)
    latent = torch.zeros(shape, device=comfy.model_management.intermediate_device())
    noise = comfy.sample.prepare_noise(latent, seed)
    scheduler = params["scheduler"]
    sigmas = None
    if scheduler == "beta57":
        # RES4LYF beta57 uses Comfy's beta schedule with alpha=.5, beta=.7.
        discard = params["sampler"] in comfy.samplers.KSampler.DISCARD_PENULTIMATE_SIGMA_SAMPLERS
        sigmas = comfy.samplers.beta_scheduler(sampling, steps + int(discard), alpha=0.5, beta=0.7)
        if discard:
            sigmas = torch.cat([sigmas[:-2], sigmas[-1:]])
        sigmas = sigmas.to(model.load_device)
        scheduler = "beta"
    slg = (f"uncond skip · double [{params['slg_double_layers']}] · single [{params['slg_single_layers']}] · "
           f"{float(params['slg_start']):g}–{float(params['slg_end']):g}") if params["slg_enabled"] else "关闭"
    ctx.metadata(采样器=params["sampler"], 调度器=params["scheduler"], Shift=float(params["shift"]),
                 SLG=slg, CFG=float(params["cfg"]), 尺寸=f"{params['width']} × {params['height']}")
    ctx.status("开始采样…")
    with torch.no_grad():
        started = time.monotonic()
        samples = comfy.sample.sample(model, noise, steps, float(params["cfg"]), params["sampler"],
                                      scheduler, positive, negative, latent,
                                      sigmas=sigmas, callback=callback, disable_pbar=True, seed=seed)
        ctx.metadata(采样秒=round(time.monotonic() - started, 3))
        if spectrum is not None:
            ctx.metadata(Spectrum实际次数=sum(branch.actual_count for branch in spectrum.branches.values()),
                         Spectrum预测次数=sum(branch.forecast_count for branch in spectrum.branches.values()))
        ctx.status("解码图片…")
        started = time.monotonic()
        pixels = vae.decode(samples).detach().cpu().clamp(0, 1).mul(255).to(torch.uint8).numpy()
        ctx.metadata(解码秒=round(time.monotonic() - started, 3))
    return [Image.fromarray(image) for image in pixels]
