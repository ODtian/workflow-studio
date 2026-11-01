<script>
  import {untrack} from 'svelte';
  import {Button} from '$lib/components/ui/button';
  import {Switch} from '$lib/components/ui/switch';
  import {Minus,Plus} from '@lucide/svelte';
  import ZoomSurface from './ZoomSurface.svelte';
  import {zoomViewport} from './imageViewport.js';
  import ComparisonPane from './ComparisonPane.svelte';
  let {entries=[],loadOriginal,loadPreview,thumbnails={},expanded=false}=$props();
  let sources=$state({}),shared=$state({zoom:1,x:0,y:0}),views=$state({}),synchronized=$state(true),columns=$state(2);
  let mode=$state('side'),cuts=$state([]);
  let maskStage=$state(null);let dragging=-1;
  $effect(()=>{cuts=entries.slice(1).map((_,index)=>(index+1)*100/entries.length);});
  let layoutColumns=$derived(Math.min(columns,entries.length));
  $effect(()=>{
    const selected=entries;let active=true;
    untrack(()=>{for(const entry of selected){
      if(!sources[entry.name])sources[entry.name]=thumbnails[entry.name]||'';
      let original=false;
      loadPreview(entry).then(image=>{if(active&&!original)sources[entry.name]=image.url;});
      loadOriginal(entry).then(image=>{original=true;if(active)sources[entry.name]=image.url;});
    }});
    return()=>{active=false;};
  });
  function change(name,view){if(synchronized)shared=view;else views[name]=view;}
  function toggleSync(value){if(!value)views=Object.fromEntries(entries.map(entry=>[entry.name,{...shared}]));else shared=views[entries[0].name]||shared;synchronized=value;}
  function reset(){shared={zoom:1,x:0,y:0};views={};}
  function setCut(index,value){
    const left=index?cuts[index-1]+.1:0,right=index+1<cuts.length?cuts[index+1]-.1:100;
    cuts[index]=Math.max(left,Math.min(right,value));
  }
  function dragStart(event,index){dragging=index;event.currentTarget.setPointerCapture(event.pointerId);}
  function dragMove(event,index){if(dragging!==index)return;const bounds=maskStage.getBoundingClientRect();setCut(index,(event.clientX-bounds.left)/bounds.width*100);}
  function dividerKey(event,index){if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();setCut(index,cuts[index]+(event.key==='ArrowLeft'?-1:1));}}

