<script>
  import ImageComparison from './ImageComparison.svelte';
  let {history = [], loadPreview, loadThumbnail, download} = $props();
  let selectedA = $state('');
  let selectedB = $state('');
  let mode = $state('side');
  let expanded = $state(false);
  let page = $state(0);
  let thumbnails = $state({});
  let infoName = $state('');
  let parameterDialog;
  const pageSize = 16;
  let pageCount = $derived(Math.max(1, Math.ceil(history.length / pageSize)));
  let visible = $derived(history.slice(page * pageSize, (page + 1) * pageSize));
  let a = $derived(history.find(entry => entry.name === selectedA));
  let b = $derived(history.find(entry => entry.name === selectedB));
  let comparing = $derived(Boolean(a && b));
  let info = $derived(history.find(entry => entry.name === infoName));
  const dateLabel = entry => new Date(entry.created_at).toLocaleString('zh-CN', {hour12:false});
  const optionLabel = entry => dateLabel(entry)+' · '+entry.name.slice(0,-4).split('-').at(-1);
  const imageTitle = entry => dateLabel(entry)+' · '+entry.width+' × '+entry.height+' · Seed '+(entry.params.seed ?? '—');
  function choose(entry) {
    if (!selectedA) selectedA = entry.name;
    else selectedB = entry.name;
  }
  function showParameters(entry) {infoName = entry.name; parameterDialog.showModal();}
  $effect(() => {history.length; page = 0;});
  $effect(() => {
    const entries = visible;
    let active = true;
    for (const entry of entries) loadThumbnail(entry).then(image => {
      if (active) thumbnails[entry.name] = image.url;
    });
    return () => {active = false;};
  });
</script>

