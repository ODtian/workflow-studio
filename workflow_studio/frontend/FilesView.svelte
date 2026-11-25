<script>
  import {Button} from '$lib/components/ui/button';
  import {Input} from '$lib/components/ui/input';
  import {Progress} from '$lib/components/ui/progress';
  import * as Tabs from '$lib/components/ui/tabs';
  import {ArrowLeftRight, BookOpen, Cloud, HardDrive, History, Pencil, Play, Plus, Search, X} from '@lucide/svelte';
  import FilePane from './FilePane.svelte';
  import {bytes, taskStatus} from './fileFormat.js';

  let {files = {}, send} = $props();
  let tab = $state('transfer');
  let mobilePane = $state('local');
  let query = $state('');
  let editing = $state(false);
  let draft = $state({});
  const act = command => send('files', {command});

  let recipes = $derived(files.recipes || []);
  let shortcuts = $derived(recipes.toReversed().filter(item =>
    [item.label, item.local_path, item.drive_path, item.repo_id].join(' ').toLowerCase().includes(query.trim().toLowerCase())));
  let activeTasks = $derived((files.tasks || []).filter(task => ['running', 'queued'].includes(task.status)));
  let history = $derived((files.tasks || []).filter(task => !['running', 'queued'].includes(task.status)).toReversed());
  let hfDraft = $derived(draft.source_provider === 'huggingface');
  let canSave = $derived(!!draft.local_path?.trim() &&
    (hfDraft ? !!draft.hf_url?.trim() : !!draft.label?.trim() && !!draft.drive_path?.trim()));

  function editShortcut(record) {
    const source = record.hf_sources?.[0] || {};
    draft = {
      ...record,
      hf_url: record.hf_url || source.repo_id || record.repo_id || '',
      hf_revision: source.revision || 'main',
      hf_patterns: (source.allow_patterns || []).join(', ')
    };
    editing = true;
  }

  function addShortcut() {
    editShortcut({label: '', source_provider: 'huggingface', direction: 'download',
      source_kind: 'file', drive_path: '', local_path: files.model_directory || ''});
  }

  function saveShortcut(replay = false) {
    act({action: 'save_recipe', recipe: {...draft}, replay});
    editing = false;
  }

  function sourceLabel(task) {
    if (task.source === 'huggingface') return 'Hugging Face';
    if (task.direction === 'copy') return 'Drive 复制';
    return task.direction === 'download' ? 'Drive 下载' : '上传至 Drive';
  }

  const displayTime = new Intl.DateTimeFormat('zh-CN', {dateStyle: 'short', timeStyle: 'short'});
</script>

