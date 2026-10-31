<script>
import {Button} from '$lib/components/ui/button';import {Folder,File,RefreshCw,ArrowUp,ArrowRight,HardDrive,Cloud} from '@lucide/svelte';import {bytes} from './fileFormat.js';
import {Input} from '$lib/components/ui/input';
let {name,pane={},target={},connected,auth={},send}=$props();let selected=$state([]),directory='',authorizationCode=$state('');
let entries=$derived(pane.entries||[]),parent=$derived((pane.breadcrumbs||[]).at(-2));
let targetPath=$derived((target.breadcrumbs||[]).map(i=>i.label).join('/'));
const navigate=entry_id=>send({action:'navigate',pane:name,entry_id});
$effect(()=>{if(directory!==pane.directory_id){directory=pane.directory_id;selected=[];}});
function toggle(entry,checked){selected=checked?[...selected,entry.id]:selected.filter(id=>id!==entry.id);}
</script>
<section class="file-pane" aria-label={name==='drive'?'Drive 文件':'Molab 文件'}>
  <div class="file-pane-heading"><div class="row">{#if name==='drive'}<Cloud size={17}/>{:else}<HardDrive size={17}/>{/if}<h2>{name==='drive'?'Google Drive':'Molab'}</h2>{#if name==='drive'}<i class="status-dot" class:disconnected={!connected} title={connected?'Drive 已连接':'Drive 连接待就绪'} aria-label={connected?'Drive 已连接':'Drive 连接待就绪'}></i>{/if}</div>{#if name==='drive'}<Button variant="outline" size="sm" disabled={auth.phase==='working'} onclick={()=>send({action:'drive_connect'})}>{connected?'重新连接':auth.url?'重新获取授权链接':'连接 Google Drive'}</Button>{/if}</div>
  {#if name==='drive'&&(!connected||auth.phase==='pending'||auth.phase==='working'||auth.error)}
    <section class="drive-authorization" aria-label="Google Drive 连接">
      <p>{auth.storage_description || '首次授权保存在本 Notebook 的 Secrets，后续打开自动重连。'}</p>
      {#if auth.url}
        <a class="drive-authorization-link" href={auth.url} target="_blank" rel="noopener noreferrer">1. 前往 Google 授权 ↗</a>
        <p>完成 Google 授权后，按下面的顺序继续。</p>
        <form onsubmit={event=>{event.preventDefault();const code=authorizationCode;authorizationCode='';send({action:'drive_authorize',code});}}>
          <Input type="password" autocomplete="off" aria-label="Google Drive 一次性授权码" placeholder="2. 粘贴 Google 返回的一次性授权码" bind:value={authorizationCode}/>
          <Button type="submit" disabled={!authorizationCode.trim()||auth.phase==='working'}>3. 完成连接</Button>
        </form>
      {/if}
      {#if auth.phase==='working'}<p role="status">正在验证授权并保存连接…</p>{/if}
      {#if auth.error}<p class="error-text" role="alert">{auth.error}</p>{/if}
    </section>
  {/if}
  <div class="file-navigation"><Button variant="outline" size="icon-sm" aria-label="上一级" disabled={!parent||pane.loading} onclick={()=>navigate(parent.id)}><ArrowUp size={14}/></Button><select aria-label={name+'目录'} value={pane.directory_id||''} disabled={pane.loading} onchange={e=>{const v=e.currentTarget.value;v.startsWith('root:')?send({action:'root',pane:name,root:v.slice(5)}):navigate(v);}}><option value={pane.directory_id||''}>{(pane.breadcrumbs||[]).map(i=>i.label).join('/')||'当前位置'}</option>{#each pane.roots||[] as root}<option value={'root:'+root.id}>常用 · {root.label}</option>{/each}{#each (pane.breadcrumbs||[]).slice(0,-1) as crumb}<option value={crumb.id}>{crumb.label}</option>{/each}</select><Button size="icon-sm" variant="ghost" aria-label="刷新目录" disabled={pane.loading} onclick={()=>send({action:'refresh',pane:name})}><RefreshCw size={15}/></Button></div>
  <div class="file-table-head"><label><input type="checkbox" aria-label="全选文件" checked={!!selected.length&&selected.length===entries.filter(e=>e.copyable!==false).length} onchange={e=>selected=e.currentTarget.checked?entries.filter(e=>e.copyable!==false).map(e=>e.id):[]}/>名称</label><span>大小</span></div>
  <div class="file-table" aria-label={name==='drive'?'Drive 目录内容':'Molab 目录内容'}>
    {#if pane.loading}<p class="empty-resource">读取目录…</p>{/if}
    {#each entries as entry}<div class="file-entry" class:selected={selected.includes(entry.id)}><input type="checkbox" aria-label={'选择 '+entry.name} checked={selected.includes(entry.id)} disabled={pane.loading||entry.copyable===false} onchange={e=>toggle(entry,e.currentTarget.checked)}/>
      <button class="file-entry-name" title={entry.name} onclick={()=>entry.kind==='directory'?navigate(entry.id):toggle(entry,!selected.includes(entry.id))}>{#if entry.kind==='directory'}<Folder size={17} class="folder-icon"/>{:else}<File size={16}/>{/if}<span>{entry.name}</span></button><small>{entry.kind==='directory'?'文件夹':bytes(entry.size)}</small></div>{/each}
    {#if pane.error&&(name!=='drive'||connected)}<p class="error-text">{pane.error}</p>{:else if !pane.loading&&!entries.length&&(name!=='drive'||connected)}<div class="empty-resource"><Folder size={25}/><p>此目录为空</p></div>{/if}
  </div>
  <div class="file-pane-footer"><div class="file-selection"><span>{selected.length?`已选 ${selected.length} / ${entries.length} 项`:`${entries.length} 项`}</span><p title={targetPath}>目标 · {targetPath||'选择目标目录'}</p></div><Button class="copy-button" title={targetPath} disabled={!selected.length||!connected||!target.canReceive||pane.loading||target.loading} onclick={()=>{send({action:'transfer',entry_ids:[...selected],target_id:target.directory_id});selected=[];}}>复制到 {name==='drive'?'Molab':'Drive'} <ArrowRight size={14}/></Button></div>
</section>
<style>
.drive-authorization{padding:12px 14px;border-bottom:1px solid var(--border);display:grid;gap:10px;font-size:13px;line-height:1.5}.drive-authorization p{margin:0}.drive-authorization-link{color:var(--primary-foreground);background:var(--primary);border-radius:6px;padding:8px 12px;font-weight:500;text-decoration:none;justify-self:start}.drive-authorization form{display:flex;gap:8px}.drive-authorization form :global(input){min-width:0;flex:1}
</style>
