"""Cover transfer history across Studio and Colab runtime lifetimes."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "workflow_studio")]
from transfer_history import TransferHistory, workspace_store


def task(source, status="completed"):
    return {"id": uuid.uuid4().hex, "name": "weights.safetensors", "source": source,
            "status": status, "direction": "download", "bytes": 42}


class ColabTransferHistoryTest(unittest.TestCase):
    def test_runtime_history_syncs_when_drive_is_mounted_later(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            drive = root / "drive"
            hf, copied = task("huggingface"), task("drive")
            with patch.object(workspace_store, "STORE", root / "first"):
                history = TransferHistory(drive)
                self.assertEqual(history.storage, "runtime")
                history.finish(hf)
                history.finish(copied)
                self.assertEqual(len(TransferHistory(drive).visible()), 2)
                drive.mkdir()
                history.sync()
                self.assertEqual(history.storage, "drive")
                self.assertTrue(history.set_deleted(hf["id"], True))
            with patch.object(workspace_store, "STORE", root / "second"):
                history = TransferHistory(drive)
                self.assertEqual([entry["id"] for entry in history.visible()], [copied["id"]])
                self.assertTrue(history.set_deleted(hf["id"], False))
                self.assertEqual(len(TransferHistory(drive).visible()), 2)

    def test_existing_hugging_face_history_migrates_without_inventing_dates(self):
        with TemporaryDirectory() as directory, patch.object(workspace_store, "STORE", Path(directory)):
            failed = task("huggingface", "failed")
            workspace_store.edit(lambda state: state.update(hf_downloads=[failed]))
            history = TransferHistory(None)
            self.assertEqual(history.visible(), [{**failed, "updated_at": 0}])
            history.set_deleted(failed["id"], True)
            self.assertEqual(TransferHistory(None).visible(), [])
