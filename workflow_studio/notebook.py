import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    from panel import get_panel
    mo.ui.anywidget(get_panel())
    return


if __name__ == "__main__":
    app.run()
