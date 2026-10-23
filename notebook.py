import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as _studio_mo
    
    def _current_studio():
        from pathlib import Path
        import subprocess
        import sys
    
        workspace = Path.cwd()
        source = Path("/tmp/workflow-studio-source")
        if (source / ".git").exists():
            subprocess.run(["git", "-C", str(source), "pull", "--ff-only"],
                           check=True, capture_output=True, text=True)
        else:
            subprocess.run(["git", "clone", "--depth", "1", "--branch", "main",
                            "https://github.com/ODtian/workflow-studio.git", str(source)],
                           check=True, capture_output=True, text=True)
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        from studio_bootstrap import get_studio
        return get_studio(workspace=workspace)
    
    studio_panel = _current_studio()
    _studio_mo.ui.anywidget(studio_panel)
    return


if __name__ == "__main__":
    app.run()
