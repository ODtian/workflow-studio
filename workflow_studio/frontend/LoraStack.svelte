<script>
  import {tick} from 'svelte';
  import {Block} from '@gradio/atoms';
  import {BaseButton} from '@gradio/button';
  import {BaseDropdown} from '@gradio/dropdown';
  import NumberInput from '@gradio/number';
  let {value = $bindable([]),options = [],busy = false,idPrefix = ''} = $props();
  let getters = [];
</script>

<section class="lora-stack" aria-label="LoRA">
  {#each value as item,index}
    <div class="lora-row">
      <Block allow_overflow={true}><BaseDropdown label={`LoRA ${index+1}`} bind:value={item.name}
        choices={options.map(name => [name,name])} interactive={!busy} filterable={true} /></Block>
      <NumberInput shared_props={{id:idPrefix+'lora-'+index,label:'权重',show_label:true,container:true,
        visible:true,interactive:!busy,min_width:0,
        register_component:(_id,_set,get) => getters[index] = get,
        dispatcher:async (_id,event) => {if (event === 'input') {
          await tick(); const strength = (await getters[index]()).value;
          value = value.map((entry,i) => i === index ? {...entry,strength} : entry);
        }}}}
        props={{value:item.strength,step:0.05,buttons:[]}} />
      <BaseButton size="sm" disabled={busy} onclick={() => value = value.filter((_,i) => i !== index)}>移除</BaseButton>
    </div>
  {/each}
  <BaseButton size="sm" disabled={busy || !options.length}
    onclick={() => value = [...value,{name:options[0],strength:1}]}>添加 LoRA</BaseButton>
</section>

<style>
  .lora-stack{display:grid;gap:7px;}
  .lora-row{display:grid;grid-template-columns:minmax(0,1fr) 95px auto;gap:6px;align-items:center;}
  .lora-row :global(button){font-size:11px;min-width:0;}
  .lora-stack> :global(button){justify-self:start;}
  @media(max-width:650px){.lora-row{grid-template-columns:minmax(0,1fr) 85px auto;}}
</style>
