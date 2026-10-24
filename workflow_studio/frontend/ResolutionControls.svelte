<script>
import {Input} from '$lib/components/ui/input';import {Button} from '$lib/components/ui/button';import {dimensionsForMP} from './resolution.js';
let {presets,values=$bindable(),busy=false,idPrefix=''}=$props();
let width=$derived(Number(values[presets.width_key])),height=$derived(Number(values[presets.height_key])),megapixels=$derived(width*height/1e6);
function apply(mp,ratio=width/height){const size=dimensionsForMP(mp,ratio,presets.step||16);values={...values,[presets.width_key]:size.width,[presets.height_key]:size.height};}
</script>
<label class="field"><span>分辨率 · MP</span><Input type="number" min={0.1} step={0.1} value={Number(megapixels.toFixed(2))} disabled={busy} onchange={e=>apply(Number(e.currentTarget.value))}/></label>
<div class="size-presets">{#each presets.items as preset}{@const size=dimensionsForMP(megapixels,preset.width/preset.height,presets.step||16)}<Button size="sm" variant={width===size.width&&height===size.height?'secondary':'outline'} disabled={busy} onclick={()=>apply(megapixels,preset.width/preset.height)}>{preset.label}</Button>{/each}</div>
<style>.size-presets{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 12px}</style>
