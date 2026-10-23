<script>
  import {Block} from '@gradio/atoms';
  import {BaseButton} from '@gradio/button';
  import {BaseDropdown} from '@gradio/dropdown';
  import {BaseTextbox} from '@gradio/textbox';
  import {BaseTabs} from '@gradio/tabs';
  import {BaseTabItem} from '@gradio/tabitem';
  import FilePane from './FilePane.svelte';
  import {bytes,taskStatus} from './fileFormat.js';

  let {files = {},send} = $props();
  let tab = $state('transfer');
  let query = $state('');
  let editing = $state(false);
  let draft = $state({});
  const act = command => send('files',{command});
  const tabs = ['transfer','shortcuts'].map((id,index)=>({id,label:['双栏传输','快捷复制'][index],
    elem_id:undefined,visible:true,interactive:true,scale:0,component_id:index}));
  let recipes = $derived(files.recipes || []);
  let shortcuts = $derived(recipes.toReversed().filter(item =>
    [item.label,item.name,item.local_path,item.drive_id].join(' ').toLowerCase().includes(query.trim().toLowerCase())));
  let activeTasks = $derived((files.tasks || []).filter(task => ['running','queued'].includes(task.status)));
  let history = $derived((files.tasks || []).filter(task => !['running','queued'].includes(task.status)).toReversed());
  const endpoints = (direction,kind) => direction === 'download'
    ? [{key:'drive_id',label:(kind === 'directory' ? '源文件夹 · Drive 目录链接' : '源文件 · Drive 文件链接')},{key:'local_path',label:'目标目录 · Molab'}]
    : [{key:'local_path',label:(kind === 'directory' ? '源文件夹 · Molab 完整路径' : '源文件 · Molab 完整路径')},{key:'drive_id',label:'目标目录 · Drive 目录链接'}];
</script>

