const chunkSize = 256 * 1024;

export function createChatUploader(send) {
  const waiting = new Map();
  return {
    async upload(panelId, file, onProgress) {
      const uploadId = crypto.randomUUID();
      onProgress({received:0, total:file.size});
      for (let offset = 0; offset < file.size; offset += chunkSize) {
        const bytes = new Uint8Array(await file.slice(offset, offset + chunkSize).arrayBuffer());
        const data = btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(''));
        const progress = await new Promise((resolve, reject) => {
          waiting.set(uploadId, {resolve, reject});
          send('chat_upload', {id:panelId, upload_id:uploadId, name:file.name,
            mime:file.type, total:file.size, offset, data});
        });
        onProgress(progress);
      }
      return {upload_id:uploadId, name:file.name};
    },
    receive(message) {
      const request = waiting.get(message.upload_id);
      waiting.delete(message.upload_id);
      if (message.error) request.reject(new Error(message.error));
      else request.resolve(message);
    },
    close() {
      for (const request of waiting.values()) request.reject(new Error('页面已关闭'));
      waiting.clear();
    },
  };
}
