import {mount, unmount} from 'svelte';
import App from './App.svelte';
import './theme.css';

export function render({model, el}) {
  const host = document.createElement('div');
  host.className = 'workflow-studio';
  el.append(host);
  const shadow = host.attachShadow({mode: 'open'});
  const style = document.createElement('style');
  style.textContent = GRADIO_COMPONENT_CSS.replaceAll(':root', ':host') +
    ':host{display:block;width:100%}';
  shadow.append(style);
  let expanded = true;
  const place = () => {
    if (expanded) {
      document.body.append(host);
      host.style.cssText = 'position:fixed;inset:0;z-index:1000;overflow:hidden;background:#fafafa;';
    } else {
      el.append(host);
      host.style.cssText = '';
    }
  };
  place();
  const app = mount(App, {target: shadow, props: {model, initialExpanded: expanded, expand: () => {
    expanded = !expanded;
    place();
    return expanded;
  }}});
  return () => {unmount(app); host.remove();};
}

export default {render};
