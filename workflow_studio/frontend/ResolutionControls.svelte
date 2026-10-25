<script>
import {Input} from '$lib/components/ui/input';import {Button} from '$lib/components/ui/button';import {dimensionsForMP} from './resolution.js';
let {presets,values=$bindable(),busy=false,idPrefix=''}=$props();
const extraRatios=[[4,5],[5,4],[16,10],[10,16]].map(([width,height])=>({label:`${width}:${height}`,width,height}));
let ratios=$derived([...presets.items,...extraRatios.filter(ratio=>!presets.items.some(item=>item.width*ratio.height===item.height*ratio.width))]);
let width=$derived(Number(values[presets.width_key])),height=$derived(Number(values[presets.height_key])),megapixels=$derived(width*height/1e6);
function apply(mp,ratio=width/height){const size=dimensionsForMP(mp,ratio,presets.step||16);values={...values,[presets.width_key]:size.width,[presets.height_key]:size.height};}
</script>
<label class="field"><span>分辨率 · MP</span><Input type="number" min={0.1} step={0.1} value={Number(megapixels.toFixed(2))} disabled={busy} onchange={e=>apply(Number(e.currentTarget.value))}/></label>
<div class="size-presets" role="group" aria-label="画面比例">{#each ratios as preset}{@const size=dimensionsForMP(megapixels,preset.width/preset.height,presets.step||16)}<Button size="sm" variant={width===size.width&&height===size.height?'secondary':'outline'} disabled={busy} onclick={()=>apply(megapixels,preset.width/preset.height)}>{preset.label}</Button>{/each}</div>
<style>
.size-presets{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0 8px}
.size-presets :global([data-slot=button]){height:26px;min-height:26px;padding:0 7px;font-size:11px}
@media(max-width:760px),(max-width:1000px) and (max-height:500px){
  .size-presets{flex-wrap:nowrap;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;overscroll-behavior-x:contain}
  .size-presets::-webkit-scrollbar{display:none}
  .size-presets :global([data-slot=button]){flex:0 0 auto}
}
</style>
