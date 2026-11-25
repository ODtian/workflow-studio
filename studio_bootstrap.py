"""Start Studio with notebook configuration and temporary runtime files."""
from pathlib import Path
import os
import shutil
import sys
import tempfile


SOURCE = Path(__file__).parent


def get_studio(workspace=None, *, runtime=None, models=None, comfy=None, drive_directory=None, state_directory=None):
    workspace = Path(workspace or Path.cwd()).resolve()
    runtime = Path(runtime or Path(tempfile.gettempdir()) / 'workflow-studio-runtime').resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / 'input').mkdir(exist_ok=True)
    source = SOURCE / 'workflow_studio'
    for directory in (SOURCE, source):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    os.environ['WORKFLOW_WORKSPACE'] = str(runtime)
    os.environ['WORKFLOW_GZIP_CONTENT'] = '1'
    os.environ['WORKFLOW_MODELS_DIR'] = str(Path(models or workspace / 'models').resolve())
    os.environ['WORKFLOW_COMFY_ROOT'] = str(Path(comfy or runtime / 'comfy-core').resolve())
    os.environ['WORKFLOW_STUDIO_STATE_DIR'] = str(Path(state_directory or runtime / 'settings').resolve())
    import workspace_store
    output = workspace_store.CONTENT_DIR / 'media'
    os.environ['WORKFLOW_OUTPUT_DIR'] = str(output)
    os.environ['WORKFLOW_PI_SESSIONS'] = str(workspace_store.CONTENT_DIR / '.pi/agent/sessions')
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

    from studio_panel import get_panel
    return get_panel(workflow_dir=workflows, output_dir=output, settings_backup=save_settings,
                     drive_directory=drive_directory)
