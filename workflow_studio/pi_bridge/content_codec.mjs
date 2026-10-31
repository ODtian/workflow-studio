import {createCipheriv, createDecipheriv, randomBytes} from 'node:crypto';
import {gzipSync, gunzipSync} from 'node:zlib';

const MAGIC = Buffer.from('WFC1');
let key = null;

export function setContentKey(value) {
  key = Buffer.from(value);
}

export function packContent(value) {
  const compressed = gzipSync(value);
  if (!key) return compressed;
  const nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, nonce);
  cipher.setAAD(MAGIC);
  const encrypted = Buffer.concat([cipher.update(compressed), cipher.final()]);
  return Buffer.concat([MAGIC, nonce, encrypted, cipher.getAuthTag()]);
}

export function unpackContent(value) {
  let data = Buffer.from(value);
  if (data.subarray(0, 4).equals(MAGIC)) {
    const decipher = createDecipheriv('aes-256-gcm', key, data.subarray(4, 16));
    decipher.setAAD(MAGIC);
    decipher.setAuthTag(data.subarray(-16));
    data = Buffer.concat([decipher.update(data.subarray(16, -16)), decipher.final()]);
  }
  return data[0] === 0x1f && data[1] === 0x8b ? gunzipSync(data) : data;
}
