import {mount, unmount} from 'svelte';
import App from './App.svelte';
import './theme.css';
import './mobile.css';
import {watchColorTheme} from './colorTheme.js';
export {watchColorTheme, setColorTheme} from './colorTheme.js';

export function render({model, el}) {
  const host = document.createElement('div');
  host.className = 'workflow-studio';
  const stopTheme = watchColorTheme(host);
  el.append(host);
  const shadow = host.attachShadow({mode: 'open'});
  const style = document.createElement('style');
  style.textContent = GRADIO_COMPONENT_CSS.replaceAll(':root', ':host') +
    ':host{display:block;width:100%;background:var(--background)}' +
    ':host(.studio-expanded){position:fixed;inset:0;z-index:1000;overflow:hidden}';
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
    host.classList.toggle('studio-expanded', expanded);
    if (expanded) {
      document.body.append(host);
    } else {
      el.append(host);
      host.style.top = '';
      host.style.height = '';
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
    stopTheme();
    window.removeEventListener('resize', updateViewport);
    viewport?.removeEventListener('resize', updateViewport);
    viewport?.removeEventListener('scroll', updateViewport);
    unmount(app); host.remove();
  };
}

export default {render};
