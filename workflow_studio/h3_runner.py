"""MiniMax H3 image, reference and chained AV generation in the notebook process."""
from __future__ import annotations

import base64
import io
import json
import secrets
import time

from moss_runner import MODELS, model_files, prepare_core, preferred
from content_store import enabled, read_bytes, write_bytes

_components = {}
_lora_models = {}
_conditioning = {}
FPS = 24


def h3_files():
    files = model_files()
    return {folder: sorted({name for name in names if folder == "loras" or "h3" in name.lower() or "minimax" in name.lower()})
            for folder, names in files.items()}


def ensure_weights(params, ctx):
    selected = [("diffusion_models", params["model"]), ("text_encoders", params["text_encoder"]),
                ("vae", params["vae"]), ("vae", params["audio_vae"])]
    selected.extend(("loras", item["name"]) for item in params.get("loras", []) if item["strength"])
    missing = [str(MODELS / folder / name) for folder, name in selected
               if not (MODELS / folder / name).is_file()]
    if missing:
        raise FileNotFoundError("缺少本地模型文件：\n" + "\n".join(missing))


def load_models(params, ctx):
    ensure_weights(params, ctx)
    prepare_core(ctx, spark=params.get('attention', 'auto') in {'auto', 'spark'})
    import comfy.sd
    import comfy.utils

    parts = []
    for name, folder in (("model", "diffusion_models"), ("text_encoder", "text_encoders"),
                         ("vae", "vae"), ("audio_vae", "vae")):
        path = MODELS / folder / params[name]
        key = str(path), path.stat().st_mtime_ns
        if key not in _components:
            ctx.status("加载 H3 · " + path.name)
            started = time.monotonic()
            if name == "model":
                value = comfy.sd.load_diffusion_model(str(path))
                import comfy.model_management
                comfy.model_management.load_models_gpu([value])
            elif name == "text_encoder":
                value = comfy.sd.load_clip([str(path)], clip_type=comfy.sd.CLIPType.MINIMAX,
                                           embedding_directory=[str(MODELS / "embeddings")])
            else:
                weights, metadata = comfy.utils.load_torch_file(str(path), return_metadata=True)
                value = comfy.sd.VAE(sd=weights, metadata=metadata)
            _components[key] = value
            ctx.metadata(**{name + "加载秒": round(time.monotonic() - started, 3)})
        parts.append(_components[key])
    return parts


def apply_loras(model, clip, loras, ctx):
    import comfy.sd
    import comfy.utils

    enabled = [(MODELS / "loras" / item["name"], float(item["strength"]))
               for item in loras if float(item["strength"]) != 0]
    key = (id(model), id(clip), tuple((str(path), path.stat().st_mtime_ns, strength)
                                    for path, strength in enabled))
    if key not in _lora_models:
        for path, strength in enabled:
            ctx.status("加载 LoRA · " + path.name)
            weights = comfy.utils.load_torch_file(str(path), safe_load=True)
            model, clip = comfy.sd.load_lora_for_models(model, clip, weights, strength, strength)
        _lora_models[key] = model, clip
    if enabled:
        ctx.metadata(LoRA=" · ".join(f"{path.name}: {strength:g}" for path, strength in enabled))
    return _lora_models[key]


def apply_attention(model, params, ctx):
    import torch
    import comfy_kitchen
    from comfy.ldm.modules import attention
    from h3_spark import apply as apply_spark, supported as spark_supported

    mode = params.get('attention', 'auto')
    if mode == 'spark' or (mode == 'auto' and spark_supported()):
        return apply_spark(model, params, ctx)
    if mode == "auto":
        if comfy_kitchen.sol_attn_is_available(model.load_device):
            mode = "sol"
        elif comfy_kitchen.int8_attention_is_available(model.load_device):
            mode = "int8"
        else:
            mode = "pytorch"
    patched = model.clone()
    dense_method = "comfy_kitchen_int8" if mode in {"sol", "int8"} else "pytorch"
    config = torch.tensor(list(json.dumps({"attention": dense_method}).encode()), dtype=torch.uint8)
    for name, module in model.model.diffusion_model.named_modules():
        if isinstance(module, attention.ComfyAttention):
            if mode == "pytorch":
                selected = attention.ComfyAttention()
                selected.function = attention.attention_pytorch
                selected.method = "pytorch"
            else:
                selected = module.with_config(config)
            patched.add_object_patch("diffusion_model." + name, selected)
    if mode == "sol":
        from comfy_extras.nodes_sparse_attention import apply_block_sparse_attention

        patched = apply_block_sparse_attention(
            patched, tau=1.0, topk_ratio=0.0, vsa=False,
            start_percent=0.2, end_percent=1.0, min_tokens=12288,
            dense_blocks=set(), sink_conditioning="exact_kv_and_rows",
            extra_tokens=256, verbose=False,
        )
    ctx.metadata(Attention={"sol": "Sol 稀疏（参考与音频精确）", "int8": "INT8", "pytorch": "PyTorch"}[mode])
    return patched


