<script>
  import {tick} from 'svelte';
  import {Block, UploadText} from '@gradio/atoms';
  import {BaseTextbox} from '@gradio/textbox';
  import {BaseDropdown} from '@gradio/dropdown';
  import NumberInput from '@gradio/number';
  import {BaseImageUploader} from '@gradio/image';
  import {readFile, i18n} from './bridge.js';
  import LoraStack from './LoraStack.svelte';

  let {field, value = $bindable(), busy = false, idPrefix = '', paste = false, compact = false} = $props();
  let pasteError = $state('');
  let getNumber;
  let uploaded = $state(null);
  let serverPath = $state(String(value || '').startsWith('data:') ? '' : value || '');
  const choices = (options) => {
    const items = options.map(o => typeof o === 'string' ? [o, o] : [o.label, o.value]);
    return value && !items.some(item => item[1] === value) ? [...items,[String(value) + ' · 已保存',value]] : items;
  };

  async function upload(files) {
    return Promise.all(files.map(async file => ({...file, path: file.orig_name, url: await readFile(file.blob)})));
  }
</script>

{#if field.type === 'number'}
  <NumberInput
    shared_props={{id: idPrefix + field.key, label: field.label, show_label: true, container: true,
      visible: true, interactive: !busy, min_width: 0,
      register_component: (_id, _set, get) => {getNumber = get;},
      dispatcher: async (_id, event) => {
        if (event === 'input') {await tick(); value = (await getNumber()).value;}
      }}}
    props={{value, minimum: field.min, maximum: field.max, step: field.step || 1,
      info: field.hint, buttons: []}}
  />
{:else if field.type === 'boolean'}
  <Block>
    <label class="toggle-field">
      <input type="checkbox" role="switch" bind:checked={value} disabled={busy} />
      <span>{field.label}</span>
    </label>
    {#if field.hint}<p class="toggle-hint">{field.hint}</p>{/if}
  </Block>
{:else if field.type === 'select'}
  <Block allow_overflow={true}>
    <BaseDropdown label={field.label} show_label={!compact} bind:value choices={choices(field.options)}
      interactive={!busy} info={field.hint} filterable={field.options.length > 12} />
  </Block>
{:else if field.type === 'lora_stack'}
  <LoraStack bind:value options={field.options} {busy} {idPrefix} />
{:else if field.type === 'image'}
  <div class="image-field">
    <Block height={240} padding={false}>
      <BaseImageUploader label={field.label} show_label={true} bind:value={uploaded}
        sources={['upload']} active_source="upload" root="" {i18n} {upload}
        show_fullscreen_button={false} webcam_options={{mirror: false}}
        onupload={() => {value = uploaded.url; serverPath = '';}}
        onclear={() => {value = ''; serverPath = '';}}>
        <UploadText type="image" {i18n} />
      </BaseImageUploader>
    </Block>
    <Block>
      <BaseTextbox label={field.label + ' · 服务端路径'} bind:value={serverPath}
        disabled={busy} placeholder="容器 / Drive 中的图片路径" max_lines={1}
        onchange={path => {value = path; uploaded = null;}} />
    </Block>
  </div>
{:else}
  <Block>
    <BaseTextbox label={field.label} bind:value disabled={busy}
      lines={field.type === 'textarea' ? field.rows || 3 : 1}
      max_lines={field.type === 'textarea' ? field.rows || 3 : 1}
      placeholder={field.placeholder || ''} info={field.hint}
      buttons={paste ? [{id:1,value:'粘贴',icon:null}] : []}
      oncustombuttonclick={async () => {
        try {value = await navigator.clipboard.readText(); pasteError = '';}
        catch (error) {pasteError = '请允许浏览器读取剪贴板，然后点击粘贴。';}
      }} />
  </Block>
  {#if pasteError}<p class="paste-error" role="status">{pasteError}</p>{/if}
{/if}

<style>
  .toggle-field{display:flex;align-items:center;gap:8px;min-height:38px;font-size:12px;cursor:pointer;}
  .toggle-field input{appearance:none;position:relative;width:34px;height:20px;flex:0 0 auto;border:0;border-radius:999px;background:#c9ced6;cursor:pointer;}
  .toggle-field input::after{content:'';position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:white;}
  .toggle-field input:checked{background:#e58c47;}
  .toggle-field input:checked::after{transform:translateX(14px);}
  .toggle-hint{font-size:11px;color:#748090;margin:4px 0;}
  .image-field {display: grid; gap: var(--layout-gap);}
  .paste-error{font-size:12px;color:#a35b16;}
</style>
