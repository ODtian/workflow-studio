<script>
  import {Button} from '$lib/components/ui/button';
  import {Badge} from '$lib/components/ui/badge';
  import {Download,Info,Maximize2,X,ChevronLeft,ChevronRight,Play} from '@lucide/svelte';
  import ImageComparison from './ImageComparison.svelte';
  import ZoomPreview from './ZoomPreview.svelte';
  let {history=[],playback=$bindable({volume:0.25,muted:false}),loadPreview,loadThumbnail,loadOriginal,download}=$props();
  let selectedNames=$state([]),expanded=$state(false),page=$state(0),thumbnails=$state({}),infoName=$state('');
  let parameterDialog;
  let videoURL=$state(''),videoName=$state('');
  const pageSize=16;
  let pageCount=$derived(Math.max(1,Math.ceil(history.length/pageSize)));
  let visible=$derived(history.slice(page*pageSize,(page+1)*pageSize));
  let selected=$derived(selectedNames.map(name=>history.find(entry=>entry.name===name)).filter(Boolean));
  let comparing=$derived(selected.length>1);
  let info=$derived(history.find(entry=>entry.name===infoName));
  const dateLabel=entry=>new Date(entry.created_at).toLocaleString('zh-CN',{hour12:false});
  const imageTitle=entry=>dateLabel(entry)+' · '+entry.width+' × '+entry.height+' · Seed '+(entry.params.seed??'—');
  function toggle(entry){selectedNames=selectedNames.includes(entry.name)?selectedNames.filter(name=>name!==entry.name):[...selectedNames,entry.name];}
  function showParameters(entry){infoName=entry.name;parameterDialog.showModal();}
  async function playVideo(entry){videoName=entry.name;videoURL=(await loadPreview(entry)).url;}
  $effect(()=>{history.length;page=0;});
  $effect(()=>{
    const entries=visible;let active=true;
    for(const entry of entries)loadThumbnail(entry).then(image=>{if(active)thumbnails[entry.name]=image.url;});
    return()=>{active=false;};
  });