def _media_source(item):
    value = item.get("data") or item.get("path") if isinstance(item, dict) else item
    if str(value).startswith("data:"):
        return io.BytesIO(base64.b64decode(value.split(",", 1)[1]))
    return io.BytesIO(read_bytes(value)) if enabled() else str(value)


def read_image(item):
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    with Image.open(_media_source(item)) as image:
        pixels = np.array(ImageOps.exif_transpose(image).convert("RGB"), copy=True)
    return torch.from_numpy(pixels).float().unsqueeze(0) / 255


def read_audio(item):
    import av
    import numpy as np
    import torch

    with av.open(_media_source(item)) as container:
        if not container.streams.audio:
            return None
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=32000)
        chunks = [frame.to_ndarray() for source in container.decode(audio=0)
                  for frame in resampler.resample(source)]
        chunks.extend(frame.to_ndarray() for frame in resampler.resample(None))
    return {"waveform": torch.from_numpy(np.concatenate(chunks, axis=1)).unsqueeze(0),
            "sample_rate": 32000}


def read_video(item, width, height, *, seconds=15):
    import av
    import numpy as np
    import torch

    frames = []
    with av.open(_media_source(item)) as container:
        stream = container.streams.video[0]
        source_fps = float(stream.average_rate or FPS)
        next_time = 0
        for index, frame in enumerate(container.decode(video=0)):
            timestamp = float(frame.time) if frame.time is not None else index / source_fps
            if timestamp + 1e-6 < next_time:
                continue
            array = frame.reformat(width=width, height=height, format="rgb24").to_ndarray()
            frames.append(torch.from_numpy(np.array(array, copy=True)))
            next_time = len(frames) / FPS
            if next_time >= seconds:
                break
    return torch.stack(frames).float() / 255


def _pil(frame):
    import torch
    from PIL import Image

    return Image.fromarray((frame[..., :3].clamp(0, 1) * 255).to(torch.uint8).cpu().numpy())


def _references(items, width, height):
    images, videos, video_audios, audios = {}, {}, {}, {}
    for item in items:
        kind = item["kind"]
        if kind == "image":
            images[f"ref_image_{len(images)+1}"] = read_image(item)
        elif kind == "video":
            index = len(videos) + 1
            videos[f"ref_video_{index}"] = read_video(item, width, height)
            audio = read_audio(item) if item.get("include_audio") else None
            if audio is not None:
                video_audios[f"ref_video_audio_{index}"] = audio
        elif kind == "audio":
            audios[f"ref_audio_{len(audios)+1}"] = read_audio(item)
    if len(images) > 9 or len(videos) > 3 or len(audios) > 3 or len(items) > 12:
        raise ValueError("H3 参考素材上限：9 张图片、3 段视频、3 段音频，合计 12 项")
    return dict(ref_images=images, ref_videos=videos, ref_video_audios=video_audios, ref_audios=audios)


