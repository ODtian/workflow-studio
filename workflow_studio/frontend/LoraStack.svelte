<script>
import {Input} from '$lib/components/ui/input';import {Button} from '$lib/components/ui/button';import Dropdown from './ui/Dropdown.svelte';
let {value=$bindable([]),options=[],busy=false,idPrefix=''}=$props();
</script>
<div class="lora-stack">
{#each value as item,index}<div class="lora-row"><Dropdown label={`LoRA ${index+1}`} bind:value={item.name} choices={options.map(o=>[o,o])} interactive={!busy} filterable={true}/><label class="field"><span>权重</span><Input type="number" step={0.05} bind:value={item.strength} disabled={busy}/></label><Button variant="ghost" disabled={busy} onclick={()=>value=value.filter((_,i)=>i!==index)}>移除</Button></div>{/each}
<Button variant="outline" size="sm" disabled={busy||!options.length} onclick={()=>value=[...value,{name:options[0],strength:1}]}>＋ 添加 LoRA</Button>
</div>
<style>.lora-stack{display:grid;gap:8px}.lora-row{display:grid;grid-template-columns:minmax(0,1fr) 80px auto;gap:6px;align-items:end}</style>
