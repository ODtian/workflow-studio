"""Exercise the Colab profile and Git plugin restore on fresh directories."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import colab_runtime
from comfy_plugins import remember_plugins, restore_plugins


class ComfyPersistenceTest(unittest.TestCase):
    def test_profile_preserves_drive_settings_and_keeps_sqlite_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy = root / "runtime" / "ComfyUI"
            local = comfy / "user"
            profile = root / "drive" / "MyDrive" / "Workflow Studio" / "ComfyUI"
            saved = profile / "user"
            (local / "default" / "workflows").mkdir(parents=True)
            (saved / "default").mkdir(parents=True)
            (local / "comfyui.db").write_text("local database")
            (local / "default" / "comfy.settings.json").write_text("local settings")
            (saved / "default" / "comfy.settings.json").write_text("saved settings")
            (local / "default" / "workflows" / "my-flow.json").write_text("{}")

            with patch.object(colab_runtime, "ROOT", comfy.parent), patch.object(colab_runtime, "COMFY", comfy):
                self.assertEqual(colab_runtime._comfy_profile(), profile)
            self.assertFalse((saved / "comfyui.db").exists())
            self.assertEqual((saved / "default" / "comfy.settings.json").read_text(), "saved settings")
            self.assertTrue((saved / "default" / "workflows" / "my-flow.json").is_file())

    def test_manifest_reclones_the_saved_commit_and_keeps_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "current" / "custom_nodes"
            nodes = root / "fresh" / "custom_nodes"
            plugin = existing / "a-node"
            manifest = root / "plugins.json"
            remote = "https://example.invalid/a-node.git"
            plugin.mkdir(parents=True)
            nodes.mkdir(parents=True)

            def git(*args):
                return subprocess.run(["git", *args], cwd=plugin, check=True, capture_output=True, text=True).stdout.strip()

            def commit(text):
                (plugin / "__init__.py").write_text(text, encoding="utf-8")
                git("add", "__init__.py")
                git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Test revision")
                return git("rev-parse", "HEAD")

            git("init", "-q")
            git("remote", "add", "origin", "https://secret@example.invalid/a-node.git")
            first_revision = commit("first version")
            remember_plugins(existing, manifest)
            self.assertEqual(json.loads(manifest.read_text())["a-node"], {"repository": remote, "revision": first_revision})
            commit("second version")

            with patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1",
                        "GIT_CONFIG_KEY_0": f"url.{plugin.as_uri()}.insteadOf", "GIT_CONFIG_VALUE_0": remote}):
                restore_plugins(nodes, manifest)
                restored = nodes / "a-node" / "__init__.py"
                self.assertEqual(restored.read_text(), "first version")
                restored.write_text("local update", encoding="utf-8")
                restore_plugins(nodes, manifest)
                self.assertEqual(restored.read_text(), "local update")
