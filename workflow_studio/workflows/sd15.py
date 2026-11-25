from diffusers_runner import fields, run_diffusion
from size_presets import common_size_presets
from studio_paths import model_directory

_fields = fields("sd15")
SPEC = {
    "name": "SD 1.5 · 文生图 / 图生图",
    "run_label": "生成图片",
    "description": "SD 1.5 模型的独立工作流，参数由本文件声明。",
    "fields": _fields,
    "model_root": str(model_directory()),
    "ready": bool(_fields[0]["options"]),
    "size_presets": common_size_presets(base=512, step=64),
}


def run(params, ctx):
    return run_diffusion("sd15", params, ctx)
