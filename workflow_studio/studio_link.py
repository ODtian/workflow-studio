"""Show the current Molab GPU's direct workbench address."""
import anywidget


class StudioLink(anywidget.AnyWidget):
    _esm = """
    export function render({el}) {
      const sandbox = location.hostname.match(/^(sb-[a-z0-9]+)(?:-session)?\\.sb\\.molab\\.run$/);
      if (!sandbox) {
        el.textContent = '启动 GPU 后，在这里显示工作台链接。';
        return;
      }
      const link = document.createElement('a');
      link.href = `https://${sandbox[1]}.sb.molab.run/`;
      link.textContent = link.href;
      link.target = '_blank';
      link.rel = 'noopener';
      el.append(link);
    }
    """
