<script>
  import {Button} from '$lib/components/ui/button';
  import {Input} from '$lib/components/ui/input';
  import {Switch} from '$lib/components/ui/switch';
  import {Plus, X, Image, Film, Music, ClipboardPaste} from '@lucide/svelte';
  import {readFile} from './bridge.js';
  let {value=$bindable([]), timeline=false, busy=false, label='参考素材'}=$props();
  let picker, path=$state(''), time=$state(0), error=$state('');
  const kindOf = file => file.type?.startsWith('video/') || /\.(mp4|webm|mov|mkv)$/i.test(file.name) ? 'video'
    : file.type?.startsWith('audio/') || /\.(wav|mp3|flac|ogg|m4a)$/i.test(file.name) ? 'audio' : 'image';
  function tag(item,index) {
    if(timeline)return `${item.time||0} s`;
    const ordinal=value.slice(0,index+1).filter(v=>v.kind===item.kind).length;
    const videoAudio=value.filter(v=>v.kind==='video'&&v.include_audio).length;
    const label=`<${{image:'Picture',video:'Video',audio:'Audio'}[item.kind]} ${ordinal+(item.kind==='audio'?videoAudio:0)}>`;
    return item.kind==='video'&&item.include_audio ? label+` · <Audio ${value.slice(0,index+1).filter(v=>v.kind==='video'&&v.include_audio).length}>` : label;
  }
  async function addFiles(files) {
    error='';
    try {
      const added=[];
      for(const file of files) added.push({name:file.name,kind:kindOf(file),data:await readFile(file),...(timeline?{time:Number(time)}:{})});
      value=[...(value||[]),...added];
    } catch(e) {error=String(e.message||e);}
  }
  async function pasteImage() {
    error='';
    try {
      for(const item of await navigator.clipboard.read()) {
        const type=item.types.find(type=>type.startsWith('image/'));
        if(type) await addFiles([new File([await item.getType(type)],'clipboard.png',{type})]);
      }
    } catch {error='请使用上传按钮，或在素材区域粘贴图片';}
  }
  function addPath() {
    if(!path.trim())return;
    const name=path.trim().split(/[\\/]/).at(-1);
    value=[...(value||[]),{name,path:path.trim(),kind:kindOf({name}),...(timeline?{time:Number(time)}:{})}];
    path='';
  }
</script>
<div class="media-inputs" aria-label={label} onpaste={event=>{const files=[...event.clipboardData.files];if(files.length){event.preventDefault();addFiles(files);}}}>
  <input hidden type="file" accept="image/*,video/*,audio/*" multiple bind:this={picker} onchange={async()=>{await addFiles(picker.files);picker.value='';}}/>
  <div class="media-actions">
    {#if timeline}<Input type="number" aria-label="关键帧时间 / 秒" title="时间 / 秒" min={0} step={0.1} bind:value={time} disabled={busy}/>{/if}
    <Button size="sm" variant="outline" disabled={busy} onclick={()=>picker.click()}><Plus size={13}/>{timeline?'添加关键帧':'添加素材'}</Button>
    <Button size="icon-sm" variant="ghost" aria-label={'粘贴'+label} title="粘贴图片" disabled={busy} onclick={pasteImage}><ClipboardPaste size={14}/></Button>
  </div>
  {#each value||[] as item,index}
    <div class="media-item">
      <div class="media-thumb">{#if item.kind==='image'&&item.data}<img src={item.data} alt={item.name}/>{:else if item.kind==='video'}<Film size={20}/>{:else if item.kind==='audio'}<Music size={20}/>{:else}<Image size={20}/>{/if}</div>
      <div class="media-name"><span title={item.path||item.name}>{item.name}</span><code>{tag(item,index)}</code></div>
      {#if item.kind==='video'&&!timeline}<Switch aria-label={'引用视频声音 '+item.name} title="引用视频声音" checked={item.include_audio||false} disabled={busy} onCheckedChange={checked=>value=value.map((v,i)=>i===index?{...v,include_audio:checked}:v)}/>{/if}
      {#if timeline}<Input type="number" aria-label={'关键帧时间 '+(index+1)} min={0} step={0.1} value={item.time||0} disabled={busy} oninput={event=>value=value.map((v,i)=>i===index?{...v,time:Number(event.currentTarget.value)}:v)}/>{/if}
      <Button size="icon-sm" variant="ghost" aria-label={'移除 '+item.name} disabled={busy} onclick={()=>value=value.filter((_,i)=>i!==index)}><X size={13}/></Button>
    </div>
  {/each}
  <details class="media-path"><summary>容器路径</summary><div class="media-actions"><Input bind:value={path} placeholder="图片、视频或音频路径" aria-label={label+'路径'} disabled={busy} onkeydown={event=>{if(event.key==='Enter')addPath();}}/><Button size="icon-sm" variant="outline" aria-label={'添加'+label+'路径'} disabled={busy||!path.trim()} onclick={addPath}><Plus size={13}/></Button></div></details>
  {#if error}<small role="alert">{error}</small>{/if}
</div>
<style>
  .media-inputs{display:flex;flex-direction:column;gap:6px;min-width:0}.media-actions{display:flex;align-items:center;gap:5px}.media-actions :global(input[type=number]){width:76px}.media-item{display:flex;gap:8px;align-items:center;border:1px solid var(--border);border-radius:7px;padding:5px;min-width:0}.media-thumb{width:36px;height:36px;flex-shrink:0;display:grid;place-items:center;color:#8491a3;background:#f1f4f8;border-radius:4px;overflow:hidden}.media-thumb img{width:100%;height:100%;object-fit:cover}.media-name{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.media-name span{font-size:11px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.media-name code{font-size:10px;color:#85909f}.media-item :global(input){width:70px}.media-path summary{font-size:10px;color:#85909f;cursor:pointer;padding:3px 0}.media-path .media-actions{margin-top:4px}
</style>
