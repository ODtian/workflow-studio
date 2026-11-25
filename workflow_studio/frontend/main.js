import {mount, unmount} from 'svelte';
import App from './App.svelte';
import './theme.css';
import './mobile.css';
import {watchColorTheme} from './colorTheme.js';
export {watchColorTheme, setColorTheme} from './colorTheme.js';

export function render({model, el}) {
  const colabOutput = globalThis.google?.colab?.output;
  const host = document.createElement('div');
  host.className = 'workflow-studio';
  const stopTheme = watchColorTheme(host);
  el.append(host);
  const outputStyle = colabOutput && document.createElement('style');
  if (outputStyle) {
    // Colab adds padding around cell output, including in its fullscreen view.
    outputStyle.textContent = 'body:has(.workflow-studio){margin:0;padding:0}';
    el.append(outputStyle);
  }
  const shadow = host.attachShadow({mode: 'open'});
  const style = document.createElement('style');
  style.textContent = GRADIO_COMPONENT_CSS.replaceAll(':root', ':host') +
    ':host{display:block;width:100%;background:var(--background)}';
  shadow.append(style);
  const app = mount(App, {target: shadow, props: {model}});
  const toolbar = shadow.querySelector('.app-topbar');
  const initialOutputHeight = 760;
  const viewport = window.visualViewport;
  const compact = window.matchMedia('(max-width:760px), (max-width:1000px) and (max-height:500px)');
  const updateViewport = () => {
    const frameHeight = window.innerHeight;
    const visibleHeight = (compact.matches && viewport?.height) || frameHeight;
    // Colab can restore a placeholder that is shorter than the toolbar.
    const height = colabOutput && frameHeight <= (toolbar?.offsetHeight || 0)
      ? initialOutputHeight
      : visibleHeight || initialOutputHeight;
    host.style.height = height+'px';
    host.style.setProperty('--studio-viewport-height', height+'px');
    host.dataset.keyboardOpen = String(compact.matches && frameHeight-height>120);
  };
  window.addEventListener('resize', updateViewport);
  viewport?.addEventListener('resize', updateViewport);
  viewport?.addEventListener('scroll', updateViewport);
  // Keep Colab from resizing the frame in response to its own viewport height.
  colabOutput?.setIframeHeight?.(initialOutputHeight, false);
  updateViewport();
  return () => {
    stopTheme();
    window.removeEventListener('resize', updateViewport);
    viewport?.removeEventListener('resize', updateViewport);
    viewport?.removeEventListener('scroll', updateViewport);
    unmount(app);
    host.remove();
    outputStyle?.remove();
  };
}

export default {render};
