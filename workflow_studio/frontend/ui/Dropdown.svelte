<script>
let {label='',show_label=true,value=$bindable(''),choices=[],interactive=true,on_change,info=''}=$props();
</script>
<label class="field"><span class:sr-only={!show_label} title={info}>{label}</span>
<select aria-label={label} title={String(choices.find(c=>c[1]===value)?.[0] || '')} bind:value disabled={!interactive} onchange={()=>on_change?.(value)}>
{#each choices as item}<option value={item[1]}>{item[0]}</option>{/each}</select>
</label>
