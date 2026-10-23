"""A second kind of workflow, with image-processing parameters."""
from PIL import ImageEnhance, ImageOps

SPEC = {
    "name": "图片调色 · Pillow",
    "run_label": "应用调色",
    "description": "载入图片后逐步调整亮度、对比度、饱和度和清晰度。",
    "fields": [
        {"key": "image", "label": "输入图片", "type": "image", "section": "图片", "default": ""},
        {"key": "brightness", "label": "亮度", "type": "number", "section": "调色", "default": 1.05, "min": 0, "max": 3, "step": 0.05},
        {"key": "contrast", "label": "对比度", "type": "number", "section": "调色", "default": 1.1, "min": 0, "max": 3, "step": 0.05},
        {"key": "saturation", "label": "饱和度", "type": "number", "section": "调色", "default": 1, "min": 0, "max": 3, "step": 0.05},
        {"key": "sharpness", "label": "清晰度", "type": "number", "section": "调色", "default": 1.1, "min": 0, "max": 5, "step": 0.1},
        {"key": "max_edge", "label": "输出最长边", "type": "number", "section": "输出", "default": 2048, "min": 64, "step": 64},
    ],
}


def run(params, ctx):
    if not params["image"]:
        raise ValueError("请先选择输入图片。")
    image = ImageOps.exif_transpose(ctx.image(params["image"])).convert("RGB")
    image.thumbnail((int(params["max_edge"]), int(params["max_edge"])))
    adjustments = [("brightness", ImageEnhance.Brightness), ("contrast", ImageEnhance.Contrast),
                   ("saturation", ImageEnhance.Color), ("sharpness", ImageEnhance.Sharpness)]
    for step, (key, enhancer) in enumerate(adjustments, 1):
        image = enhancer(image).enhance(float(params[key]))
        ctx.progress(step, len(adjustments), image, "处理 · " + key)
    ctx.metadata(引擎="Pillow", 尺寸=f"{image.width}×{image.height}")
    return image
