<script>
import {onMount,untrack} from 'svelte';
import {Button} from '$lib/components/ui/button';
import {Input} from '$lib/components/ui/input';
import {Textarea} from '$lib/components/ui/textarea';
import {Switch} from '$lib/components/ui/switch';
import {Plus,Scissors,Combine,Undo2,Image,Diamond,Play,RefreshCw,ClipboardPaste} from '@lucide/svelte';
import Field from './Field.svelte';
import MediaInputs from './MediaInputs.svelte';
import LoraStack from './LoraStack.svelte';
import ResolutionControls from './ResolutionControls.svelte';
import {readFile} from './bridge.js';
import {FPS,MAX_FRAMES,frameCount,seconds,uid,methodNames,initialTimeline,planTimeline,resourceRuns,mergeClips,splitClip,reorderClip,moveBoundary} from './h3Timeline.js';

let {panel,values=$bindable(),children,send,playhead=$bindable(0),onseek,onplay,hasPreview=false}=$props();
let selectedId=$state(''),checked=$state([]),view=$state('preview'),inspector=$state('segment'),resourceId=$state(''),notice=$state(''),undo=$state([]),drag=$state(null),picker;
let timeline=$derived(values.timeline?.clips?values.timeline:{clips:[],resources:[]});
let plan=$derived(planTimeline(timeline));
let selected=$derived(plan.find(c=>c.id===selectedId)||plan[0]);
let total=$derived(plan.at(-1)?.end||Number(values.duration)||0);
let axisEnd=$derived(Math.max(total,...plan.map(c=>c.sampleEnd))||1);
let busy=$derived(panel.busy||panel.initializing);
let allSources=$derived([...(values.references||[]).map(item=>({...item,resourceKind:'reference'})),...(values.loras||[]).map(item=>({...item,resourceKind:'lora'}))]);
let tracks=$derived(timeline.resources.map(resource=>({...resource,source:allSources.find(item=>item.id===resource.id)})).filter(resource=>resource.source));
let activeResource=$derived(tracks.find(r=>r.id===resourceId));
let resourceVersion=$derived(allSources.map(item=>item.id).join('|'));
let anchors=$derived([...(values.first_frame?[{id:'__first',time:0,data:values.first_frame,name:'首帧'}]:[]),...(values.guides||[]),...(values.last_frame?[{id:'__last',time:Math.max(0,total-1/FPS),data:values.last_frame,name:'尾帧'}]:[])]);
const clone=value=>JSON.parse(JSON.stringify(value));
const pct=time=>100*time/axisEnd;
const fmt=time=>Number(Number(time).toFixed(3));
const field=key=>panel.spec.fields.find(f=>f.key===key);
const act=(action,data={})=>send(action,{id:panel.id,...data});

