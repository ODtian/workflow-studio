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
from copy_registry import sync as sync_shortcuts
from hf_downloads import HuggingFaceDownloads
from transfer_core import TransferController
from transfer_history import TransferHistory, workspace_store


class ModelSourcesTest(unittest.TestCase):
    def test_shortcuts_restore_across_runtimes_without_reviving_deleted_items(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            drive = root / 'drive'
            drive.mkdir()
            record = {'id': 'db98fa191cde40dc9122a689d8fb3a7d', 'label': 'File',
                      'source_provider': 'drive', 'direction': 'download', 'source_kind': 'file',
                      'drive_path': 'models/file', 'local_path': '/content/models', 'updated_at': 1}
            with patch.object(workspace_store, 'STORE', root / 'first'):
                workspace_store.edit(lambda state: state['copies'].append(record))
                self.assertEqual(sync_shortcuts(drive), 'drive')
            with patch.object(workspace_store, 'STORE', root / 'second'):
                self.assertEqual(sync_shortcuts(drive), 'drive')
                self.assertEqual(workspace_store.read()['copies'], [record])
                workspace_store.edit(lambda state: state.update(copies=[], copy_trash=[{**record, 'updated_at': 2}]))
                self.assertEqual(sync_shortcuts(drive), 'drive')
            with patch.object(workspace_store, 'STORE', root / 'first'):
                self.assertEqual(sync_shortcuts(drive), 'drive')
                self.assertEqual(workspace_store.read()['copies'], [])
                self.assertEqual(workspace_store.read()['copy_trash'], [{**record, 'updated_at': 2}])

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
        with (tempfile.TemporaryDirectory() as directory, ThreadPoolExecutor(max_workers=1) as pool,
              patch.object(workspace_store, "STORE", Path(directory) / "settings")):
            path = Path(directory) / "weight.safetensors"
            path.write_bytes(b"fixture")
            history = TransferHistory(None)
            controller = SimpleNamespace(lock=threading.RLock(), tasks=[], transfers=pool, closed=False,
                                         _publish=lambda: None, on_finish=history.finish)
            with patch("huggingface_hub.snapshot_download", return_value=[
                    SimpleNamespace(commit_hash="resolved-ref", filename=path.name)]) as snapshot, patch(
                    "huggingface_hub.hf_hub_download", return_value=str(path)) as download:
                manager = HuggingFaceDownloads(controller)
                snapshot.assert_not_called()
                download.assert_not_called()
                manager.download({"local_path": directory, "hf_sources": [
                    {"repo_id": "owner/repo", "revision": "main", "allow_patterns": [path.name]}]})
                self.assertTrue(snapshot.call_args.kwargs["dry_run"])
                self.assertEqual(download.call_args.kwargs["revision"], "resolved-ref")
                self.assertEqual(download.call_args.kwargs["local_dir"], directory)
                saved, = TransferHistory(None).visible()
                self.assertEqual(saved["status"], "completed")
                self.assertEqual(saved["target_path"], str(path))

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
