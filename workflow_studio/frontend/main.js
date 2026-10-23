import {mount, unmount} from 'svelte';
import App from './App.svelte';
import reset from '@gradio/theme/reset.css?inline';
import global from '@gradio/theme/global.css?inline';
import pollen from '@gradio/theme/pollen.css?inline';
import theme from './theme.css?inline';

export function render({model, el}) {
  const host = document.createElement('div');
  host.className = 'workflow-studio';
  el.append(host);
  const shadow = host.attachShadow({mode: 'open'});
  const style = document.createElement('style');
  style.textContent = reset + global + pollen.replaceAll(':root', ':host') + theme.replaceAll(':root', ':host') + GRADIO_COMPONENT_CSS +
    ':host{display:block;width:100%}';
  shadow.append(style);
  let expanded = true;
  const place = () => {
    if (expanded) {
      document.body.append(host);
      host.style.cssText = 'position:fixed;inset:0;z-index:1000;overflow:auto;background:#f6f7f9;';
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
