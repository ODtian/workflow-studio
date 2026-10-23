"""A Python workflow defines its own parameters and execution."""
from diffusers_runner import fields, run_diffusion
from size_presets import common_size_presets

SPEC = {
    "name": "SDXL · 文生图 / 图生图",
    "run_label": "生成图片",
    "description": "直接使用 Diffusers 推理，支持实时预览、批量出图和图生图。",
    "fields": fields("sdxl"),
    "size_presets": common_size_presets(step=64),
}


def run(params, ctx):
    return run_diffusion("sdxl", params, ctx)
