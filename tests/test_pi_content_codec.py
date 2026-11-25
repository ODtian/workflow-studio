"""Python/Node compatibility for gzip Pi conversation files."""
import base64
import gzip
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from content_store import GZIP_MAGIC, pack, unpack


class PiContentCodecTest(unittest.TestCase):
    def test_conversation_round_trip_between_python_and_node(self):
        text = '测试 Pi 会话'
        with patch.dict('os.environ', {'WORKFLOW_GZIP_CONTENT': '1'}):
            compressed = pack(text.encode())
        config = {'message': text,
            'python_payload': base64.b64encode(compressed).decode(),
            'plain_payload': base64.b64encode(text.encode()).decode()}
        script = """
import {pathToFileURL} from 'node:url';
const codec = await import(pathToFileURL(process.argv[1]).href);
let source = ''; for await (const chunk of process.stdin) source += chunk;
const input = JSON.parse(source);
console.log(JSON.stringify({
  python_decoded: codec.unpackContent(Buffer.from(input.python_payload, 'base64')).toString(),
  plain_decoded: codec.unpackContent(Buffer.from(input.plain_payload, 'base64')).toString(),
  node_payload: codec.packContent(input.message).toString('base64')
}));
"""
        result = subprocess.run(['node', '--input-type=module', '-e', script,
            str(ROOT / 'workflow_studio/pi_bridge/content_codec.mjs')],
            input=json.dumps(config), encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        decoded = json.loads(result.stdout)
        self.assertEqual(decoded['python_decoded'], text)
        self.assertEqual(decoded['plain_decoded'], text)
        node_payload = base64.b64decode(decoded['node_payload'])
        self.assertTrue(node_payload.startswith(GZIP_MAGIC))
        self.assertEqual(gzip.decompress(node_payload).decode(), text)
        self.assertEqual(unpack(node_payload).decode(), text)


if __name__ == '__main__':
    unittest.main()
