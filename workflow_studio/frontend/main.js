import {mount, unmount} from 'svelte';
import App from './App.svelte';
import './theme.css';
import './mobile.css';

export function render({model, el}) {
  const host = document.createElement('div');
  host.className = 'workflow-studio';
  el.append(host);
  const shadow = host.attachShadow({mode: 'open'});
  const style = document.createElement('style');
  style.textContent = GRADIO_COMPONENT_CSS.replaceAll(':root', ':host') +
    ':host{display:block;width:100%;color-scheme:light}';
  shadow.append(style);
  let expanded = true;
  const viewport = window.visualViewport;
  const compact = window.matchMedia('(max-width:760px), (max-width:1000px) and (max-height:500px)');
  const updateViewport = () => {
    const height = compact.matches ? viewport?.height || window.innerHeight : window.innerHeight;
    host.style.setProperty('--studio-viewport-height', height+'px');
    if (expanded) {
      host.style.top = (compact.matches ? viewport?.offsetTop || 0 : 0)+'px';
      host.style.height = height+'px';
    }
    host.dataset.keyboardOpen = String(compact.matches && window.innerHeight-height>120);
  };
  const place = () => {
    if (expanded) {
      document.body.append(host);
      host.style.cssText = 'position:fixed;inset:0;z-index:1000;overflow:hidden;background:#fafafa;';
    } else {
      el.append(host);
      host.style.cssText = '';
    }
    updateViewport();
  };
  window.addEventListener('resize', updateViewport);
  viewport?.addEventListener('resize', updateViewport);
  viewport?.addEventListener('scroll', updateViewport);
  place();
  const app = mount(App, {target: shadow, props: {model, initialExpanded: expanded, expand: () => {
    expanded = !expanded;
    place();
    return expanded;
  }}});
  return () => {
    window.removeEventListener('resize', updateViewport);
    viewport?.removeEventListener('resize', updateViewport);
    viewport?.removeEventListener('scroll', updateViewport);
    unmount(app); host.remove();
  };
}

export default {render};
