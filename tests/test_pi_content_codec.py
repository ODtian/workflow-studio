"""Python/Node compatibility for encrypted Pi conversation files."""
import base64
import gzip
import json
from pathlib import Path
import secrets
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from content_store import ENCRYPTED_MAGIC, pack, unpack, use_encryption


class PiContentCodecTest(unittest.TestCase):
    def test_conversation_ciphertext_round_trip_between_python_and_node(self):
        key = secrets.token_bytes(32)
        text = 'private-conversation-' + secrets.token_hex(20)
        use_encryption(key)
        config = {'key': base64.b64encode(key).decode(), 'message': text,
            'python_payload': base64.b64encode(pack(text.encode())).decode(),
            'legacy_payload': base64.b64encode(gzip.compress(text.encode())).decode()}
        script = """
import {pathToFileURL} from 'node:url';
const codec = await import(pathToFileURL(process.argv[1]).href);
let source = ''; for await (const chunk of process.stdin) source += chunk;
const input = JSON.parse(source);
codec.setContentKey(Buffer.from(input.key, 'base64'));
console.log(JSON.stringify({
  python_decoded: codec.unpackContent(Buffer.from(input.python_payload, 'base64')).toString(),
  legacy_decoded: codec.unpackContent(Buffer.from(input.legacy_payload, 'base64')).toString(),
  node_payload: codec.packContent(input.message).toString('base64')
}));
"""
        result = subprocess.run(['node', '--input-type=module', '-e', script,
            str(ROOT / 'workflow_studio/pi_bridge/content_codec.mjs')],
            input=json.dumps(config), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        decoded = json.loads(result.stdout)
        self.assertEqual(decoded['python_decoded'], text)
        self.assertEqual(decoded['legacy_decoded'], text)
        ciphertext = base64.b64decode(decoded['node_payload'])
        self.assertTrue(ciphertext.startswith(ENCRYPTED_MAGIC))
        self.assertNotIn(text.encode(), ciphertext)
        self.assertEqual(unpack(ciphertext).decode(), text)


if __name__ == '__main__':
    unittest.main()
