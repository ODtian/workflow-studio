<script>
  import {onMount, untrack} from 'svelte';
  import {Block} from '@gradio/atoms';
  import {BaseButton} from '@gradio/button';
  import {BaseDropdown} from '@gradio/dropdown';
  import {BaseTabs} from '@gradio/tabs';
  import {BaseTabItem} from '@gradio/tabitem';
  import WorkflowView from './WorkflowView.svelte';
  import ChatView from './ChatView.svelte';
  import FilesView from './FilesView.svelte';
  import {download, downloadBuffer} from './bridge.js';
  import {filesForModel, bindingFromValues} from './modelBindings.js';

  let {model, expand, initialExpanded = true} = $props();
  let state = $state(model.get('state'));
  let previews = $state({});
  const previewData = new Map();
  const previewURLs = new Map();
  const originalImages = new Map();
  const thumbnailImages = new Map();
  const comparisonImages = new Map();
  const comparisonPending = new Map();
  const imageRequests = new Map();
  let imageRequestId = 0;
  let texts = $state(model.get('texts'));
  let results = $state(model.get('results'));
  let histories = $state(model.get('histories') || {});
  let chats = $state(model.get('chats') || {});
  const chatResponses = new Map();
  let pageVisible = $state(!document.hidden);
  let files = $state(model.get('files') || {});
  let drafts = $state({});
  let specs = {};
  let modelBindings = $state(state.model_bindings || {});
  const bindingModels = new Map();
  let addWorkflow = $state('');
  let expanded = $state(initialExpanded);
  let transferNotice = $state('');
  let activeId = $state('');
  let settingsReady = $state(false);
  let settingsNotice = $state('设置已保存');
  let toolsOpen = $state(false);
  let codeInput;
  const send = (action, data = {}) => model.send({action, ...data});
  function loadOriginal(id, result) {
    if (originalImages.has(result.name)) return Promise.resolve(originalImages.get(result.name));
    return new Promise(resolve => {
      const request = ++imageRequestId;
      imageRequests.set(request, resolve);
      send('image_detail', {id,name:result.name,request});
    });
  }
  function loadThumbnail(id, result) {
    if (thumbnailImages.has(result.name)) return Promise.resolve(thumbnailImages.get(result.name));
    return new Promise(resolve => {
      const request = ++imageRequestId;
      imageRequests.set(request, resolve);
      send('image_thumbnail', {id,name:result.name,request});
    });
  }
  function loadPreview(id, result) {
    if (comparisonImages.has(result.name)) return Promise.resolve(comparisonImages.get(result.name));
    if (comparisonPending.has(result.name)) return comparisonPending.get(result.name);
    const promise = new Promise(resolve => {
      const request = ++imageRequestId;
      imageRequests.set(request, resolve);
      send('image_preview', {id,name:result.name,request});
    });
    comparisonPending.set(result.name, promise);
    return promise;
  }
  const tabLabel = panel => (panel.spec.tab_name || panel.spec.name.split(' · ')[0]) + (panel.busy ? ' · 运行中' : '');
  let tabs = $derived([{label:'文件',id:'__files__',elem_id:undefined,visible:true,interactive:true,scale:0,component_id:0},
    ...state.panels.map((panel, index) => ({label:tabLabel(panel), id:panel.id,
      elem_id:undefined, visible:true, interactive:true, scale:0, component_id:index+1}))]);
  let settingsSnapshot = $derived(JSON.stringify({active:activeId, model_bindings:modelBindings, panels:state.panels.map(panel => ({
    id:panel.id, params:Object.fromEntries(panel.spec.fields
      .filter(field => field.persist ?? (field.area !== 'prompts' && field.type !== 'image'))
      .map(field => [field.key,drafts[panel.id]?.[field.key] ?? field.default ?? '']))
  }))}));
  $effect(() => {
    for (const panel of state.panels) {
      const fields = panel.spec.model_binding_fields;
      const values = drafts[panel.id];
      if (!fields || !values?.model) continue;
      const modelName = values.model;
      const selected = bindingFromValues(values, fields);
      untrack(() => {
        const previous = bindingModels.get(panel.id);
        if (previous !== modelName) {
          bindingModels.set(panel.id, modelName);
          if (previous === undefined && !modelBindings[modelName]) {
            modelBindings = {...modelBindings, [modelName]:selected};
          } else {
            drafts[panel.id] = {...values, ...filesForModel(modelBindings, modelName, fields)};
          }
        } else if (JSON.stringify(modelBindings[modelName]) !== JSON.stringify(selected)) {
          modelBindings = {...modelBindings, [modelName]:selected};
        }
      });
    }
  });

  let preparation = $derived.by(() => {
    const panel = state.panels.find(panel => panel.id === activeId);
    if (!panel?.spec.prepare_fields || panel.spec.ready === false || panel.busy) return '';
    const params = Object.fromEntries(panel.spec.prepare_fields.map(key => [key,drafts[panel.id]?.[key]]));
    return JSON.stringify({id:panel.id,params});
  });
  let chatVisibility = $derived(JSON.stringify(state.panels.filter(panel => panel.spec.chat)
    .map(panel => ({id:panel.id,visible:panel.id === activeId && pageVisible}))));

  $effect(() => {
    const panels = chatVisibility;
    if (settingsReady) send('chat_visibility', {panels:JSON.parse(panels)});
  });

  $effect(() => {
    const request = preparation;
    if (!settingsReady || !request) return;
    const timer = setTimeout(() => send('prepare', JSON.parse(request)), 500);
    return () => clearTimeout(timer);
  });

  function applyChatResponse(id, node) {
    const chat = chats[id];
    if (chat?.nodes[node.id]) chats[id] = {...chat,nodes:{...chat.nodes,[node.id]:node}};
  }
  $effect(() => {
    const id = activeId;
    const visible = pageVisible;
    const ready = settingsReady;
    if (ready && visible && state.panels.find(panel => panel.id === id)?.spec.chat) {
      untrack(() => {
        if (chatResponses.has(id)) applyChatResponse(id, chatResponses.get(id));
        send('chat_sync', {id});
      });
    }
  });

  $effect(() => {
    const snapshot = settingsSnapshot;
    if (!settingsReady) return;
    settingsNotice = '正在保存设置…';
    const timer = setTimeout(() => send('settings', JSON.parse(snapshot)), 400);
    return () => clearTimeout(timer);
  });

  function updateState() {
    const next = model.get('state');
    for (const panel of next.panels) {
      const version = JSON.stringify(panel.spec);
      if (specs[panel.id] !== version) {
        const saved = drafts[panel.id] || panel.params;
        drafts[panel.id] = Object.fromEntries(panel.spec.fields.map(field => {
          let value = saved[field.key] ?? field.default ?? '';
          if (field.area === 'models' && field.type === 'select' && !value) value = field.default ?? '';
          return [field.key, value];
        }));
        specs[panel.id] = version;
      }
    }
    if (!activeId) activeId = next.active || '';
    if (next.panels.length > state.panels.length) activeId = next.panels.at(-1).id;
    if (activeId !== '__files__' && !next.panels.some(panel => panel.id === activeId)) activeId = next.panels[0]?.id || '__files__';
    state = next;
    if (!addWorkflow) addWorkflow = next.workflows[0]?.id || '';
  }
  updateState();

  function updatePreviews() {
    const current = model.get('previews') || {};
    for (const [id,source] of Object.entries(current)) {
      if (previewData.get(id) === source) continue;
      if (previewURLs.get(id)?.startsWith('blob:')) URL.revokeObjectURL(previewURLs.get(id));
      previewData.set(id,source);
      previewURLs.set(id,typeof source === 'string' ? source : URL.createObjectURL(new Blob([source],{type:'image/jpeg'})));
    }
    for (const id of previewData.keys()) {
      if (!(id in current)) {
        if (previewURLs.get(id)?.startsWith('blob:')) URL.revokeObjectURL(previewURLs.get(id));
        previewData.delete(id);previewURLs.delete(id);
      }
    }
    previews = Object.fromEntries(previewURLs);
  }
  updatePreviews();

  function targetsFor(panel) {
    return state.panels.filter(p => p.id !== panel.id && !p.busy).flatMap(p =>
      p.spec.fields.filter(f => ['text', 'textarea'].includes(f.type))
        .map(f => ({label:`${p.spec.name} · ${f.label}`, value:`${p.id}:${f.key}`})));
  }
  function transfer(target, text) {
    const [id, key] = target.split(':');
    drafts[id] = {...drafts[id], [key]:text};
    activeId = id;
    transferNotice = '文本已填入目标工作流，可继续编辑或生成。';
  }

  onMount(() => {
    const scanModels = () => {if (!document.hidden) send('scan_models');};
    const visibility = () => {pageVisible = !document.hidden;scanModels();};
    const modelTimer = setInterval(scanModels, 5000);
    document.addEventListener('visibilitychange', visibility);
    scanModels();
    const updateTexts = () => texts = model.get('texts');
    const updateResults = () => {
      results = model.get('results');
    };
    const updateHistories = () => histories = model.get('histories');
    const updateChats = () => {
      chats = {...model.get('chats')};
      for (const [id,node] of chatResponses) {
        if (chats[id]?.nodes[node.id]?.status === 'pending') applyChatResponse(id,node);
        else chatResponses.delete(id);
      }
    };
    const updateFiles = () => files = model.get('files');
    const custom = (msg, buffers) => {
      if (msg.type === 'chat_delta') {
        chatResponses.set(msg.id, msg.node);
        if (msg.id === activeId && pageVisible) applyChatResponse(msg.id,msg.node);
      }
      if (msg.type === 'chat_snapshot') {
        chats[msg.id] = msg.chat;
        chatResponses.delete(msg.id);
      }
      if (msg.type === 'workflow') download(msg.name, msg.source);
      if (msg.type === 'download') downloadBuffer(msg.name, buffers[0], msg.mime);
      if (['image_detail','image_thumbnail','image_preview'].includes(msg.type)) {
        const thumbnail = msg.type === 'image_thumbnail';
        const comparison = msg.type === 'image_preview';
        const image = {url:URL.createObjectURL(new Blob([buffers[0]], {type:thumbnail || comparison ? 'image/jpeg' : 'image/png'}))};
        (comparison ? comparisonImages : thumbnail ? thumbnailImages : originalImages).set(msg.name, image);
        if (comparison) comparisonPending.delete(msg.name);
        imageRequests.get(msg.request)(image);
        imageRequests.delete(msg.request);
      }
      if (msg.type === 'settings_saved') settingsNotice = '设置已保存';
    };
    model.on('change:state', updateState);
    model.on('change:previews', updatePreviews);
    model.on('change:texts', updateTexts);
    model.on('change:results', updateResults);
    model.on('change:histories', updateHistories);
    model.on('change:chats', updateChats);
    model.on('change:files', updateFiles);
    model.on('msg:custom', custom);
    settingsReady = true;
    return () => {
      clearInterval(modelTimer);
      document.removeEventListener('visibilitychange', visibility);
      model.off('change:state', updateState);
      model.off('change:previews', updatePreviews);
      model.off('change:texts', updateTexts);
      model.off('change:results', updateResults);
      model.off('change:histories', updateHistories);
      model.off('change:chats', updateChats);
      model.off('change:files', updateFiles);
      model.off('msg:custom', custom);
      for (const url of previewURLs.values()) if (url.startsWith('blob:')) URL.revokeObjectURL(url);
      for (const image of originalImages.values()) URL.revokeObjectURL(image.url);
      for (const image of thumbnailImages.values()) URL.revokeObjectURL(image.url);
      for (const image of comparisonImages.values()) URL.revokeObjectURL(image.url);
    };
  });
