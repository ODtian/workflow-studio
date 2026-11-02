<script>
  import {moveViewport,zoomViewport} from './imageViewport.js';
  let {view,onchange,label,children}=$props();
  let surface;
  const pointers=new Map();
  const point=(x,y)=>{const bounds=surface.getBoundingClientRect();return {x:(x-bounds.left)/bounds.width-.5,y:(y-bounds.top)/bounds.height-.5};};
  function zoom(factor,position){onchange(zoomViewport(view,view.zoom*factor,position));}
  function wheel(event){event.preventDefault();zoom(Math.exp(-event.deltaY*.002),point(event.clientX,event.clientY));}
  $effect(()=>{const element=surface;element.addEventListener('wheel',wheel,{passive:false});return()=>element.removeEventListener('wheel',wheel);});
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
<button class="zoom-surface" type="button" bind:this={surface} aria-label={label} onpointerdown={down} onpointermove={move} onpointerup={event=>pointers.delete(event.pointerId)} onpointercancel={event=>pointers.delete(event.pointerId)} onkeydown={key} ondblclick={()=>onchange(view.zoom>1?{zoom:1,x:0,y:0}:{zoom:2,x:0,y:0})}>{@render children()}</button>
<style>
.zoom-surface{position:relative;display:block;width:100%;height:100%;min-height:220px;flex:1;border:0;padding:0;overflow:hidden;background:var(--preview-background);touch-action:none;cursor:grab;color:var(--muted-foreground)}.zoom-surface:active{cursor:grabbing}.zoom-surface:focus-visible{outline:2px solid #809a8b;outline-offset:-2px}
</style>
