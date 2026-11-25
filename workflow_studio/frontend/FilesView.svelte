<script>
import {Button} from '$lib/components/ui/button';import {Badge} from '$lib/components/ui/badge';import {Input} from '$lib/components/ui/input';import {Progress} from '$lib/components/ui/progress';import * as Tabs from '$lib/components/ui/tabs';import {ArrowLeftRight,Plus,Search,History,Play,Settings2,Cloud,HardDrive} from '@lucide/svelte';
import FilePane from './FilePane.svelte';import {bytes,taskStatus} from './fileFormat.js';
let {files={},send}=$props();let tab=$state('transfer'),query=$state(''),editing=$state(false),draft=$state({});const act=command=>send('files',{command});
function editShortcut(record){
  const source=record.hf_sources?.[0]||{};
  draft={...record,hf_url:record.hf_url||source.repo_id||record.repo_id||'',hf_revision:source.revision||'main',hf_patterns:(source.allow_patterns||[]).join(', ')};
  editing=true;
}
function saveShortcut(replay=false){act({action:'save_recipe',recipe:{...draft},replay});editing=false;}
let mobilePane=$state('drive');
let shortcuts=$derived((files.recipes||[]).toReversed().filter(i=>[i.label,i.local_path,i.drive_path,i.repo_id].join(' ').toLowerCase().includes(query.toLowerCase())));
let activeTasks=$derived((files.tasks||[]).filter(t=>['running','queued'].includes(t.status))),history=$derived((files.tasks||[]).filter(t=>!['running','queued'].includes(t.status)).toReversed());
const sourceLabel = task => {
  if (task.source === 'huggingface') return 'Hugging Face 下载';
  if (task.direction === 'copy') return 'Drive 复制';
  return task.direction === 'download' ? 'Drive 下载' : '上传至 Drive';
};
const displayTime = new Intl.DateTimeFormat('zh-CN', {dateStyle:'short', timeStyle:'short'});
</script>
<article class="files-workspace page-padding" aria-label="文件传输">
  <Tabs.Root class="files-root" bind:value={tab}><div class="files-tabs"><Tabs.List><Tabs.Trigger value="transfer"><ArrowLeftRight size={14}/>传输</Tabs.Trigger><Tabs.Trigger value="shortcuts">快捷复制</Tabs.Trigger><Tabs.Trigger value="history"><History size={14}/>传输记录</Tabs.Trigger></Tabs.List>{#if tab==='shortcuts'}<Button size="sm" onclick={()=>editShortcut({label:'',source_provider:'huggingface',direction:'download',source_kind:'file',drive_path:'',local_path:files.model_directory||''})}><Plus size={14}/>新增快捷复制</Button>{/if}</div>
  <Tabs.Content class="transfer-view" value="transfer"><nav class="file-pane-tabs" aria-label="文件位置"><Button variant={mobilePane==='drive'?'secondary':'ghost'} aria-pressed={mobilePane==='drive'} onclick={()=>mobilePane='drive'}><Cloud size={17}/>Google Drive<i class="status-dot" class:disconnected={!files.connected} aria-label={files.connected?'Drive 已连接':'Drive 连接待就绪'}></i></Button><Button variant={mobilePane==='local'?'secondary':'ghost'} aria-pressed={mobilePane==='local'} onclick={()=>mobilePane='local'}><HardDrive size={17}/>运行时</Button></nav><div class="transfer-panes">{#each ['drive','local'] as name}<div class="file-pane-slot" class:mobile-hidden={mobilePane!==name}><FilePane {name} pane={files.panes?.[name]||{}} target={files.panes?.[name==='drive'?'local':'drive']||{}} connected={files.connected} driveDirectory={files.drive_directory} send={act}/></div>{/each}</div></Tabs.Content>
  <Tabs.Content value="shortcuts"><div class="shortcut-search"><Search size={16}/><Input aria-label="搜索快捷复制" placeholder="搜索名称或目录…" bind:value={query}/></div><div class="shortcut-grid">{#each shortcuts as item}<div class="surface shortcut-card"><div class="row"><ArrowLeftRight size={17}/><h3 title={item.source_kind==='directory'?'文件夹 · 包含子目录':'文件'}>{item.label}</h3><Badge variant="secondary">{item.source_provider==='huggingface'?'HF → 本机':item.direction==='download'?'Drive → 运行时':'运行时 → Drive'}</Badge></div><p class="path-text">{item.local_path}</p><div class="row"><Button size="sm" disabled={item.source_provider!=='huggingface'&&!files.connected} onclick={()=>act({action:'replay',ids:[item.id]})}><Play size={13}/>{item.source_provider==='huggingface'?'复制到本机':'复制'}</Button><Button size="sm" variant="outline" onclick={()=>editShortcut(item)}><Settings2 size={13}/>管理</Button></div></div>{:else}<div class="empty-resource">暂无快捷操作</div>{/each}</div></Tabs.Content>
  <Tabs.Content value="history">
    {#if files.history_storage === 'memory'}
      <p class="hint history-storage" role="status">记录暂存在内存中。检查运行时可用空间后刷新目录。</p>
    {:else if files.history_storage === 'runtime'}
      <p class="hint history-storage">记录保存在当前 Colab 运行时。挂载可写的 Google Drive 后刷新 Drive 目录，可跨运行时保留记录。</p>
    {/if}
    <div class="surface transfer-history">
      {#each history as task (task.id)}
        <div class="transfer-record">
          <div class="transfer-record-details">
            <strong>{task.name}</strong>
            <p class="hint">{sourceLabel(task)}{#if task.bytes} · {bytes(task.bytes)}{/if}{#if task.finished_at} · {displayTime.format(task.finished_at * 1000)}{/if}</p>
            {#if task.target_path || task.local_path}<p class="path-text">{task.target_path || task.local_path}</p>{/if}
            {#if task.error}<p class="error-text">{task.error}</p>{/if}
          </div>
          <Badge variant="secondary">{taskStatus[task.status]}</Badge>
          {#if ['failed','cancelled'].includes(task.status) && task.retryable}
            <Button size="sm" variant="outline" onclick={()=>act({action:'retry',task_id:task.id})}>重试</Button>
          {/if}
          <Button size="sm" variant="ghost" onclick={()=>act({action:'delete_task',id:task.id})}>删除记录</Button>
        </div>
      {:else}
        <p class="empty-resource">暂无传输记录</p>
      {/each}
    </div>
  </Tabs.Content>
  </Tabs.Root>
  {#if editing}<section class="surface shortcut-editor"><h2>快捷操作设置</h2><div class="parameter-grid"><label class="field"><span>名称</span><Input bind:value={draft.label}/></label><label class="field"><span>复制方向</span><select value={draft.source_provider==='huggingface'?'huggingface':draft.direction} onchange={event=>{const value=event.currentTarget.value;draft.source_provider=value==='huggingface'?'huggingface':'drive';draft.direction=value==='upload'?'upload':'download';}}><option value="huggingface">HF → 本机</option><option value="download">Drive → 本机</option><option value="upload">本机 → Drive</option></select></label>{#if draft.source_provider==='huggingface'}
<label class="field wide"><span>HF 仓库或文件地址</span><Input placeholder="owner/repo 或 https://huggingface.co/.../resolve/main/file" bind:value={draft.hf_url}/></label>
<label class="field wide"><span>文件范围（多个规则用逗号分隔）</span><Input placeholder="例如 IQ3_S/*.gguf；留空复制全部" bind:value={draft.hf_patterns}/></label>
<label class="field"><span>版本</span><Input bind:value={draft.hf_revision}/></label>
{#if draft.hf_sources?.length>1}<div class="field wide"><span>配套来源</span>{#each draft.hf_sources.slice(1) as source}<code>{source.repo_id} · {source.allow_patterns?.join(', ')||'全部文件'}</code>{/each}</div>{/if}
{:else}<label class="field"><span>内容</span><select bind:value={draft.source_kind}><option value="file">文件</option><option value="directory">文件夹 · 包含子目录</option></select></label><label class="field"><span>Drive 相对路径</span><Input placeholder="例如 models/diffusion_models" bind:value={draft.drive_path}/></label>{/if}<label class="field wide"><span>{draft.source_provider==='huggingface'?'运行时目标目录':'运行时完整路径'}</span><Input bind:value={draft.local_path}/></label></div><div class="row">{#if draft.source_provider==='huggingface'}<Button disabled={!draft.hf_url.trim()||!draft.local_path.trim()} onclick={()=>saveShortcut(true)}>保存并复制</Button>{:else}<Button onclick={()=>saveShortcut()}>保存快捷操作</Button>{/if}{#if draft.id}<Button variant="destructive" onclick={()=>{act({action:'delete_recipe',id:draft.id});editing=false;}}>删除快捷操作</Button>{/if}<Button variant="ghost" onclick={()=>editing=false}>收起</Button></div></section>{/if}
  {#if files.error||files.message||files.notice||files.can_undo}<div class="file-notice" role="status"><span>{files.error||files.message||files.notice}</span>{#if files.can_undo}<Button variant="outline" size="sm" onclick={()=>act({action:'undo'})}>撤销删除</Button>{/if}</div>{/if}
  {#if activeTasks.length}<section class="transfer-queue"><h3>正在传输</h3>{#each activeTasks as task}<div class="surface transfer-task"><div class="row"><strong>{task.name}</strong><span>{bytes(task.bytes)} / {bytes(task.total)}{task.speed?' · '+bytes(task.speed)+'/s':''}</span><Button size="sm" variant="ghost" onclick={()=>act({action:'cancel',task_id:task.id})}>停止</Button></div><Progress max={task.total||1} value={task.bytes}/></div>{/each}</section>{/if}
</article>

<style>
  .history-storage { margin: 0 0 10px; }
  .transfer-record-details { min-width: 0; overflow-wrap: anywhere; }
</style>
