import test from 'node:test';
import assert from 'node:assert/strict';
import {createChatUploader} from '../workflow_studio/frontend/chatUpload.js';

test('uploads each chunk immediately and reports backend acknowledgements', async () => {
  const sent = [], progress = [];
  const uploader = createChatUploader((action, message) => {
    sent.push({action, ...message});
    queueMicrotask(() => uploader.receive({upload_id:message.upload_id,
      received:message.offset + atob(message.data).length, total:message.total}));
  });
  const file = new File([new Uint8Array(700000)], 'sample.png', {type:'image/png'});
  const reference = await uploader.upload('chat', file, value => progress.push(value.received));
  assert.deepEqual(sent.map(message => message.action), ['chat_upload','chat_upload','chat_upload']);
  assert.deepEqual(sent.map(message => message.offset), [0,262144,524288]);
  assert.deepEqual(progress, [0,262144,524288,700000]);
  assert.equal(reference.name, 'sample.png');
  assert.equal(reference.upload_id, sent[0].upload_id);
  assert.equal(reference.url, undefined);
});
