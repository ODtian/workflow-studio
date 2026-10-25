<script>
import {Input} from '$lib/components/ui/input';
let {label='',show_label=true,value=$bindable(''),choices=[],interactive=true,filterable=false,on_change,info=''}=$props();
let query=$state('');
let options=$derived(choices.filter(item=>String(item[0]).toLowerCase().includes(query.toLowerCase())));
</script>
<label class="field"><span class:sr-only={!show_label} title={info}>{label}</span>
{#if filterable && choices.length>12}<Input aria-label={'筛选'+label} placeholder="筛选…" bind:value={query} disabled={!interactive}/>{/if}
<select aria-label={label} title={String(choices.find(c=>c[1]===value)?.[0] || '')} bind:value disabled={!interactive} onchange={()=>on_change?.(value)}>
{#each options as item}<option value={item[1]}>{item[0]}</option>{/each}</select>
</label>