def plan_segments(params):
    """Plan the delivered timeline separately from H3's 17k+5 sampling grid."""
    if params.get('output_type') == 'video' and params.get('timeline', {}).get('clips'):
        from h3_timeline import plan_timeline
        return plan_timeline(params)
    image = params.get("output_type", "image") == "image"
    total = 1 if image else max(1, round(float(params["duration"]) * FPS))
    technique = params.get("long_video", "motion")
    prompts = [part.strip() for part in params.get("shot_prompts", "").split("\n\n") if part.strip()]
    chunk = max(1, round(float(params.get("segment_seconds", 5)) * FPS))
    if technique == "single":
        chunk = 362
    carry = int(params.get("context_frames", 22)) if technique in ("motion", "overlap", "shots") else 1
    boundaries = [round(index * total / len(prompts)) for index in range(len(prompts)+1)] if technique == "shots" and prompts else [0, total]
    segments, start = [], 0
    while start < total:
        shot_index = next(index for index, end in enumerate(boundaries[1:]) if start < end)
        shot_start, shot_end = boundaries[shot_index:shot_index+2]
        continuation = "motion" if technique in ("motion", "overlap", "shots") else "tail"
        overlap = min(carry, start) if segments else 0
        if technique == "shots" and start == shot_start:
            overlap = 0
        sample_frames = max(5, min(shot_end - start + overlap, chunk + overlap, 362))
        sample_frames += (5 - sample_frames) % 17
        if sample_frames > 362:
            sample_frames -= 17
        delivered = min(shot_end - start, sample_frames - overlap)
        prompt = params["prompt"]
        if technique == "shots" and prompts:
            prompt = "\n".join(part for part in (prompt, prompts[shot_index]) if part)
        segments.append({"start": start, "frames": delivered, "sample_frames": sample_frames,
                         "carry": overlap, "prompt": prompt, "continuation": continuation})
        start += delivered
    return segments


def _condition(clip, vae, audio_vae, params, segment, refs, first, last):
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3ImageToVideo, MiniMaxH3ReferenceToVideo

    common = dict(clip=clip, prompt=segment["prompt"], width=int(params["width"]),
                  height=int(params["height"]), length=segment["sample_frames"])
    if params.get("references"):
        result = MiniMaxH3ReferenceToVideo.execute(**common, vae=vae, audio_vae=audio_vae,
                                                 ref_image_size=params.get("ref_image_size", "match"), **refs)
        positive, latent = result[0], result[1]
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide
        end_frame = segment["carry"] + segment["frames"] - 1
        for index, frame in ((0, first), (end_frame, last)):
            if frame is not None:
                positive = MiniMaxH3AddGuide.execute(positive, latent, index, vae=vae, image=frame)[0]
        return positive, latent
    result = MiniMaxH3ImageToVideo.execute(**common, vae=vae, first_frame=first, last_frame=last)
    positive = result[0]
    if last is not None:
        import node_helpers
        keyframes = [dict(frame) for frame in positive[0][1]["minimax_keyframes"]]
        keyframes[-1]["resolved_frame_index"] = segment["carry"] + segment["frames"] - 1
        positive = node_helpers.conditioning_set_values(positive, {"minimax_keyframes": keyframes})
    return positive, result[1]


def _guides(positive, latent, guides, segment, vae, audio_vae, width, height):
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide

    for guide in guides:
        index = round(float(guide.get("time", 0)) * FPS) - segment["start"] + segment["carry"]
        if not segment["carry"] <= index < segment["carry"] + segment["frames"]:
            continue
        kind = guide["kind"]
        image = read_image(guide) if kind == "image" else None
        audio = read_audio(guide) if kind in ("audio", "video") else None
        if kind == "video":
            remaining = (segment["sample_frames"] - index) / FPS
            image = read_video(guide, width, height, seconds=remaining)
        positive = MiniMaxH3AddGuide.execute(positive, latent, index, vae=vae,
                                           audio_vae=audio_vae, image=image, audio=audio)[0]
    return positive


def _save_clip(frames, audio, path):
    from comfy_extras.nodes_video import CreateVideo
    from comfy_api.latest import Types

    video = CreateVideo.execute(frames, FPS, audio=audio)[0]
    output = io.BytesIO() if enabled() else str(path)
    video.save_to(output, format=Types.VideoContainer.MP4, codec=Types.VideoCodec.H264,
                  crf=18, preset="fast")
    if enabled():
        write_bytes(path, output.getvalue())


def _fit_audio(audio, frames):
    import torch.nn.functional as F

    length = round(frames / FPS * audio["sample_rate"])
    waveform = audio["waveform"][..., :length]
    return {**audio, "waveform": F.pad(waveform, (0, length - waveform.shape[-1]))}


