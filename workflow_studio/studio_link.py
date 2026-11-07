"""Show the current Molab GPU's direct workbench address."""
import base64
import anywidget


class StudioLink(anywidget.AnyWidget):
    _esm = "data:text/javascript;base64," + base64.b64encode("""
    export function render({el}) {
      const sandbox = location.hostname.match(/^(sb-[a-z0-9]+)(?:-session)?\\.sb\\.molab\\.run$/);
      if (!sandbox) {
        el.textContent = '启动 GPU 后，在这里显示工作台链接。';
        return;
      }
      const link = document.createElement('a');
      link.href = location.href;
      link.textContent = '在新窗口打开工作台';
      link.target = '_blank';
      link.rel = 'noopener';
      el.append(link);
    }
    """.encode("utf-8")).decode("ascii")
