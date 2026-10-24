"""Start Workflow Studio from a Git checkout and a notebook workspace."""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys


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
        config.update(json.loads(config_path.read_text(encoding="utf-8")))
    source = SOURCE / "workflow_studio"
    os.environ["WORKFLOW_MODELS_DIR"] = config["model_dir"]
    os.environ["WORKFLOW_COMFY_ROOT"] = config["core_dir"]
    os.environ["WORKFLOW_WORKSPACE"] = str(workspace)
    for directory in (SOURCE, source):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
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
    import workspace_store
    settings = workspace / "studio_settings.json"
    saved = workspace_store.read().get("studio_settings")
    if not settings.exists() and saved:
        settings.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    def save_settings(value):
        workspace_store.edit(lambda state: state.update(studio_settings=value))
    if settings.exists():
        value = json.loads(settings.read_text(encoding="utf-8"))
        for item in value.get("panels", []):
            params = item.get("params", {})
            if item["workflow"] == "llama_cpp.py" and params.get("model") == "Qwen3.8-27B-Uncensored-FP8":
                from llama_runner import DEFAULT_MODEL, DEFAULT_MMPROJ, DEFAULT_MTP
                params.update(model=DEFAULT_MODEL, mmproj=DEFAULT_MMPROJ, mtp=DEFAULT_MTP,
                              n_gpu_layers=999, speculative_tokens=2, thinking="off")
        settings.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        save_settings(value)
    from panel import get_panel
    return get_panel(workflow_dir=workflows, output_dir=config["output_dir"], settings_backup=save_settings)
