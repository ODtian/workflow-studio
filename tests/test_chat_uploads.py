import base64
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workflow_studio'))
from chat_uploads import ChatUploads


class ChatUploadTest(unittest.TestCase):
    def test_upload_acknowledges_received_bytes_before_prompt_resolves_reference(self):
        uploads = ChatUploads()
        original = bytes(range(256)) * 3000
        received = []
        for offset in range(0, len(original), 256 * 1024):
            chunk = original[offset:offset + 256 * 1024]
            progress = uploads.receive({'id': 'chat', 'upload_id': 'image',
                'name': 'sample.png', 'mime': 'image/png', 'total': len(original),
                'offset': offset, 'data': base64.b64encode(chunk).decode()})
            received.append(progress['received'])
        self.assertEqual(received, [262144, 524288, len(original)])
        image, = uploads.resolve('chat', [{'upload_id': 'image', 'name': 'sample.png'}])
        self.assertEqual(image['name'], 'sample.png')
        self.assertEqual(base64.b64decode(image['url'].split(',', 1)[1]), original)


if __name__ == '__main__':
    unittest.main()
