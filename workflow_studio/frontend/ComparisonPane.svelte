<script>
  import {Button} from '$lib/components/ui/button';
  import {Minus, Plus, RotateCcw} from '@lucide/svelte';
  import {zoomViewport} from './imageViewport.js';
  import ZoomSurface from './ZoomSurface.svelte';
  let {entry,source='',index,view,onchange}=$props();
  function zoom(factor){onchange(zoomViewport(view,view.zoom*factor));}
</script>
<figure>
  <figcaption><span class="number">{index+1}</span><span class="image-name" title={entry.name}>{entry.width} × {entry.height} · Seed {entry.params.seed ?? '—'}</span><div class="zoom-tools"><Button size="icon-xs" variant="ghost" aria-label={'缩小图片 '+(index+1)} onclick={()=>zoom(1/1.25)}><Minus size={13}/></Button><output aria-label={'图片 '+(index+1)+' 缩放'}>{Math.round(view.zoom*100)}%</output><Button size="icon-xs" variant="ghost" aria-label={'放大图片 '+(index+1)} onclick={()=>zoom(1.25)}><Plus size={13}/></Button><Button size="icon-xs" variant="ghost" aria-label={'还原图片 '+(index+1)} onclick={()=>onchange({zoom:1,x:0,y:0})}><RotateCcw size={12}/></Button></div></figcaption>
  <ZoomSurface {view} {onchange} label={'对比图片 '+(index+1)+'，滚轮或双指缩放，拖动平移'}>
    {#if source}<img src={source} alt={'对比图 '+(index+1)} draggable="false" style:transform={`translate(${view.x*100}%,${view.y*100}%) scale(${view.zoom})`}/>{:else}<span>加载原图…</span>{/if}
  </ZoomSurface>
</figure>
<style>
figure{margin:0;min-width:0;display:flex;flex-direction:column;background:var(--preview-background);border:1px solid var(--border);border-radius:8px;overflow:hidden;height:100%;min-height:260px}figcaption{display:flex;align-items:center;gap:8px;padding:7px 9px;background:var(--background);font-size:10px;flex-wrap:wrap}.number{display:grid;place-items:center;width:22px;height:22px;border-radius:5px;background:#273643;color:white;font-weight:600}.image-name{flex:1;min-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted-foreground)}.zoom-tools{display:flex;align-items:center;gap:2px}.zoom-tools output{min-width:38px;text-align:center;font-variant-numeric:tabular-nums;color:var(--text-secondary)}img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;transform-origin:center;pointer-events:none;user-select:none}
</style>
