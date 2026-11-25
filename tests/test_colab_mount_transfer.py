"""Verify file transfer behavior on a Colab-style POSIX filesystem."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transfer_core import Entry, TransferController


@unittest.skipUnless(os.name == "posix", "Colab mounts use POSIX directory handles")
class ColabMountTransferTest(unittest.TestCase):
    def test_recursive_copy_preserves_an_existing_file_and_ignores_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            local, drive = root / "runtime", root / "drive"
            source = local / "models"
            (source / "lora").mkdir(parents=True)
            (drive / "models").mkdir(parents=True)
            (source / "base.safetensors").write_bytes(b"new")
            (source / "lora" / "style.safetensors").write_bytes(b"nested")
            (source / "link").symlink_to(drive, target_is_directory=True)
            (drive / "models" / "base.safetensors").write_bytes(b"existing")
            complete = threading.Event()

            def update(state):
                if any(task["status"] in ("completed", "failed") for task in state["tasks"]):
                    complete.set()

            controller = TransferController(drive, local_roots={"root": local}, on_change=update)
            try:
                controller.handle({"action": "transfer", "entry_ids": [
                    controller._register(Entry("local", ("models",), "directory"))],
                    "target_id": controller._register(Entry("drive", (), "directory"))})
                self.assertTrue(complete.wait(10))
                self.assertEqual(controller.snapshot()["tasks"][0]["status"], "completed")
                self.assertEqual((drive / "models" / "base.safetensors").read_bytes(), b"existing")
                self.assertEqual((drive / "models" / "base (2).safetensors").read_bytes(), b"new")
                self.assertEqual((drive / "models" / "lora" / "style.safetensors").read_bytes(), b"nested")
                self.assertFalse((drive / "models" / "link").exists())
            finally:
                controller.close()
