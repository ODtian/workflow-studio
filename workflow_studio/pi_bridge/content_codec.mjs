import {gzipSync, gunzipSync} from 'node:zlib';

export function packContent(value) {
  return gzipSync(value);
}

export function unpackContent(data) {
  return data[0] === 0x1f && data[1] === 0x8b ? gunzipSync(data) : data;
}
