<script>
  import {Button} from '$lib/components/ui/button';
  import {ArrowRight, ArrowUp, ChevronRight, Cloud, CloudOff, File, Folder, HardDrive, RefreshCw} from '@lucide/svelte';
  import {bytes} from './fileFormat.js';

  let {name, pane = {}, target = {}, connected, send} = $props();
  let selected = $state([]);
  let directory = '';
  let drive = $derived(name === 'drive');
  let entries = $derived(pane.entries || []);
  let selectable = $derived(entries.filter(entry => entry.copyable !== false));
  let crumbs = $derived(pane.breadcrumbs || []);
  let parent = $derived(crumbs.at(-2));
  let targetLabel = $derived(drive ? '运行时' : 'Drive');
  let location = $derived(pane.location || (crumbs.length === 1 ? 'root' : ''));
  const navigate = entry_id => send({action: 'navigate', pane: name, entry_id});
  const refresh = () => send({action: 'refresh', pane: name});

  $effect(() => {
    if (directory !== pane.directory_id) {
      directory = pane.directory_id;
      selected = [];
    }
  });

  function toggle(id, checked) {
    selected = checked ? [...selected, id] : selected.filter(item => item !== id);
  }

  function copy() {
    send({action: 'transfer', entry_ids: [...selected], target_id: target.directory_id});
    selected = [];
  }
</script>

