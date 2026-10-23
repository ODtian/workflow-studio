<script>
  import {tick} from 'svelte';
  import {MediaQuery} from 'svelte/reactivity';
  import {Block} from '@gradio/atoms';
  import {BaseButton} from '@gradio/button';
  import {BaseDropdown} from '@gradio/dropdown';
  import CheckboxGroup from '@gradio/checkboxgroup';
  import {bytes} from './fileFormat.js';

  let {name,pane,target,connected,send} = $props();
  const mobile = new MediaQuery('(max-width:650px)');
  let selected = $state([]);
  let selectedFolders = $state([]);
  let selectedItems = $derived([...selectedFolders,...selected]);
  let getSelection;
  let directory = '';
  let entries = $derived(pane.entries || []);
  let directories = $derived(entries.filter(entry => entry.kind === 'directory'));
  let files = $derived(entries.filter(entry => entry.kind === 'file' && entry.copyable !== false));
  let copyableFolders = $derived(directories.filter(entry => entry.copyable !== false));
  let allSelected = $derived(selectedItems.length === files.length + copyableFolders.length && selectedItems.length > 0);
  let path = $derived((pane.breadcrumbs || []).map(item => item.label).join('/').replace(/^\/\//,'/'));
  let targetPath = $derived((target.breadcrumbs || []).map(item => item.label).join('/').replace(/^\/\//,'/'));
  let currentFolder = $derived((pane.breadcrumbs || []).at(-1)?.label || '/');
  let targetFolder = $derived((target.breadcrumbs || []).at(-1)?.label || '/');
  let selectedBytes = $derived(files.filter(entry => selected.includes(entry.id)).reduce((total,entry) => total + (entry.size || 0),0));
  let parent = $derived((pane.breadcrumbs || []).at(-2));
  let locations = $derived([
    [(mobile.current ? currentFolder : path) || '当前位置',pane.directory_id || ''],
    ...(pane.roots || []).map(item => [`常用 · ${item.label}`,'root:'+item.id]),
    ...(pane.breadcrumbs || []).slice(0,-1).map(item => [`上级 · ${item.label}`,item.id])
  ]);
  function shared() {
    return {id:'files-'+name,label:'文件',show_label:false,container:false,visible:true,
      interactive:true,min_width:0,
      register_component:(_id,_set,get) => getSelection = get,
      dispatcher:async (_id,event) => {
        if (event === 'input') {
          await tick();
          selected = (await getSelection()).value;
        }
      }};
  }
  const navigate = entry_id => send({action:'navigate',pane:name,entry_id});
  $effect(() => {
    if (directory !== pane.directory_id) {directory = pane.directory_id; selected = []; selectedFolders = [];}
  });
</script>

<section class="file-pane" aria-label={name === 'drive' ? 'Drive 文件' : 'Molab 文件'}>
  <div class="pane-heading">
    <h3><span class="desktop-title">{name === 'drive' ? 'Google Drive' : 'Molab'}</span><span class="mobile-title">{name === 'drive' ? 'Drive' : 'Molab'}</span></h3>
    <div class="pane-tools">
      <BaseButton size="sm" disabled={!(files.length + copyableFolders.length) || pane.loading}
        onclick={() => {const clear=allSelected; selected=clear ? [] : files.map(entry => entry.id); selectedFolders=clear ? [] : copyableFolders.map(entry => entry.id);}}>
        {allSelected ? '清空' : '全选'}
      </BaseButton>
      <BaseButton size="sm" elem_classes={['refresh-button']} disabled={pane.loading} onclick={() => send({action:'refresh',pane:name})}>
        <span class="refresh-icon" aria-hidden="true">↻</span><span class="refresh-text">刷新</span>
      </BaseButton>
    </div>
  </div>
  <div class="navigation" title={path}>
    <BaseButton size="sm" elem_classes={['up-button']} disabled={!parent || pane.loading} onclick={() => navigate(parent.id)}>
      <span class="up-icon" aria-hidden="true">↑</span><span class="up-text">上一级</span>
    </BaseButton>
    <Block min_width={0} allow_overflow={true}><BaseDropdown label="目录" show_label={false}
      value={pane.directory_id || ''} choices={locations} interactive={!pane.loading}
      filterable={true} on_change={value => {
        if (value.startsWith('root:')) send({action:'root',pane:name,root:value.slice(5)});
        else if (value !== pane.directory_id) navigate(value);
      }} /></Block>
  </div>
  <div class="file-list" aria-label={name === 'drive' ? 'Drive 目录内容' : 'Molab 目录内容'}>
    {#if pane.loading}<p class="loading" role="status">读取目录…</p>{/if}
    {#each directories as entry (entry.id)}
      <div class="folder-row">
        <input class="folder-select" type="checkbox" aria-label={'选择文件夹 ' + entry.name}
          disabled={pane.loading || entry.copyable === false} checked={selectedFolders.includes(entry.id)}
          onchange={event => selectedFolders = event.currentTarget.checked ? [...selectedFolders,entry.id] : selectedFolders.filter(id => id !== entry.id)} />
        <BaseButton size="sm" disabled={pane.loading} onclick={() => navigate(entry.id)}>
          <span class="folder-name">📁 {entry.name}</span><span aria-hidden="true">›</span>
        </BaseButton>
      </div>
    {/each}
    {#if files.length}
      <CheckboxGroup shared_props={shared()}
        props={{value:selected,
          choices:files.map(entry => [mobile.current ? entry.name : `${entry.name} · ${bytes(entry.size)}`,entry.id]),show_select_all:false,buttons:[]}} />
    {/if}
    {#if pane.error}<p class="empty" role="alert">{pane.error}</p>
    {:else if !pane.loading && !entries.length}<p class="empty">此目录为空。</p>{/if}
  </div>
  <div class="pane-actions">
    <p class="folder-hint">文件夹按原名复制本层文件。</p>
    <div class="copy-target" title={targetPath}>
      {#if mobile.current}
        {selectedItems.length ? `${selectedItems.length} 项${selectedFolders.length ? '' : ' · '+bytes(selectedBytes)} → ` : '目标：'}{targetFolder}
      {:else}目标：{name === 'drive' ? 'Molab' : 'Drive'} · {targetPath}{/if}
    </div>
    <BaseButton variant="primary" disabled={!selectedItems.length || !connected || !target.canReceive || pane.loading || target.loading}
      onclick={() => {send({action:'transfer',entry_ids:[...selectedItems],target_id:target.directory_id}); selected = []; selectedFolders = [];}}>
      {#if mobile.current}{name === 'drive' ? '复制到 Molab →' : '← 复制到 Drive'}
      {:else}{name === 'local' ? '← ' : ''}复制{selectedItems.length ? ` ${selectedItems.length} 项` : ''}到 {name === 'drive' ? 'Molab →' : 'Drive'}{/if}
    </BaseButton>
  </div>
</section>

<style>
  .file-pane{display:grid;grid-template-rows:auto auto 1fr auto;gap:8px;min-width:0;}
  .pane-heading,.pane-tools,.navigation,.folder-row{display:flex;gap:7px;align-items:center;min-width:0;}
  .mobile-title,.refresh-icon,.up-icon{display:none;}
  h3{font-size:14px;font-weight:600;flex:1;margin:0;}
  .navigation :global(.block){flex:1;min-width:0;}
  .navigation :global(.wrap){min-width:0;}
  .navigation :global(input){min-width:0;}
  .file-list{height:clamp(280px,50dvh,600px);overflow:auto;border:1px solid #e1e5eb;border-radius:7px;padding:5px;}
  .file-list :global(.wrap){display:flex;flex-direction:column;gap:2px;}
  .file-list :global(label){min-height:36px;width:100%;min-width:0;border:0;box-shadow:none;justify-content:flex-start;padding:6px;}
  .file-list :global(label>span){font-size:13px;overflow-wrap:anywhere;text-align:left;min-width:0;}
  .folder-row> :global(button){flex:1;width:auto;display:flex;justify-content:space-between;text-align:left;font-size:13px;min-width:0;min-height:36px;background:transparent;box-shadow:none;border:0;padding:6px;}
  .folder-select{appearance:none;position:relative;box-sizing:border-box;width:17px;height:17px;flex-shrink:0;margin:0 3px;border:1.5px solid #9a9fab;border-radius:4px;background:#fff;cursor:pointer;}
  .folder-select:checked{border-color:#e58c47;background:#e58c47 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='m3.5 8 3 3 6-6.5' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center/13px 13px no-repeat;}
  .folder-select:focus-visible{outline:2px solid #e58c47;outline-offset:2px;}
  .folder-select:disabled{opacity:.45;cursor:default;}
  .folder-hint{font-size:11px;color:#78818d;margin:0;}
  .folder-name{min-width:0;overflow-wrap:anywhere;}
  .pane-actions{display:grid;gap:6px;min-width:0;}
  .copy-target{color:#657083;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  .empty{padding:20px 8px;color:#778392;font-size:13px;}
  .loading{padding:5px 8px;color:#778392;font-size:12px;}
  @media(max-width:650px){
    .file-pane{gap:6px;min-height:0;}
    h3{font-size:14px;}
    .desktop-title{display:none;}
    .mobile-title,.refresh-icon,.up-icon{display:inline;}
    .pane-heading,.pane-tools,.navigation,.folder-row{gap:4px;}
    .file-pane :global(button){font-size:12px;padding:5px 7px;min-width:0;min-height:36px;}
    .pane-heading :global(.refresh-button),.navigation :global(.up-button){width:34px;flex-shrink:0;}
    .refresh-icon,.up-icon{font-size:22px;line-height:1;}
    .refresh-text,.up-text{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap;}
    .navigation :global(.block){padding:2px 5px;min-height:38px;}
    .navigation :global(input){text-overflow:ellipsis;}
    .file-list{height:auto;min-height:0;padding:2px;overscroll-behavior:contain;scrollbar-width:thin;}
    .file-list :global(label){min-height:48px;padding:6px 4px;align-items:center;}
    .file-list :global(label>span){font-size:13px;line-height:1.4;margin-left:5px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;}
    .file-list :global(input){width:18px;height:18px;flex-shrink:0;}
    .folder-row> :global(button){font-size:13px;min-height:44px;padding:6px 4px;}
    .folder-select{width:17px;height:17px;flex-shrink:0;margin:0 3px;accent-color:#e58c47;}
  .folder-hint{font-size:11px;color:#78818d;margin:0;}
  .folder-name{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;}
    .pane-actions{position:sticky;bottom:0;background:white;padding-top:4px;gap:5px;}
    .pane-actions> :global(button){font-size:13px;min-height:44px;font-weight:600;padding:7px 3px;}
    .copy-target{font-size:11px;line-height:16px;}
  }
</style>
