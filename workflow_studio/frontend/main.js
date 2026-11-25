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
  const initialOutputHeight = 760;
  const viewport = window.visualViewport;
  const compact = window.matchMedia('(max-width:760px), (max-width:1000px) and (max-height:500px)');
  const updateViewport = () => {
    const height = (compact.matches && viewport?.height) || window.innerHeight || initialOutputHeight;
    host.style.height = height+'px';
    host.style.setProperty('--studio-viewport-height', height+'px');
    host.dataset.keyboardOpen = String(compact.matches && window.innerHeight-height>120);
  };
  window.addEventListener('resize', updateViewport);
  viewport?.addEventListener('resize', updateViewport);
  viewport?.addEventListener('scroll', updateViewport);
  // Seed the Colab output before it measures the widget.
  colabOutput?.setIframeHeight?.(initialOutputHeight, true);
  updateViewport();
  const app = mount(App, {target: shadow, props: {model}});
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
