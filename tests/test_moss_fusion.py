"""Check MOSS fusion settings against the Comfy patcher interface."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow_studio"))

import moss_runner


class Patcher:
    def __init__(self, weight):
        self.weight = weight
        self.applied = None
        self.model = SimpleNamespace(
            named_parameters=lambda **_: [("diffusion_model.weight", weight)],
            named_buffers=lambda **_: [],
        )

    def clone(self):
        return Patcher(self.weight)

    def model_state_dict(self, filter_prefix=None):
        return {"diffusion_model.weight": self.weight, "diffusion_model.weight_scale": 8}

    def get_key_patches(self, prefix):
        return {name: value for name, value in self.model_state_dict().items() if name.startswith(prefix)}

    def add_patches(self, patches, source_strength, base_strength):
        self.applied = patches, source_strength, base_strength
        return list(patches)


class MossFusionTest(unittest.TestCase):
    def test_fusion_uses_second_model_weight_and_filters_serialization_keys(self):
        base, secondary = Patcher(2), Patcher(10)
        mixed = moss_runner._merge_diffusion_models(base, secondary, 0.25)
        self.assertEqual(mixed.applied, ({"diffusion_model.weight": 10}, 0.25, 0.75))
        self.assertIsNone(base.applied)
        self.assertIn("diffusion_model.weight_scale", secondary.model_state_dict())

    def test_old_parameters_and_fusion_endpoints_use_only_one_checkpoint(self):
        with patch.object(moss_runner, "MODELS", Path("models")):
            base = Path("models/diffusion_models/base.safetensors")
            secondary = Path("models/diffusion_models/sft.safetensors")
            params = {"model": base.name, "mix_model": secondary.name}
            self.assertEqual(moss_runner._diffusion_selection({"model": base.name}), ((base,), 0))
            self.assertEqual(moss_runner._diffusion_selection({**params, "mix_enabled": True}), ((base, secondary), 0.5))
            self.assertEqual(moss_runner._diffusion_selection({**params, "mix_enabled": True, "mix_weight": 0}), ((base,), 0))
            self.assertEqual(moss_runner._diffusion_selection({**params, "mix_enabled": True, "mix_weight": 1}), ((secondary,), 1))
            with self.assertRaises(ValueError):
                moss_runner._diffusion_selection({**params, "mix_enabled": True, "mix_model": ""})
            with self.assertRaises(ValueError):
                moss_runner._diffusion_selection({**params, "mix_enabled": True, "mix_weight": 2})
