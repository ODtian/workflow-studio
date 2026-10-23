<script>
  import {onDestroy} from 'svelte';
  import {Block} from '@gradio/atoms';
  import {BaseStaticImage} from '@gradio/image';
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
  <Block padding={false} elem_classes={['result-image']}>
    <BaseStaticImage show_label={false} alt_text="工作流图片"
      value={preview ? {url:preview,path:'display.jpg',orig_name:'display.jpg'} : null}
      buttons={['fullscreen']} bind:fullscreen onfullscreen={open} onselect={open} {i18n} {onload} />
  </Block>
</div>

<style>
  .image-preview,.image-preview :global(>.block){height:100%;width:100%;border:0;background:transparent;margin:0;}
  .image-preview :global(.image-container){height:100%;}
  .image-preview :global(.image-frame){background:transparent;}
  .image-preview :global(img){object-fit:contain;}
  :global(.pswp){z-index:5000;}
  :global(.pswp__top-bar){padding:env(safe-area-inset-top) max(12px,env(safe-area-inset-right)) 0 12px;box-sizing:border-box;}
</style>
