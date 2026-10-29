# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo>=0.25.1",
#     "workflow-studio @ git+https://github.com/ODtian/workflow-studio.git@main",
# ]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    from studio_entry import load_studio
    studio_panel = load_studio()
    mo.ui.anywidget(studio_panel)
    return (studio_panel,)


if __name__ == "__main__":
    app.run()
