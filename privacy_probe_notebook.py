# /// script
# requires-python = ">=3.10"
# dependencies = ["marimo>=0.25.1", "anywidget>=0.9.18", "cryptography", "Pillow"]
# ///
"""Minimal private text-workflow validation inside the native Studio widget."""
import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path
    import subprocess
    import sys

    _source = Path('/tmp/workflow-studio-private-probe-source')
    if not _source.exists():
        subprocess.run(['git', 'clone', '--depth', '1', '--branch',
            'codex/private-notebook-probe', 'https://github.com/ODtian/workflow-studio.git',
            str(_source)], check=True, capture_output=True)
    sys.path[:0] = [str(_source / 'workflow_studio'), str(_source)]
    from private_probe import PrivateStudioProbe
    _probe = PrivateStudioProbe(Path.cwd() / '.workflow-private-probe')
    mo.ui.anywidget(_probe)
    return


if __name__ == '__main__':
    app.run()
