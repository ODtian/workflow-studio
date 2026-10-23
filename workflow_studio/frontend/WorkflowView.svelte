<script>
  import {Block} from '@gradio/atoms';
  import {BaseButton} from '@gradio/button';
  import {BaseDropdown} from '@gradio/dropdown';
  import {BaseTextbox} from '@gradio/textbox';
  import ZoomPreview from './ZoomPreview.svelte';
  import ImageHistory from './ImageHistory.svelte';
  import ResolutionControls from './ResolutionControls.svelte';
  import Field from './Field.svelte';
  import {i18n} from './bridge.js';

  let {panel, values = $bindable(), preview = '', text = '', results = [], send,
       history = [], loadThumbnail, loadPreview,
       targets = [], onTransfer, loadOriginal, mode = 'full'} = $props();
  let fields = $derived(panel.spec.fields || []);
  let parameterFields = $derived(fields.filter(f => !f.area));
  let groups = $derived([...new Set(parameterFields.map(f => f.section || '参数'))]);
  let sizePresets = $derived(panel.spec.size_presets);
  let isText = $derived(panel.spec.output === 'text');
  let imageIndex = $state(0);
  let target = $state('');
  let copied = $state(false);
  let displayMs = $state(0);
  let modelsOpen = $state(matchMedia('(min-width:651px)').matches);
  let receivedAt = 0;
  let activeResult = $derived(results[imageIndex]);
  const act = (action, data = {}) => send(action, {id: panel.id, ...data});

  $effect(() => {if (preview) receivedAt = performance.now();});
  $effect(() => {results; imageIndex = 0;});
  $effect(() => {if (!targets.some(t => t.value === target)) target = targets[0]?.value || '';});

  function loaded() {
    if (receivedAt && ['publishing', 'complete'].includes(panel.phase)) {
      displayMs = Math.round(performance.now() - receivedAt);
      act('displayed', {ms: displayMs});
    }
  }
</script>

