"""Load Studio from this checkout or the installed package's Git commit."""
from importlib.metadata import distribution
from pathlib import Path
import json
import subprocess
import sys
import tempfile


def load_studio(*, privacy_probe=False):
    workspace = Path.cwd()
    source = Path(__file__).resolve().parent
    if not (source / "workflow_studio").is_dir():
        direct_url = json.loads(distribution("workflow-studio").read_text("direct_url.json"))
        revision = direct_url["vcs_info"]["commit_id"]
        source = Path(tempfile.gettempdir()) / ("workflow-studio-" + revision)
        if not (source / ".git").exists():
            subprocess.run(["git", "clone", "--depth", "1", "--no-checkout",
                            direct_url["url"], str(source)], check=True, capture_output=True, text=True)
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
