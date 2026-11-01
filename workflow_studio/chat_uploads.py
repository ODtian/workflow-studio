"""Receive chat attachments before a prompt over the existing widget channel."""
import base64


class ChatUploads:
    def __init__(self):
        self.images = {}

    def receive(self, content):
        key = content['id'], content['upload_id']
        if content['offset'] == 0:
            self.images[key] = {'name': content['name'], 'mime': content['mime'],
                                'total': content['total'], 'data': bytearray()}
        image = self.images[key]
        if content['offset'] != len(image['data']):
            raise ValueError('图片上传位置发生变化，请重新上传')
        image['data'].extend(base64.b64decode(content['data']))
        return {'id': content['id'], 'upload_id': content['upload_id'],
                'received': len(image['data']), 'total': image['total']}

    def resolve(self, panel_id, images):
        resolved = []
        for reference in images:
            if 'upload_id' not in reference:
                resolved.append(reference)
                continue
            image = self.images[panel_id, reference['upload_id']]
            if len(image['data']) != image['total']:
                raise ValueError('图片正在上传')
            resolved.append({'name': image['name'], 'url': 'data:' + image['mime'] +
                             ';base64,' + base64.b64encode(image['data']).decode()})
            del self.images[panel_id, reference['upload_id']]
        return resolved

    def discard(self, panel_id, upload_id):
        self.images.pop((panel_id, upload_id), None)