<article class="workflow-card" class:controls-only={mode === 'controls'} class:output-only={mode === 'output'} aria-label={panel.spec.name}>
  {#if mode !== 'output'}
  <div class="card-heading">
    <div><h2>{panel.spec.name}</h2>{#if panel.initializing}<span class="preparation" role="status">{panel.initialization}</span>{/if}</div>
    <div class="card-actions">
      {#if fields.some(f => f.area === 'models')}<BaseButton size="sm" onclick={() => act('refresh')}>刷新模型</BaseButton>{/if}
      <BaseButton size="sm" onclick={() => act('export')}>导出代码</BaseButton>
      <BaseButton size="sm" disabled={panel.busy} onclick={() => act('remove')}>移除</BaseButton>
    </div>
  </div>
  {#if fields.some(f => f.area === 'models')}
    <details class="model-settings" bind:open={modelsOpen}><summary>模型选择</summary>
    <div class="model-strip">
      {#each fields.filter(f => f.area === 'models') as field (field.key)}
        <Field {field} idPrefix={panel.id} bind:value={values[field.key]} busy={panel.busy} />
      {/each}
    </div>
    </details>
  {/if}
  {/if}
  <div class="workspace">
    {#if mode !== 'output'}
    <section class="controls" aria-label="工作流参数">
      <div class="prompts">
        {#each fields.filter(f => f.area === 'prompts') as field (field.key)}
          <Field {field} idPrefix={panel.id} bind:value={values[field.key]} busy={panel.busy} paste={true} />
        {/each}
      </div>
      {#each groups as group}
        <section class="parameter-section">
          <h3>{group}</h3>
          {#if sizePresets?.section === group}
            <ResolutionControls presets={sizePresets} bind:values busy={panel.busy} idPrefix={panel.id} />
          {/if}
          <div class="fields">
            {#each parameterFields.filter(f => (f.section || '参数') === group) as field (field.key)}
            <div class:wide={['boolean', 'text', 'textarea', 'image', 'lora_stack'].includes(field.type)}>
                <Field {field} idPrefix={panel.id} bind:value={values[field.key]} busy={panel.busy} />
              </div>
            {/each}
          </div>
        </section>
      {/each}
      {#if fields.some(f => f.area === 'advanced')}
        <details class="advanced"><summary>高级设置</summary><div class="fields">
          {#each fields.filter(f => f.area === 'advanced') as field (field.key)}
            <div class:wide={['text', 'textarea', 'select'].includes(field.type)}>
              <Field {field} idPrefix={panel.id} bind:value={values[field.key]} busy={panel.busy} />
            </div>
          {/each}
        </div></details>
      {/if}
      {#if panel.spec.ready === false}<p class="empty-models">{panel.spec.description}</p>{/if}
      <div class="runbar">
        <BaseButton variant="primary" size="lg" disabled={panel.busy || panel.spec.ready === false}
          onclick={() => act('run', {params: {...values}})}>{panel.busy ? (panel.phase === 'queued' ? '等待执行…' : '正在生成…') : panel.spec.run_label || '运行工作流'}</BaseButton>
        <BaseButton variant="stop" size="lg" disabled={!panel.busy} onclick={() => act('cancel')}>停止</BaseButton>
      </div>
    </section>
    {/if}
    {#if mode !== 'controls'}
    <section class="output" aria-label="工作流输出">
      <div class="output-heading"><h3>{panel.busy ? (isText ? '实时输出' : '实时预览') : '生成结果'}</h3>
        <span>{isText ? '流式文本' : activeResult ? `${activeResult.width} × ${activeResult.height}` : '图片预览'}</span>
      </div>
      {#if isText}
        <div class="text-viewer" aria-live="off">
          <Block><BaseTextbox label="文本结果" show_label={false} value={text} disabled={true}
            lines={18} max_lines={28} autoscroll={true} buttons={['copy']}
            placeholder="生成的文字会逐步显示在这里。" /></Block>
        </div>
        <div class="text-actions">
          <BaseButton size="sm" disabled={!text} onclick={async () => {await navigator.clipboard.writeText(text); copied = true;}}> {copied ? '已复制' : '复制文本'}</BaseButton>
          <BaseButton size="sm" disabled={!activeResult} onclick={() => act('download', {name: activeResult.name})}>下载 TXT</BaseButton>
        </div>
        {#if targets.length}
          <div class="transfer">
            <Block allow_overflow={true}><BaseDropdown label="发送到" choices={targets.map(t => [t.label, t.value])}
              bind:value={target} interactive={true} filterable={false} /></Block>
            <BaseButton size="sm" disabled={!text || panel.busy} onclick={() => onTransfer(target, text)}>填入参数</BaseButton>
          </div>
        {/if}
      {:else}
        <div class="viewer" class:working={panel.busy}>
          <ZoomPreview {preview} result={activeResult} {loadOriginal} onload={loaded} />
        </div>
      {/if}
      <div class="progress-track"><progress max={panel.total || 1} value={panel.step} aria-label="执行进度"></progress></div>
      <div class="output-status"><p role="status">{panel.message}{panel.busy && panel.total ? ` · ${panel.step}/${panel.total}` : ''}</p>
        <span>{panel.elapsed ? `${panel.elapsed.toFixed(1)} s` : ''}{displayMs ? ` · 显示 ${displayMs} ms` : ''}</span>
      </div>
      {#if !isText}
        <div class="result-actions">
          {#if results.length > 1}<div class="image-selector">
            {#each results as result, index}<BaseButton size="sm" variant={imageIndex === index ? 'primary' : 'secondary'}
              onclick={() => {imageIndex = index; act('show_result', {name: result.name});}}>图片 {index + 1}</BaseButton>{/each}
          </div>{/if}
          <BaseButton size="sm" disabled={!activeResult} onclick={() => act('download', {name: activeResult.name})}>下载原图 PNG</BaseButton>
        </div>
      {/if}
      <details class="generation-info"><summary>运行信息</summary>
        <p>{Object.entries(panel.metadata || {}).map(([k,v]) => `${k} ${v}`).join(' · ')}</p>
        {#if panel.spec.model_root}<p>模型目录：{panel.spec.model_root}</p>{/if}
      </details>
    </section>
    {/if}
  </div>
  {#if !isText && mode !== 'controls'}
    <ImageHistory {history} {loadPreview} {loadThumbnail} download={result => act('download', {name:result.name})} />
  {/if}
</article>

<style>
  .workflow-card {container-type:inline-size; min-width:0; border:1px solid #dde2e8; border-radius:10px; background:#fff; padding:0 18px 8px; box-shadow:0 2px 8px #172b4d04;}
  .controls-only,.output-only {container-type:normal;border:0;border-radius:0;padding:0;box-shadow:none;}
  .controls-only .workspace,.output-only .workspace {display:block;}
  .controls-only .card-heading>div:first-child {display:none;}
  .controls-only .card-heading {min-height:35px;justify-content:flex-end;border:0;}
  .output-only .output {position:static;}
  .output-only .viewer {height:clamp(440px,68vh,900px);}
  .output-only .text-viewer :global(textarea) {min-height:50vh;font-size:14px;}
  .card-heading,.card-heading>div,.card-actions,.output-heading,.output-status,.result-actions,.text-actions {display:flex;align-items:center;gap:8px;}
  .card-heading {justify-content:space-between;min-height:58px;border-bottom:1px solid #e9ebef;}
  .preparation{font-size:11px;color:#8b6a48;}
  h2 {font-size:13px;font-weight:650;line-height:1.5;}
  .kind {font-size:9px;letter-spacing:.7px;background:#fff2e7;color:#bd5c16;padding:4px 6px;border-radius:4px;font-weight:650;}
  .card-actions :global(button) {font-size:10px;padding:5px 7px;min-width:0;}
  .model-strip {display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;padding:12px 0;border-bottom:1px solid #e9ebef;}
  .model-settings>summary{font-size:12px;}
  .model-settings[open]>summary{padding-bottom:0;}
  .model-settings[open] .model-strip{padding-top:7px;}
  .workspace {display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr);gap:18px;padding-top:14px;}
  .controls,.output {min-width:0;}
  .prompts {display:grid;gap:8px;}
  .parameter-section {margin-top:13px;}
  h3 {font-size:11px;font-weight:650;color:#59616d;}
  .parameter-section h3 {margin-bottom:7px;}
  .fields {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;}
  .fields :global(.block) {margin:0;}
  .wide {grid-column:1/-1;}
  .advanced {margin:10px 0;color:#636b76;}
  summary {cursor:pointer;font-size:11px;padding:7px 0;}
  .advanced .fields {margin-top:6px;}
  .empty-models {color:#9b681f;font-size:11px;line-height:1.7;margin:10px 0;}
  .runbar {position:sticky;bottom:0;z-index:10;display:flex;gap:8px;background:white;padding:12px 0;border-top:1px solid #e9ebef;}
  .runbar :global(button:first-child) {flex:1;min-height:44px;font-weight:650;}
  .runbar :global(button:last-child) {width:66px;min-width:0;}
  .output {position:sticky;top:90px;align-self:start;}
  .output-heading {justify-content:space-between;height:22px;margin-bottom:8px;}
  .output-heading span {font-size:10px;color:#87909a;}
  .viewer {height:clamp(440px,64vh,900px);border:1px solid #e0e4e9;border-radius:8px;overflow:hidden;background:#f4f5f7;}
  .working {border-color:#f4ba8e;}
  .text-viewer :global(.block) {padding:10px;background:#fafbfc;}
  .text-viewer :global(textarea:disabled) {opacity:1;color:#30363f;line-height:1.8;font-size:14px;min-height:52vh;}
  .text-actions {margin-top:8px;}
  .transfer {display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid #e9ebef;}
  .transfer :global(button) {margin-bottom:2px;}
  .progress-track {height:3px;margin-top:10px;}
  progress {display:block;width:100%;height:3px;appearance:none;border:0;border-radius:3px;overflow:hidden;}
  progress::-webkit-progress-bar {background:#e9ebef;}
  progress::-webkit-progress-value {background:#f59b52;}
  .output-status {justify-content:space-between;align-items:flex-start;margin:9px 0 12px;font-size:11px;line-height:1.7;}
  .output-status span {color:#87909a;font-size:10px;white-space:nowrap;}
  .result-actions {flex-wrap:wrap;}
  .image-selector {display:flex;gap:5px;}
  .generation-info {border-top:1px solid #e9ebef;margin-top:14px;color:#7c838d;font-size:10px;}
  .generation-info p {line-height:1.7;margin:6px 0;word-break:break-all;}
  @container(max-width:620px){.workspace{grid-template-columns:1fr}.output{position:static}.viewer{height:360px}.card-heading{flex-wrap:wrap;padding:10px 0;gap:6px}}
  @media(max-width:650px){
    .workflow-card{padding:0 9px 8px;border-radius:7px;}
    .card-heading{min-height:38px;padding:4px 0;}
    .card-heading h2{font-size:12px;}
    .workspace{padding-top:8px;gap:10px;}
    .prompts{gap:7px;}
    .prompts :global(textarea){font-size:16px;line-height:1.5;}
    .parameter-section{margin-top:9px;}
    .fields{gap:6px;}
    .fields :global(input){font-size:16px;}
    .runbar{padding:7px 0 max(7px,env(safe-area-inset-bottom));}
    .viewer{height:clamp(300px,60dvh,650px);}
    .output-heading span{display:none;}
    .output-status{margin:6px 0;font-size:12px;}
    .output-status>span{display:none;}
    .generation-info{margin-top:8px;}
  }
</style>
