"""Load the current Studio source for the small notebook entry cell."""
from pathlib import Path
import subprocess
import sys


def load_studio():
    workspace = Path.cwd()
    source = Path('/tmp/workflow-studio-source')
    if (source / '.git').exists():
        subprocess.run(['git', '-C', str(source), 'pull', '--ff-only'],
                       check=True, capture_output=True, text=True)
    else:
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', 'main',
                        'https://github.com/ODtian/workflow-studio.git', str(source)],
                       check=True, capture_output=True, text=True)
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    from studio_bootstrap import get_studio
    return get_studio(workspace=workspace)
