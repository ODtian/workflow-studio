"""Load the current Studio source for the small notebook entry cell."""
from pathlib import Path
import subprocess
import sys


def load_studio(*, privacy_probe=False):
    workspace = Path.cwd()
    branch = 'codex/private-notebook-probe' if privacy_probe else 'main'
    source = Path('/tmp/workflow-studio-private-probe-source' if privacy_probe else '/tmp/workflow-studio-source')
    if (source / '.git').exists():
        subprocess.run(['git', '-C', str(source), 'pull', '--ff-only'],
                       check=True, capture_output=True, text=True)
    else:
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', branch,
                        'https://github.com/ODtian/workflow-studio.git', str(source)],
                       check=True, capture_output=True, text=True)
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    if privacy_probe:
        package_source = str(source / 'workflow_studio')
        if package_source not in sys.path:
            sys.path.insert(0, package_source)
        from private_probe import get_private_studio
        return get_private_studio(workspace=workspace)
    from studio_bootstrap import get_studio
    return get_studio(workspace=workspace)
