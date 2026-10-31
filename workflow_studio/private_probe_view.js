const enc = new TextEncoder();
const dec = new TextDecoder();
const encode = data => btoa(Array.from(new Uint8Array(data), x => String.fromCharCode(x)).join(''));
const decode = data => Uint8Array.from(atob(data), x => x.charCodeAt(0));

export async function render({model, el}) {
  const form = document.createElement('form');
  const label = document.createElement('label');
  const setup = model.get('password_setup');
  label.textContent = setup ? '设置工作台密码' : '工作台密码';
  const passwordField = document.createElement('input');
  passwordField.type = 'password';
  passwordField.autocomplete = setup ? 'new-password' : 'current-password';
  passwordField.required = true;
  passwordField.setAttribute('aria-label', setup ? '设置工作台密码' : '工作台密码');
  const confirmation = document.createElement('input');
  confirmation.type = 'password';
  confirmation.autocomplete = 'new-password';
  confirmation.required = setup;
  confirmation.setAttribute('aria-label', '确认密码');
  const confirmationLabel = document.createElement('label');
  confirmationLabel.textContent = '确认密码';
  confirmationLabel.append(confirmation);
  const button = document.createElement('button');
  button.textContent = setup ? '设置密码并打开' : '解锁工作台';
  const notice = document.createElement('p');
  notice.setAttribute('role', 'status');
  form.style.cssText = 'display:grid;gap:14px;max-width:440px;margin:24px;padding:24px;border:1px solid #d8dee7;border-radius:12px;background:#fff;color:#202830';
  for (const field of [passwordField, confirmation]) {
    field.style.cssText = 'display:block;box-sizing:border-box;width:100%;margin-top:6px;padding:10px;border:1px solid #b8c1ce;border-radius:6px;background:#fff;color:#202830';
  }
  button.style.cssText = 'padding:10px 16px;border:0;border-radius:6px;background:#397453;color:#fff;cursor:pointer';
  label.append(passwordField);
  form.append(label);
  if (setup) form.append(confirmationLabel);
  form.append(button, notice);
  el.append(form);
  let client, sessionKey, dispose, importer;
  let outgoing = Promise.resolve();
  let incoming = Promise.resolve();
  const listeners = new Set();
  const aad = direction => enc.encode(model.get('protocol') + ':' + client + ':' + direction);
  const adapter = {
    on: (name, fn) => listeners.add(fn),
    off: (name, fn) => listeners.delete(fn),
    send(content) {
      outgoing = outgoing.then(async () => {
        const nonce = crypto.getRandomValues(new Uint8Array(12));
        const data = await crypto.subtle.encrypt(
          {name: 'AES-GCM', iv: nonce, additionalData: aad('c2s')}, sessionKey,
          enc.encode(JSON.stringify(content)));
        model.send({type: 'sealed', client, nonce: encode(nonce), data: encode(data)});
      });
    },
  };
  const receive = packet => {
    if (packet.client !== client) return;
    incoming = incoming.then(async () => {
      if (packet.type === 'locked') {
        notice.textContent = packet.message;
        button.disabled = false;
        return;
      }
      if (packet.type !== 'sealed') return;
      const plaintext = await crypto.subtle.decrypt(
        {name: 'AES-GCM', iv: decode(packet.nonce), additionalData: aad('s2c')},
        sessionKey, decode(packet.data));
      const message = JSON.parse(dec.decode(plaintext));
      if (message.content.type === 'unlocked') {
        passwordField.value = '';
        confirmation.value = '';
        form.remove();
        const url = URL.createObjectURL(new Blob([STUDIO_SOURCE], {type: 'text/javascript'}));
        const studio = await import(url);
        URL.revokeObjectURL(url);
        dispose = studio.render({model: adapter, el});
        importer = document.createElement('details');
        importer.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2001;background:white;color:#202830;border:1px solid #ccc;border-radius:8px;padding:10px;max-width:90vw';
        const summary = document.createElement('summary');
        summary.textContent = '导入私密工作流';
        const filename = document.createElement('input');
        filename.value = 'private_workflow.py';
        filename.setAttribute('aria-label', '私密工作流文件名');
        const source = document.createElement('textarea');
        source.setAttribute('aria-label', '私密工作流源码');
        source.style.cssText = 'display:block;width:480px;max-width:80vw;height:240px';
        const submit = document.createElement('button');
        submit.textContent = '加密导入';
        submit.onclick = () => {
          adapter.send({action: 'import', name: filename.value, source: source.value});
          source.value = '';
          importer.open = false;
        };
        importer.append(summary, filename, source, submit);
        document.body.append(importer);
      } else {
        const buffers = message.buffers.map(value => decode(value).buffer);
        for (const callback of listeners) callback(message.content, buffers);
      }
    }).catch(() => {notice.textContent = '加密消息校验失败'; button.disabled = false;});
  };
  model.on('msg:custom', receive);
  form.onsubmit = async event => {
    event.preventDefault();
    if (setup && passwordField.value !== confirmation.value) {
      notice.textContent = '请再次输入相同密码';
      return;
    }
    button.disabled = true;
    notice.textContent = '正在解锁…';
    client = crypto.randomUUID();
    const passwordMaterial = await crypto.subtle.importKey('raw', enc.encode(passwordField.value),
      'PBKDF2', false, ['deriveBits']);
    const passwordKey = new Uint8Array(await crypto.subtle.deriveBits(
      {name: 'PBKDF2', salt: decode(model.get('password_salt')),
       iterations: model.get('password_iterations'), hash: 'SHA-256'}, passwordMaterial, 256));
    const transportKey = crypto.getRandomValues(new Uint8Array(32));
    sessionKey = await crypto.subtle.importKey('raw', transportKey, 'AES-GCM', false, ['encrypt', 'decrypt']);
    const publicKey = await crypto.subtle.importKey('spki', decode(model.get('public_key')),
      {name: 'RSA-OAEP', hash: 'SHA-256'}, false, ['encrypt']);
    const keys = new Uint8Array(64);
    keys.set(passwordKey);
    keys.set(transportKey, 32);
    const wrapped = await crypto.subtle.encrypt({name: 'RSA-OAEP'}, publicKey, keys);
    keys.fill(0);
    passwordKey.fill(0);
    transportKey.fill(0);
    model.send({type: 'unlock', client, wrapped: encode(wrapped)});
  };
  return () => {dispose?.(); importer?.remove(); model.off('msg:custom', receive); form.remove();};
}

export default {render};
