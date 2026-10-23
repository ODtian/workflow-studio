"""Apply a saved Studio source update while keeping loaded models and chats."""
from pathlib import Path
import importlib
import json
import sys
import threading


def apply_update(widget):
    import panel
    inference_lock, chats = panel.INFERENCE_LOCK, panel.CHATS
    with inference_lock:
        for name, cache_names in (
            ("moss_runner", ("_loaded", "_loaded_key", "_adapted", "_adapted_key")),
            ("llama_runner", ("_loaded", "_loaded_key")),
        ):
            module = importlib.import_module(name)
            cache = {key: getattr(module, key) for key in cache_names}
            importlib.reload(module)
            for key, value in cache.items():
                setattr(module, key, value)
            if name == "moss_runner":
                module._core_ready = "comfy.sd" in sys.modules
            else:
                module._library = sys.modules.get("llama_cpp")
        import size_presets
        importlib.reload(size_presets)

        for name, old_import, new_import, root, fields, prepare in (
            ("moss_image.py", "from moss_runner import MODELS, model_files, preferred, run_moss",
             "from moss_runner import MODELS, model_files, preferred, prepare_moss, run_moss",
             'str(MODELS)', ["model", "text_encoder", "vae", "loras"], "prepare_moss"),
            ("llama_cpp.py", "from llama_runner import MODELS, model_files, run_llama",
             "from llama_runner import MODELS, model_files, prepare_llama, run_llama",
             'str(MODELS / "LLM")', ["model", "n_ctx", "n_gpu_layers", "n_batch", "chat_format"], "prepare_llama"),
        ):
            path = widget.workflow_dir / name
            code = path.read_text(encoding="utf-8").replace(old_import, new_import)
            if '"prepare_fields"' not in code:
                marker = '    "model_root": ' + root + ','
                code = code.replace(marker, marker + '\n    "prepare_fields": ' + json.dumps(fields) + ',')
            if "\ndef prepare(" not in code:
                code += f"\n\ndef prepare(params, ctx):\n    return {prepare}(params, ctx)\n"
            path.write_text(code, encoding="utf-8")

        widget_class = type(widget)
        widget.on_msg(widget._message, remove=True)
        importlib.reload(panel)
        panel.INFERENCE_LOCK, panel.CHATS = inference_lock, chats
        widget_class._message = panel.WorkflowPanel._message
        widget.on_msg(widget._message)
        for session in widget.sessions.values():
            session.__class__ = panel.WorkflowSession
            session.prepare_guard = threading.Lock()
            session.prepare_pending = None
            session.prepare_running = False
            session.prepared_signature = None
            session.state = {**session.state, "initializing": False, "initialization": ""}
        widget.refresh()
        source = Path(__file__).parent
        widget._esm = "const GRADIO_COMPONENT_CSS = " + json.dumps(
            (source / "assets/components.css").read_text(encoding="utf-8")) + ";\n" + (
            source / "assets/view.js").read_text(encoding="utf-8")
    print("LIVE_UPDATE_OK · model caches and temporary chats retained")
