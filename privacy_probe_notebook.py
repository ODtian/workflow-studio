# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo>=0.25.1", "anywidget>=0.9.18", "cryptography", "Pillow",
#     "workflow-studio @ git+https://github.com/ODtian/workflow-studio.git@codex/private-notebook-probe",
# ]
# ///
"""Minimal private text-workflow validation inside the native Studio widget."""
import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    from studio_entry import load_studio
    studio_panel = load_studio(privacy_probe=True)
    mo.ui.anywidget(studio_panel)
    return (studio_panel,)


if __name__ == '__main__':
    app.run()
