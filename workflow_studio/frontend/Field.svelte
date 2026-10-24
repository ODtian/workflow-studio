<script>
import {Input} from '$lib/components/ui/input';import {Textarea} from '$lib/components/ui/textarea';import {Switch} from '$lib/components/ui/switch';
import Dropdown from './ui/Dropdown.svelte';import {Button} from '$lib/components/ui/button';import LoraStack from './LoraStack.svelte';import {readFile} from './bridge.js';
let {field,value=$bindable(),busy=false,idPrefix='',paste=false,compact=false}=$props();
let uploadInput;
let options=$derived((field.options||[]).map(o=>typeof o==='string'?[o,o]:[o.label,o.value]));
</script>
{#if field.type==='lora_stack'}<LoraStack bind:value options={field.options} {busy} {idPrefix}/>
{:else if field.type==='boolean'}
<label class="field switch-field"><span>{field.label}</span><Switch bind:checked={value} disabled={busy}/></label>
{:else if field.type==='select'}<Dropdown label={field.label} show_label={!compact} bind:value choices={value && !options.some(o=>o[1]===value)?[...options,[value,value]]:options} interactive={!busy} filterable={true} info={field.hint}/>
{:else}
<label class="field"><span>{field.label}</span>
{#if field.type==='number'}<Input type="number" bind:value min={field.min} max={field.max} step={field.step||1} disabled={busy}/>
{:else if field.type==='image'}
<input hidden type="file" accept="image/*" bind:this={uploadInput} onchange={async()=>{if(uploadInput.files[0])value=await readFile(uploadInput.files[0]);}}/>
{#if String(value||'').startsWith('data:')}<img class="upload-preview" src={value} alt="参考图"/>{/if}
<div class="row"><Button variant="outline" disabled={busy} onclick={()=>uploadInput.click()}>上传参考图</Button><Button variant="ghost" disabled={busy||!value} onclick={()=>value=''}>清除</Button></div>
<Input value={String(value||'').startsWith('data:')?'':value} oninput={e=>value=e.currentTarget.value} placeholder="容器中的图片路径" disabled={busy}/>
{:else if field.type==='textarea'}<Textarea bind:value rows={field.rows||3} placeholder={field.placeholder||''} disabled={busy}/>
{:else}<Input bind:value placeholder={field.placeholder||''} disabled={busy}/>{/if}
{#if field.hint}<small>{field.hint}</small>{/if}</label>
{/if}
<style>.switch-field{display:flex;align-items:center;justify-content:space-between;gap:12px}.upload-preview{max-height:180px;width:100%;object-fit:contain;border-radius:8px}</style>
