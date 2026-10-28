"""Start Workflow Studio from a Git checkout and a notebook workspace."""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from content_store import enabled, read_text, migrate_file


SOURCE = Path(__file__).parent


def get_studio(workspace=None):
    from dotenv import load_dotenv
    workspace = Path(workspace or Path.cwd()).resolve()
    load_dotenv(workspace / ".env")
    config_path = workspace / "studio_config.json"
    config = {
        "model_dir": "/tmp/molab-comfy-runtime/models",
        "core_dir": "/tmp/workflow-studio-comfy-core",
        "workflow_dir": "studio_workflows",
        "output_dir": "/tmp/workflow-studio-results",
    }
    if config_path.exists():
        config.update(json.loads(read_text(config_path)))
    old_output = Path(config['output_dir'])
    source = SOURCE / "workflow_studio"
    os.environ["WORKFLOW_WORKSPACE"] = str(workspace)
    for directory in (SOURCE, source):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    import workspace_store
    saved_state = workspace_store.read()
    config.update(saved_state.get("studio_config", {}))
    if enabled():
        content = workspace_store.CONTENT_DIR
        config['output_dir'] = str(content / 'media')
        os.environ['WORKFLOW_GZIP_CONTENT'] = '1'
        os.environ['WORKFLOW_PI_SESSIONS'] = str(content / '.pi/agent/sessions')
        for directory in (workspace / 'studio_history', old_output):
            if directory.exists() and directory != content / 'media':
                for path in directory.rglob('*'):
                    if path.is_file():
                        migrate_file(path, content / 'media' / path.relative_to(directory))
    workspace_store.edit(lambda state: state.update(studio_config=config))
    os.environ["WORKFLOW_MODELS_DIR"] = config["model_dir"]
    os.environ["WORKFLOW_COMFY_ROOT"] = config["core_dir"]
    os.environ["WORKFLOW_OUTPUT_DIR"] = config["output_dir"]
    if importlib.util.find_spec("anywidget") is None:
        subprocess.run(["uv", "pip", "install", "--no-deps", "--python", sys.executable,
                        "anywidget"], check=True)
    workflows = workspace / config["workflow_dir"]
    workflows.mkdir(exist_ok=True)
    for sample in (SOURCE / "studio_workflows").glob("*.py"):
        target = workflows / sample.name
        if target.resolve() != sample.resolve():
            shutil.copy2(sample, target)
    for sample in (source / "workflows").glob("*.py"):
        target = workflows / sample.name
        if not target.exists():
            shutil.copy2(sample, target)
    workspace_store.restore_files()
    if enabled():
        session_dir = workspace / '.pi/agent/sessions'
        relocated = {}
        for path in session_dir.rglob('*.jsonl'):
            target = content / path.relative_to(workspace)
            migrate_file(path, target)
            relocated[str(path)] = str(target)
        def relocate_sessions(state):
            for value in state.get('pi_preferences', {}).values():
                if value.get('saved_session') in relocated:
                    value['saved_session'] = relocated[value['saved_session']]
        workspace_store.edit(relocate_sessions)
    settings = workspace / "studio_settings.json"
    saved = workspace_store.read().get("studio_settings")
    if saved and not enabled():
        settings.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    def save_settings(value):
        workspace_store.edit(lambda state: state.update(studio_settings=value))
    if settings.exists():
        value = saved or json.loads(read_text(settings))
        for item in value.get("panels", []):
            params = item.get("params", {})
            if item["workflow"] == "llama_cpp.py" and params.get("model") == "Qwen3.8-27B-Uncensored-FP8":
                from llama_runner import DEFAULT_MODEL, DEFAULT_MMPROJ, DEFAULT_MTP
                params.update(model=DEFAULT_MODEL, mmproj=DEFAULT_MMPROJ, mtp=DEFAULT_MTP,
                              n_gpu_layers=999, speculative_tokens=2, thinking="off")
        if not enabled():
            settings.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        save_settings(value)
        if enabled():
            settings.unlink()
    if enabled():
        for name in ('output_prompt.md', 'prompt_output.md'):
            path = workspace / name
            if path.is_file():
                migrate_file(path, content / 'text' / name)
        for path in (workspace / 'studio_chats').rglob('*'):
            if path.is_file():
                migrate_file(path, content / 'legacy_chats' / path.relative_to(workspace / 'studio_chats'))
    from panel import get_panel
    panel = get_panel(workflow_dir=workflows, output_dir=config["output_dir"], settings_backup=save_settings)
    return panel
