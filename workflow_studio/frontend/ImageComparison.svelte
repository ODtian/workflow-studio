<script>
  import {untrack} from 'svelte';
  import {Button} from '$lib/components/ui/button';
  import {Switch} from '$lib/components/ui/switch';
  import ComparisonPane from './ComparisonPane.svelte';
  let {entries=[],loadOriginal,loadPreview,thumbnails={},expanded=false}=$props();
  let sources=$state({}),shared=$state({zoom:1,x:0,y:0}),views=$state({}),synchronized=$state(true),columns=$state(2);
  let layoutColumns=$derived(Math.min(columns,entries.length));
  $effect(()=>{
    const selected=entries;let active=true;
    untrack(()=>{for(const entry of selected){
      if(!sources[entry.name])sources[entry.name]=thumbnails[entry.name]||'';
      let original=false;
      loadPreview(entry).then(image=>{if(active&&!original)sources[entry.name]=image.url;});
      loadOriginal(entry).then(image=>{original=true;if(active)sources[entry.name]=image.url;});
    }});
    return()=>{active=false;};
  });
  function change(name,view){if(synchronized)shared=view;else views[name]=view;}
  function toggleSync(value){if(!value)views=Object.fromEntries(entries.map(entry=>[entry.name,{...shared}]));else shared=views[entries[0].name]||shared;synchronized=value;}
  function reset(){shared={zoom:1,x:0,y:0};views={};}
</script>
<section class="comparison" class:expanded aria-label={entries.length+' 张图片对比'}>
  <div class="comparison-toolbar"><strong>对比 {entries.length} 张</strong><label class="sync-control"><Switch checked={synchronized} onCheckedChange={toggleSync} aria-label="同步缩放和平移"/>同步缩放 / 平移</label><label class="column-control">每行<select aria-label="对比每行图片数" bind:value={columns}>{#each entries as _,index}<option value={index+1}>{index+1} 张</option>{/each}</select></label><Button size="sm" variant="outline" onclick={reset}>全部适应</Button><span class="hint">滚轮 / 双指缩放 · 拖动平移</span></div>
  <div class="comparison-grid" style:--columns={layoutColumns}>{#each entries as entry,index (entry.name)}<ComparisonPane {entry} {index} source={sources[entry.name]||''} view={synchronized?shared:views[entry.name]||{zoom:1,x:0,y:0}} onchange={view=>change(entry.name,view)}/>{/each}</div>
</section>
<style>
.comparison{min-width:0;display:flex;flex-direction:column;gap:10px}.comparison-toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-size:11px}.comparison-toolbar strong{font-size:13px}.sync-control,.column-control{display:flex;align-items:center;gap:7px}.column-control select{padding:4px 7px;min-width:60px}.comparison-grid{display:grid;grid-template-columns:repeat(var(--columns),minmax(240px,1fr));grid-auto-rows:minmax(320px,58dvh);gap:9px;overflow:auto;padding-bottom:5px}.expanded .comparison-grid{grid-auto-rows:minmax(320px,68dvh)}@media(max-width:760px){.comparison-toolbar{gap:8px}.comparison-toolbar .hint{width:100%}.comparison-grid{grid-template-columns:repeat(var(--columns),minmax(260px,1fr));grid-auto-rows:58dvh}.column-control select{font-size:13px;min-height:30px}}
</style>
