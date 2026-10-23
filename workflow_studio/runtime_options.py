"""Sampling choices for the native engine, available before model initialization."""
import json
from pathlib import Path
import sys


def sampling_options():
    native = sys.modules.get("comfy.samplers")
    if native is not None:
        schedulers = list(native.KSampler.SCHEDULERS)
        return list(native.KSampler.SAMPLERS), list(dict.fromkeys([*schedulers, "beta57"]))
    catalog = json.loads((Path(__file__).parent / "sampling_options.json").read_text(encoding="utf-8"))
    return catalog["samplers"], list(dict.fromkeys([*catalog["schedulers"], "beta57"]))
