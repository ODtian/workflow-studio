"""Load Studio directly from a Git checkout or an explicitly selected Git ref."""
from pathlib import Path
import subprocess
import sys
import tempfile


def load_studio(*, privacy_probe=False, source_ref=None):
    workspace = Path.cwd()
    source = Path(__file__).resolve().parent
    if not (source / "workflow_studio").is_dir():
        revision = source_ref or ("codex/private-notebook-probe" if privacy_probe else "main")
        source = Path(tempfile.gettempdir()) / ("workflow-studio-" + revision.replace("/", "-"))
        if not (source / ".git").exists():
            subprocess.run(["git", "clone", "--depth", "1", "--no-checkout",
                            "https://github.com/ODtian/workflow-studio.git", str(source)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source), "fetch", "--depth", "1", "origin", revision],
                       check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD"],
                       check=True, capture_output=True, text=True)
    for directory in (source, source / "workflow_studio"):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    if privacy_probe:
        from private_probe import get_private_studio
        return get_private_studio(workspace=workspace)
    from studio_bootstrap import get_studio
    return get_studio(workspace=workspace)