def run_h3(params, ctx):
    import torch
    from h3_selflift import sample as sample_selflift, validate as validate_selflift
    if params.get('selflift_enabled'):
        validate_selflift(params)
    segments = plan_segments(params)
    used_loras = {item['name']:item for segment in segments
                  for item in segment.get('loras', params.get('loras', [])) if item['strength']}
    base_model, base_clip, vae, audio_vae = load_models({**params, 'loras':list(used_loras.values())}, ctx)
    import comfy.sample
    import comfy.model_management
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3SigmaShift
    from comfy_extras.nodes_audio import vae_decode_audio
    from vendor.h3_motion_context.nodes import MiniMaxH3MotionContext, MiniMaxH3MotionContextTrim
    from latent_preview import Latent2RGBPreviewer

    variants = {}
    latent_format = base_model.model.latent_format
    previewer = Latent2RGBPreviewer(latent_format.latent_rgb_factors, latent_format.latent_rgb_factors_bias)
    width, height = int(params["width"]), int(params["height"])
    seed = int(params.get("seed", -1))
    if seed == -1:
        seed = secrets.randbelow(2**32)
    steps = int(params["steps"])
    total_steps = steps * len(segments)
    ctx.metadata(Seed=seed, 模型=params["model"], 引擎="Comfy · H3 进程内", 分段数=len(segments),
                 长视频技术=params.get("long_video", "motion"))
    ctx.status("读取 H3 参考素材…")
    first = read_image(params["first_frame"]) if params.get("first_frame") else None
    last = read_image(params["last_frame"]) if params.get("last_frame") else None
    reference_cache = {}
    previous_latent = None
    previous_tail = None
    previous_frames = None
    previous_audio = None
    clips = []
    sample_seconds = 0
    decode_seconds = 0
    prefix = time.strftime("%Y%m%d-%H%M%S") + "-h3-" + secrets.token_hex(3)
    any_audio = any(segment.get('audio', params.get('audio', True)) for segment in segments)
    ctx.metadata(时间轴=[{'id':segment.get('id', str(index)), 'start':segment['start'],
        'frames':segment['frames'], 'sample_frames':segment['sample_frames'], 'carry':segment['carry'],
        'method':segment.get('method', params.get('long_video', 'motion')),
        'references':[item.get('id', item.get('name', '')) for item in segment.get('references', params.get('references', []))],
        'loras':[{key:item[key] for key in ('name', 'strength')} for item in segment.get('loras', params.get('loras', []))]}
        for index, segment in enumerate(segments)])
    with torch.inference_mode():
        for number, segment in enumerate(segments):
            ctx.check_cancelled()
            loras = segment.get('loras', params.get('loras', []))
            key = tuple((item['name'], float(item['strength'])) for item in loras)
            if key not in variants:
                model, clip = apply_loras(base_model, base_clip, loras, ctx)
                model = MiniMaxH3SigmaShift.execute(model, float(params.get('shift', 12)), float(params.get('audio_shift', 3)))[0]
                variants[key] = apply_attention(model, params, ctx), clip
            model, clip = variants[key]
            references = segment.get('references', params.get('references', []))
            reference_key = tuple(item.get('id') or item.get('path') or item.get('data') for item in references)
            if reference_key not in reference_cache:
                reference_cache[reference_key] = _references(references, width, height)
            refs = reference_cache[reference_key]
            segment_params = {**params, 'references':references}
            ctx.status(f"第 {number+1}/{len(segments)} 段 · 编码条件…")
            segment_first = first if number == 0 else (
                previous_tail if segment["continuation"] == "tail" else None)
            segment_last = last if number == len(segments)-1 else None
            positive, latent = _condition(clip, vae, audio_vae, segment_params, segment, refs,
                                          segment_first, segment_last)
            positive = _guides(positive, latent, params.get("guides", []), segment,
                               vae, audio_vae, width, height)
            trim = 0
            if number and segment['carry'] and segment['continuation'] == 'motion':
                positive, trim = MiniMaxH3MotionContext().apply(
                    positive, vae, latent, str(segment["carry"]),
                    audio_context_length=int(segment.get('audio_context_frames', params.get('audio_context_frames', 18))),
                    **({'context_latent':previous_latent} if previous_latent is not None else
                       {'context_frames':previous_frames, 'context_audio':previous_audio, 'audio_vae':audio_vae}))
            elif segment_first is not None and number:
                trim = 1
            negative_key = id(clip), params.get("negative_prompt", "")
            if negative_key not in _conditioning:
                _conditioning[negative_key] = clip.encode_from_tokens_scheduled(
                    clip.tokenize(negative_key[1]))
            noise = None
            low_steps = max(1, min(steps-1, int(steps*float(params.get('selflift_low_steps', .75))+.5)))

            def callback(step, x0, x, count):
                preview = None
                if time.monotonic() - ctx.last_preview >= 0.5 or step+1 == count:
                    video = x0.tensors[0] if x0.is_nested else x0
                    preview = previewer.decode_latent_to_preview(video[:, :, -1:])
                stage = ('低分辨率采样' if step < low_steps else '高分辨率采样') if params.get('selflift_enabled') else '采样'
                ctx.progress(number * steps + step + 1, total_steps,
                             preview=preview,
                             message=f"第 {number+1}/{len(segments)} 段 · {stage} {step+1}/{count}")

            started = time.monotonic()
            if params.get('selflift_enabled'):
                samples = sample_selflift(model,positive,_conditioning[negative_key],vae,latent,params,seed+number,callback,ctx)
            else:
                noise = comfy.sample.prepare_noise(latent['samples'],seed+number)
                samples = comfy.sample.sample(model, noise, steps, float(params["cfg"]),
                    params["sampler"], params["scheduler"], positive, _conditioning[negative_key],
                    latent["samples"], noise_mask=latent.get("noise_mask"), callback=callback,
                    disable_pbar=True, seed=seed + number)
            sample_seconds += time.monotonic() - started
            video_latent, audio_latent = samples.unbind()
            started = time.monotonic()
            ctx.status(f"第 {number+1}/{len(segments)} 段 · 解码…")
            frames = vae.decode(video_latent).reshape(-1, height, width, 3).cpu()
            next_segment = segments[number+1] if number+1 < len(segments) else None
            need_context_audio = next_segment is not None and next_segment['continuation'] == 'motion'
            output_audio = segment.get('audio', params.get('audio', True))
            audio = vae_decode_audio(audio_vae, {"samples": audio_latent}) if output_audio or need_context_audio else None
            decode_seconds += time.monotonic() - started
            if params.get("output_type", "image") == "image":
                ctx.metadata(采样秒=round(sample_seconds, 3), 解码秒=round(decode_seconds, 3))
                return [_pil(frames[0])]
            fade = segment.get('blend_frames', 6 if params.get('long_video') == 'overlap' and number else 0)
            if fade and trim:
                # The pinned head warms up motion; blend its final frame into the delivered head.
                fade = min(fade, segment['frames'])
                alpha = torch.linspace(0, 1, fade).view(-1, 1, 1, 1)
                frames[trim:trim+fade] = frames[trim-1:trim] * (1-alpha) + frames[trim:trim+fade] * alpha
            if trim:
                frames, audio = MiniMaxH3MotionContextTrim().trim(frames, trim, audio=audio, fps=FPS)
            frames = frames[:segment["frames"]]
            if audio is not None:
                audio = _fit_audio(audio, len(frames))
            previous_tail = frames[-1:].clone()
            previous_latent = None
            previous_frames = None
            previous_audio = None
            if next_segment is not None and next_segment['continuation'] == 'motion':
                if segment['sample_frames'] == trim + segment['frames']:
                    previous_latent = {'samples':samples.to(device='cpu')}
                else:
                    previous_frames = frames[-next_segment['carry']:].clone()
                    previous_audio = audio
            poster = _pil(frames[0])
            ctx.progress((number+1)*steps, total_steps, preview=poster,
                         message=f"第 {number+1}/{len(segments)} 段 · 保存…")
            path = ctx.output_dir / f"{prefix}-part{number+1}.mp4"
            if not output_audio:
                audio = {'waveform':torch.zeros((1, 2, round(len(frames)/FPS*32000))), 'sample_rate':32000} if any_audio else None
            _save_clip(frames, audio, path)
            clips.append(path)
            del frames, audio, noise, video_latent, audio_latent, positive, latent, samples
    ctx.status("合成 H3 视频…")
    output = ctx.output_dir / f"{prefix}.mp4"
    if len(clips) == 1:
        clips[0].replace(output)
    else:
        from comfy_api.latest import InputImpl, Types
        video = InputImpl.VideoFromList([InputImpl.VideoFromFile(str(path)) for path in clips])
        video.save_to(str(output), format=Types.VideoContainer.MP4, codec=Types.VideoCodec.H264,
                      crf=18, preset="fast")
        for path in clips:
            path.unlink()
    ctx.metadata(采样秒=round(sample_seconds, 3), 解码秒=round(decode_seconds, 3),
                 帧数=sum(part["frames"] for part in segments), FPS=FPS)
    return {"kind": "video", "path": output, "poster": poster, "width": width, "height": height,
            "frames": sum(part["frames"] for part in segments), "fps": FPS,
            "duration": sum(part["frames"] for part in segments) / FPS, "segments": len(segments)}
