"""Verify that model discovery and explicit downloads stay independent."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "workflow_studio")]

from diffusers_runner import fields
from hf_downloads import HuggingFaceDownloads
from transfer_core import TransferController


class ModelSourcesTest(unittest.TestCase):
    def test_diffusers_lists_only_detected_local_weights(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                "os.environ", {"WORKFLOW_MODELS_DIR": directory}):
            root = Path(directory).resolve()
            self.assertEqual(fields("sdxl")[0]["options"], [])
            checkpoint = root / "checkpoints" / "local.safetensors"
            checkpoint.parent.mkdir()
            checkpoint.touch()
            pipeline = root / "diffusers" / "local-xl"
            pipeline.mkdir(parents=True)
            (pipeline / "model_index.json").write_text('{"_class_name":"StableDiffusionXLPipeline"}')
            (checkpoint.parent / "unfinished.tmp").touch()
            self.assertEqual([option["value"] for option in fields("sdxl")[0]["options"]],
                             [str(checkpoint), str(pipeline)])
            self.assertEqual([option["value"] for option in fields("sd15")[0]["options"]], [str(checkpoint)])

    def test_hf_download_starts_only_after_file_panel_request(self):
        with tempfile.TemporaryDirectory() as directory, ThreadPoolExecutor(max_workers=1) as pool:
            path = Path(directory) / "weight.safetensors"
            path.write_bytes(b"fixture")
            controller = SimpleNamespace(lock=threading.RLock(), tasks=[], transfers=pool, closed=False,
                                         _publish=lambda: None)
            saved = {}
            store = SimpleNamespace(read=lambda: saved, edit=lambda change: change(saved))
            with patch("huggingface_hub.snapshot_download", return_value=[
                    SimpleNamespace(commit_hash="resolved-ref", filename=path.name)]) as snapshot, patch(
                    "huggingface_hub.hf_hub_download", return_value=str(path)) as download:
                manager = HuggingFaceDownloads(SimpleNamespace(controller=controller, store=store))
                snapshot.assert_not_called()
                download.assert_not_called()
                manager.download({"local_path": directory, "hf_sources": [
                    {"repo_id": "owner/repo", "revision": "main", "allow_patterns": [path.name]}]})
                self.assertTrue(snapshot.call_args.kwargs["dry_run"])
                self.assertEqual(download.call_args.kwargs["revision"], "resolved-ref")
                self.assertEqual(download.call_args.kwargs["local_dir"], directory)
                self.assertEqual(saved["hf_downloads"][0]["status"], "completed")

    def test_drive_starts_at_the_signed_in_accounts_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = TransferController(None, local_roots={"root": root, "models": root / "models"})
            try:
                state = controller.snapshot()
                self.assertFalse(state["connected"])
                self.assertEqual([location["id"] for location in state["panes"]["drive"]["roots"]], ["root"])
                self.assertEqual([location["id"] for location in state["panes"]["local"]["roots"]],
                                 ["root", "models"])
            finally:
                controller.close()