</script>
<section class="comparison" class:expanded aria-label={entries.length+' 张图片对比'}>
  <div class="comparison-toolbar"><strong>对比 {entries.length} 张</strong>
    <div class="segmented"><Button size="sm" variant={mode==='side'?'secondary':'ghost'} aria-pressed={mode==='side'} onclick={()=>mode='side'}>并排</Button><Button size="sm" variant={mode==='mask'?'secondary':'ghost'} aria-pressed={mode==='mask'} onclick={()=>mode='mask'}>遮罩</Button></div>
    {#if mode==='side'}<label class="sync-control"><Switch checked={synchronized} onCheckedChange={toggleSync} aria-label="同步缩放和平移"/>同步缩放 / 平移</label><label class="column-control">每行<select aria-label="对比每行图片数" bind:value={columns}>{#each entries as _,index}<option value={index+1}>{index+1} 张</option>{/each}</select></label>
    {:else}<div class="mask-zoom"><Button size="icon-sm" variant="ghost" aria-label="缩小遮罩图片" onclick={()=>shared=zoomViewport(shared,shared.zoom/1.25)}><Minus size={13}/></Button><output aria-label="遮罩缩放">{Math.round(shared.zoom*100)}%</output><Button size="icon-sm" variant="ghost" aria-label="放大遮罩图片" onclick={()=>shared=zoomViewport(shared,shared.zoom*1.25)}><Plus size={13}/></Button></div>{/if}
    <Button size="sm" variant="outline" onclick={reset}>全部适应</Button><span class="hint">{mode==='mask'?'拖动分界线 · 滚轮 / 双指缩放 · 拖动图片平移':'滚轮 / 双指缩放 · 拖动平移'}</span>
  </div>
  {#if mode==='mask'}
    <section class="mask-stage" bind:this={maskStage} aria-label={entries.length+' 张图片遮罩对比'}>
      <ZoomSurface view={shared} onchange={view=>shared=view} label="遮罩图片画布，滚轮或双指缩放，拖动平移">
        {#each entries as entry,index (entry.name)}
          {@const left=index?cuts[index-1]:0}
          {@const right=index<cuts.length?cuts[index]:100}
          <span class="mask-layer" style:clip-path={'inset(0 '+(100-right)+'% 0 '+left+'%)'}>{#if sources[entry.name]}<img src={sources[entry.name]} alt={'遮罩对比图 '+(index+1)} draggable="false" style:transform={`translate(${shared.x*100}%,${shared.y*100}%) scale(${shared.zoom})`}/>{/if}</span>
          <span class="mask-number" style:left={(left+right)/2+'%'}>{index+1}</span>
        {/each}
      </ZoomSurface>
      {#each cuts as cut,index}<button type="button" class="mask-divider" style:left={cut+'%'} aria-label={'拖动遮罩分界线 '+(index+1)} onpointerdown={event=>dragStart(event,index)} onpointermove={event=>dragMove(event,index)} onpointerup={()=>dragging=-1} onpointercancel={()=>dragging=-1} onkeydown={event=>dividerKey(event,index)}><span>↔</span></button>{/each}
    </section>
    <div class="mask-controls">{#each cuts as cut,index}<label><span>{index+1} / {index+2}</span><input type="range" min="0" max="100" step="0.1" aria-label={'遮罩分界线 '+(index+1)} value={cut} oninput={event=>setCut(index,Number(event.currentTarget.value))}/><output>{Math.round(cut)}%</output></label>{/each}</div>
  {:else}<div class="comparison-grid" style:--columns={layoutColumns}>{#each entries as entry,index (entry.name)}<ComparisonPane {entry} {index} source={sources[entry.name]||''} view={synchronized?shared:views[entry.name]||{zoom:1,x:0,y:0}} onchange={view=>change(entry.name,view)}/>{/each}</div>{/if}
</section>
<style>
.comparison{min-width:0;display:flex;flex-direction:column;gap:10px}.comparison-toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-size:11px}.comparison-toolbar strong{font-size:13px}.sync-control,.column-control{display:flex;align-items:center;gap:7px}.column-control select{padding:4px 7px;min-width:60px}.comparison-grid{display:grid;grid-template-columns:repeat(var(--columns),minmax(240px,1fr));grid-auto-rows:minmax(320px,58dvh);gap:9px;overflow:auto;padding-bottom:5px}.expanded .comparison-grid{grid-auto-rows:minmax(320px,68dvh)}@media(max-width:760px){.comparison-toolbar{gap:8px}.comparison-toolbar .hint{width:100%}.comparison-grid{grid-template-columns:repeat(var(--columns),minmax(260px,1fr));grid-auto-rows:58dvh}.column-control select{font-size:13px;min-height:30px}}
.mask-zoom{display:flex;align-items:center;gap:4px}.mask-zoom output{min-width:40px;text-align:center;font-variant-numeric:tabular-nums}.mask-stage{position:relative;width:100%;height:58dvh;min-height:320px;overflow:hidden;border-radius:8px;background:#e9edf1}.expanded .mask-stage{height:68dvh}.mask-layer{position:absolute;inset:0;pointer-events:none}.mask-layer img{position:absolute;inset:0;display:block;width:100%;height:100%;object-fit:contain;transform-origin:center;pointer-events:none;user-select:none}.mask-number{position:absolute;top:10px;transform:translateX(-50%);display:grid;place-items:center;width:24px;height:24px;border-radius:5px;color:white;background:#273643b8;font-size:11px;pointer-events:none}.mask-divider{position:absolute;top:0;bottom:0;width:24px;transform:translateX(-50%);border:0;padding:0;touch-action:none;cursor:col-resize;background:linear-gradient(to right,transparent 11px,#fff 11px,#fff 13px,transparent 13px);filter:drop-shadow(0 0 2px #25364755)}.mask-divider span{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:grid;place-items:center;width:32px;height:32px;border:1px solid white;border-radius:50%;background:#273643a8;color:white;font-size:19px}.mask-divider:focus-visible span{outline:2px solid #397453;outline-offset:3px}.mask-controls{display:flex;flex-wrap:wrap;gap:10px}.mask-controls label{display:flex;align-items:center;gap:8px;min-width:180px;flex:1;font-size:11px;color:#718092}.mask-controls input{min-width:70px;flex:1;accent-color:#397453}.mask-controls output{min-width:35px;text-align:right}
</style>
