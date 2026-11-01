<script>
  import {Button} from '$lib/components/ui/button';
  import {Minus, Plus, RotateCcw} from '@lucide/svelte';
  import {moveViewport, zoomViewport} from './imageViewport.js';
  let {entry, source='', index, view, onchange}=$props();
  let surface;
  const pointers=new Map();
  const point=(x,y)=>{const bounds=surface.getBoundingClientRect();return {x:(x-bounds.left)/bounds.width-.5,y:(y-bounds.top)/bounds.height-.5};};
  function zoom(factor,position){onchange(zoomViewport(view,view.zoom*factor,position));}
  function wheel(event){event.preventDefault();zoom(Math.exp(-event.deltaY*.002),point(event.clientX,event.clientY));}
  $effect(()=>{surface.addEventListener('wheel',wheel,{passive:false});return()=>surface.removeEventListener('wheel',wheel);});
  function down(event){surface.setPointerCapture(event.pointerId);pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});}
  function move(event){
    const previous=pointers.get(event.pointerId);if(!previous)return;
    const old=[...pointers.values()];
    pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
    const bounds=surface.getBoundingClientRect();
    if(pointers.size===2){
      const next=[...pointers.values()];
      const distance=points=>Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y);
      const center=points=>({x:(points[0].x+points[1].x)/2,y:(points[0].y+points[1].y)/2});
      const before=center(old),after=center(next);
      const updated=zoomViewport(view,view.zoom*distance(next)/distance(old),point(before.x,before.y));
      onchange(moveViewport(updated,updated.x+(after.x-before.x)/bounds.width,updated.y+(after.y-before.y)/bounds.height));
    }else onchange(moveViewport(view,view.x+(event.clientX-previous.x)/bounds.width,view.y+(event.clientY-previous.y)/bounds.height));
  }
  function key(event){if(['+','=','-','0'].includes(event.key)){event.preventDefault();if(event.key==='0')onchange({zoom:1,x:0,y:0});else zoom(event.key==='-'?1/1.25:1.25);}}
</script>
<figure>
  <figcaption><span class="number">{index+1}</span><span class="image-name" title={entry.name}>{entry.width} × {entry.height} · Seed {entry.params.seed ?? '—'}</span><div class="zoom-tools"><Button size="icon-xs" variant="ghost" aria-label={'缩小图片 '+(index+1)} onclick={()=>zoom(1/1.25)}><Minus size={13}/></Button><output aria-label={'图片 '+(index+1)+' 缩放'}>{Math.round(view.zoom*100)}%</output><Button size="icon-xs" variant="ghost" aria-label={'放大图片 '+(index+1)} onclick={()=>zoom(1.25)}><Plus size={13}/></Button><Button size="icon-xs" variant="ghost" aria-label={'还原图片 '+(index+1)} onclick={()=>onchange({zoom:1,x:0,y:0})}><RotateCcw size={12}/></Button></div></figcaption>
  <button class="zoom-surface" type="button" bind:this={surface} aria-label={'对比图片 '+(index+1)+'，滚轮或双指缩放，拖动平移'} onpointerdown={down} onpointermove={move} onpointerup={event=>pointers.delete(event.pointerId)} onpointercancel={event=>pointers.delete(event.pointerId)} onkeydown={key} ondblclick={()=>onchange(view.zoom>1?{zoom:1,x:0,y:0}:{zoom:2,x:0,y:0})}>
    {#if source}<img src={source} alt={'对比图 '+(index+1)} draggable="false" style:transform={`translate(${view.x*100}%,${view.y*100}%) scale(${view.zoom})`}/>{:else}<span>加载原图…</span>{/if}
  </button>
</figure>
<style>
figure{margin:0;min-width:0;display:flex;flex-direction:column;background:#e9edf1;border:1px solid #dce2e9;border-radius:8px;overflow:hidden;height:100%;min-height:260px}figcaption{display:flex;align-items:center;gap:8px;padding:7px 9px;background:white;font-size:10px;flex-wrap:wrap}.number{display:grid;place-items:center;width:22px;height:22px;border-radius:5px;background:#273643;color:white;font-weight:600}.image-name{flex:1;min-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#718092}.zoom-tools{display:flex;align-items:center;gap:2px}.zoom-tools output{min-width:38px;text-align:center;font-variant-numeric:tabular-nums;color:#485b6d}.zoom-surface{position:relative;display:block;width:100%;min-height:220px;flex:1;border:0;padding:0;overflow:hidden;background:#e9edf1;touch-action:none;cursor:grab;color:#718092}.zoom-surface:active{cursor:grabbing}.zoom-surface:focus-visible{outline:2px solid #809a8b;outline-offset:-2px}.zoom-surface img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;transform-origin:center;pointer-events:none;user-select:none}
</style>