</script>
<section class="history" class:expanded aria-label="历史生成记录">
  <div class="gallery-toolbar"><h3>生成历史 <Badge variant="secondary">{history.length}</Badge></h3>
    <span class="selection-count" role="status">已选 {selected.length} 张</span>
    {#if selected.length}<Button variant="ghost" size="sm" onclick={()=>{selectedNames=[];}}>清空选择</Button>{/if}
    <Button variant="ghost" size="icon-sm" aria-label={expanded?'收起历史':'全屏历史'} onclick={()=>expanded=!expanded}>{#if expanded}<X size={15}/>{:else}<Maximize2 size={15}/>{/if}</Button>
  </div>
  {#if videoURL}<div class="history-video"><video src={videoURL} bind:volume={playback.volume} bind:muted={playback.muted} controls playsinline preload="metadata" aria-label={'历史视频 '+videoName}></video><Button size="icon-sm" variant="ghost" aria-label="关闭历史视频" onclick={()=>{videoURL='';videoName='';}}><X size={15}/></Button></div>{/if}
  {#if comparing&&selected.length>1}<ImageComparison entries={selected} {loadOriginal} {loadPreview} {expanded} {thumbnails}/>{/if}
  <div class="image-gallery" class:filmstrip={comparing&&selected.length>1}>{#each visible as entry (entry.name)}
    <article class="gallery-record" class:chosen={selectedNames.includes(entry.name)}>
      <div class="gallery-image">
        {#if entry.kind==='video'}<button class="video-open" aria-label={'播放视频 '+entry.name} onclick={()=>playVideo(entry)}>{#if thumbnails[entry.name]}<img src={thumbnails[entry.name]} alt={'历史预览 '+dateLabel(entry)}/>{/if}<span class="video-badge"><Play size={14}/>{entry.duration.toFixed(1)} s</span></button>
        {:else}<ZoomPreview compact preview={thumbnails[entry.name]||''} result={entry} {loadOriginal} label={'查看原图 '+entry.name}/>{/if}
      </div>
      <div class="gallery-card-actions"><Button variant="secondary" size="icon-xs" aria-label={'生成参数 '+entry.name} onclick={()=>showParameters(entry)}><Info size={12}/></Button><Button variant="secondary" size="icon-xs" aria-label={'下载 '+entry.name} onclick={()=>download(entry)}><Download size={12}/></Button></div>
      <div class="gallery-caption"><time>{dateLabel(entry)}</time>{#if entry.kind!=='video'}<label class="select-image"><input type="checkbox" aria-label={'选择对比 '+entry.name} checked={selectedNames.includes(entry.name)} onchange={()=>toggle(entry)}/><span>{selectedNames.includes(entry.name)?'已选 '+(selectedNames.indexOf(entry.name)+1):'对比'}</span></label>{/if}</div>
    </article>{:else}<div class="empty-resource">生成结果会显示在这里。</div>{/each}
  </div>
  {#if pageCount>1}<div class="gallery-pages"><Button variant="outline" size="icon-sm" aria-label="上一页" disabled={page===0} onclick={()=>page-=1}><ChevronLeft size={15}/></Button><span>{page+1} / {pageCount}</span><Button variant="outline" size="icon-sm" aria-label="下一页" disabled={page+1>=pageCount} onclick={()=>page+=1}><ChevronRight size={15}/></Button></div>{/if}
</section>
<dialog bind:this={parameterDialog} aria-label="生成参数"><div class="gallery-dialog-heading"><h3>生成参数</h3><Button variant="ghost" size="icon-sm" aria-label="关闭生成参数" onclick={()=>parameterDialog.close()}><X size={15}/></Button></div>{#if info}<p class="hint">{imageTitle(info)}</p><dl>{#each Object.entries(info.params) as [key,value]}<dt>{key}</dt><dd>{typeof value==='object'?JSON.stringify(value):String(value)}</dd>{/each}</dl>{/if}</dialog>
<style>
.history{min-width:0}.history.expanded{position:fixed;inset:0;z-index:4000;background:var(--surface-subtle);padding:20px;overflow:auto}.gallery-toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:16px}.gallery-toolbar h3{display:flex;align-items:center;gap:9px;font-size:14px;font-weight:600;margin-right:auto}.selection-count{font-size:11px;color:var(--muted-foreground)}.image-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}.gallery-record{position:relative;min-width:0;border:1px solid var(--border);border-radius:10px;overflow:hidden;background:var(--background)}.gallery-record.chosen{border-color:#648675;box-shadow:0 0 0 1px #648675}.gallery-image{height:220px;position:relative;background:var(--preview-background);overflow:hidden}.gallery-card-actions{position:absolute;top:8px;right:8px;display:flex;gap:5px;opacity:0;transition:opacity .15s}.gallery-record:hover .gallery-card-actions,.gallery-record:focus-within .gallery-card-actions{opacity:1}.gallery-caption{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:8px}.gallery-caption time{font-size:9px;color:var(--muted-foreground)}.select-image{display:flex;align-items:center;gap:5px;font-size:11px;cursor:pointer;white-space:nowrap}.select-image input{width:16px;height:16px;accent-color:var(--success)}.filmstrip{display:flex;overflow:auto;gap:9px;padding:15px 0}.filmstrip .gallery-record{width:150px;flex-shrink:0}.filmstrip .gallery-image{height:110px}.filmstrip .gallery-caption{flex-wrap:wrap}.gallery-pages{display:flex;align-items:center;justify-content:center;gap:14px;padding:20px 0;font-size:11px;color:var(--muted-foreground)}.history-video{position:relative;display:flex;justify-content:center;background:#10151c;border-radius:8px;margin-bottom:12px;overflow:hidden}.history-video video{width:100%;max-height:55vh;object-fit:contain}.history-video :global(button){position:absolute;right:5px;top:5px;background:var(--background)}.video-open{padding:0;border:0;width:100%;height:100%;position:relative;cursor:pointer}.video-open>img{width:100%;height:100%;object-fit:cover}.video-badge{position:absolute;left:7px;bottom:7px;border-radius:5px;display:flex;align-items:center;gap:5px;padding:3px 6px;background:#142033c9;color:white;font-size:11px}dialog{margin:auto;border:1px solid var(--border);border-radius:12px;background:var(--background);color:var(--foreground);padding:24px;width:min(660px,90vw);max-height:85dvh;overflow:auto}dialog::backdrop{background:#1d2a3c55;backdrop-filter:blur(3px)}.gallery-dialog-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:15px}dl{display:grid;grid-template-columns:130px 1fr;gap:9px;margin-top:18px;font-size:12px}dt{color:var(--muted-foreground)}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}@media(max-width:760px){.history.expanded{padding:12px;height:var(--studio-viewport-height,100dvh);inset:0 0 auto}.gallery-toolbar{gap:7px}.gallery-toolbar :global(button){font-size:12px}.image-gallery{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.gallery-image{height:180px}.gallery-card-actions{opacity:1;top:5px;right:5px}.gallery-caption{flex-wrap:wrap}.gallery-caption time{font-size:9px}.select-image{min-height:28px}dialog{width:calc(100% - 24px);padding:16px}dl{grid-template-columns:1fr}}
</style>