</script>

<main class="gradio-container gradio-style" class:expanded>
  <header>
    <BaseButton size="sm" onclick={() => toolsOpen = !toolsOpen}>工作流管理</BaseButton>
    {#if settingsNotice !== '设置已保存'}<span class="settings-notice" role="status">{settingsNotice}</span>{/if}
    <BaseButton size="sm" onclick={() => {expanded = expand();}}>{expanded ? '返回 notebook' : '展开工作台'}</BaseButton>
  </header>
  {#if toolsOpen}
  <div class="composition-toolbar">
    <div class="workflow-picker"><Block allow_overflow={true}><BaseDropdown label="添加工作流" show_label={false}
      bind:value={addWorkflow} interactive={true} filterable={false} choices={state.workflows.map(w => [w.name,w.id])} /></Block></div>
    <BaseButton size="sm" variant="primary" disabled={!addWorkflow} onclick={() => send('add', {workflow:addWorkflow})}>添加工作流</BaseButton>
    <BaseButton size="sm" onclick={() => send('refresh')}>刷新工作流</BaseButton>
    <div class="toolbar-end"><BaseButton size="sm" onclick={() => codeInput.click()}>导入工作流</BaseButton></div>
  </div>
  {/if}
  {#if state.message}<p class="notice" role="status">{state.message}</p>{/if}
  {#if transferNotice}<p class="notice" role="status">{transferNotice}</p>{/if}
  <div class="workflow-tabs">
    <BaseTabs bind:selected={activeId} initial_tabs={tabs} overflow_behavior="menu">
      {#each state.panels as panel, index (panel.id)}
        <BaseTabItem label={tabLabel(panel)} id={panel.id} order={index+1} component_id={index+1} visible={true} interactive={true} scale={0}>
          {#if panel.spec.chat}
          <ChatView {panel} active={activeId === panel.id && pageVisible} bind:values={drafts[panel.id]} chat={chats[panel.id]} {send}
            targets={targetsFor(panel)} onTransfer={transfer} />
          {:else}
          <WorkflowView {panel} bind:values={drafts[panel.id]} preview={previews[panel.id] || ''}
            text={texts[panel.id] || ''} results={results[panel.id] || []} {send}
            history={histories[panel.selected] || []} loadThumbnail={result => loadThumbnail(panel.id, result)}
            loadPreview={result => loadPreview(panel.id, result)}
            targets={targetsFor(panel)} onTransfer={transfer} loadOriginal={result => loadOriginal(panel.id, result)} />
          {/if}
        </BaseTabItem>
      {/each}
      <BaseTabItem label="文件" id="__files__" order={0} component_id={0} visible={true} interactive={true} scale={0}>
        <FilesView {files} {send} />
      </BaseTabItem>
    </BaseTabs>
  </div>
  <input type="file" accept=".py" hidden bind:this={codeInput} onchange={async () => {
    const file = codeInput.files[0];
    if (file) send('import', {name:file.name, source:await file.text()});
    codeInput.value = '';
  }} />
</main>

<style>
  main {--block-label-background-fill:transparent;--block-label-text-color:#646d79;--block-label-margin:0;--block-label-padding:0;
    --block-padding:6px 10px;--block-radius:7px;--input-radius:5px;--layout-gap:10px;--input-padding:6px 8px;--input-border-width:0px;
    --input-background-fill:transparent;--input-text-size:13px;--block-label-text-size:12px;--block-label-text-weight:500;
    padding:0 26px;color:#252a32;background:#f6f7f9;font-size:13px;min-height:100%;}
  header,.composition-toolbar,.toolbar-end {display:flex;align-items:center;gap:10px;}
  header {min-height:44px;border-bottom:1px solid #e0e3e8;}
  header :global(button:last-child){margin-left:auto;}
  .settings-notice{font-size:11px;color:#788391;}
  .composition-toolbar {padding:14px 0;}
  .workflow-picker {width:280px;min-width:150px;}
  .workflow-picker :global(.block) {padding:3px 10px;}
  .toolbar-end {margin-left:auto;color:#8a929d;font-size:11px;}
  .notice {color:#727b87;font-size:12px;padding:0 0 12px;}
  .workflow-tabs :global(.tab-nav) {margin-bottom:14px;}
  .workflow-tabs :global(.tab-nav button) {font-size:13px;padding:12px 18px;}
  @media(min-width:1800px){main{padding:0 36px}}
  @media(max-width:650px){
    main{padding:0 7px;--input-text-size:16px;--block-label-text-size:12px;--input-padding:6px;}
    header{min-height:40px;gap:6px;}
    header :global(button){font-size:11px;padding:4px 7px;min-height:30px;}
    .composition-toolbar{flex-wrap:wrap;padding:8px 0;gap:6px;}
    .workflow-picker{flex:1;min-width:180px;}
    .toolbar-end{margin-left:0;}
    .workflow-tabs :global(.tab-nav){margin-bottom:7px;}
    .workflow-tabs :global(.tab-nav button){font-size:12px;padding:9px 10px;min-height:38px;}
  }
</style>
