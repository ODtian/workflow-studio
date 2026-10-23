<script>
  import {tick} from 'svelte';
  import {BaseButton} from '@gradio/button';
  import NumberInput from '@gradio/number';
  import {dimensionsForMP} from './resolution.js';

  let {presets, values = $bindable(), busy = false, idPrefix = ''} = $props();
  let width = $derived(Number(values[presets.width_key]));
  let height = $derived(Number(values[presets.height_key]));
  let megapixels = $derived(width * height / 1_000_000);
  let getNumber;

  function apply(megapixels, ratio = width / height) {
    if (megapixels > 0) {
      const size = dimensionsForMP(megapixels, ratio, presets.step || 16);
      values = {...values, [presets.width_key]:size.width, [presets.height_key]:size.height};
    }
  }
</script>

<div class="resolution-controls">
  <NumberInput shared_props={{id:idPrefix+'megapixels',label:'分辨率 (MP)',show_label:true,container:true,
      visible:true,interactive:!busy,min_width:0,
      register_component:(_id,_set,get) => getNumber = get,
      dispatcher:async (_id,event) => {
        if (event === 'blur' || event === 'submit') {await tick(); apply((await getNumber()).value);}
      }}}
    props={{value:Number(megapixels.toFixed(2)),minimum:0.1,step:0.1,buttons:[]}} />
  <div class="size-presets" role="group" aria-label="常见比例">
    {#each presets.items as preset}
      {@const size = dimensionsForMP(megapixels, preset.width / preset.height, presets.step || 16)}
      <BaseButton size="sm" disabled={busy}
        variant={width === size.width && height === size.height ? 'primary' : 'secondary'}
        onclick={() => apply(megapixels, preset.width / preset.height)}>
        <span>{preset.label}</span><small>{size.width} × {size.height}</small>
      </BaseButton>
    {/each}
  </div>
</div>

<style>
  .resolution-controls{display:grid;gap:8px;margin-bottom:8px;}
  .size-presets{display:flex;flex-wrap:wrap;gap:5px;}
  .size-presets :global(button){flex-direction:column;gap:3px;flex:1 0 56px;padding:6px;min-height:40px;}
  .size-presets span{font-size:11px;font-weight:600;}
  .size-presets small{font-size:9px;opacity:.7;white-space:nowrap;}
  @media(max-width:650px){.resolution-controls :global(input){font-size:16px}}
</style>
