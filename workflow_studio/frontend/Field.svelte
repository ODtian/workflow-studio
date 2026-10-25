<script>
import {Input} from '$lib/components/ui/input';import {Textarea} from '$lib/components/ui/textarea';import {Switch} from '$lib/components/ui/switch';
import Dropdown from './ui/Dropdown.svelte';import {Button} from '$lib/components/ui/button';import LoraStack from './LoraStack.svelte';import {readFile} from './bridge.js';
import {ClipboardPaste} from '@lucide/svelte';
import MediaInputs from './MediaInputs.svelte';
let {field,value=$bindable(),busy=false,idPrefix='',paste=false,compact=false}=$props();
const inputId=$props.id();
let uploadInput;
let pasteError=$state('');
let options=$derived((field.options||[]).map(o=>typeof o==='string'?[o,o]:[o.label,o.value]));
async function replaceFromClipboard(){
  pasteError='';
  try{value=await navigator.clipboard.readText();}
  catch{pasteError='浏览器需要剪贴板读取权限';}
}
</script>
{#if field.type==='lora_stack'}<LoraStack bind:value options={field.options} {busy} {idPrefix}/>
{:else if ['media_list','keyframe_list'].includes(field.type)}<div class="field"><span title={field.hint}>{field.label}</span><MediaInputs bind:value timeline={field.type==='keyframe_list'} {busy} label={field.label}/></div>
{:else if field.type==='boolean'}
<div class="field switch-field"><label for={inputId} title={field.hint}>{field.label}</label><Switch id={inputId} aria-label={field.label} bind:checked={value} disabled={busy}/></div>
{:else if field.type==='select'}<Dropdown label={field.label} show_label={!compact} bind:value choices={options} interactive={!busy} info={field.hint}/>
{:else if paste && ['text','textarea'].includes(field.type)}
<div class="field">
  <div class="field-heading"><label for={inputId} title={field.hint}>{field.label}</label><Button variant="ghost" size="icon-sm" disabled={busy} aria-label={'用剪贴板替换'+field.label} title={'用剪贴板替换'+field.label} onclick={replaceFromClipboard}><ClipboardPaste size={14}/></Button></div>
  {#if field.type==='textarea'}<Textarea id={inputId} bind:value rows={field.rows||3} placeholder={field.placeholder||''} disabled={busy}/>
  {:else}<Input id={inputId} bind:value placeholder={field.placeholder||''} disabled={busy}/>{/if}
  {#if pasteError}<small role="alert">{pasteError}</small>{/if}
</div>
{:else}
<label class="field"><span title={field.hint}>{field.label}</span>
{#if field.type==='number'}<Input type="number" bind:value min={field.min} max={field.max} step={field.step||1} disabled={busy}/>
{:else if field.type==='image'}
<input hidden type="file" accept="image/*" bind:this={uploadInput} onchange={async()=>{if(uploadInput.files[0])value=await readFile(uploadInput.files[0]);}}/>
{#if String(value||'').startsWith('data:')}<img class="upload-preview" src={value} alt="参考图"/>{/if}
<div class="row"><Button variant="outline" disabled={busy} onclick={()=>uploadInput.click()}>上传参考图</Button><Button variant="ghost" disabled={busy||!value} onclick={()=>value=''}>清除</Button></div>
<Input value={String(value||'').startsWith('data:')?'':value} oninput={e=>value=e.currentTarget.value} placeholder="容器中的图片路径" disabled={busy}/>
{:else if field.type==='textarea'}<Textarea bind:value rows={field.rows||3} placeholder={field.placeholder||''} disabled={busy}/>
{:else}<Input bind:value placeholder={field.placeholder||''} disabled={busy}/>{/if}
</label>
{/if}
<style>.field-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:22px}.field-heading label{font-size:12px}.switch-field{display:flex;flex-direction:row;align-items:center;justify-content:space-between;gap:12px;min-height:32px}.switch-field>label{flex:1;min-width:0;font-size:12px;font-weight:500;color:#85909f}.upload-preview{max-height:180px;width:100%;object-fit:contain;border-radius:8px}</style>
