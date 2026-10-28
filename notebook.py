import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as _studio_mo
    from urllib.request import urlopen as _studio_open
    _studio_entry = {}
    exec(_studio_open('https://raw.githubusercontent.com/ODtian/workflow-studio/main/studio_entry.py').read(), _studio_entry)
    studio_panel = _studio_entry['load_studio']()
    _studio_mo.ui.anywidget(studio_panel)
    return


if __name__ == "__main__":
    app.run()
