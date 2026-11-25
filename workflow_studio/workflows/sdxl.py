"""A Python workflow defines its own parameters and execution."""
from diffusers_runner import fields, run_diffusion
from size_presets import common_size_presets
from studio_paths import model_directory

_fields = fields("sdxl")
SPEC = {
    "name": "SDXL · 文生图 / 图生图",
    "run_label": "生成图片",
    "description": "直接使用 Diffusers 推理，支持实时预览、批量出图和图生图。",
    "fields": _fields,
    "model_root": str(model_directory()),
    "ready": bool(_fields[0]["options"]),
    "size_presets": common_size_presets(step=64),
}


def run(params, ctx):
    return run_diffusion("sdxl", params, ctx)
