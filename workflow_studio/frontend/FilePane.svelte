<script>
import {Button} from '$lib/components/ui/button';import {Badge} from '$lib/components/ui/badge';import {Folder,File,RefreshCw,ArrowUp,ArrowRight,HardDrive,Cloud} from '@lucide/svelte';import {bytes} from './fileFormat.js';
let {name,pane={},target={},connected,send}=$props();let selected=$state([]),directory='';
let entries=$derived(pane.entries||[]),parent=$derived((pane.breadcrumbs||[]).at(-2));
let targetPath=$derived((target.breadcrumbs||[]).map(i=>i.label).join('/'));
const navigate=entry_id=>send({action:'navigate',pane:name,entry_id});
$effect(()=>{if(directory!==pane.directory_id){directory=pane.directory_id;selected=[];}});
function toggle(entry,checked){selected=checked?[...selected,entry.id]:selected.filter(id=>id!==entry.id);}
</script>
<section class="file-pane" aria-label={name==='drive'?'Drive 文件':'Molab 文件'}>
  <div class="file-pane-heading"><div class="row">{#if name==='drive'}<Cloud size={19}/>{:else}<HardDrive size={19}/>{/if}<h2>{name==='drive'?'Google Drive':'Molab'}</h2></div><Button size="icon-sm" variant="ghost" aria-label="刷新目录" disabled={pane.loading} onclick={()=>send({action:'refresh',pane:name})}><RefreshCw size={15}/></Button></div>
  <div class="file-navigation"><Button variant="outline" size="icon-sm" aria-label="上一级" disabled={!parent||pane.loading} onclick={()=>navigate(parent.id)}><ArrowUp size={14}/></Button><select aria-label={name+'目录'} value={pane.directory_id||''} disabled={pane.loading} onchange={e=>{const v=e.currentTarget.value;v.startsWith('root:')?send({action:'root',pane:name,root:v.slice(5)}):navigate(v);}}><option value={pane.directory_id||''}>{(pane.breadcrumbs||[]).map(i=>i.label).join('/')||'当前位置'}</option>{#each pane.roots||[] as root}<option value={'root:'+root.id}>常用 · {root.label}</option>{/each}{#each (pane.breadcrumbs||[]).slice(0,-1) as crumb}<option value={crumb.id}>{crumb.label}</option>{/each}</select></div>
  <div class="file-table-head"><label><input type="checkbox" aria-label="全选文件" checked={!!selected.length&&selected.length===entries.filter(e=>e.copyable!==false).length} onchange={e=>selected=e.currentTarget.checked?entries.filter(e=>e.copyable!==false).map(e=>e.id):[]}/>名称</label><span>大小</span></div>
  <div class="file-table" aria-label={name==='drive'?'Drive 目录内容':'Molab 目录内容'}>
    {#if pane.loading}<p class="empty-resource">读取目录…</p>{/if}
    {#each entries as entry}<div class="file-entry" class:selected={selected.includes(entry.id)}><input type="checkbox" aria-label={'选择 '+entry.name} checked={selected.includes(entry.id)} disabled={pane.loading||entry.copyable===false} onchange={e=>toggle(entry,e.currentTarget.checked)}/>
      <button class="file-entry-name" title={entry.name} onclick={()=>entry.kind==='directory'?navigate(entry.id):toggle(entry,!selected.includes(entry.id))}>{#if entry.kind==='directory'}<Folder size={17} class="folder-icon"/>{:else}<File size={16}/>{/if}<span>{entry.name}</span></button><small>{entry.kind==='directory'?'文件夹':bytes(entry.size)}</small></div>{/each}
    {#if pane.error}<p class="error-text">{pane.error}</p>{:else if !pane.loading&&!entries.length}<div class="empty-resource"><Folder size={25}/><p>此目录为空</p></div>{/if}
  </div>
  <div class="file-pane-footer"><div class="row"><span>{selected.length} 项已选</span><span>{entries.length} 项</span></div><p title={targetPath}>目标 · {targetPath||'选择目标目录'}</p><Button class="copy-button" disabled={!selected.length||!connected||!target.canReceive||pane.loading||target.loading} onclick={()=>{send({action:'transfer',entry_ids:[...selected],target_id:target.directory_id});selected=[];}}>复制到 {name==='drive'?'Molab':'Drive'} <ArrowRight size={14}/></Button></div>
</section>
