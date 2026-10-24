<script>
  import {onDestroy} from 'svelte';
  import {Button} from '$lib/components/ui/button';
  import {Maximize2, Image} from '@lucide/svelte';
  import PhotoSwipe from 'photoswipe';
  import 'photoswipe/style.css';
  import {i18n} from './bridge.js';

  let {preview = '', result, loadOriginal, onload} = $props();
  let container;
  let viewer;
  let fullscreen = $state(false);

  async function open() {
    if (viewer?.isOpen) return;
    fullscreen = true;
    const image = container.querySelector('img');
    const source = [{src:preview, width:result?.width || image.naturalWidth,
      height:result?.height || image.naturalHeight, alt:'生成图片'}];
    const current = new PhotoSwipe({
      dataSource:source, appendToEl:container.getRootNode(),
      wheelToZoom:true, pinchToClose:false, closeOnVerticalDrag:false, allowPanToNext:false,
      initialZoomLevel:'fit', secondaryZoomLevel:level => level.fit * 2, maxZoomLevel:8,
      bgOpacity:1, counter:false, arrowPrev:false, arrowNext:false,
      closeTitle:'关闭', zoomTitle:'放大 / 还原', trapFocus:false,
      showHideAnimationType:'fade', showAnimationDuration:100, hideAnimationDuration:100
    });
    viewer = current;
    current.on('destroy', () => {fullscreen = false; viewer = null;});
    current.init();
    if (result && loadOriginal) {
      const original = await loadOriginal(result);
      if (!current.isDestroying) {
        const {currZoomLevel, pan} = current.currSlide;
        const position = {...pan};
        source[0] = {...source[0], src:original.url};
        current.refreshSlideContent(0);
        current.currSlide.zoomTo(currZoomLevel, {x:current.viewportSize.x / 2,y:current.viewportSize.y / 2}, 0);
        current.currSlide.panTo(position.x, position.y);
      }
    }
  }
  onDestroy(() => viewer?.destroy());
</script>

<div class="image-preview" bind:this={container}>
  {#if preview}<button class="preview-image" aria-label="放大生成图片" onclick={open}><img src={preview} alt="工作流图片" {onload}/></button><Button class="preview-expand" variant="secondary" size="icon" aria-label="全屏预览" onclick={open}><Maximize2 size={17}/></Button>
  {:else}<div class="preview-empty"><p>暂无预览</p></div>{/if}
</div>

<style>
  .image-preview{position:relative;height:100%;width:100%;}
  .preview-image{display:block;border:0;background:transparent;padding:20px;width:100%;height:100%;cursor:zoom-in;}
  .preview-image img{width:100%;height:100%;object-fit:contain;}
  .image-preview :global(.preview-expand){position:absolute;right:16px;top:16px;}
  .preview-empty{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--muted-foreground);gap:12px;}
  .preview-empty>div{border:1px solid var(--border);background:var(--background);padding:22px;border-radius:18px;margin-bottom:4px;}
  .preview-empty h2{font-weight:500;font-size:17px;color:var(--foreground);}.preview-empty p{font-size:13px;}
  .image-preview :global(.image-container){height:100%;}
  .image-preview :global(.image-frame){background:transparent;}
  .image-preview :global(img){object-fit:contain;}
  :global(.pswp){z-index:5000;}
  :global(.pswp__top-bar){padding:env(safe-area-inset-top) max(12px,env(safe-area-inset-right)) 0 12px;box-sizing:border-box;}
</style>
