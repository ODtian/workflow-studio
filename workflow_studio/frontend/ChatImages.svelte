<script>
  let {value = []} = $props();
  let selected = $state(null);
  let viewer;
</script>

<div class="images" style:--columns={Math.min(value.length,2)}>
  {#each value as image}<figure>
    <button aria-label={'查看图片 '+image.orig_name} onclick={() => {selected=image;viewer.showModal();}}>
      <img src={image.url} alt={image.orig_name} />
    </button>
    <figcaption>{image.orig_name}</figcaption>
  </figure>{/each}
</div>
<dialog bind:this={viewer} aria-label="聊天图片预览">
  <button class="close" aria-label="关闭图片预览" onclick={() => viewer.close()}>×</button>
  {#if selected}<img src={selected.url} alt={selected.orig_name} />{/if}
</dialog>

<style>
  .images{display:grid;grid-template-columns:repeat(var(--columns),minmax(0,1fr));gap:7px;width:100%;}
  figure{margin:0;min-width:0;}
  figure button{display:block;width:100%;padding:0;border:0;background:#fff;border-radius:5px;overflow:hidden;cursor:zoom-in;}
  figure img{display:block;width:100%;height:205px;object-fit:contain;}
  figcaption{font-size:9px;color:#8a929e;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:4px;}
  dialog{position:fixed;inset:0;margin:auto;padding:18px;max-width:90vw;max-height:90dvh;border:1px solid #dce3eb;border-radius:9px;background:#fff;box-shadow:0 18px 70px #13283d33;}
  dialog::backdrop{background:#14243566;backdrop-filter:blur(3px);}
  dialog>img{display:block;max-width:85vw;max-height:82dvh;object-fit:contain;}
  .close{position:absolute;top:3px;right:4px;display:grid;place-items:center;width:24px;height:24px;border:0;border-radius:50%;background:#fff;color:#69788b;font-size:20px;cursor:pointer;}
  @media(max-width:650px){figure img{height:130px;}.images{gap:4px;}}
</style>
