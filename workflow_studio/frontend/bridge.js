export const readFile = file => new Promise(resolve => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result);
  reader.readAsDataURL(file);
});

const labels = {
  'image.image': '图片', 'image.drop_to_upload': '拖入或点击上传图片',
  'upload_text.drop_image': '拖入图片', 'upload_text.click_to_upload': '点击上传',
  'common.or': '或', 'common.clear': '清除', 'common.download': '下载',
  'common.fullscreen': '全屏', 'common.upload': '上传', 'common.loading': '载入中',
  'chatbot.clear':'新对话', 'chatbot.retry':'重新生成', 'chatbot.undo':'回退',
  'chatbot.edit':'编辑并创建分支', 'chatbot.edit_submit':'保存分支', 'chatbot.edit_cancel':'取消',
  'common.copy':'复制', 'common.copied':'已复制', 'chatbot.copy':'复制',
  'chatbot.copy_all':'复制对话', 'chatbot.copy_message':'复制消息',
  'chatbot.submit':'保存并生成分支', 'chatbot.cancel':'取消'
};
export const i18n = key => labels[key] || key;

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const field = document.createElement('textarea');
    field.value = text;
    field.style.cssText = 'position:fixed;inset:0;opacity:0;pointer-events:none';
    const focused = document.activeElement;
    document.body.append(field);
    field.select();
    const copied = document.execCommand('copy');
    field.remove();
    focused?.focus({preventScroll:true});
    if (!copied) throw new Error('复制失败');
  }
}

export function downloadBuffer(name, buffer, type) {
  const data = ArrayBuffer.isView(buffer) ? new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength) : buffer;
  const url = URL.createObjectURL(new Blob([data], {type}));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function download(name, content, type = 'text/x-python') {
  const link = document.createElement('a');
  const objectURL = !content.startsWith('data:');
  link.href = objectURL ? URL.createObjectURL(new Blob([content], {type})) : content;
  link.download = name;
  link.click();
  if (objectURL) setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
