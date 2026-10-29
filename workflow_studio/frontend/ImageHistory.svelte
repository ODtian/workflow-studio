<script>
  import {Button} from '$lib/components/ui/button';
  import {Badge} from '$lib/components/ui/badge';
  import {Download, Info, Maximize2, X, ArrowLeftRight, ChevronLeft, ChevronRight, Play} from '@lucide/svelte';
  import ImageComparison from './ImageComparison.svelte';
  let {history = [], playback=$bindable({volume:0.25,muted:false}), loadPreview, loadThumbnail, loadOriginal, download} = $props();
  let selectedA = $state('');
  let selectedB = $state('');
  let mode = $state('side');
  let expanded = $state(false);
  let page = $state(0);
  let thumbnails = $state({});
  let infoName = $state('');
  let parameterDialog;
  let videoURL=$state(''),videoName=$state('');
  let images=$derived(history.filter(entry=>entry.kind!=='video'));
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
  async function choose(entry) {
    if(entry.kind==='video') {videoName=entry.name;videoURL=(await loadPreview(entry)).url;return;}
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

<section class="history" class:expanded aria-label="历史生成记录">
  <div class="gallery-toolbar"><h3>生成历史 <Badge variant="secondary">{history.length}</Badge></h3>
    {#if images.length>1}<div class="gallery-selectors"><select aria-label="对比图 A" bind:value={selectedA}><option value="">选择图片 A</option>{#each images as entry}<option value={entry.name}>{optionLabel(entry)}</option>{/each}</select><Button variant="ghost" size="icon-sm" aria-label="交换 A/B" disabled={!comparing} onclick={()=>{[selectedA,selectedB]=[selectedB,selectedA];}}><ArrowLeftRight size={13}/></Button><select aria-label="对比图 B" bind:value={selectedB}><option value="">选择图片 B</option>{#each images as entry}<option value={entry.name}>{optionLabel(entry)}</option>{/each}</select></div>{/if}
    {#if comparing}<div class="segmented"><Button size="sm" variant={mode==='side'?'secondary':'ghost'} onclick={()=>mode='side'}>并排</Button><Button size="sm" variant={mode==='mask'?'secondary':'ghost'} onclick={()=>mode='mask'}>遮罩</Button><Button size="sm" variant="ghost" onclick={()=>{selectedA='';selectedB='';}}>图片墙</Button></div>{/if}
    <Button variant="ghost" size="icon-sm" aria-label={expanded?'收起对比':'展开对比'} onclick={()=>expanded=!expanded}>{#if expanded}<X size={15}/>{:else}<Maximize2 size={15}/>{/if}</Button>
  </div>
  {#if videoURL}<div class="history-video"><video src={videoURL} bind:volume={playback.volume} bind:muted={playback.muted} controls playsinline preload="metadata" aria-label={'历史视频 '+videoName}></video><Button size="icon-sm" variant="ghost" aria-label="关闭历史视频" onclick={()=>{videoURL='';videoName='';}}><X size={15}/></Button></div>{/if}
  {#if comparing}<div class="comparison-slot"><ImageComparison {a} {b} {mode} {loadPreview} {expanded} thumbnailA={thumbnails[a.name]||''} thumbnailB={thumbnails[b.name]||''}/></div>{/if}
  <div class="image-gallery" class:filmstrip={comparing}>{#each visible as entry}
    <article class="gallery-record" class:chosen={entry.name===selectedA||entry.name===selectedB}>
      <button class="gallery-image" aria-label={(entry.kind==='video'?'播放视频 ':'选择图片 ')+entry.name} onclick={()=>choose(entry)}>{#if thumbnails[entry.name]}<img src={thumbnails[entry.name]} alt={'历史预览 '+dateLabel(entry)}/>{:else}<span>载入中…</span>{/if}{#if entry.kind==='video'}<span class="video-badge"><Play size={14}/>{entry.duration.toFixed(1)} s</span>{/if}</button>
      <div class="gallery-card-actions"><Button variant="secondary" size="icon-xs" aria-label={'生成参数 '+entry.name} onclick={()=>showParameters(entry)}><Info size={12}/></Button><Button variant="secondary" size="icon-xs" aria-label={'下载 '+entry.name} onclick={()=>download(entry)}><Download size={12}/></Button></div>
      <div class="gallery-caption"><time>{dateLabel(entry)}</time>{#if entry.kind!=='video'}<div class="row"><Button variant={selectedA===entry.name?'secondary':'ghost'} size="xs" onclick={()=>selectedA=entry.name}>A</Button><Button variant={selectedB===entry.name?'secondary':'ghost'} size="xs" onclick={()=>selectedB=entry.name}>B</Button></div>{/if}</div>
    </article>{:else}<div class="empty-resource">生成结果会显示在这里。</div>{/each}</div>
  {#if pageCount>1}<div class="gallery-pages"><Button variant="outline" size="icon-sm" aria-label="上一页" disabled={page===0} onclick={()=>page-=1}><ChevronLeft size={15}/></Button><span>{page+1} / {pageCount}</span><Button variant="outline" size="icon-sm" aria-label="下一页" disabled={page+1>=pageCount} onclick={()=>page+=1}><ChevronRight size={15}/></Button></div>{/if}
</section>
<dialog bind:this={parameterDialog} aria-label="生成参数"><div class="gallery-dialog-heading"><h3>生成参数</h3><Button variant="ghost" size="icon-sm" aria-label="关闭生成参数" onclick={()=>parameterDialog.close()}><X size={15}/></Button></div>{#if info}<p class="hint">{imageTitle(info)}</p><dl>{#each Object.entries(info.params) as [key,value]}<dt>{key}</dt><dd>{typeof value==='object'?JSON.stringify(value):String(value)}</dd>{/each}</dl>{/if}</dialog>
<style>
.history-video{position:relative;display:flex;justify-content:center;background:#10151c;border-radius:8px;margin-bottom:12px;overflow:hidden}.history-video video{width:100%;max-height:55vh;object-fit:contain}.history-video :global(button){position:absolute;right:5px;top:5px;background:#fff}.gallery-image{position:relative}.video-badge{position:absolute;left:7px;bottom:7px;border-radius:5px;display:flex;align-items:center;gap:5px;padding:3px 6px;background:#142033c9;color:white;font-size:11px}
.history{min-width:0}.history.expanded{position:fixed;inset:0;z-index:4000;background:#fafbfc;padding:20px;display:flex;flex-direction:column;overflow:auto}.gallery-toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}.gallery-toolbar h3{display:flex;align-items:center;gap:9px;font-size:13px;font-weight:600;margin-right:auto}.gallery-selectors{display:flex;align-items:center;gap:4px;min-width:0}.gallery-selectors select{max-width:160px;font-size:10px}.image-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}.gallery-record{position:relative;min-width:0;border:1px solid var(--border);border-radius:10px;overflow:hidden;background:white}.gallery-record.chosen{border-color:#7f92ab;box-shadow:0 0 0 1px #7f92ab}.gallery-image{height:220px;display:block;width:100%;padding:0;border:0;background:#edf1f6;color:#a3adba;overflow:hidden}.gallery-image img{width:100%;height:100%;object-fit:cover;transition:transform .2s}.gallery-image:hover img{transform:scale(1.025)}.gallery-card-actions{position:absolute;top:9px;right:9px;display:flex;gap:5px;opacity:0;transition:opacity .15s}.gallery-record:hover .gallery-card-actions,.gallery-record:focus-within .gallery-card-actions{opacity:1}.gallery-caption{display:flex;align-items:center;justify-content:space-between;gap:4px;padding:7px 8px}.gallery-caption time{font-size:9px;color:#99a5b5}.filmstrip{display:flex;overflow:auto;gap:9px;padding:15px 0}.filmstrip .gallery-record{width:150px;flex-shrink:0}.filmstrip .gallery-image{height:120px}.gallery-pages{display:flex;align-items:center;justify-content:center;gap:14px;padding:20px 0;font-size:11px;color:#99a5b5}dialog{margin:auto;border:1px solid var(--border);border-radius:12px;background:#fff;color:var(--foreground);padding:24px;width:min(660px,90vw);max-height:85dvh;overflow:auto}dialog::backdrop{background:#1d2a3c55;backdrop-filter:blur(3px)}.gallery-dialog-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:15px}.gallery-dialog-heading h3{font-size:15px;font-weight:600}dl{display:grid;grid-template-columns:130px 1fr;gap:9px;margin-top:18px;font-size:12px}dt{color:#9ca9bc}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}@media(max-width:760px){.image-gallery{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.gallery-image{height:180px}.gallery-caption{flex-wrap:wrap}.gallery-caption time{font-size:8px}.gallery-card-actions{opacity:1}.gallery-selectors select{max-width:110px}.gallery-selectors{width:100%}.gallery-caption .row{gap:1px}}
@media (max-width:760px), (max-width:1000px) and (max-height:500px){.history.expanded{padding:12px;height:var(--studio-viewport-height,100dvh);inset:0 0 auto}.gallery-toolbar{gap:8px;margin-bottom:12px}.gallery-selectors{width:100%}.gallery-selectors select{max-width:none;flex:1;min-width:0}.gallery-card-actions{opacity:1;top:6px;right:6px}.gallery-caption{flex-wrap:wrap}.gallery-caption .row{gap:2px}.gallery-caption time{font-size:10px}.image-gallery{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.gallery-image{height:180px}dialog{width:calc(100% - 24px);max-height:calc(var(--studio-viewport-height,100dvh) - 24px);padding:16px}dl{grid-template-columns:minmax(0,1fr);gap:5px;font-size:13px}dd{margin-bottom:10px}.gallery-dialog-heading{position:sticky;top:-16px;background:white;padding-block:8px;z-index:1}}
</style>
