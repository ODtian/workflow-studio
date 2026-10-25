<script>
import {Button} from '$lib/components/ui/button';import {Badge} from '$lib/components/ui/badge';import {Progress} from '$lib/components/ui/progress';import {Textarea} from '$lib/components/ui/textarea';
import {Play,Square,Download,Image,History,SlidersHorizontal,ChevronDown,RefreshCw,Copy,Maximize2} from '@lucide/svelte';
import Field from './Field.svelte';import ResolutionControls from './ResolutionControls.svelte';import ZoomPreview from './ZoomPreview.svelte';import ImageHistory from './ImageHistory.svelte';
let {panel,values=$bindable(),preview='',previewInfo={},text='',results=[],send,history=[],loadThumbnail,loadPreview,targets=[],onTransfer,loadOriginal,mode='full'}=$props();
let tab=$state('preview'),imageIndex=$state(0),modelsOpen=$state(false),displayMs=$state(0);
let mobileView=$state('settings');
let requestedRun=$state(''),totalMs=$state(0),elapsedMs=$state(0);
let requestStartedAt=0;
let fields=$derived(panel.spec.fields||[]),parameterFields=$derived(fields.filter(f=>!f.area)),groups=$derived([...new Set(parameterFields.map(f=>f.section||'参数'))]);
let isText=$derived(panel.spec.output==='text'),activeResult=$derived(results[imageIndex]);
const act=(action,data={})=>send(action,{id:panel.id,...data});let receivedAt=0;
$effect(()=>{if(preview)receivedAt=performance.now();});$effect(()=>{results;imageIndex=0;});
function generate(){
  requestedRun=crypto.randomUUID();requestStartedAt=performance.now();totalMs=0;elapsedMs=0;displayMs=0;
  tab='preview';mobileView='preview';act('run',{run_id:requestedRun,params:{...values}});
}
$effect(()=>{
  if(!requestedRun||totalMs||['error','cancelled'].includes(panel.phase))return;
  const timer=setInterval(()=>elapsedMs=performance.now()-requestStartedAt,100);
  return()=>clearInterval(timer);
});
async function loaded(event){
  const frame=previewInfo,source=preview,image=event.currentTarget;
  if(!frame.final||frame.run_id!==requestedRun||!requestStartedAt||totalMs)return;
  await image.decode();
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  if(image.currentSrc!==source||frame.run_id!==requestedRun)return;
  displayMs=Math.round(performance.now()-receivedAt);totalMs=Math.round(performance.now()-requestStartedAt);
  act('displayed',{run_id:frame.run_id,ms:displayMs,end_to_end_ms:totalMs,server_ms:frame.server_ms});
}
let timingLabel=$derived(requestedRun&&!totalMs&&!['error','cancelled'].includes(panel.phase)
  ? `${(elapsedMs/1000).toFixed(1)} s`
  : totalMs||panel.end_to_end_ms ? `总 ${((totalMs||panel.end_to_end_ms)/1000).toFixed(1)} s`
  : panel.elapsed ? `后端 ${panel.elapsed.toFixed(1)} s` : '');