{#snippet shortcutEditor()}
  <div class="record-editor" role="group" aria-label="快捷操作设置">
    <Block><BaseTextbox label="快捷操作名称" bind:value={draft.label} /></Block>
    <Block allow_overflow={true}><BaseDropdown label="复制方向" bind:value={draft.direction} interactive={true} filterable={false}
      choices={[["Drive → Molab","download"],["Molab → Drive","upload"]]} /></Block>
    <Block allow_overflow={true}><BaseDropdown label="复制内容" bind:value={draft.source_kind} interactive={true} filterable={false}
      choices={[["文件","file"],["文件夹 · 本层文件","directory"]]} /></Block>
    {#each endpoints(draft.direction,draft.source_kind) as field (field.key)}
      <Block><BaseTextbox label={field.label} bind:value={draft[field.key]} /></Block>
    {/each}
    <div class="record-actions">
      <BaseButton size="sm" variant="primary" onclick={() => {act({action:'save_recipe',recipe:{...draft}});editing=false;}}>保存快捷操作</BaseButton>
      {#if draft.id}<BaseButton size="sm" onclick={() => {act({action:'delete_recipe',id:draft.id});editing=false;}}>删除快捷操作</BaseButton>{/if}
      <BaseButton size="sm" onclick={() => editing=false}>收起</BaseButton>
    </div>
  </div>
{/snippet}

<article class="files-card" aria-label="文件传输">
  <BaseTabs bind:selected={tab} initial_tabs={tabs} overflow_behavior="menu">
    <BaseTabItem id="transfer" label="双栏传输" order={0} component_id={0} visible={true} interactive={true} scale={0}>
      <div class="transfer-panes">
        {#each ['drive','local'] as name}
          <FilePane {name} pane={files.panes?.[name] || {}} target={files.panes?.[name === 'drive' ? 'local' : 'drive'] || {}}
            connected={files.connected} send={act} />
        {/each}
      </div>
    </BaseTabItem>
    <BaseTabItem id="shortcuts" label="快捷复制" order={1} component_id={1} visible={true} interactive={true} scale={0}>
      <div class="history-tools">
        <Block min_width={0}><BaseTextbox label="搜索快捷复制" show_label={false} bind:value={query} placeholder="搜索文件或目标目录" /></Block>
        <BaseButton size="sm" onclick={() => {draft={label:'',direction:'download',drive_id:'',local_path:'',enabled:true,source_kind:'file'};editing=true;}}>新增快捷操作</BaseButton>
      </div>
      <p class="shortcut-hint">快捷记录保存源位置和目标目录；文件夹每次复制时读取当前本层文件。</p>
      {#if editing && !draft.id}{@render shortcutEditor()}{/if}
      <div class="shortcut-list" aria-label="已保存的快捷复制">
        {#each shortcuts as item (item.id)}
          <div class="shortcut-row">
            <div class="shortcut-info">
              <strong title={item.label}>{item.source_kind === 'directory' ? '📁 ' : ''}{item.label}</strong>
              {#if item.source_kind === 'directory'}<small class="folder-recipe">文件夹 · 本层文件</small>{/if}
              <div class="shortcut-path" title={item.local_path}>
                {#if item.direction === 'download'}→ Molab · {item.local_path}
                {:else}{item.local_path} → <a href={'https://drive.google.com/drive/folders/'+item.drive_id} target="_blank" rel="noreferrer">Drive 目标目录 ↗</a>{/if}
              </div>
            </div>
            <BaseButton size="sm" variant="primary" disabled={!files.connected} onclick={() => act({action:'replay',ids:[item.id]})}>复制</BaseButton>
            <BaseButton size="sm" onclick={() => {draft={source_kind:'file',...item};editing=true;}}>管理</BaseButton>
            {#if editing && draft.id === item.id}{@render shortcutEditor()}{/if}
          </div>
        {:else}<p class="shortcut-hint">{query ? '调整搜索词查找快捷操作。' : '在双栏中选择文件和目标目录完成一次复制，或点击“新增快捷操作”。'}</p>{/each}
      </div>
      {#if history.length}<details class="transfer-history"><summary>传输历史（{history.length}）</summary><div class="history-list" aria-label="传输历史">
        {#each history as task (task.id)}
          <div class="history-row">
            <span class="task-name" title={task.name}>{task.name}</span>
            <small>{taskStatus[task.status]}</small>
            {#if ['failed','cancelled'].includes(task.status) && task.retryable !== false}<BaseButton size="sm" onclick={() => act({action:'retry',task_id:task.id})}>重试</BaseButton>{/if}
            <BaseButton size="sm" onclick={() => act({action:'delete_task',id:task.id})}>删除记录</BaseButton>
          </div>
        {/each}
      </div></details>{/if}
    </BaseTabItem>
  </BaseTabs>
  {#if files.error || files.message || files.notice || files.can_undo}
    <div class="file-notice" role="status"><span>{files.error || files.message || files.notice || ''}</span>
      {#if files.can_undo}<BaseButton size="sm" onclick={() => act({action:'undo'})}>撤销删除</BaseButton>{/if}
    </div>
  {/if}
  {#if activeTasks.length}<section class="queue" aria-label="正在传输">
    {#each activeTasks as task (task.id)}
      <div class="task-row"><span class="task-name">{task.name}</span>
        <small>{taskStatus[task.status]} · {bytes(task.bytes)} / {bytes(task.total)}{task.speed ? ` · ${bytes(task.speed)}/s` : ''}</small>
        <BaseButton size="sm" onclick={() => act({action:'cancel',task_id:task.id})}>停止</BaseButton>
        <progress max={task.total || 1} value={task.bytes}></progress>
      </div>
    {/each}
  </section>{/if}
</article>

<style>
  .files-card{background:#fff;border:1px solid #dde2e8;border-radius:9px;padding:12px 16px;min-width:0;margin:auto;}
  .transfer-panes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;}
  .history-tools,.record-actions,.file-notice,.history-row,.task-row{display:flex;gap:8px;align-items:center;min-width:0;}
  .history-tools :global(.block){flex:1;min-width:0;}
  .history-tools> :global(button){flex-shrink:0;}
  .shortcut-hint{font-size:12px;line-height:1.5;color:#748090;margin:8px 0;}
  .shortcut-list{max-height:min(58dvh,480px);overflow:auto;overscroll-behavior:contain;}
  .shortcut-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px;padding:10px 0;border-bottom:1px solid #edf0f4;}
  .shortcut-info{min-width:0;}
  .shortcut-info strong{display:block;font-size:13px;font-weight:600;overflow-wrap:anywhere;}
  .folder-recipe{display:block;color:#748090;font-size:11px;margin:3px 0;}
  .shortcut-path{font-size:12px;line-height:1.5;color:#748090;overflow-wrap:anywhere;margin-top:2px;}
  .shortcut-path a{color:#a65a23;text-decoration:underline;}
  .shortcut-row> :global(button){min-width:0;}
  .shortcut-row>.record-editor{grid-column:1/-1;}
  .transfer-history{margin-top:14px;}
  .transfer-history summary{font-size:12px;color:#748090;cursor:pointer;padding:7px 0;}
  .record-actions{flex-wrap:wrap;margin-top:8px;}
  .record-editor>.record-actions{grid-column:1/-1;}
  .record-actions>span{font-size:12px;overflow-wrap:anywhere;color:#6e7887;}
  .record-editor{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px;}
  .history-list{max-height:280px;overflow:auto;margin-top:14px;}
  .history-row{border-bottom:1px solid #edf0f4;padding:6px 0;}
  .history-row :global(button){font-size:11px;min-width:0;}
  .task-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;}
  small{font-size:11px;white-space:nowrap;color:#748090;}
  .file-notice{font-size:12px;color:#687589;margin-top:10px;}
  .file-notice>span{flex:1;}
  .queue{margin-top:12px;display:grid;gap:7px;}
  .task-row{flex-wrap:wrap;}
  progress{height:3px;width:100%;appearance:none;border:0;}
  progress::-webkit-progress-bar{background:#edf0f4;}
  progress::-webkit-progress-value{background:#f59b52;}
  @media(max-width:650px){
    .files-card{padding:6px;border-radius:7px;}
    .files-card :global(.tab-nav){margin-bottom:6px;}
    .files-card :global(.tab-nav button){min-height:34px;padding:7px 10px;}
    .transfer-panes{gap:6px;height:calc(100dvh - 156px);min-height:340px;}
    .record-editor{grid-template-columns:1fr;}
    .shortcut-row{gap:6px;}
    .shortcut-info strong{font-size:13px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;}
    .shortcut-path{font-size:11px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;}
    .shortcut-row> :global(button){font-size:12px;padding:5px 8px;min-height:40px;}
    .history-row{gap:5px;flex-wrap:wrap;padding:8px 0;}
    .history-row .task-name{flex-basis:calc(100% - 70px);}
    .history-row :global(button){min-height:36px;padding:5px 8px;}
    .task-row>small{order:3;width:100%;}
    .history-tools> :global(button){font-size:12px;}
  }
</style>