<section class="file-pane" aria-label={drive ? 'Drive 文件' : '运行时文件'}>
  <header class="pane-heading">
    <div class="pane-title">
      <span class="pane-icon">{#if drive}<Cloud size={17}/>{:else}<HardDrive size={17}/>{/if}</span>
      <h2>{drive ? 'Google Drive' : '运行时'}</h2>
    </div>
    {#if drive}<span class="connection" class:connected><i></i>{connected ? '已挂载' : '未挂载'}</span>{/if}
    {#if !drive && pane.roots?.length > 1}
      <nav class="pane-roots" aria-label="常用目录">
        {#each pane.roots as root (root.id)}
          <button type="button" aria-pressed={location === root.id} disabled={pane.loading}
            onclick={() => send({action: 'root', pane: name, root: root.id})}>{root.id === 'root' ? '根目录' : root.label}</button>
        {/each}
      </nav>
    {/if}
  </header>

  {#if drive && !connected}
    <div class="pane-empty unmounted">
      <span class="empty-icon"><CloudOff size={22}/></span>
      <strong>连接 Google Drive</strong>
      <p>在 Colab 左侧「文件」面板挂载云端硬盘，再刷新目录。</p>
      <Button size="sm" variant="outline" onclick={refresh} disabled={pane.loading}>
        <RefreshCw size={14}/>刷新目录
      </Button>
    </div>
  {:else}
    <div class="pane-location">
      <Button size="icon-sm" variant="ghost" aria-label="上一级" title="上一级" disabled={!parent || pane.loading} onclick={() => navigate(parent.id)}>
        <ArrowUp size={15}/>
      </Button>
      <nav class="breadcrumbs" aria-label="当前目录" title={pane.path}>
        {#each crumbs as crumb, index (crumb.id)}
          {#if index}<ChevronRight size={12}/>{/if}
          {#if index === crumbs.length - 1}
            <span aria-current="page">{crumb.label}</span>
          {:else}
            <button type="button" onclick={() => navigate(crumb.id)} disabled={pane.loading}>{crumb.label}</button>
          {/if}
        {/each}
      </nav>
      <Button size="icon-sm" variant="ghost" aria-label="刷新目录" title="刷新目录" disabled={pane.loading} onclick={refresh}>
        <RefreshCw size={15}/>
      </Button>
    </div>

    <div class="file-columns">
      <label>
        <input type="checkbox" aria-label="全选文件" disabled={!selectable.length || pane.loading}
          checked={!!selected.length && selected.length === selectable.length}
          onchange={event => selected = event.currentTarget.checked ? selectable.map(entry => entry.id) : []}/>
        名称
      </label>
      <span>大小</span>
    </div>
    <div class="file-list" aria-label={drive ? 'Drive 目录内容' : '运行时目录内容'} aria-busy={!!pane.loading}>
      {#if pane.loading}
        <div class="pane-empty" role="status">正在读取目录…</div>
      {:else if pane.error}
        <div class="pane-empty" role="status"><p class="error-text">{pane.error}</p><Button size="sm" variant="outline" onclick={refresh}>重试</Button></div>
      {:else if !entries.length}
        <div class="pane-empty"><Folder size={24}/><strong>此目录为空</strong></div>
      {:else}
        {#each entries as entry (entry.id)}
          <div class="file-row" class:selected={selected.includes(entry.id)}>
            <input type="checkbox" aria-label={'选择 ' + entry.name} checked={selected.includes(entry.id)}
              disabled={entry.copyable === false} onchange={event => toggle(entry.id, event.currentTarget.checked)}/>
            <button type="button" class="file-name" title={entry.name}
              disabled={entry.kind !== 'directory' && entry.copyable === false}
              onclick={() => entry.kind === 'directory' ? navigate(entry.id) : toggle(entry.id, !selected.includes(entry.id))}>
              {#if entry.kind === 'directory'}<Folder size={16}/>{:else}<File size={15}/>{/if}
              <span>{entry.name}</span>
            </button>
            <span class="file-size">{entry.kind === 'directory' ? '文件夹' : bytes(entry.size)}</span>
          </div>
        {/each}
      {/if}
    </div>

    <footer class="pane-footer">
      <div class="selection">
        <span>{selected.length ? '已选 ' + selected.length + ' 项' : entries.length + ' 项'}</span>
        {#if selected.length}
          <small title={target.path || ''}>{target.canReceive ? target.path : '请选择可写的目标目录'}</small>
        {/if}
      </div>
      <Button size="sm" variant={selected.length && connected && target.canReceive ? 'default' : 'outline'}
        disabled={!selected.length || !connected || !target.canReceive || pane.loading || target.loading}
        title={!connected ? '请先挂载 Google Drive' : target.path} onclick={copy}>
        复制到 {targetLabel}<ArrowRight size={14}/>
      </Button>
    </footer>
  {/if}
</section>

<style>
  .file-pane {
    min-width: 0;
    min-height: 0;
    width: 100%;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border);
    border-radius: 11px;
    overflow: hidden;
    background: var(--background);
  }
  .pane-heading, .pane-title, .connection, .pane-location, .breadcrumbs, .pane-roots, .file-columns,
  .file-columns label, .file-row, .file-name, .pane-footer { display: flex; align-items: center; }
  .pane-heading {
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px;
    background: var(--surface-subtle);
    border-bottom: 1px solid var(--border);
  }
  .pane-title { gap: 9px; }
  .pane-title h2 { font-size: 14px; font-weight: 650; }
  .pane-icon, .empty-icon {
    display: grid;
    place-items: center;
    color: var(--muted-foreground);
    background: var(--secondary);
    width: 29px;
    height: 29px;
    border-radius: 7px;
  }
  .connection { color: var(--muted-foreground); gap: 6px; font-size: 11px; white-space: nowrap; }
  .connection i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .connection.connected { color: var(--success); }
  .pane-location { gap: 5px; padding: 6px 10px; }
  .breadcrumbs {
    min-width: 0;
    flex: 1;
    gap: 4px;
    white-space: nowrap;
    overflow: auto hidden;
    scrollbar-width: thin;
    color: var(--muted-foreground);
    font-size: 12px;
  }
  .breadcrumbs button, .pane-roots button { border: 0; background: transparent; border-radius: 5px; white-space: nowrap; }
  .breadcrumbs button, .breadcrumbs span { padding: 4px; }
  .breadcrumbs span { color: var(--foreground); font-weight: 550; }
  .breadcrumbs button:hover, .pane-roots button:hover { background: var(--secondary); }
  .breadcrumbs :global(svg) { flex-shrink: 0; }
  .pane-roots { gap: 5px; flex-wrap: wrap; }
  .pane-roots button { padding: 3px 8px; color: var(--muted-foreground); font-size: 11px; }
  .pane-roots button[aria-pressed="true"] { background: var(--secondary); color: var(--foreground); font-weight: 600; }
  .file-columns {
    justify-content: space-between;
    flex-shrink: 0;
    gap: 12px;
    padding: 6px 14px;
    border-block: 1px solid var(--border);
    color: var(--muted-foreground);
    background: var(--surface-subtle);
    font-size: 11px;
  }
  .file-columns label { gap: 10px; }
  .file-columns input, .file-row input { width: 14px; height: 14px; flex-shrink: 0; accent-color: var(--primary); }
  .file-list { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; scrollbar-width: thin; }
  .file-row { gap: 10px; min-height: 34px; padding: 3px 14px; }
  .file-row + .file-row { border-top: 1px solid color-mix(in srgb, var(--border) 52%, transparent); }
  .file-row:hover, .file-row.selected { background: var(--secondary); }
  .file-name { gap: 8px; flex: 1; min-width: 0; padding: 3px 0; border: 0; background: transparent; text-align: left; }
  .file-name :global(svg) { flex-shrink: 0; color: var(--muted-foreground); }
  .file-name span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-size { color: var(--muted-foreground); font-size: 11px; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .pane-footer {
    flex-shrink: 0;
    justify-content: space-between;
    gap: 10px;
    min-height: 48px;
    padding: 8px 12px;
    background: var(--surface-subtle);
    border-top: 1px solid var(--border);
  }
  .selection { min-width: 0; color: var(--muted-foreground); font-size: 11px; }
  .selection small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pane-empty {
    min-height: 100%;
    padding: 18px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 9px;
    color: var(--muted-foreground);
    text-align: center;
  }
  .pane-empty strong { color: var(--foreground); font-weight: 600; }
  .pane-empty p { max-width: 245px; font-size: 12px; line-height: 1.7; }
  .unmounted { flex: 1; min-height: 0; }
  .empty-icon { width: 44px; height: 44px; border-radius: 10px; margin-bottom: 3px; }

  @media (max-width:760px), (max-width:1000px) and (max-height:500px) {
    .pane-heading { display: none; }
    .pane-heading:has(.pane-roots) { display: flex; padding: 5px 9px; }
    .pane-heading:has(.pane-roots) .pane-title { display: none; }
    .file-row { min-height: 38px; }
    .pane-roots button { min-height: 28px; }
  }
</style>