function commit(next,{history=true}={}){
  const invalid=planTimeline(next).find(c=>c.sample>MAX_FRAMES);
  if(invalid){notice=`第 ${invalid.index+1} 段计算窗口 ${invalid.sample} 帧，单次上限 ${MAX_FRAMES} 帧`;return false;}
  if(history)undo=[...undo.slice(-9),clone(timeline)];
  values.timeline=next;values.duration=seconds(next.clips.reduce((n,c)=>n+frameCount(c.duration),0));
  notice='';return true;
}
function prepareSources(){
  for(const key of ['references','loras','guides'])if((values[key]||[]).some(item=>!item.id))values[key]=values[key].map(item=>item.id?item:{...item,id:uid()});
}
function syncResources(){
  if(!timeline.clips.length)return;
  prepareSources();
  const sources=[...(values.references||[]).map(item=>({...item,kind:'reference'})),...(values.loras||[]).map(item=>({...item,kind:'lora'}))];
  const missing=sources.filter(item=>!timeline.resources.some(r=>r.id===item.id)),removed=timeline.resources.some(r=>!sources.some(item=>item.id===r.id));
  if(!missing.length&&!removed)return;
  const next=clone(timeline);next.resources=next.resources.filter(r=>sources.some(item=>item.id===r.id));
  for(const source of missing)next.resources.push({id:source.id,kind:source.kind,segments:[selected?.id||next.clips[0].id],...(source.kind==='lora'?{weights:{[selected?.id||next.clips[0].id]:Number(source.strength)}}:{})});
  commit(next,{history:false});
}
$effect(()=>{resourceVersion;untrack(syncResources);});
onMount(()=>{
  prepareSources();
  if(!values.timeline?.clips?.length)values.timeline=initialTimeline(values);
  selectedId=values.timeline.clips[0]?.id||'';
  window.addEventListener('pointermove',pointerMove);window.addEventListener('pointerup',pointerUp);
  return()=>{window.removeEventListener('pointermove',pointerMove);window.removeEventListener('pointerup',pointerUp);};
});
function choose(id,event){selectedId=id;inspector='segment';if(event?.shiftKey&&checked.length){const indices=timeline.clips.map(c=>c.id),a=indices.indexOf(checked[0]),b=indices.indexOf(id);checked=indices.slice(Math.min(a,b),Math.max(a,b)+1);}view='segment';}
function patchClip(key,value){const next=clone(timeline),clip=next.clips.find(c=>c.id===selected.id);clip[key]=value;commit(next);}
function merge(){
  const indices=checked.length>1?checked.map(id=>timeline.clips.findIndex(c=>c.id===id)):[selected.index,Math.min(selected.index+1,timeline.clips.length-1)];
  const first=Math.min(...indices),last=Math.max(...indices);if(first===last)return;
  try{const next=mergeClips(timeline,first,last),id=next.clips[first].id;if(commit(next)){selectedId=id;checked=[];notice=`已合并 ${last-first+1} 段 · 沿用前段衔接参数，提示词与资源范围已合并`;}}catch(error){notice=error.message;}
}
function split(){const current=plan.find(c=>c.start<playhead&&playhead<c.end);if(current)commit(splitClip(timeline,current.id,playhead));else notice='把播放头移入分段后切分';}
function autoSplit(){const next=initialTimeline(values),old=plan;
  for(const resource of next.resources){const previous=timeline.resources.find(r=>r.id===resource.id);if(!previous)continue;resource.segments=[];for(const clip of planTimeline(next)){const source=old.find(c=>(clip.start+clip.end)/2<c.end)||old.at(-1);if(previous.segments.includes(source.id)){resource.segments.push(clip.id);if(resource.kind==='lora')resource.weights[clip.id]=previous.weights[source.id];}}}
  if(commit(next)){selectedId=next.clips[0].id;checked=[];}
}
function toggleResource(id,clipId){const next=clone(timeline),resource=next.resources.find(r=>r.id===id);resource.segments=resource.segments.includes(clipId)?resource.segments.filter(v=>v!==clipId):[...resource.segments,clipId];if(resource.kind==='lora'&&resource.weights[clipId]===undefined)resource.weights[clipId]=allSources.find(s=>s.id===id).strength;commit(next);}
function setScope(all){const next=clone(timeline),resource=next.resources.find(r=>r.id===resourceId);resource.segments=all?next.clips.map(c=>c.id):[selected.id];commit(next);}
function weight(id,value){const next=clone(timeline);next.resources.find(r=>r.id===resourceId).weights[id]=Number(value);commit(next);}
function chooseResource(resource){resourceId=resource.id;inspector=resource.kind==='lora'?'loras':'references';view='segment';}
function beginDrag(event,type,id,edge,run){if(busy||event.target.closest('input'))return;event.preventDefault();if(type==='clip')selectedId=id;const rect=event.currentTarget.closest('.h3-track').getBoundingClientRect();drag={type,id,edge,run,startX:event.clientX,width:rect.width,snapshot:clone(timeline),axis:axisEnd};}
function pointerMove(event){
  if(!drag)return;const delta=(event.clientX-drag.startX)/drag.width*drag.axis;
  if(drag.type==='clip'){
    const before=planTimeline(drag.snapshot),index=before.findIndex(c=>c.id===drag.id),clip=before[index];
    if(drag.edge==='left'&&index)commit(moveBoundary(drag.snapshot,index,clip.start+delta),{history:false});
    else if(drag.edge==='right'&&index<before.length-1)commit(moveBoundary(drag.snapshot,index+1,clip.end+delta),{history:false});
    else if(!drag.edge&&Math.abs(event.clientX-drag.startX)>5){const target=before.findIndex(c=>clip.start+clip.duration/2+delta<c.end);if(target>=0)commit(reorderClip(drag.snapshot,drag.id,target),{history:false});}
  }else{
    const next=clone(drag.snapshot),resource=next.resources.find(r=>r.id===drag.id),before=planTimeline(next),boundaries=[...before.map(c=>c.start),before.at(-1).end],nearest=t=>boundaries.reduce((best,v,i)=>Math.abs(v-t)<Math.abs(boundaries[best]-t)?i:best,0);
    let first=drag.run.first,last=drag.run.last+1;
    if(drag.edge==='left')first=Math.max(0,Math.min(last-1,nearest(drag.run.start+delta)));
    else if(drag.edge==='right')last=Math.max(first+1,Math.min(before.length,nearest(drag.run.end+delta)));
    else{const size=last-first;first=Math.max(0,Math.min(before.length-size,nearest(drag.run.start+delta)));last=first+size;}
    resource.segments=[...new Set([...resource.segments.filter(id=>!drag.run.ids.includes(id)),...before.slice(first,last).map(c=>c.id)])];commit(next,{history:false});
  }
}
function pointerUp(){if(drag){undo=[...undo.slice(-9),drag.snapshot];drag=null;}}
function seek(event){const rect=event.currentTarget.getBoundingClientRect();playhead=Math.max(0,Math.min(total,seconds(frameCount((event.clientX-rect.left)/rect.width*axisEnd))));onseek?.(playhead);}
async function addKeyframe(event){const file=event.currentTarget.files[0];if(file)values.guides=[...(values.guides||[]),{id:uid(),name:file.name,kind:'image',data:await readFile(file),time:seconds(frameCount(playhead))}];event.currentTarget.value='';}
function sourceName(resource){return allSources.find(item=>item.id===resource.id)?.name||'';}
function keyTime(anchor){return Math.min(total-1/FPS,Math.max(0,Number(anchor.time||0)));}
function chooseAnchor(anchor){inspector='anchors';view='segment';notice=anchor.name||'关键帧';}
async function pastePrompt(){try{patchClip('prompt',await navigator.clipboard.readText());}catch{notice='浏览器需要剪贴板读取权限';}}
</script>

