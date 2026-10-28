"""Start Studio with notebook configuration and temporary runtime files."""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile


SOURCE = Path(__file__).parent


def get_studio(workspace=None):
    from dotenv import load_dotenv
    workspace = Path(workspace or Path.cwd()).resolve()
    load_dotenv(workspace / '.env')
    runtime = Path(tempfile.gettempdir()) / 'workflow-studio-runtime'
    runtime.mkdir(exist_ok=True)
    (runtime / 'input').mkdir(exist_ok=True)
    source = SOURCE / 'workflow_studio'
    for directory in (SOURCE, source):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    os.environ['WORKFLOW_WORKSPACE'] = str(runtime)
    os.environ['WORKFLOW_GZIP_CONTENT'] = '1'
    os.environ['WORKFLOW_MODELS_DIR'] = str(Path(tempfile.gettempdir()) / 'molab-comfy-runtime/models')
    os.environ['WORKFLOW_COMFY_ROOT'] = str(Path(tempfile.gettempdir()) / 'workflow-studio-comfy-core-0.42.0')
    import workspace_store
    output = workspace_store.CONTENT_DIR / 'media'
    os.environ['WORKFLOW_OUTPUT_DIR'] = str(output)
    os.environ['WORKFLOW_PI_SESSIONS'] = str(workspace_store.CONTENT_DIR / '.pi/agent/sessions')
    if importlib.util.find_spec('anywidget') is None:
        subprocess.run(['uv', 'pip', 'install', '--no-deps', '--python', sys.executable,
                        'anywidget'], check=True)
    workflows = runtime / 'workflows'
    workflows.mkdir(exist_ok=True)
    for sample in (SOURCE / 'studio_workflows').glob('*.py'):
        shutil.copy2(sample, workflows / sample.name)
    for sample in (source / 'workflows').glob('*.py'):
        target = workflows / sample.name
        if not target.exists():
            shutil.copy2(sample, target)
    workspace_store.restore_files()

    def save_settings(value):
        workspace_store.edit(lambda state: state.update(studio_settings=value))

    from panel import get_panel
    return get_panel(workflow_dir=workflows, output_dir=output, settings_backup=save_settings)