</script>
<article class="generation-workspace" data-mobile-view={mobileView} aria-label={panel.spec.name}>
  <nav class="mobile-generation-tabs" aria-label="生成视图"><Button variant={mobileView==='settings'?'secondary':'ghost'} aria-pressed={mobileView==='settings'} onclick={()=>mobileView='settings'}><SlidersHorizontal size={16}/>参数</Button><Button variant={mobileView==='preview'?'secondary':'ghost'} aria-pressed={mobileView==='preview'} onclick={()=>mobileView='preview'}><Image size={16}/>预览与历史{#if panel.busy}<i class="status-dot pulse"></i>{/if}</Button></nav>
  <section class="generation-controls">
    <div class="controls-scroll">
      <details class="models-panel" bind:open={modelsOpen}><summary title={panel.spec.model_root}><SlidersHorizontal size={15}/><span>模型配置</span><ChevronDown size={14}/></summary><div class="settings-fields">{#each fields.filter(f=>f.area==='models') as field}<Field {field} bind:value={values[field.key]} busy={panel.busy}/>{/each}<Button variant="outline" size="sm" onclick={()=>act('refresh')}><RefreshCw size={13}/>刷新模型列表</Button></div></details>
      <div class="generation-prompts">{#each fields.filter(f=>f.area==='prompts') as field}<div class:secondary-prompt={field.key==='negative_prompt'}><Field field={{...field,rows:field.key==='negative_prompt'?1:Math.min(field.rows||3,3)}} bind:value={values[field.key]} busy={panel.busy} paste/></div>{/each}</div>
      {#each groups as group}<details class="settings-group" open><summary>{group}<ChevronDown size={13}/></summary><div class="parameter-grid">
      {#if panel.spec.size_presets?.section===group}<div class="wide"><ResolutionControls presets={panel.spec.size_presets} bind:values busy={panel.busy}/></div>{/if}
      {#each parameterFields.filter(f=>(f.section||'参数')===group) as field}<div class:wide={['boolean','text','textarea','image','lora_stack'].includes(field.type)}><Field {field} bind:value={values[field.key]} busy={panel.busy}/></div>{/each}</div></details>{/each}
      {#if fields.some(f=>f.area==='advanced')}<details class="settings-group"><summary>高级设置<ChevronDown size={13}/></summary><div class="settings-fields">{#each fields.filter(f=>f.area==='advanced') as field}<Field {field} bind:value={values[field.key]} busy={panel.busy}/>{/each}</div></details>{/if}
    </div>
  </section>
  <section class="generation-output">
    <div class="output-toolbar"><div class="segmented"><Button variant={tab==='preview'?'secondary':'ghost'} size="sm" onclick={()=>tab='preview'}><Image size={14}/>预览</Button><Button variant={tab==='history'?'secondary':'ghost'} size="sm" onclick={()=>tab='history'}><History size={14}/>历史 <span class="count">{history.length}</span></Button></div><div class="row">{#if activeResult}<Badge variant="outline">{activeResult.width} × {activeResult.height}</Badge>{/if}<Button variant="outline" size="sm" disabled={!activeResult} onclick={()=>act('download',{name:activeResult.name})}><Download size={14}/>下载原图</Button></div></div>
    {#if tab==='history'}<div class="history-content"><ImageHistory {history} {loadThumbnail} {loadPreview} download={r=>act('download',{name:r.name})}/></div>
    {:else}<div class="generation-canvas" class:working={panel.busy}>
      {#if isText}<Textarea value={text} readonly rows={20} aria-label="文本结果"/>{:else}<ZoomPreview {preview} result={activeResult} {loadOriginal} onload={loaded}/>{/if}
    </div>
    <div class="generation-bottom"><Progress value={panel.step} max={panel.total||1} aria-label="执行进度"/><div class="output-status"><div class="row"><i class="status-dot" class:pulse={panel.busy}></i><span role="status">{requestedRun&&requestedRun!==panel.run_id?'提交任务…':panel.message}{panel.busy&&panel.total?` · ${panel.step}/${panel.total}`:''}</span></div><span title="点击生成至最终图片显示">{timingLabel}</span></div>
    {#if results.length>1}<div class="row">{#each results as result,index}<Button size="sm" variant={imageIndex===index?'secondary':'ghost'} onclick={()=>{imageIndex=index;act('show_result',{name:result.name});}}>图片 {index+1}</Button>{/each}</div>{/if}
    {#if Object.keys(panel.metadata||{}).length}<details class="run-info"><summary>运行信息<ChevronDown size={12}/></summary><dl>{#each Object.entries(panel.metadata||{}) as [key,value]}<div><dt>{key}</dt><dd>{String(value)}</dd></div>{/each}</dl></details>{/if}</div>{/if}
  </section>
  <div class="generation-runbar">{#if panel.initializing}<p class="hint">{panel.initialization}</p>{/if}<div class="row"><Button class="generate-button" size="lg" disabled={panel.busy||panel.spec.ready===false} onclick={generate}><Play size={15}/>{panel.busy?'正在生成…':panel.spec.run_label||'生成图片'}</Button><Button size="lg" variant="outline" disabled={!panel.busy} onclick={()=>act('cancel')}><Square size={13}/>停止</Button></div></div>
</article>