<section class="history" class:expanded class:comparing aria-label="历史生成记录">
  <div class="toolbar">
    <h3>历史 <span>{history.length}</span></h3>
    {#if history.length}
      <label class="picker"><span>A</span><select aria-label="对比图 A" bind:value={selectedA}><option value="">选择图片 A</option>{#each history as entry (entry.name)}<option value={entry.name}>{optionLabel(entry)}</option>{/each}</select></label>
      <button class="icon-button swap" aria-label="交换 A/B" title="交换 A/B" disabled={!comparing} onclick={() => {[selectedA, selectedB] = [selectedB, selectedA];}}>⇄</button>
      <label class="picker"><span>B</span><select aria-label="对比图 B" bind:value={selectedB}><option value="">选择图片 B</option>{#each history as entry (entry.name)}<option value={entry.name}>{optionLabel(entry)}</option>{/each}</select></label>
      <div class="modes" role="group" aria-label="对比模式">
        <button class:active={mode === 'side'} aria-label="并排对比" aria-pressed={mode === 'side'} onclick={() => mode = 'side'}>并排</button>
        <button class:active={mode === 'mask'} aria-label="遮罩对比" aria-pressed={mode === 'mask'} onclick={() => mode = 'mask'}>遮罩</button>
      </div>
      {#if comparing}<button class="quiet" onclick={() => {selectedA = ''; selectedB = '';}}>图片墙</button>{:else}<span class="hint">点选两张图片开始对比</span>{/if}
      <div class="toolbar-end">
        {#if pageCount > 1}<div class="pages"><button class="icon-button" aria-label="上一页" disabled={page === 0} onclick={() => page -= 1}>‹</button><span>{page+1}/{pageCount}</span><button class="icon-button" aria-label="下一页" disabled={page + 1 >= pageCount} onclick={() => page += 1}>›</button></div>{/if}
        <button class="icon-button" aria-label={expanded ? '收起对比' : '展开对比'} title={expanded ? '收起对比' : '展开对比'} onclick={() => expanded = !expanded}>{expanded ? '↙' : '⛶'}</button>
      </div>
    {/if}
  </div>
  {#if comparing}
    <div class="comparison-slot"><ImageComparison {a} {b} {mode} {loadPreview} {expanded} thumbnailA={thumbnails[a.name] || ''} thumbnailB={thumbnails[b.name] || ''} /></div>
  {/if}
  {#if history.length}
    <div class="gallery" class:filmstrip={comparing} aria-label="历史图片">
      {#each visible as entry (entry.name)}
        <article class="record" class:selected={entry.name === selectedA || entry.name === selectedB} style:--ratio={entry.width / entry.height}>
          <button class="image-select" aria-label={'选择图片：'+entry.name} title={imageTitle(entry)} onclick={() => choose(entry)}>
            {#if thumbnails[entry.name]}<img src={thumbnails[entry.name]} alt={'历史生成图片 '+dateLabel(entry)} />{:else}<span class="loading">载入中…</span>{/if}
          </button>
          <div class="badges">{#if entry.name === selectedA}<span>A</span>{/if}{#if entry.name === selectedB}<span>B</span>{/if}</div>
          <div class="card-tools">
            <button aria-label={'生成参数：'+entry.name} title="生成参数" onclick={() => showParameters(entry)}>ⓘ</button>
            <button aria-label={'下载：'+entry.name} title="下载原图" onclick={() => download(entry)}>↓</button>
          </div>
          <div class="card-bottom"><time datetime={entry.created_at}>{dateLabel(entry)}</time><div class="assign"><button class:chosen={entry.name === selectedA} aria-pressed={entry.name === selectedA} aria-label={'设为 A：'+entry.name} onclick={() => selectedA = entry.name}>A</button><button class:chosen={entry.name === selectedB} aria-pressed={entry.name === selectedB} aria-label={'设为 B：'+entry.name} onclick={() => selectedB = entry.name}>B</button></div></div>
        </article>
      {/each}
    </div>
  {:else}
    <p class="empty">生成完成后，图片会自动出现在这里。</p>
  {/if}
</section>

<dialog bind:this={parameterDialog} aria-label="生成参数">
  <div class="dialog-heading"><h3>生成参数</h3><button class="icon-button" aria-label="关闭生成参数" onclick={() => parameterDialog.close()}>×</button></div>
  {#if info}<p class="detail-title">{imageTitle(info)}</p><dl>{#each Object.entries(info.params) as [key, value]}<dt>{key}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>{/each}</dl><p class="run-info">{Object.entries(info.run_info).map(([key,value]) => key+': '+value).join(' · ')}</p><p class="filename">{info.name}</p>{/if}
</dialog>

<style>
  .history {margin-top:14px;padding-top:7px;border-top:1px solid #e2e6ed;min-width:0;}
  .history.expanded {position:fixed;inset:0;z-index:4000;display:flex;flex-direction:column;margin:0;padding:6px;background:#f6f7f9;border:0;}
  .toolbar {display:flex;align-items:center;gap:7px;min-height:37px;margin-bottom:6px;flex-wrap:wrap;}
  h3 {display:flex;align-items:center;gap:5px;margin:0 5px 0 0;font-size:12px;font-weight:650;color:#475262;white-space:nowrap;}
  h3>span {font-size:10px;font-weight:500;color:#84909f;}
  .picker {display:flex;align-items:center;gap:5px;width:clamp(140px,17vw,240px);min-width:0;font-size:11px;color:#5f6b7c;}
  .picker>span {font-size:10px;font-weight:650;}
  select {width:100%;min-width:0;height:28px;border:1px solid #e1e6ec;background:#fff;color:#596677;border-radius:4px;font-size:10px;padding:0 5px;text-overflow:ellipsis;}
  button {cursor:pointer;}
  .icon-button,.quiet,.modes button {display:inline-grid;place-items:center;height:27px;min-width:27px;border:0;border-radius:4px;background:transparent;color:#6c7888;font-size:13px;padding:0 6px;}
  button:disabled {opacity:.3;cursor:default;}
  .icon-button:hover:enabled,.quiet:hover {background:#e8edf2;}
  .swap {font-size:17px;min-width:20px;padding:0 2px;}
  .quiet {font-size:10px;}
  .modes {display:flex;gap:2px;padding:2px;border-radius:5px;background:#eaf0f4;}
  .modes button {height:23px;min-width:41px;font-size:10px;}
  .modes button.active {background:#fff;color:#4d5e70;box-shadow:0 1px 3px #26384d16;}
  .hint {font-size:10px;color:#9aa3ae;}
  .toolbar-end {margin-left:auto;display:flex;align-items:center;gap:6px;}
  .pages {display:flex;align-items:center;font-size:10px;color:#8b97a6;font-variant-numeric:tabular-nums;}
  .comparison-slot {min-height:0;}
  .expanded .comparison-slot {flex:1;}
  .gallery {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));align-items:start;gap:6px;}
  .record {position:relative;min-width:0;aspect-ratio:var(--ratio);overflow:hidden;border-radius:5px;background:#edf0f3;}
  .record.selected {outline:2px solid #e1a16d;outline-offset:-2px;}
  .image-select {display:block;width:100%;height:100%;padding:0;border:0;background:transparent;}
  .image-select img {display:block;width:100%;height:100%;object-fit:contain;}
  .loading {color:#9ba5b2;font-size:11px;}
  .badges {position:absolute;top:7px;left:7px;display:flex;gap:4px;pointer-events:none;}
  .badges span,.assign button,.card-tools button {display:grid;place-items:center;width:24px;height:24px;background:#162431a6;color:white;font-size:10px;border:0;border-radius:4px;backdrop-filter:blur(5px);}
  .badges span {background:#172734ce;font-weight:650;}
  .card-tools {position:absolute;top:6px;right:6px;display:flex;gap:4px;opacity:0;transition:opacity .12s;}
  .card-tools button {font-size:15px;}
  .card-bottom {position:absolute;bottom:0;left:0;right:0;display:flex;align-items:flex-end;justify-content:space-between;gap:3px;min-height:36px;padding:14px 6px 6px;background:linear-gradient(transparent,#1424358c);color:white;opacity:0;transition:opacity .12s;pointer-events:none;}
  time {font-size:9px;white-space:nowrap;text-overflow:ellipsis;overflow:hidden;line-height:24px;}
  .assign {display:flex;gap:3px;pointer-events:auto;}
  .assign button {width:24px;height:23px;}
  .assign button.chosen {background:#e7ad7d;color:#35281d;}
  .record:hover .card-tools,.record:focus-within .card-tools,.record:hover .card-bottom,.record:focus-within .card-bottom {opacity:1;}
  .gallery.filmstrip {display:flex;flex:none;gap:5px;margin-top:6px;padding:2px 0 3px;overflow-x:auto;overflow-y:hidden;scrollbar-width:thin;}
  .filmstrip .record {flex:none;height:104px;width:calc(104px * var(--ratio));}
  .filmstrip time {display:none;}.filmstrip .card-bottom {min-height:0;padding-top:8px;justify-content:flex-end;}
  .filmstrip .badges {top:4px;left:4px;}.filmstrip .badges span {width:19px;height:19px;font-size:9px;}
  .expanded>.gallery:not(.filmstrip) {overflow-y:auto;}
  .empty {padding:16px 0;color:#909ba8;font-size:11px;text-align:center;}
  dialog {position:fixed;inset:0;margin:auto;width:min(620px,90vw);max-height:80dvh;padding:16px;border:1px solid #dce3eb;border-radius:9px;background:#fff;color:#536173;box-shadow:0 16px 80px #11253d33;}
  dialog::backdrop {background:#1424355c;backdrop-filter:blur(3px);}
  .dialog-heading {display:flex;justify-content:space-between;align-items:center;}
  .detail-title,.filename,.run-info {font-size:11px;line-height:1.7;overflow-wrap:anywhere;}
  dl {display:grid;grid-template-columns:auto minmax(0,1fr);gap:8px 12px;font-size:11px;line-height:1.7;margin:14px 0;}
  dt {font-weight:600;}dd {margin:0;white-space:pre-wrap;overflow-wrap:anywhere;}
  @media(hover:none){.card-tools,.card-bottom{opacity:1;}}
  @media(max-width:650px){.toolbar{gap:5px;min-height:32px;}.toolbar h3{font-size:11px;}.picker{flex:1;min-width:90px;width:auto;}select{font-size:10px;height:27px;}.hint{display:none;}.toolbar-end{margin-left:0;}.gallery{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;}.filmstrip .record{height:82px;width:calc(82px * var(--ratio));}.card-tools button,.assign button{width:22px;height:22px;}.card-bottom time{font-size:8px;}}
</style>
