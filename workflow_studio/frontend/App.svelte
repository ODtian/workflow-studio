<script>
  import {onMount, untrack} from 'svelte';
  import {Button} from '$lib/components/ui/button';
  import {Badge} from '$lib/components/ui/badge';
  import {MessageSquare, Image, FolderOpen, Settings2, ArrowUpRight, Plus, RefreshCw, Upload, PanelLeftClose, PanelLeftOpen} from '@lucide/svelte';
  import Dropdown from './ui/Dropdown.svelte';
  import WorkflowView from './WorkflowView.svelte';
  import ChatView from './ChatView.svelte';
  import FilesView from './FilesView.svelte';
  import {download, downloadBuffer} from './bridge.js';
  import {filesForModel, bindingFromValues, parameterFields, fieldValue} from './modelBindings.js';

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
  let submittedSettingsSnapshot = '';
  let settingsRequest = '';
  let toolsOpen = $state(false);
  let sidebarOpen = $state(true);
  let mobile = $state(false);
  let pi = $state({});
  const piVersions = new Map();
  let activePanel = $derived(state.panels.find(p=>p.id===activeId));
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
            drafts[panel.id] = {...values, ...filesForModel(modelBindings, modelName, fields, parameterFields(panel.spec, modelName))};
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
    if (!settingsReady || snapshot === submittedSettingsSnapshot) return;
    settingsNotice = '正在保存设置…';
    const timer = setTimeout(() => {
      submittedSettingsSnapshot = snapshot;
      settingsRequest = crypto.randomUUID();
      send('settings', {...JSON.parse(snapshot), request:settingsRequest});
    }, 400);
    return () => clearTimeout(timer);
  });

  function updateState() {
    const next = model.get('state');
    if (next.settings_result?.request === settingsRequest) {
      settingsNotice = next.settings_result.error ? '设置保存失败' : '设置已保存';
    }
    for (const panel of next.panels) {
      if (panel.pi && piVersions.get(panel.id)!==JSON.stringify(panel.pi)) {
        piVersions.set(panel.id,JSON.stringify(panel.pi));
        pi[panel.id] = panel.pi;
      }
      const version = JSON.stringify(panel.spec);
      if (specs[panel.id] !== version) {
        const saved = drafts[panel.id] || panel.params;
        const modelField = panel.spec.fields.find(field => field.key === 'model');
        const selectedModel = modelField ? fieldValue(modelField, saved.model ?? modelField.default) : '';
        drafts[panel.id] = Object.fromEntries(parameterFields(panel.spec, selectedModel).map(field => {
          return [field.key, fieldValue(field, saved[field.key] ?? field.default ?? '')];
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
    transferNotice = '已填入';
  }

  onMount(() => {
    const compact = window.matchMedia('(max-width:760px), (max-width:1000px) and (max-height:500px)');
    const updateCompact = () => mobile = compact.matches;
    updateCompact();
    compact.addEventListener('change', updateCompact);
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
      if (msg.type === 'pi_event') {
        const current=pi[msg.id] || {messages:[]};
        let messages=[...(current.messages || [])];
        const event=msg.event;
        if(event.type==='message_start') messages.push(event.message);
        if(event.type==='message_update') messages[messages.length-1]=event.message;
        if(event.type==='message_end') messages[messages.length-1]=event.message;
        pi[msg.id]={...current,messages,event};
      }
      if (msg.type === 'pi_export') download(msg.name,msg.source,'application/jsonl');
      if (msg.type === 'pi_skill') pi[msg.id]={...pi[msg.id],editingSkill:{path:msg.path,source:msg.source}};
      if (msg.type === 'pi_skill_saved') pi[msg.id]={...pi[msg.id],skillSave:msg};
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
    };
    model.on('change:state', updateState);
    model.on('change:previews', updatePreviews);
    model.on('change:texts', updateTexts);
    model.on('change:results', updateResults);
    model.on('change:histories', updateHistories);
    model.on('change:chats', updateChats);
    model.on('change:files', updateFiles);
    model.on('msg:custom', custom);
    submittedSettingsSnapshot = settingsSnapshot;
    settingsReady = true;
    return () => {
      compact.removeEventListener('change', updateCompact);
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

<main class="studio" class:expanded class:nav-closed={!sidebarOpen}>
  <aside class="app-sidebar">
    <nav aria-label="工作空间导航">
      {#each state.panels as panel (panel.id)}
        <button class:active={activeId===panel.id} onclick={()=>{activeId=panel.id;toolsOpen=false;}}>
          {#if panel.spec.chat}<MessageSquare size={17}/>{:else}<Image size={17}/>{/if}
          <span>{panel.spec.chat?'Pi 对话':panel.spec.tab_name || panel.spec.name.split(' · ')[0]}</span>
          {#if panel.busy}<i class="status-dot pulse"></i>{/if}
        </button>
      {/each}
      <button class:active={activeId==='__files__'} onclick={()=>{activeId='__files__';toolsOpen=false;}}><FolderOpen size={17}/><span>文件与传输</span></button>
    </nav>
    <div class="sidebar-bottom"><button class:active={toolsOpen} onclick={()=>toolsOpen=!toolsOpen}><Settings2 size={17}/>工作流管理</button></div>
  </aside>
  <div class="app-main">
    <header class="app-topbar">
      <Button class="sidebar-toggle" variant="ghost" size="icon" aria-label="切换侧栏" onclick={()=>sidebarOpen=!sidebarOpen}>{#if sidebarOpen}<PanelLeftClose size={17}/>{:else}<PanelLeftOpen size={17}/>{/if}</Button>
      <div class="breadcrumb"><strong>{toolsOpen?'工作流管理':activeId==='__files__'?'文件与传输':activePanel?.spec.chat?'Pi 对话':activePanel?.spec.tab_name || '生成工作台'}</strong></div>
      <nav class="mobile-navigation" aria-label="手机工作空间导航">
        {#each state.panels as panel (panel.id)}
          <button class:active={!toolsOpen&&activeId===panel.id} aria-current={!toolsOpen&&activeId===panel.id?'page':undefined} onclick={()=>{activeId=panel.id;toolsOpen=false;}}>
            <span>{panel.spec.chat?'对话':panel.spec.tab_name || panel.spec.name.split(' · ')[0]}</span>{#if panel.busy}<i class="status-dot pulse"></i>{/if}
          </button>
        {/each}
        <button class:active={!toolsOpen&&activeId==='__files__'} aria-current={!toolsOpen&&activeId==='__files__'?'page':undefined} onclick={()=>{activeId='__files__';toolsOpen=false;}}>文件</button>
        <button class:active={toolsOpen} aria-current={toolsOpen?'page':undefined} onclick={()=>toolsOpen=!toolsOpen}>管理</button>
      </nav>
      <div class="topbar-right">{#if activePanel?.busy}<Badge variant="secondary">运行中</Badge>{:else if settingsNotice==='正在保存设置…'}<span class="saved-label">{settingsNotice}</span>{/if}<Button size="sm" variant="outline" aria-label={expanded?'返回 notebook':'展开工作台'} title={expanded?'返回 notebook':'展开工作台'} onclick={()=>expanded=expand()}><span class="return-label">{expanded?'返回 notebook':'展开工作台'}</span><ArrowUpRight size={13}/></Button></div>
    </header>
    {#if state.message}<div class="app-notice" role="status">{state.message}</div>{/if}
    {#if transferNotice}<button class="app-notice" onclick={()=>transferNotice=''}>{transferNotice} ×</button>{/if}
    <div class="app-content">
      {#if toolsOpen}
        <section class="management page-padding">
          <div class="surface management-add"><Dropdown label="可用工作流" show_label={false} bind:value={addWorkflow} choices={state.workflows.map(w=>[w.name,w.id])}/><Button disabled={!addWorkflow} onclick={()=>send('add',{workflow:addWorkflow})}><Plus size={15}/>添加</Button><Button variant="outline" onclick={()=>send('refresh')}><RefreshCw size={15}/>刷新</Button><Button variant="outline" onclick={()=>codeInput.click()}><Upload size={15}/>导入 Python</Button></div>
          <div class="workflow-list">{#each state.panels as panel}<div class="surface workflow-row"><div class="workflow-name"><h3 title={panel.selected}>{panel.spec.name}</h3></div>{#if panel.busy}<Badge variant="secondary">运行中</Badge>{/if}<Button variant="outline" onclick={()=>send('export',{id:panel.id})}>导出</Button><Button variant="ghost" disabled={panel.busy} onclick={()=>send('remove',{id:panel.id})}>移除</Button></div>{/each}</div>
        </section>
      {/if}
      {#each state.panels as panel (panel.id)}
        <section class="panel-page" hidden={toolsOpen || activeId!==panel.id}>
          {#if panel.spec.chat}
            <ChatView {panel} {mobile} active={activeId===panel.id && pageVisible} bind:values={drafts[panel.id]} pi={pi[panel.id] || {messages:[]}} {send} targets={targetsFor(panel)} onTransfer={transfer}/>
          {:else}
            <WorkflowView {panel} bind:values={drafts[panel.id]} preview={previews[panel.id]||''} text={texts[panel.id]||''} results={results[panel.id]||[]} {send} history={histories[panel.selected]||[]} loadThumbnail={r=>loadThumbnail(panel.id,r)} loadPreview={r=>loadPreview(panel.id,r)} targets={targetsFor(panel)} onTransfer={transfer} loadOriginal={r=>loadOriginal(panel.id,r)}/>
          {/if}
        </section>
      {/each}
      <section class="panel-page" hidden={toolsOpen || activeId!=='__files__'}><FilesView {files} {send}/></section>
    </div>
  </div>
  <input type="file" accept=".py" hidden bind:this={codeInput} onchange={async()=>{const file=codeInput.files[0];if(file)send('import',{name:file.name,source:await file.text()});codeInput.value='';}}/>
</main>
