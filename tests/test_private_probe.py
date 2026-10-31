"""One end-to-end check of the private workflow, widget, and file boundaries."""
import base64
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import threading
import time
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'workflow_studio'), str(ROOT)]
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from private_probe import EncryptedStore, PrivateStudioProbe, PROTOCOL, b64


def password_key(widget, password, salt=None):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
        salt=salt if salt is not None else base64.b64decode(widget.password_salt),
        iterations=widget.password_iterations).derive(password.encode())


def unlock(widget, client, password, transport):
    public = serialization.load_der_public_key(base64.b64decode(widget.public_key))
    wrapped = public.encrypt(password_key(widget, password) + transport, padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    widget._receive(widget, {'type': 'unlock', 'client': client, 'wrapped': b64(wrapped)}, [])


class PrivateProbeTest(unittest.TestCase):
    def setUp(self):
        self.workspace = {'schema': 1, 'nodes': [], 'copies': []}
        workspace = ModuleType('workspace_store')
        workspace.read = lambda: deepcopy(self.workspace)
        workspace.edit = lambda callback: callback(self.workspace)
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'workspace_store': workspace}).start()
        patch.dict(os.environ, {'WORKFLOW_GZIP_CONTENT': '0'}).start()
        find_spec = importlib.util.find_spec
        patch('importlib.util.find_spec', side_effect=lambda name, *args:
            None if name == 'transfer_core' else find_spec(name, *args)).start()

        def open_test_runtime(owner, saved):
            from content_store import use_encryption
            from private_runtime import EncryptedWorkflowPanel
            use_encryption(owner._key)
            workflows = owner.directory / 'public-workflows'
            workflows.mkdir(exist_ok=True)
            for folder in (ROOT / 'workflow_studio/workflows', ROOT / 'studio_workflows'):
                for path in folder.glob('*.py'):
                    shutil.copy2(path, workflows / path.name)
            return EncryptedWorkflowPanel(owner, saved, workflow_dir=workflows,
                output_dir=owner.directory / 'results')

        patch('private_runtime.open_runtime', side_effect=open_test_runtime).start()

    def test_workflow_content_is_encrypted_at_widget_and_file_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            packets = []
            with patch('anywidget.AnyWidget.send', side_effect=lambda owner, value, **kw: packets.append(value)):
                widget = PrivateStudioProbe(directory)
                password = 'studio-test-' + secrets.token_hex(12)
                transport = secrets.token_bytes(32)

                def request(content):
                    nonce = secrets.token_bytes(12)
                    raw = json.dumps(content).encode()
                    cipher = AESGCM(transport).encrypt(nonce, raw, PROTOCOL + b':owner:c2s')
                    widget._receive(widget, {'type': 'sealed', 'client': 'owner',
                        'nonce': b64(nonce), 'data': b64(cipher)}, [])

                unlock(widget, 'owner', password, transport)
                self.assertFalse(widget.password_setup)
                markers = {name: name + '-' + secrets.token_hex(16)
                           for name in ('source', 'prompt', 'input', 'result', 'log')}
                source = "\n".join([
                    "SPEC = {'name':'Private probe', 'output':'text', 'fields':[",
                    "{'key':'prompt','type':'text','default':''},",
                    "{'key':'input','type':'text','default':''}]}",
                    f"SOURCE_TAG = {markers['source']!r}",
                    "def run(params, ctx):",
                    f"    print({markers['log']!r})",
                    f"    return {markers['result']!r} + params['prompt'] + params['input']",
                ])
                request({'action': 'import', 'name': 'private.py', 'source': source})
                session = next(s for s in widget.sessions.values() if s.state['selected'] == 'private.py')
                params = {'prompt': markers['prompt'], 'input': markers['input']}
                session.params.update(params)
                widget.save_settings()
                session.started_at = time.monotonic()
                session.execute(widget.load('private.py'), params, threading.Event())
                request({'action': 'sync'})
                result_path = next((Path(directory) / 'results').glob('*.txt'))
                from content_store import read_text
                plaintext = read_text(result_path)
                self.assertIn(markers['result'], plaintext)
                self.assertIn(markers['log'], widget.store.read('logs.bin').decode())
                visible = json.dumps(widget.get_state()).encode() + json.dumps(packets).encode()
                visible += b''.join(path.read_bytes() for path in Path(directory).rglob('*') if path.is_file())
                for marker in markers.values():
                    self.assertNotIn(marker.encode(), visible)
                self.assertNotIn(password.encode(), visible)
                self.assertNotIn(widget._key, visible)
                self.assertNotIn(password_key(widget, password), visible)
                unlock(widget, 'returning-owner', password, secrets.token_bytes(32))
                self.assertIn('returning-owner', widget.clients)
                unlock(widget, 'visitor', 'wrong-password', secrets.token_bytes(32))
                self.assertNotIn('visitor', widget.clients)
                self.assertEqual(packets[-1]['type'], 'locked')
                widget.close()

    def test_password_setup_preserves_an_existing_encrypted_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy_key = secrets.token_bytes(32)
            source = "SPEC = {'name':'Existing private workflow','fields':[]}"
            saved = {'workflows': {'existing.py': source}, 'panels': [], 'active': ''}
            EncryptedStore(directory, legacy_key).write('state.wfs', json.dumps(saved).encode())
            password = 'migration-test-' + secrets.token_hex(12)
            with patch('anywidget.AnyWidget.send'):
                widget = PrivateStudioProbe(directory, legacy_key=legacy_key)
                unlock(widget, 'setup-owner', password, secrets.token_bytes(32))
                self.assertEqual(widget._key, legacy_key)
                self.assertEqual(widget._sources['existing.py'], source)
                widget.close()
                reopened = PrivateStudioProbe(directory)
                self.assertFalse(reopened.password_setup)
                unlock(reopened, 'owner', password, secrets.token_bytes(32))
                self.assertEqual(reopened._sources['existing.py'], source)
                visible = b''.join(path.read_bytes() for path in Path(directory).rglob('*') if path.is_file())
                self.assertNotIn(password.encode(), visible)
                self.assertNotIn(legacy_key, visible)
                reopened.close()

    def test_original_workflow_catalog_and_drive_action_are_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('anywidget.AnyWidget.send'):
                widget = PrivateStudioProbe(directory)
                transport = secrets.token_bytes(32)
                unlock(widget, 'owner', 'catalog-test-password', transport)
                expected = {'moss_image.py', 'minimax_h3.py', 'llama_cpp.py',
                            'sd15.py', 'sdxl.py', 'image_grade.py'}
                self.assertTrue(expected.issubset({item['id'] for item in widget.runtime.state['workflows']}))
                self.assertTrue({'moss_image.py', 'minimax_h3.py', 'llama_cpp.py'}.issubset(
                    {session.state['selected'] for session in widget.sessions.values()}))
                from files_bridge import FilesBridge
                state = {'panes': {name: {'entries': [{'name': 'fixture'}]} for name in ('drive', 'local')},
                         'tasks': [], 'connected': False}
                controller = SimpleNamespace(state=state, tools_listeners=[], snapshot=lambda: deepcopy(state))
                authorization = SimpleNamespace(begin=lambda: 'https://accounts.google.com/o/oauth2/auth?test=1')
                widget.runtime.files_bridge = FilesBridge(widget.runtime, controller=controller,
                    authorization_factory=lambda: authorization)
                content = {'action': 'files', 'command': {'action': 'drive_connect'}}
                nonce = secrets.token_bytes(12)
                data = AESGCM(transport).encrypt(nonce, json.dumps(content).encode(), PROTOCOL + b':owner:c2s')
                widget._receive(widget, {'type': 'sealed', 'client': 'owner',
                    'nonce': b64(nonce), 'data': b64(data)}, [])
                self.assertEqual(widget.runtime.files_bridge.drive_auth['phase'], 'pending')
                self.assertTrue(widget.runtime.files_bridge.drive_auth['url'].startswith('https://accounts.google.com/'))
                widget.close()

    def test_password_change_keeps_data_and_updates_the_unlock_password(self):
        with tempfile.TemporaryDirectory() as directory:
            packets = []
            with patch('anywidget.AnyWidget.send', side_effect=lambda owner, value, **kw: packets.append(value)):
                widget = PrivateStudioProbe(directory)
                original = 'original-' + secrets.token_hex(12)
                replacement = 'replacement-' + secrets.token_hex(12)
                transport = secrets.token_bytes(32)
                unlock(widget, 'owner', original, transport)
                widget.store.write('result.bin', b'private result retained across password update')
                result_file = Path(directory) / 'result.bin'
                original_result = result_file.read_bytes()
                original_config = (Path(directory) / 'password.json').read_bytes()
                salt = secrets.token_bytes(16)
                new_key = password_key(widget, replacement, salt)

                def change(current):
                    nonce = secrets.token_bytes(12)
                    content = {'action': 'change_password', 'request': 'change-test',
                        'current_key': b64(password_key(widget, current)),
                        'replacement_key': b64(new_key), 'replacement_salt': b64(salt)}
                    ciphertext = AESGCM(transport).encrypt(nonce, json.dumps(content).encode(),
                        PROTOCOL + b':owner:c2s')
                    widget._receive(widget, {'type': 'sealed', 'client': 'owner',
                        'nonce': b64(nonce), 'data': b64(ciphertext)}, [])
                    packet = packets[-1]
                    decoded = AESGCM(transport).decrypt(base64.b64decode(packet['nonce']),
                        base64.b64decode(packet['data']), PROTOCOL + b':owner:s2c')
                    return json.loads(decoded)['content']

                self.assertFalse(change('incorrect-current-password')['ok'])
                self.assertEqual((Path(directory) / 'password.json').read_bytes(), original_config)
                self.assertTrue(change(original)['ok'])
                self.assertEqual(result_file.read_bytes(), original_result)
                self.assertEqual(widget.store.read('result.bin'), b'private result retained across password update')
                unlock(widget, 'old-password-visitor', original, secrets.token_bytes(32))
                self.assertNotIn('old-password-visitor', widget.clients)
                widget.close()
                reopened = PrivateStudioProbe(directory)
                unlock(reopened, 'new-password-owner', replacement, secrets.token_bytes(32))
                self.assertIn('new-password-owner', reopened.clients)
                visible = b''.join(path.read_bytes() for path in Path(directory).rglob('*') if path.is_file())
                self.assertNotIn(original.encode(), visible)
                self.assertNotIn(replacement.encode(), visible)
                self.assertNotIn(new_key, visible)
                reopened.close()

    def test_original_image_workflow_keeps_preview_and_encrypted_output(self):
        from PIL import Image
        from content_store import open_image, ENCRYPTED_MAGIC
        with tempfile.TemporaryDirectory() as directory:
            transport = secrets.token_bytes(32)
            preview_received = threading.Event()

            def capture(owner, packet, **kwargs):
                if packet.get('type') != 'sealed' or packet.get('client') != 'owner':
                    return
                raw = AESGCM(transport).decrypt(base64.b64decode(packet['nonce']),
                    base64.b64decode(packet['data']), PROTOCOL + b':owner:s2c')
                if json.loads(raw)['content']['type'] == 'preview_frame':
                    preview_received.set()

            with patch('anywidget.AnyWidget.send', side_effect=capture):
                widget = PrivateStudioProbe(directory)
                unlock(widget, 'owner', 'image-test-password', transport)
                image = io.BytesIO()
                Image.new('RGB', (4, 4), 'blue').save(image, 'PNG')
                session = widget.runtime.add('image_grade.py')
                params = {**session.params, 'image': 'data:image/png;base64,' + b64(image.getvalue())}
                session.started_at = time.monotonic()
                session.state['run_id'] = 'image-test'
                session.execute(widget.runtime.load('image_grade.py'), params, threading.Event())
                self.assertEqual(session.state['phase'], 'complete')
                self.assertTrue(preview_received.wait(timeout=3))
                output = next(widget.output_dir.glob('*.png'))
                self.assertTrue(output.read_bytes().startswith(ENCRYPTED_MAGIC))
                self.assertEqual(open_image(output).size, (4, 4))
                widget.close()


if __name__ == '__main__':
    unittest.main()
