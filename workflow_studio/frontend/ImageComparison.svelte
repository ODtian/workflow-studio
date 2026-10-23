<script>
  let {a, b, mode = 'side', loadPreview, thumbnailA = '', thumbnailB = '', expanded = false} = $props();
  let sourceA = $state('');
  let sourceB = $state('');
  let split = $state(50);
  $effect(() => {
    const entry = a;
    let active = true;
    sourceA = thumbnailA;
    loadPreview(entry).then(image => {if (active) sourceA = image.url;});
    return () => {active = false;};
  });
  $effect(() => {
    const entry = b;
    let active = true;
    sourceB = thumbnailB;
    loadPreview(entry).then(image => {if (active) sourceB = image.url;});
    return () => {active = false;};
  });
</script>

<div class="comparison" class:expanded aria-label="历史图片对比">
  {#if mode === 'side'}
    <div class="side-by-side">
      <figure>
        {#if sourceA}<img src={sourceA} alt="对比图 A" />{/if}
        <figcaption><strong>A</strong><span>{a.width} × {a.height} · Seed {a.params.seed ?? '—'}</span></figcaption>
      </figure>
      <figure>
        {#if sourceB}<img src={sourceB} alt="对比图 B" />{/if}
        <figcaption><strong>B</strong><span>{b.width} × {b.height} · Seed {b.params.seed ?? '—'}</span></figcaption>
      </figure>
    </div>
  {:else}
    <div class="mask-stage" style:--split={split+'%'}>
      {#if sourceB}<img src={sourceB} alt="对比图 B" />{/if}
      {#if sourceA}<img class="masked" src={sourceA} alt="对比图 A" style:clip-path={'inset(0 '+(100-split)+'% 0 0)'} />{/if}
      <span class="image-label label-a">A</span><span class="image-label label-b">B</span>
      <div class="divider"><span>↔</span></div>
      <input class="drag-mask" type="range" min="0" max="100" step="0.1" bind:value={split} aria-label="拖动遮罩分界线" />
      <div class="mask-control"><span>A</span><input type="range" min="0" max="100" step="0.1" bind:value={split} aria-label="遮罩位置" /><span>B</span><output>{Math.round(split)}%</output></div>
    </div>
  {/if}
</div>

<style>
  .comparison {width:100%;height:clamp(440px,76dvh,1050px);min-height:0;overflow:hidden;background:#edf0f3;border-radius:6px;}
  .comparison.expanded {height:100%;}
  .side-by-side {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:3px;height:100%;background:#d8dfe6;}
  figure,.mask-stage {position:relative;margin:0;min-width:0;height:100%;overflow:hidden;background:#edf0f3;}
  img {position:absolute;inset:0;display:block;width:100%;height:100%;object-fit:contain;}
  figcaption {position:absolute;inset:0 0 auto;display:flex;align-items:center;gap:8px;padding:10px;color:#fff;font-size:11px;background:linear-gradient(#15223270,transparent);pointer-events:none;}
  strong,.image-label {display:grid;place-items:center;background:#182633b5;color:#fff;font-size:11px;font-weight:650;border-radius:4px;width:23px;height:23px;}
  .image-label {position:absolute;top:10px;z-index:2;pointer-events:none;}
  .label-a {left:10px;}.label-b {right:10px;}
  .divider {position:absolute;top:0;bottom:0;left:var(--split);width:2px;background:#fff;box-shadow:0 0 4px #0006;transform:translateX(-1px);pointer-events:none;}
  .divider span {position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);border:1px solid #fff;background:#182633a6;color:#fff;border-radius:50%;width:30px;height:30px;display:grid;place-items:center;font-size:19px;}
  .drag-mask {position:absolute;inset:0;z-index:3;width:100%;height:100%;margin:0;opacity:0;cursor:ew-resize;}
  .mask-stage:focus-within {outline:2px solid #e6a16e;outline-offset:-2px;}
  .mask-control {position:absolute;bottom:9px;left:50%;transform:translateX(-50%);z-index:4;display:flex;align-items:center;gap:8px;width:min(340px,65%);height:28px;padding:0 10px;background:#152232a6;backdrop-filter:blur(7px);border-radius:15px;color:white;font-size:10px;}
  .mask-control input {flex:1;min-width:0;accent-color:#f2af77;}
  output {width:32px;text-align:right;font-variant-numeric:tabular-nums;}
  @media(max-width:650px){.comparison{height:65dvh;min-height:320px;}figcaption{padding:7px;font-size:10px;}figcaption span{max-width:calc(100% - 30px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
</style>
