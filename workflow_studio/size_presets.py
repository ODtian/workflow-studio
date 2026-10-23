"""Common aspect ratios aligned to each workflow's dimension step."""
from math import gcd, sqrt


def common_size_presets(base=1024, step=16):
    items = []
    for width, height in ((1, 1), (4, 3), (3, 4), (3, 2), (2, 3), (16, 9), (9, 16), (21, 9)):
        label = f"{width}:{height}"
        divisor = gcd(width, height)
        width, height = width // divisor, height // divisor
        unit = max(1, round(base / (sqrt(width * height) * step))) * step
        items.append({"label": label, "width": width * unit, "height": height * unit})
    return {"section": "画面", "width_key": "width", "height_key": "height", "step": step, "items": items}