<article class="files-workspace" aria-label="文件传输">
  <Tabs.Root class="files-root" bind:value={tab}>
    <div class="view-bar">
      <Tabs.List variant="line" aria-label="文件与传输">
        <Tabs.Trigger value="transfer"><ArrowLeftRight size={15}/>传输</Tabs.Trigger>
        <Tabs.Trigger value="shortcuts"><BookOpen size={15}/>快捷复制</Tabs.Trigger>
        <Tabs.Trigger value="history"><History size={15}/>传输记录</Tabs.Trigger>
      </Tabs.List>
      {#if tab === 'shortcuts' && (recipes.length || editing)}
        <Button size="sm" onclick={addShortcut} disabled={editing}><Plus size={15}/>新增快捷复制</Button>
      {/if}
    </div>

    {#if files.error || files.message || files.notice || files.can_undo}
      <div class="file-notice" role="status">
        <span>{files.error || files.message || files.notice}</span>
        {#if files.can_undo}<Button size="sm" variant="outline" onclick={() => act({action: 'undo'})}>撤销删除</Button>{/if}
      </div>
    {/if}

    <Tabs.Content class="transfer-view" value="transfer">
      <nav class="pane-switch" aria-label="文件位置">
        <Button variant={mobilePane === 'drive' ? 'secondary' : 'ghost'} aria-pressed={mobilePane === 'drive'}
          onclick={() => mobilePane = 'drive'}><Cloud size={15}/>Google Drive</Button>
        <Button variant={mobilePane === 'local' ? 'secondary' : 'ghost'} aria-pressed={mobilePane === 'local'}
          onclick={() => mobilePane = 'local'}><HardDrive size={15}/>运行时</Button>
      </nav>
      <div class="transfer-panes" class:unmounted={!files.connected}>
        {#each ['drive', 'local'] as name (name)}
          <div class="pane-slot" class:mobile-hidden={mobilePane !== name}>
            <FilePane {name} pane={files.panes?.[name] || {}} target={files.panes?.[name === 'drive' ? 'local' : 'drive'] || {}}
              connected={files.connected} send={act}/>
          </div>
        {/each}
      </div>
    </Tabs.Content>

    <Tabs.Content class="files-list-view" value="shortcuts">
      {#if editing}
        <section class="shortcut-editor" aria-label="快捷复制设置">
          <div class="section-heading">
            <h2>{draft.id ? '编辑快捷复制' : '新增快捷复制'}</h2>
            <Button size="icon-sm" variant="ghost" aria-label="收起设置" onclick={() => editing = false}><X size={17}/></Button>
          </div>
          <div class="parameter-grid">
            <label class="field"><span>名称</span><Input bind:value={draft.label}/></label>
            <label class="field"><span>来源与方向</span>
              <select value={hfDraft ? 'huggingface' : draft.direction} onchange={event => {
                const value = event.currentTarget.value;
                draft.source_provider = value === 'huggingface' ? 'huggingface' : 'drive';
                draft.direction = value === 'upload' ? 'upload' : 'download';
              }}>
                <option value="huggingface">Hugging Face → 运行时</option>
                <option value="download">Drive → 运行时</option>
                <option value="upload">运行时 → Drive</option>
              </select>
            </label>
            {#if hfDraft}
              <label class="field wide"><span>HF 仓库或文件链接</span><Input placeholder="owner/repo" bind:value={draft.hf_url}/></label>
              <label class="field"><span>文件范围</span><Input placeholder="留空下载全部" bind:value={draft.hf_patterns}/></label>
              <label class="field"><span>版本</span><Input bind:value={draft.hf_revision}/></label>
              {#if draft.hf_sources?.length > 1}
                <div class="field wide"><span>配套来源</span>
                  {#each draft.hf_sources.slice(1) as source}
                    <code>{source.repo_id} · {source.allow_patterns?.join(', ') || '全部文件'}</code>
                  {/each}
                </div>
              {/if}
            {:else}
              <label class="field"><span>内容</span>
                <select bind:value={draft.source_kind}>
                  <option value="file">文件</option>
                  <option value="directory">文件夹（包含子目录）</option>
                </select>
              </label>
              <label class="field"><span>Drive 相对路径</span><Input bind:value={draft.drive_path} placeholder="model/文件名"/></label>
            {/if}
            <label class="field wide"><span>{draft.direction === 'upload' ? '运行时源路径' : '运行时目标目录'}</span>
              <Input bind:value={draft.local_path}/>
            </label>
          </div>
          <div class="editor-actions">
            {#if draft.id}
              <Button size="sm" variant="ghost" onclick={() => {act({action: 'delete_recipe', id: draft.id}); editing = false;}}>删除快捷复制</Button>
            {/if}
            <div class="row">
              <Button size="sm" variant={hfDraft ? 'outline' : 'default'} disabled={!canSave} onclick={() => saveShortcut()}>保存</Button>
              {#if hfDraft}<Button size="sm" disabled={!canSave} onclick={() => saveShortcut(true)}>保存并下载</Button>{/if}
            </div>
          </div>
        </section>
      {/if}

      {#if recipes.length}
        <label class="shortcut-search">
          <Search size={15}/><Input aria-label="搜索快捷复制" placeholder="搜索名称、来源或路径" bind:value={query}/>
        </label>
        <div class="records">
          {#each shortcuts as item (item.id)}
            {@const hf = item.source_provider === 'huggingface'}
            {@const missingPath = !hf && !item.drive_path}
            <div class="record">
              <div class="record-meta">
                <strong>{item.label}</strong>
                <p>{hf ? item.repo_id || item.hf_url : missingPath ? '需补齐 Drive 相对路径' : 'Drive · ' + item.drive_path}</p>
                <p class="record-path" title={item.local_path}>{item.local_path}</p>
              </div>
              <div class="record-actions">
                <Button size="sm" variant="ghost" aria-label={'编辑 ' + item.label} onclick={() => editShortcut(item)}><Pencil size={15}/>编辑</Button>
                <Button size="sm" variant="outline" disabled={missingPath || (!hf && !files.connected)}
                  onclick={() => act({action: 'replay', ids: [item.id]})}><Play size={14}/>{hf ? '下载' : '复制'}</Button>
              </div>
            </div>
          {:else}
            <div class="panel-empty">没有符合搜索条件的快捷项。</div>
          {/each}
        </div>
      {:else if !editing}
        <div class="panel-empty">
          <span class="empty-icon"><BookOpen size={21}/></span>
          <strong>暂无快捷复制</strong>
          <Button size="sm" onclick={addShortcut}><Plus size={15}/>新增快捷复制</Button>
        </div>
      {/if}
      {#if files.shortcut_storage === 'runtime'}
        <p class="storage-note">快捷项保存在当前运行时。挂载可写的 Drive 后，刷新 Drive 目录即可同步。</p>
      {/if}
    </Tabs.Content>

    <Tabs.Content class="files-list-view" value="history">
      {#if files.history_storage === 'memory'}
        <p class="storage-note" role="status">记录暂存在内存中。检查运行时可用空间后刷新目录。</p>
      {:else if files.history_storage === 'runtime'}
        <p class="storage-note">传输记录保存在当前运行时。挂载可写的 Drive 后，刷新 Drive 目录即可同步。</p>
      {/if}
      <div class="records">
        {#each history as task (task.id)}
          <div class="record">
            <div class="record-meta">
              <strong>{task.name}</strong>
              <p>{sourceLabel(task)}{#if task.bytes} · {bytes(task.bytes)}{/if}{#if task.finished_at} · {displayTime.format(task.finished_at * 1000)}{/if}</p>
              {#if task.target_path || task.local_path}<p class="record-path" title={task.target_path || task.local_path}>{task.target_path || task.local_path}</p>{/if}
              {#if task.error}<p class="error-text">{task.error}</p>{/if}
            </div>
            <div class="record-actions">
              <span class="record-status" class:completed={task.status === 'completed'}>{taskStatus[task.status]}</span>
              {#if ['failed', 'cancelled'].includes(task.status) && task.retryable}
                <Button size="sm" variant="outline" onclick={() => act({action: 'retry', task_id: task.id})}>重试</Button>
              {/if}
              <Button size="sm" variant="ghost" onclick={() => act({action: 'delete_task', id: task.id})}>删除记录</Button>
            </div>
          </div>
        {:else}
          <div class="panel-empty"><History size={23}/><strong>暂无传输记录</strong></div>
        {/each}
      </div>
    </Tabs.Content>
  </Tabs.Root>

  {#if activeTasks.length}
    <section class="transfer-queue" aria-label="正在传输">
      <h2>正在传输</h2>
      {#each activeTasks as task (task.id)}
        <div class="queue-record">
          <div class="row">
            <strong>{task.name}</strong>
            <small>{bytes(task.bytes)} / {bytes(task.total)}{task.speed ? ' · ' + bytes(task.speed) + '/s' : ''}</small>
            <Button size="sm" variant="ghost" onclick={() => act({action: 'cancel', task_id: task.id})}>停止</Button>
          </div>
          <Progress value={task.bytes} max={task.total || 1}/>
        </div>
      {/each}
    </section>
  {/if}
</article>

<style>
  .files-workspace {
    display: flex;
    flex-direction: column;
    width: 100%;
    max-width: 1450px;
    height: 100%;
    min-height: 0;
    padding: 11px 22px 18px;
    margin: auto;
  }
  .files-workspace :global(.files-root) { flex: 1; min-height: 0; gap: 12px; }
  .view-bar { min-height: 42px; border-bottom: 1px solid var(--border); }
  .view-bar, .file-notice, .section-heading, .editor-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .view-bar :global([data-slot="tabs-list"]) { padding: 0; height: 38px; }
  .view-bar :global([data-slot="tabs-trigger"]) { padding-inline: 10px; }
  .files-workspace :global(.transfer-view) { min-height: 0; display: flex; flex-direction: column; }
  .files-workspace :global(.files-list-view) { min-height: 0; overflow: auto; overscroll-behavior: contain; }
  .pane-switch { display: none; }
  .transfer-panes { flex: 1; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; min-height: 0; }
  .transfer-panes.unmounted { grid-template-columns: minmax(0, .76fr) minmax(0, 1.24fr); }
  .pane-slot { display: flex; min-width: 0; min-height: 0; }
  .shortcut-search { display: flex; align-items: center; gap: 9px; width: min(100%, 320px); margin-bottom: 12px; color: var(--muted-foreground); }
  .shortcut-search :global(svg) { flex-shrink: 0; }
  .records, .shortcut-editor {
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 10px;
  }
  .records { overflow: hidden; }
  .record { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 11px 14px; }
  .record + .record { border-top: 1px solid var(--border); }
  .record-meta { min-width: 0; flex: 1; }
  .record-meta strong { font-size: 13px; font-weight: 600; overflow-wrap: anywhere; }
  .record-meta p, .storage-note { font-size: 11px; color: var(--muted-foreground); margin: 3px 0 0; }
  .record-meta .record-path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .record-meta .error-text { color: var(--destructive); }
  .record-actions { display: flex; align-items: center; flex-shrink: 0; gap: 5px; }
  .record-status { color: var(--muted-foreground); font-size: 11px; padding: 2px 7px; border-radius: 4px; white-space: nowrap; background: var(--secondary); }
  .record-status.completed { color: var(--success); }
  .storage-note { margin: 6px 0 10px; }
  .panel-empty {
    min-height: 140px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 20px;
    color: var(--muted-foreground);
    text-align: center;
  }
  .panel-empty strong { color: var(--foreground); font-weight: 600; }
  .empty-icon { display: grid; place-items: center; border-radius: 9px; width: 40px; height: 40px; background: var(--secondary); }
  .shortcut-editor { max-width: 650px; padding: 13px 15px; margin-bottom: 12px; }
  .section-heading { margin-bottom: 9px; }
  .section-heading h2, .transfer-queue h2 { font-size: 13px; font-weight: 650; }
  .editor-actions { justify-content: flex-end; margin-top: 12px; }
  .file-notice { font-size: 11px; color: var(--muted-foreground); overflow-wrap: anywhere; }
  .file-notice span:empty { display: none; }
  .file-notice span:empty + :global(button) { margin-left: auto; }
  .transfer-queue { flex-shrink: 0; max-height: 26%; overflow: auto; margin-top: 10px; }
  .queue-record { margin-top: 6px; padding: 7px 10px; background: var(--surface-subtle); border-radius: 6px; }
  .queue-record strong { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .queue-record small { color: var(--muted-foreground); white-space: nowrap; }

  @media (max-width:760px), (max-width:1000px) and (max-height:500px) {
    .files-workspace { padding: 4px 10px 10px; }
    .files-workspace :global(.files-root) { gap: 8px; }
    .view-bar { flex-wrap: wrap; padding-bottom: 4px; min-height: 38px; }
    .view-bar :global([data-slot="tabs-list"]) { height: 34px; }
    .view-bar :global([data-slot="tabs-trigger"]) { padding-inline: 7px; }
    .pane-switch { display: flex; gap: 5px; margin-bottom: 6px; }
    .transfer-panes, .transfer-panes.unmounted { grid-template-columns: minmax(0, 1fr); }
    .pane-slot.mobile-hidden { display: none; }
    .record { align-items: flex-start; flex-wrap: wrap; gap: 8px; padding: 10px; }
    .record-meta { flex-basis: 100%; }
    .record-actions { margin-left: auto; }
    .shortcut-editor .parameter-grid { grid-template-columns: minmax(0, 1fr); }
    .editor-actions { flex-wrap: wrap; }
  }
</style>
