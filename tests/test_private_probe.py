"""One end-to-end check of the private workflow, widget, and file boundaries."""
import base64
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'workflow_studio'), str(ROOT)]
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from private_probe import PrivateStudioProbe, PROTOCOL, b64


class PrivateProbeTest(unittest.TestCase):
    def test_workflow_content_is_encrypted_at_widget_and_file_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            packets = []
            with patch('anywidget.AnyWidget.send', side_effect=lambda owner, value, **kw: packets.append(value)):
                widget = PrivateStudioProbe(directory)
                key, transport = secrets.token_bytes(32), secrets.token_bytes(32)
                public = serialization.load_der_public_key(base64.b64decode(widget.public_key))

                def unlock(client, vault_key, session_key):
                    wrapped = public.encrypt(vault_key + session_key, padding.OAEP(
                        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
                    widget._receive(widget, {'type': 'unlock', 'client': client, 'wrapped': b64(wrapped)}, [])

                def request(content):
                    nonce = secrets.token_bytes(12)
                    raw = json.dumps(content).encode()
                    cipher = AESGCM(transport).encrypt(nonce, raw, PROTOCOL + b':owner:c2s')
                    widget._receive(widget, {'type': 'sealed', 'client': 'owner',
                        'nonce': b64(nonce), 'data': b64(cipher)}, [])

                unlock('owner', key, transport)
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
                session = next(iter(widget.sessions.values()))
                params = {'prompt': markers['prompt'], 'input': markers['input']}
                session.params.update(params)
                widget.save_settings()
                session.started_at = time.monotonic()
                session.execute(widget.load('private.py'), params, threading.Event())
                request({'action': 'sync'})
                result_path = next((Path(directory) / 'results').iterdir())
                plaintext = widget.store.read('results/' + result_path.name).decode()
                self.assertIn(markers['result'], plaintext)
                self.assertIn(markers['log'], widget.store.read('logs.bin').decode())
                visible = json.dumps(widget.get_state()).encode() + json.dumps(packets).encode()
                visible += b''.join(path.read_bytes() for path in Path(directory).rglob('*') if path.is_file())
                for marker in markers.values():
                    self.assertNotIn(marker.encode(), visible)
                unlock('visitor', secrets.token_bytes(32), secrets.token_bytes(32))
                self.assertNotIn('visitor', widget.clients)
                self.assertEqual(packets[-1]['type'], 'locked')
                widget.close()


if __name__ == '__main__':
    unittest.main()
