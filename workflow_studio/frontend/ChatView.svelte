<script>
  import {Block} from '@gradio/atoms';
  import {BaseButton} from '@gradio/button';
  import {BaseDropdown} from '@gradio/dropdown';
  import {BaseTextbox} from '@gradio/textbox';
  import {BaseChatBot} from '@gradio/chatbot';
  import ChatImages from './ChatImages.svelte';
  import PiStatus from './PiStatus.svelte';
  import Field from './Field.svelte';
  import {i18n} from './bridge.js';
  import {followTail} from './followTail.js';

  let {panel, active = true, values = $bindable(), chat = {nodes:{}, active:null, selected:{}}, send,
       targets = [], onTransfer} = $props();
  let input = $state('');
  let settingsOpen = $state(false);
  let selectedMessage = $state('');
  let target = $state('');
  let following = $state(true);
  let attachments = $state([]);
  let readingImages = $state(false);
  let dragging = $state(false);
  let imageInput;
  let scrollPane;
  const act = (action, data = {}) => send(action, {id:panel.id, ...data});
  const nodeIndex = index => Array.isArray(index) ? index[0] : index;
  let path = $derived.by(() => {
    const nodes = [];
    let id = chat.active;
    while (id) {const node = chat.nodes[id]; nodes.unshift(node); id = node.parent;}
    return nodes;
  });
  let roots = $derived(chat.roots || Object.values(chat.nodes).filter(node => !node.parent));
  let root = $derived(path[0]?.id || '');
  let branches = $derived(path.map((node, index) => ({node, index,
    siblings:chat.siblings?.[node.parent || ''] || Object.values(chat.nodes).filter(item => item.parent === node.parent).map(item => item.id)})).filter(item => item.siblings.length > 1 && item.node.parent));
  let messages = $derived(active ? path.flatMap((node, index) => {
    const message = {type:'text', role:node.role, content:node.content, index, metadata:{title:null}};
    const images = node.attachments?.length ? [{type:'component',role:node.role,index:[index,-2],metadata:{title:null},
      content:{component:'gallery',constructor_args:{},props:{},alt_text:'提问图片',
        value:node.attachments.map(image => ({url:image.preview,orig_name:image.name}))}}] : [];
    const thought = {type:'text', role:'assistant', content:node.reasoning, index:[index,-1],
      metadata:{title:'Thinking', status:node.status === 'pending' && !node.content ? 'pending' : 'done'}};
    return [...images,...(node.reasoning ? [thought, message] : node.content || !images.length ? [message] : [])];
  }) : []);
  let lastAnswer = $derived(path.filter(node => node.role === 'assistant').at(-1));
  let selected = $derived(path.find(node => node.id === selectedMessage) || lastAnswer);
  let fields = $derived(panel.spec.fields);
  let groups = $derived([...new Set(fields.filter(field => !field.area).map(field => field.section || '参数'))]);
  $effect(() => {if (!targets.some(t => t.value === target)) target = targets[0]?.value || '';});

  function submit() {
    if ((!input.trim() && !attachments.length) || readingImages || panel.busy || panel.spec.ready === false) return;
    act('chat_send', {text:input, images:attachments.map(({name,url}) => ({name,url})), params:{...values}});
    input = '';
    attachments = [];
  }
  async function addImages(files) {
    readingImages = true;
    try {
      const images = await Promise.all([...files].filter(file => file.type.startsWith('image/')).map(file => new Promise((resolve,reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({id:crypto.randomUUID(),name:file.name,url:reader.result});
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      })));
      attachments = [...attachments,...images];
    } finally {readingImages = false;}
  }
  function retry(node = selected) {act('chat_retry', {node:node.id, params:{...values}});}
  function exportChat() {
    act('chat_export');
  }
  function copyConversation() {
    navigator.clipboard.writeText(path.map(node => `${node.role}: ${node.content}`).join('\n\n'));
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<article class="chat-card" class:dragging aria-label={panel.spec.name}
  ondragover={event => {if (panel.spec.images && event.dataTransfer.types.includes('Files')) {event.preventDefault();dragging = true;}}}
  ondragleave={event => {if (!event.currentTarget.contains(event.relatedTarget)) dragging = false;}}
  ondrop={event => {if (panel.spec.images) {event.preventDefault();dragging = false;addImages(event.dataTransfer.files);}}}>
  {#if dragging}<div class="drop-hint">松开添加图片</div>{/if}
  <div class="chat-toolbar">
    <div class="model-choice">
      {#each fields.filter(field => field.area === 'models') as field}
        <Field {field} idPrefix={panel.id} bind:value={values[field.key]} busy={panel.busy} compact={true} />
      {/each}
      {#if panel.initializing}<span class="preparation" role="status">{panel.initialization}</span>{/if}
    </div>
    <BaseButton size="sm" onclick={() => act('refresh')}>刷新模型</BaseButton>
    <BaseButton size="sm" variant={settingsOpen ? 'primary' : 'secondary'} onclick={() => settingsOpen = !settingsOpen}>对话设置</BaseButton>
    <BaseButton size="sm" disabled={panel.busy} onclick={() => act('chat_new')}>新对话</BaseButton>
    <details class="more"><summary>更多</summary><div>
      <BaseButton size="sm" disabled={panel.busy} onclick={exportChat}>导出聊天分支</BaseButton>
      <BaseButton size="sm" onclick={copyConversation}>复制对话正文</BaseButton>
      <BaseButton size="sm" onclick={() => act('export')}>导出工作流</BaseButton>
      <BaseButton size="sm" disabled={panel.busy} onclick={() => act('remove')}>移除标签页</BaseButton>
    </div></details>
  </div>

  {#if settingsOpen}
    <section class="settings" aria-label="对话设置">
      <div class="system-fields">
        {#each fields.filter(field => field.area === 'prompts') as field}
          <Field {field} idPrefix={panel.id} bind:value={values[field.key]} busy={panel.busy} />
        {/each}
      </div>
      <div class="setting-groups">
        {#each groups as group}<section><h3>{group}</h3><div class="settings-fields">
          {#each fields.filter(field => !field.area && (field.section || '参数') === group) as field}
            <Field {field} idPrefix={panel.id} bind:value={values[field.key]} busy={panel.busy} />
          {/each}
        </div></section>{/each}
        <section><h3>高级设置</h3><div class="settings-fields">
          {#each fields.filter(field => field.area === 'advanced') as field}
            <Field {field} idPrefix={panel.id} bind:value={values[field.key]} busy={panel.busy} />
          {/each}
        </div></section>
      </div>
    </section>
  {/if}

  {#if panel.spec.chat_engine === 'pi'}<PiStatus {panel} />{/if}
  <div class="conversation-bar">
    <div class="conversation-picker"><Block allow_overflow={true}><BaseDropdown label="本次启动的对话" show_label={false}
      value={root} choices={roots.map((node, index) => [`${index + 1}. ${node.label ?? node.content.slice(0,45)}`, node.id])}
      interactive={!panel.busy} filterable={false} placeholder="新对话"
      on_change={id => {if (id && id !== root) act('chat_select', {node:id});}} /></Block></div>
    <span>{path.filter(node => node.role === 'user').length} 轮对话 · {panel.metadata.输入模态 || '流式输出'}</span>
    {#if selected}<BaseButton size="sm" disabled={panel.busy} onclick={() => retry()}>重新生成{selected.id !== lastAnswer?.id ? `第 ${Math.floor(path.indexOf(selected) / 2) + 1} 轮` : ''}</BaseButton>{/if}
  </div>
  {#if branches.length}<div class="branch-bar" aria-label="聊天分支">
    {#each branches as branch}
      {@const current = branch.siblings.indexOf(branch.node.id)}
      <div class="branch-control"><span>第 {Math.floor(branch.index / 2) + 1} 轮{branch.node.role === 'user' ? '提问' : '回答'}</span>
        <BaseButton size="sm" disabled={panel.busy || current === 0}
          onclick={() => act('chat_select', {node:branch.siblings[current - 1]})}>‹</BaseButton>
        <span>{current + 1} / {branch.siblings.length}</span>
        <BaseButton size="sm" disabled={panel.busy || current === branch.siblings.length - 1}
          onclick={() => act('chat_select', {node:branch.siblings[current + 1]})}>›</BaseButton>
      </div>
    {/each}
  </div>{/if}

  <div class="transcript" role="region" aria-label="聊天记录" tabindex="0" bind:this={scrollPane} use:followTail={{key:chat.active,active,onChange:value => following = value}}>
   <div class="conversation-content">
    {#if active}
    <BaseChatBot value={messages} {i18n} _fetch={fetch} load_component={() => ({component:Promise.resolve({default:ChatImages})})} theme_mode="light" render_markdown={true}
      sanitize_html={true} line_breaks={true} latex_delimiters={[{left:'$$',right:'$$',display:true},{left:'\\(',right:'\\)',display:false}]}
      display_consecutive_in_same_bubble={false} layout="bubble" autoscroll={false} show_copy_button={true}
      generating={panel.busy} pending_message={panel.busy && panel.phase === 'queued'}
      editable={panel.busy ? null : 'user'} _retryable={!panel.busy} selectable={true}
      feedback_options={[]} allow_file_downloads={true} show_copy_all_button={false}
      placeholder={'### 开始对话\n输入消息，上传、粘贴或拖入图片。历史提问可编辑并创建分支。'}
      onselect={data => selectedMessage = path[nodeIndex(data.index)].id}
      onedit={data => act('chat_edit', {node:path[nodeIndex(data.index)].id, text:data.value, params:{...values}})}
      onretry={data => retry(path[nodeIndex(data.index)])} onclear={() => {if (!panel.busy) act('chat_new');}} />
    {/if}
   </div>
  </div>

  <div class="chat-bottom">
    {#if !following}<div class="jump"><BaseButton size="sm" onclick={() => scrollPane.scrollTo({top:scrollPane.scrollHeight,behavior:'smooth'})}>回到最新</BaseButton></div>{/if}
    {#if panel.busy || panel.phase === 'error'}<div class="chat-status"><p role="status">{panel.message}</p><span>
      {panel.metadata.每秒tokens ? `${panel.metadata.每秒tokens} tokens/s · ` : ''}{panel.metadata.输出tokens ? `${panel.metadata.输出tokens} tokens` : ''}
    </span></div>{/if}
    {#if attachments.length}<div class="attachments" aria-label="待发送图片">
      {#each attachments as image (image.id)}<figure><img src={image.url} alt={image.name} /><figcaption>{image.name}</figcaption>
        <button class="remove-image" aria-label={'移除图片 '+image.name} onclick={() => attachments = attachments.filter(item => item.id !== image.id)}>×</button>
      </figure>{/each}
    </div>{/if}
    <div class="composer" onpastecapture={event => {
      if (panel.spec.images && [...event.clipboardData.files].some(file => file.type.startsWith('image/'))) {
        event.preventDefault();addImages(event.clipboardData.files);
      }
    }} onkeypresscapture={event => {
      if (event.key === 'Enter' && !event.isComposing) {
        event.stopPropagation();
        if (!event.shiftKey) {event.preventDefault(); submit();}
      }
    }}>
      {#if panel.spec.images}<button class="attach-button" aria-label="上传图片" title="上传图片，也可粘贴或拖入多张图片" onclick={() => imageInput.click()}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m8 12 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l9-9a7 7 0 0 1 10 10L12 22" /></svg>
      </button>{/if}
      <Block><BaseTextbox label="消息" show_label={false} bind:value={input} lines={3} max_lines={3}
        placeholder={panel.spec.images ? '发送消息，粘贴或拖入图片…' : '发送消息…'} disabled={panel.busy} onsubmit={submit} /></Block>
      {#if panel.busy}<BaseButton variant="stop" onclick={() => act('cancel')}>停止</BaseButton>
      {:else}<BaseButton variant="primary" disabled={(!input.trim() && !attachments.length) || readingImages || panel.spec.ready === false} onclick={submit}>发送</BaseButton>{/if}
    </div>
    <input type="file" accept="image/*" multiple hidden aria-label="选择聊天图片" bind:this={imageInput}
      onchange={async () => {await addImages(imageInput.files);imageInput.value = '';}} />
    {#if readingImages}<p class="image-loading" role="status">正在读取图片…</p>{/if}
    <div class="chat-footnote"><span>Enter 发送 · Shift + Enter 换行 · 编辑历史提问可创建分支</span>
      <details class="runtime"><summary>运行信息</summary><p>{Object.entries(panel.metadata).map(([key,value]) => `${key} ${value}`).join(' · ')}</p></details>
    </div>
    {#if lastAnswer?.content && targets.length}
      <details class="transfer"><summary>将回答填入其他工作流</summary><div>
        <Block allow_overflow={true}><BaseDropdown label="发送到" show_label={false} bind:value={target}
          choices={targets.map(item => [item.label,item.value])} interactive={true} filterable={false} /></Block>
        <BaseButton size="sm" onclick={() => onTransfer(target, lastAnswer.content)}>填入参数</BaseButton>
      </div></details>
    {/if}
  </div>
</article>

<style>
  .chat-card{background:white;border:1px solid #dde2e8;border-radius:10px;overflow:visible;min-width:0;display:flex;flex-direction:column;height:calc(100dvh - 124px);min-height:400px;}
  .chat-card.dragging{outline:2px dashed #d9925c;outline-offset:-4px;}
  .drop-hint{position:absolute;left:50%;top:35%;transform:translateX(-50%);z-index:80;background:#26364ce8;color:#fff;padding:14px 22px;border-radius:8px;pointer-events:none;}
  .chat-toolbar,.conversation-bar,.branch-bar,.chat-bottom{flex-shrink:0;}
  .chat-card:has(.settings){height:auto;}
  .chat-card:has(.settings) .transcript{height:380px;flex:none;}
  .chat-toolbar,.conversation-bar,.branch-bar,.branch-control,.chat-status,.composer,.chat-footnote{display:flex;align-items:center;gap:10px;}
  .chat-toolbar{padding:12px 18px;border-bottom:1px solid #e9ebef;}
  .model-choice{flex:1;min-width:200px;}
  .model-choice :global(.block){padding:3px 10px;}
  .preparation{display:block;font-size:11px;color:#8b6a48;margin-top:4px;}
  .more{position:relative;font-size:12px;color:#747e8c;}
  summary{cursor:pointer;white-space:nowrap;}
  .more>div{position:absolute;right:0;top:25px;z-index:50;display:grid;gap:6px;width:150px;padding:10px;background:white;border:1px solid #e0e4e9;border-radius:8px;box-shadow:0 8px 25px #182b4914;}
  .settings{padding:16px 18px;background:#f8f9fb;border-bottom:1px solid #e9ebef;}
  .setting-groups{display:grid;grid-template-columns:1fr 1.5fr 1fr 1.5fr;gap:16px;margin-top:12px;}
  h3{font-size:11px;font-weight:650;color:#687383;margin-bottom:8px;}
  .settings-fields{display:grid;gap:8px;}
  .conversation-bar{padding:10px 18px;font-size:11px;color:#89929f;}
  .conversation-picker{width:370px;max-width:50%;}
  .conversation-picker :global(.block){border:0;padding:0;background:transparent;}
  .conversation-bar>span{margin-left:auto;}
  .branch-bar{padding:0 18px 8px;flex-wrap:wrap;border-bottom:1px solid #eff1f4;}
  .branch-control{gap:6px;font-size:11px;color:#6b7788;}
  .branch-control :global(button){padding:2px 8px;min-width:0;}
  .transcript{height:0;min-height:160px;flex:1;position:relative;overflow:auto;overflow-anchor:none;overscroll-behavior:contain;padding:0 28px;max-width:1250px;margin:0 auto;width:100%;box-sizing:border-box;}
  .transcript :global(.bubble-wrap){background:white;height:auto;overflow:visible;}
  .jump{display:flex;justify-content:center;padding-bottom:5px;}
  .transcript :global(.message-wrap){padding:8px 0;}
  .transcript :global(.prose.chatbot.md){opacity:1;line-height:1.75;font-size:14px;}
  .chat-bottom{padding:0 22px 13px;max-width:1250px;margin:auto;width:100%;box-sizing:border-box;}
  .chat-status{justify-content:space-between;color:#7d8796;font-size:11px;line-height:1.6;min-height:32px;}
  .chat-status p{overflow-wrap:anywhere;max-height:80px;overflow:auto;}
  .chat-status>span{white-space:nowrap;}
  .composer{align-items:stretch;}
  .composer :global(.block){flex:1;min-width:0;background:#fafbfc;border-radius:9px;padding:8px 12px;}
  .composer :global(textarea){font-size:14px;line-height:1.6;}
  .composer :global(button){width:75px;}
  .composer button.attach-button{flex:none;align-self:flex-end;width:34px;height:38px;min-width:0;padding:7px;color:#7d8999;background:transparent;border:0;border-radius:6px;cursor:pointer;}
  .attach-button:hover{background:#eef1f5;}
  .attach-button svg{width:20px;height:20px;}
  .attachments{display:flex;gap:7px;overflow-x:auto;padding:7px 0;}
  .attachments figure{position:relative;flex:none;margin:0;width:78px;height:70px;border:1px solid #e1e6ed;border-radius:6px;overflow:hidden;background:#f4f6f8;}
  .attachments img{width:100%;height:100%;object-fit:cover;}
  .attachments figcaption{position:absolute;bottom:0;left:0;right:0;background:#243249a6;color:#fff;font-size:9px;white-space:nowrap;text-overflow:ellipsis;overflow:hidden;padding:2px 4px;}
  .remove-image{position:absolute;right:2px;top:2px;width:20px;height:20px;min-width:0;padding:0;border:0;border-radius:50%;background:#243249c9;color:#fff;cursor:pointer;font-size:16px;}
  .image-loading{font-size:11px;color:#7d8999;margin:5px 0;}
  .transcript :global(.component-wrap){width:min(620px,92%);max-width:92%;}
  .chat-footnote{justify-content:space-between;margin-top:8px;font-size:10px;color:#9aa2ad;}
  .runtime{position:relative;}
  .runtime p{position:absolute;bottom:25px;right:0;width:340px;padding:12px;background:#f8f9fb;border:1px solid #e1e5eb;border-radius:8px;font-size:11px;line-height:1.8;color:#667383;z-index:10;}
  .transfer{font-size:11px;color:#778494;margin-top:10px;}
  .transfer>div{display:flex;gap:8px;margin-top:7px;}
  .transfer :global(.block){flex:1;}
  @media(max-width:1000px){.setting-groups{grid-template-columns:1fr 1fr}.chat-toolbar{flex-wrap:wrap}.transcript{padding:0 14px}.conversation-bar>span{display:none}}
  @media(max-width:650px){
    .chat-card{height:calc(100dvh - 112px);min-height:400px;border-radius:7px;}
    .model-choice{width:100%;flex:auto;min-width:0;}
    .chat-toolbar{padding:6px 9px;gap:6px;}
    .chat-toolbar :global(button){font-size:12px;min-height:32px;}
    .model-choice :global(.block){padding:2px 7px;}
    .conversation-bar{padding:4px 9px;gap:6px;}
    .conversation-picker{flex:1;max-width:100%;width:auto;}
    .conversation-bar>button{font-size:11px;}
    .transcript{padding:0 8px;min-height:140px;}
    .transcript :global(.message-buttons){margin:0;}
    .transcript :global(.prose.chatbot.md){font-size:15px;line-height:1.65;}
    .chat-bottom{padding:4px 9px max(7px,env(safe-area-inset-bottom));}
    .composer :global(.block){padding:5px 8px;}
    .composer :global(textarea){font-size:16px;}
    .composer :global(button){width:56px;font-size:14px;}
    .chat-footnote{margin-top:3px;}
    .chat-footnote>span{display:none;}
    .chat-footnote .runtime{margin-left:auto;}
    .branch-bar{padding:0 9px 4px;}
    .settings{padding:10px;}
    .setting-groups{gap:10px;}
    .transfer{margin-top:3px;}
  }
</style>