<div class="h3-workbench" data-view={view} aria-label="H3 时间轴工作台">
  <nav class="h3-mobile-tabs" aria-label="H3 视图"><Button size="sm" variant={view==='preview'?'secondary':'ghost'} onclick={()=>view='preview'}>画面</Button><Button size="sm" variant={view==='segment'?'secondary':'ghost'} onclick={()=>view='segment'}>编辑</Button></nav>
  <div class="h3-top">
    <div class="h3-stage">{@render children()}</div>
    <aside class="h3-inspector">
      <nav class="h3-inspector-tabs" aria-label="时间轴属性">{#each [['segment','分段'],['references','参考'],['loras','LoRA'],['anchors','锚点'],['settings','参数']] as [id,label]}<Button size="sm" variant={inspector===id?'secondary':'ghost'} onclick={()=>inspector=id}>{label}</Button>{/each}</nav>
      <div class="h3-property-scroll">
      {#if inspector==='segment'&&selected}
        <div class="h3-heading"><strong>第 {selected.index+1} 段</strong><span>{fmt(selected.start)}–{fmt(selected.end)} s</span></div>
        <label class="field"><span>名称</span><Input value={selected.name} disabled={busy} onchange={e=>patchClip('name',e.currentTarget.value)}/></label>
        <label class="field"><span>输出时长 / 秒</span><Input type="number" min={1/FPS} step={1/FPS} value={fmt(selected.duration)} disabled={busy} onchange={e=>{patchClip('duration',seconds(frameCount(e.currentTarget.value)));e.currentTarget.value=fmt(selected.duration);}}/></label>
        <div class="field"><div class="h3-heading"><span>片段提示词</span><Button size="icon-sm" variant="ghost" aria-label="用剪贴板替换片段提示词" disabled={busy} onclick={pastePrompt}><ClipboardPaste size={13}/></Button></div><Textarea value={selected.prompt} rows={3} disabled={busy} onchange={e=>patchClip('prompt',e.currentTarget.value)}/></div>
        {#if selected.index}<label class="field"><span>与前段衔接</span><select value={selected.method} disabled={busy} onchange={e=>patchClip('method',e.currentTarget.value)}>{#each Object.entries(methodNames) as [value,label]}<option {value}>{label}</option>{/each}</select></label>{/if}
        {#if selected.index&&['motion','overlap'].includes(selected.method)}<div class="h3-two"><label class="field"><span>运动上下文 / 帧</span><select value={selected.context_frames} disabled={busy} onchange={e=>patchClip('context_frames',Number(e.currentTarget.value))}>{#each [5,22,39,56] as value}<option {value}>{value}</option>{/each}</select></label><label class="field"><span>音频上下文 / 帧</span><Input type="number" min={0} step={3} value={selected.audio_context_frames} disabled={busy} onchange={e=>patchClip('audio_context_frames',Number(e.currentTarget.value))}/></label></div>{/if}
        {#if selected.index&&selected.method==='overlap'}<label class="field"><span>图像混合 / 帧</span><Input type="number" min={0} step={1} value={selected.blend_frames} disabled={busy} onchange={e=>patchClip('blend_frames',Number(e.currentTarget.value))}/></label>{/if}
        <div class="h3-cost">交叠 {selected.carry}f ＋ 新增 {selected.frames}f ＋ 补齐 {selected.padding}f<br>计算 {selected.sample}f · {fmt(seconds(selected.sample))} s</div>
        <div class="h3-heading"><label for={'h3-audio-'+panel.id}>本段声音</label><Switch id={'h3-audio-'+panel.id} checked={selected.audio} disabled={busy} onCheckedChange={checked=>patchClip('audio',checked)}/></div>
      {:else if inspector==='references'||inspector==='loras'}
        {@const kind=inspector==='references'?'reference':'lora'}
        {#if activeResource?.kind===kind}
          <strong class="h3-resource-title">{activeResource.source.name}</strong>
          <div class="h3-heading"><span>生效段</span><div class="row"><Button size="xs" variant="ghost" disabled={busy} onclick={()=>setScope(false)}>当前段</Button><Button size="xs" variant="ghost" disabled={busy} onclick={()=>setScope(true)}>全片</Button></div></div>
          <div class="h3-segment-picks">{#each plan as clip}<Button size="xs" variant={activeResource.segments.includes(clip.id)?'secondary':'outline'} disabled={busy} onclick={()=>toggleResource(activeResource.id,clip.id)}>第 {clip.index+1} 段</Button>{/each}</div>
          {#if kind==='lora'}{#each plan.filter(c=>activeResource.segments.includes(c.id)) as clip}<label class="h3-weight"><span>第 {clip.index+1} 段权重</span><Input type="number" step={0.05} value={activeResource.weights[clip.id]??activeResource.source.strength} disabled={busy} onchange={e=>weight(clip.id,e.currentTarget.value)}/></label>{/each}{/if}
          <hr>
        {/if}
        {#if kind==='reference'}<MediaInputs bind:value={values.references} {busy} label="参考素材"/>{:else}<LoraStack bind:value={values.loras} options={field('loras').options} {busy} weightLabel="初始权重"/>{/if}
        <div class="h3-resource-list">{#each tracks.filter(r=>r.kind===kind) as resource}<Button size="sm" variant="ghost" onclick={()=>chooseResource(resource)}>{resource.source.name}</Button>{/each}</div>
      {:else if inspector==='anchors'}
        <Field field={field('first_frame')} bind:value={values.first_frame} {busy}/><Field field={field('last_frame')} bind:value={values.last_frame} {busy}/><MediaInputs bind:value={values.guides} timeline {busy} label="时间轴关键帧"/>
      {:else if inspector==='settings'}
        <Field field={field('output_type')} bind:value={values.output_type} {busy}/>
        <details class="settings-group"><summary>模型配置</summary><div class="settings-fields">{#each panel.spec.fields.filter(f=>f.area==='models') as definition}<Field field={definition} bind:value={values[definition.key]} {busy}/>{/each}<div class="row"><Button size="sm" variant="outline" onclick={()=>act('refresh')}><RefreshCw size={13}/>刷新</Button><Button size="sm" variant="outline" disabled={busy} onclick={()=>act('unload_models')}>卸载模型</Button></div></div></details>
        <Field field={field('negative_prompt')} bind:value={values.negative_prompt} {busy} paste/>
        <ResolutionControls presets={panel.spec.size_presets} bind:values {busy}/>
        <div class="h3-two">{#each ['steps','cfg','sampler','scheduler','seed'] as key}<Field field={field(key)} bind:value={values[key]} {busy}/>{/each}</div>
        <details class="settings-group"><summary>高级设置</summary><div class="settings-fields">{#each panel.spec.fields.filter(f=>f.area==='advanced'&&!['context_frames','audio_context_frames'].includes(f.key)) as definition}<Field field={definition} bind:value={values[definition.key]} {busy}/>{/each}</div></details>
      {/if}
      </div>
    </aside>
  </div>
  <section class="h3-timeline" aria-label="视频时间轴">
    <div class="h3-tools"><Button size="sm" variant="outline" disabled={busy} onclick={()=>picker.click()}><Plus size={13}/>关键帧</Button><Button size="sm" variant="outline" disabled={busy} onclick={split}><Scissors size={13}/>切分</Button><Button size="sm" variant="outline" disabled={busy||!selected||(checked.length<2&&selected.index===plan.length-1)} onclick={merge}><Combine size={13}/>合并</Button><Button size="icon-sm" variant="ghost" aria-label="撤销时间轴编辑" disabled={busy||!undo.length} onclick={()=>{const last=undo.at(-1);undo=undo.slice(0,-1);commit(last,{history:false});selectedId=last.clips[0].id;checked=[];}}><Undo2 size={14}/></Button><span class="h3-tool-spacer"></span><label class="h3-duration">总长<Input type="number" min={1} value={fmt(total)} disabled={busy} onchange={e=>{values.duration=Number(e.currentTarget.value);autoSplit();}}/>s</label><div class="h3-auto"><select aria-label="自动分段方式" bind:value={values.long_video} disabled={busy}><option value="motion">运动上下文</option><option value="tail_frame">末帧续写</option><option value="overlap">上下文＋淡化</option><option value="shots">独立分镜</option><option value="single">最长单段</option></select><Input type="number" aria-label="自动分段时长" min={1} max={15} bind:value={values.segment_seconds} disabled={busy}/><Button size="sm" variant="ghost" disabled={busy} onclick={autoSplit}>重新分段</Button></div></div>
    <input hidden type="file" accept="image/*" bind:this={picker} onchange={addKeyframe}/>
    <div class="h3-legend"><span><i class="h3-blue"></i>交叠引用</span><span><i class="h3-orange"></i>图像混合</span><span><i class="h3-gray"></i>补齐裁剪</span></div>
    <div class="h3-ruler-row"><span class="h3-label">24 fps</span><div class="h3-track h3-ruler" role="slider" aria-label="视频播放位置" aria-valuemin={0} aria-valuemax={total} aria-valuenow={playhead} onclick={seek} onkeydown={e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){playhead=Math.max(0,Math.min(total,playhead+(e.key==='ArrowRight'?1:-1)/FPS));onseek?.(playhead);}}} tabindex="0">{#each [0,...plan.map(c=>c.end)] as time,index}<span style:left={pct(time)+'%'} class:edge={index===0} class:last={index===plan.length}>{plan.length<6||index===0||index===plan.length?fmt(time)+'s':''}</span>{/each}</div></div>
    <div class="h3-tracks">
      <div class="h3-lane"><span class="h3-label">分段</span><div class="h3-track">{#each plan as clip (clip.id)}<button class="h3-clip" class:selected={selected?.id===clip.id} aria-label={'第 '+(clip.index+1)+' 段 '+clip.name} style:left={pct(clip.start)+'%'} style:width={pct(clip.duration)+'%'} disabled={busy} onpointerdown={e=>beginDrag(e,'clip',clip.id,e.target.dataset.edge)} onclick={e=>choose(clip.id,e)}><span class="h3-edge left" data-edge="left"></span><input type="checkbox" aria-label={'选择第 '+(clip.index+1)+' 段合并'} checked={checked.includes(clip.id)} onclick={e=>e.stopPropagation()} onchange={e=>checked=e.currentTarget.checked?[...checked,clip.id]:checked.filter(id=>id!==clip.id)}/><span class="h3-clip-copy"><strong>{clip.index+1} · {clip.name}</strong><small>输出 {clip.frames}f / 计算 {clip.sample}f</small></span><span class="h3-edge right" data-edge="right"></span></button>{/each}</div></div>
      <div class="h3-lane h3-transition"><span class="h3-label">衔接</span><div class="h3-track">{#each plan as clip}{#if clip.carry}<button class="h3-context" aria-label={'第 '+(clip.index+1)+' 段交叠 '+clip.carry+' 帧'} title={'历史 '+fmt(clip.sampleStart)+'–'+fmt(clip.start)+'s · '+clip.carry+'f'} style:left={pct(clip.sampleStart)+'%'} style:width={pct(seconds(clip.carry))+'%'} onclick={()=>choose(clip.id)}></button>{/if}{#if clip.padding}<button class="h3-padding" aria-label={'第 '+(clip.index+1)+' 段补齐 '+clip.padding+' 帧'} style:left={pct(clip.end)+'%'} style:width={pct(seconds(clip.padding))+'%'} onclick={()=>choose(clip.id)}></button>{/if}{#if clip.index&&clip.method==='overlap'&&clip.blend_frames}<button class="h3-mix" aria-label={'第 '+(clip.index+1)+' 段混合 '+clip.blend_frames+' 帧'} style:left={pct(clip.start)+'%'} style:width={pct(seconds(Math.min(clip.frames,clip.blend_frames)))+'%'} onclick={()=>choose(clip.id)}></button>{/if}{#if clip.index&&clip.method==='shots'}<button class="h3-cut" style:left={pct(clip.start)+'%'} aria-label={'切换到第 '+(clip.index+1)+' 段'} onclick={()=>choose(clip.id)}>切</button>{/if}{/each}</div></div>
      <div class="h3-lane h3-anchors"><span class="h3-label">锚点</span><div class="h3-track">{#each anchors as anchor}<button class="h3-anchor" style:left={pct(keyTime(anchor))+'%'} aria-label={anchor.name+' · '+fmt(keyTime(anchor))+'秒'} onclick={()=>chooseAnchor(anchor)}>{#if anchor.data?.startsWith('data:image/')}<img src={anchor.data} alt={anchor.name}/>{:else}<Image size={14}/>{/if}</button>{/each}{#each plan.filter(c=>c.index&&(c.method==='tail_frame'||c.method==='overlap')) as clip}<button class="h3-anchor h3-reference-point" style:left={pct(clip.start-1/FPS)+'%'} aria-label={'第 '+(clip.index+1)+' 段引用上一段尾帧'} onclick={()=>choose(clip.id)}><Diamond size={12}/></button>{/each}</div></div>
      {#each tracks as resource (resource.id)}<div class="h3-lane h3-resource"><span class="h3-label">{resource.kind==='lora'?'LoRA':'参考'}</span><div class="h3-track">{#each resourceRuns(timeline,resource) as run}<button class="h3-resource-bar" style:left={pct(run.start)+'%'} style:width={pct(run.end-run.start)+'%'} aria-label={resource.source.name+' 第 '+(run.first+1)+'至'+(run.last+1)+'段'} disabled={busy} onpointerdown={e=>beginDrag(e,'resource',resource.id,e.target.dataset.edge,run)} onclick={()=>chooseResource(resource)}><span class="h3-edge left" data-edge="left"></span><span>{resource.source.name}</span><small>{resource.kind==='lora'?run.ids.map(id=>resource.weights[id]??resource.source.strength).join(' / '):'第 '+(run.first+1)+'–'+(run.last+1)+' 段'}</small><span class="h3-edge right" data-edge="right"></span></button>{/each}</div></div>{/each}
      <div class="h3-lane h3-audio"><span class="h3-label">音频</span><div class="h3-track">{#each plan as clip}<button class="h3-resource-bar" style:left={pct(clip.start)+'%'} style:width={pct(clip.duration)+'%'} class:muted={!clip.audio} onclick={()=>choose(clip.id)}>{clip.index+1} · {clip.audio?'同步音频':'静音'}</button>{#if clip.index&&['motion','overlap'].includes(clip.method)}<span class="h3-audio-carry" style:left={pct(clip.start-seconds(clip.audio_context_frames||clip.carry))+'%'} style:width={pct(seconds(clip.audio_context_frames||clip.carry))+'%'}></span>{/if}{/each}</div></div>
      <div class="h3-playhead-area"><span class="h3-playhead" style:left={pct(playhead)+'%'}></span></div>
    </div>
    <div class="h3-timeline-footer"><Button size="icon-sm" variant="ghost" aria-label="播放生成视频" disabled={!hasPreview} onclick={onplay}><Play size={13}/></Button><Input type="range" aria-label="播放头" min={0} max={total} step={1/FPS} value={playhead} oninput={e=>{playhead=Number(e.currentTarget.value);onseek?.(playhead);}}/><span>{fmt(playhead)} / {fmt(total)} s</span><span class="h3-edit-notice" role="status">{notice||plan.length+' 段 · '+frameCount(total)+' 输出帧'}</span></div>
  </section>
</div>

<style>
.h3-workbench{--h3-label:54px;display:flex;flex-direction:column;flex:1;min-height:0;min-width:0;background:#fff;color:#242b35;color-scheme:light}.h3-top{display:grid;grid-template-columns:minmax(0,1fr) 286px;flex:1;min-height:180px}.h3-stage{min-height:0;min-width:0;display:flex}.h3-stage :global(.generation-output){grid-column:auto;grid-row:auto;flex:1;min-width:0;padding:8px 12px}.h3-stage :global(.generation-canvas){min-height:100px}.h3-inspector{display:flex;flex-direction:column;border-left:1px solid var(--border);min-height:0;background:#fff}.h3-inspector-tabs{display:flex;padding:5px 6px;gap:1px;border-bottom:1px solid var(--border);flex-shrink:0}.h3-inspector-tabs :global(button){font-size:11px;padding-inline:7px;flex:1}.h3-property-scroll{display:flex;flex-direction:column;gap:9px;padding:10px;overflow:auto;min-height:0}.h3-heading{display:flex;align-items:center;justify-content:space-between;gap:6px;font-size:11px}.h3-heading>span{color:#788493}.h3-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}.h3-cost{background:#f4f6f8;border-radius:5px;padding:6px 8px;font-size:11px;color:#647184;font-variant-numeric:tabular-nums;line-height:1.7}.h3-resource-title{font-size:12px;overflow-wrap:anywhere}.h3-segment-picks{display:flex;gap:4px;flex-wrap:wrap}.h3-weight{display:grid;grid-template-columns:1fr 76px;gap:7px;align-items:center;font-size:11px}.h3-resource-list{display:grid;gap:3px}.h3-resource-list :global(button){height:auto;min-height:28px;white-space:normal;word-break:break-word;justify-content:flex-start;text-align:left;font-size:11px}hr{border:0;border-top:1px solid var(--border);margin:0}.h3-mobile-tabs{display:none}.h3-timeline{flex-shrink:0;border-top:1px solid var(--border);background:#fff;max-height:52%;overflow:auto}.h3-tools{display:flex;align-items:center;gap:5px;flex-wrap:wrap;padding:6px 8px}.h3-tools :global(button){font-size:11px}.h3-tool-spacer{flex:1}.h3-duration,.h3-auto{display:flex;align-items:center;gap:5px;font-size:11px}.h3-duration :global(input){width:57px;height:28px;font-size:11px;padding-inline:5px}.h3-auto select{width:112px;height:28px;font-size:11px}.h3-auto :global(input){width:42px;height:28px;font-size:11px;padding-inline:4px}.h3-legend{display:flex;gap:10px;padding:0 8px 5px;font-size:10px;color:#788493;flex-wrap:wrap}.h3-legend span{display:flex;align-items:center;gap:4px}.h3-legend i{width:11px;height:6px;border-radius:1px}.h3-blue{background:#81a6c0}.h3-orange{background:linear-gradient(90deg,#b98643,#eed9b6)}.h3-gray{background:#aab1bb}.h3-ruler-row{display:flex;height:24px;background:#f6f7f9;border-block:1px solid var(--border)}.h3-label{width:var(--h3-label);flex-shrink:0;padding:0 7px;display:flex;align-items:center;font-size:10px;color:#788493}.h3-track{position:relative;flex:1;min-width:0;margin-right:10px}.h3-ruler span{position:absolute;top:5px;transform:translateX(-50%);font-size:10px;font-variant-numeric:tabular-nums;white-space:nowrap}.h3-ruler .edge{transform:none}.h3-ruler .last{transform:translateX(-100%)}.h3-tracks{position:relative}.h3-lane{display:flex;height:38px;border-bottom:1px solid #edf0f3}.h3-lane:first-child{height:46px}.h3-clip,.h3-resource-bar{position:absolute;top:4px;bottom:4px;display:flex;align-items:center;gap:6px;min-width:0;padding:4px 8px;border:1px solid #dfe5eb;border-radius:4px;background:#edf2f6;color:#334155;text-align:left;overflow:hidden;touch-action:none;cursor:grab}.h3-clip.selected{border-color:#6e93ae;box-shadow:inset 0 0 0 1px #6e93ae;background:#e7eff5}.h3-clip input{width:12px;height:12px;accent-color:#597e99;flex-shrink:0}.h3-clip-copy{min-width:0;display:flex;flex-direction:column;gap:1px}.h3-clip-copy strong{font-size:11px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.h3-clip-copy small{font-size:10px;color:#788493;white-space:nowrap}.h3-edge{position:absolute;top:0;bottom:0;width:7px;cursor:ew-resize}.h3-edge.left{left:0}.h3-edge.right{right:0}.h3-transition{height:24px;background:#f8fafb}.h3-context,.h3-padding,.h3-mix{position:absolute;border:0;padding:0;border-radius:2px}.h3-context{top:4px;height:7px;background:#82a8c2}.h3-padding{bottom:4px;height:5px;background:#abb3bc}.h3-mix{top:4px;height:7px;background:linear-gradient(90deg,#b98643,#eed9b6)}.h3-cut{position:absolute;transform:translateX(-50%);height:18px;top:3px;width:17px;padding:0;border:1px solid var(--border);background:white;border-radius:3px;font-size:10px;color:#647184}.h3-anchor{position:absolute;top:5px;width:27px;height:27px;transform:translateX(-50%);display:grid;place-items:center;background:#f6f8fa;border:1px solid #dfe5eb;border-radius:4px;padding:2px;overflow:hidden}.h3-anchor img{width:100%;height:100%;object-fit:cover}.h3-reference-point{width:19px;height:19px;top:9px;background:#fff;color:#668aa5}.h3-resource{height:32px}.h3-resource-bar{font-size:10px;white-space:nowrap;gap:5px}.h3-resource-bar>span:not(.h3-edge){overflow:hidden;text-overflow:ellipsis}.h3-resource-bar small{font-size:10px;opacity:.7;flex-shrink:0}.h3-audio{height:30px}.h3-audio .h3-resource-bar{cursor:pointer}.h3-audio .muted{opacity:.4}.h3-audio-carry{position:absolute;bottom:2px;height:3px;background:#9a7bac;pointer-events:none}.h3-playhead-area{position:absolute;left:var(--h3-label);right:10px;top:0;bottom:0;pointer-events:none}.h3-playhead{position:absolute;top:-24px;bottom:0;width:1px;background:#5d88a7}.h3-playhead:before{content:'';position:absolute;width:7px;height:6px;left:-3px;top:0;background:#5d88a7;border-radius:0 0 2px 2px}.h3-timeline-footer{display:flex;gap:6px;align-items:center;padding:4px 8px;min-height:30px;font-size:10px;color:#788493}.h3-timeline-footer :global(input[type=range]){width:90px;height:22px;padding:0;border:0;box-shadow:none;accent-color:#6e93ae}.h3-edit-notice{margin-left:auto;text-align:right;overflow-wrap:anywhere;min-width:0}.h3-resource-list{max-width:100%}
.h3-property-scroll{overflow-x:hidden}
@media(max-width:760px){.h3-mobile-tabs{display:flex;border-bottom:1px solid var(--border);padding:3px 7px;gap:3px;flex-shrink:0}.h3-mobile-tabs :global(button){height:27px;font-size:11px}.h3-top{display:flex;min-height:150px}.h3-stage{flex:1}.h3-inspector{flex:1;border-left:0}.h3-workbench[data-view=preview] .h3-inspector,.h3-workbench[data-view=segment] .h3-stage{display:none}.h3-property-scroll{padding:8px 10px}.h3-timeline{max-height:48%}.h3-tools{gap:4px;padding:5px 6px}.h3-tools :global(button){font-size:10px;padding-inline:6px;height:27px}.h3-auto{width:100%;order:2}.h3-auto select{flex:1;width:auto;min-width:0}.h3-duration{margin-left:auto}.h3-clip{padding:4px 5px;gap:4px}.h3-clip-copy small{display:none}.h3-clip-copy strong{font-size:10px}.h3-clip input{width:11px;height:11px}.h3-label{padding-inline:5px}.h3-timeline-footer :global(input[type=range]){width:65px}.h3-edit-notice{font-size:10px}.h3-resource-bar small{display:none}.h3-stage :global(.generation-output){padding:6px 8px}.h3-stage :global(.generation-canvas){min-height:120px}.h3-legend{gap:8px}}
</style>
