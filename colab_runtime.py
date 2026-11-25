"""Install and start the two applications in a Google Colab runtime."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path("/content/workflow-studio-colab")
COMFY = ROOT / "ComfyUI"
STUDIO = Path(__file__).resolve().parent
COMFY_REF = "355cd6b14c92c19ac3188fe528e47a3f21ef5178"  # v0.42.0
COMFY_PORT = 8188
STUDIO_PORT = 2718
_processes = {}


def prepare():
    """Install the pinned ComfyUI release and Studio's Python dependencies."""
    ROOT.mkdir(parents=True, exist_ok=True)
    COMFY.mkdir(exist_ok=True)
    if not (COMFY / ".git").is_dir():
        subprocess.run(["git", "init", "--quiet"], cwd=COMFY, check=True)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=COMFY, capture_output=True, text=True)
    if revision.returncode or revision.stdout.strip() != COMFY_REF:
        subprocess.run(["git", "fetch", "--quiet", "--depth=1", "https://github.com/Comfy-Org/ComfyUI.git",
                        COMFY_REF], cwd=COMFY, check=True)
        subprocess.run(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], cwd=COMFY, check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "-r", str(COMFY / "requirements.txt"),
                    str(STUDIO), "marimo==0.26.0"], check=True)


def _start(name, command, cwd, port, *, env=None):
    process = _processes.get(name)
    log_path = ROOT / f"{name}.log"
    if process is None or process.poll() is not None:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, *command], cwd=cwd, env=env,
                                       stdout=log, stderr=subprocess.STDOUT)
        _processes[name] = process

    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError(log_path.read_text(errors="replace")[-5000:])
        try:
            with urlopen(f"http://127.0.0.1:{port}/", timeout=3):
                return
        except OSError:
            time.sleep(1)
    raise TimeoutError(log_path.read_text(errors="replace")[-5000:])


def _comfy_api(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(f"http://127.0.0.1:{COMFY_PORT}{path}", data=data,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def _preview_origin(output, port):
    preview = urlsplit(output.eval_js(f"google.colab.kernel.proxyPort({port})"))
    if preview.scheme != "https" or not preview.netloc:
        raise RuntimeError("Colab 未返回 HTTPS 预览地址")
    return f"{preview.scheme}://{preview.netloc}"


def start_comfy():
    """Start ComfyUI, run a model-free preview workflow and display the Colab link."""
    from google.colab import output
    import torch

    extension = COMFY / "custom_nodes" / "workflow_studio_colab_preview.py"
    preview_source = STUDIO / "colab_comfy_preview.py"
    if not extension.exists() and not extension.is_symlink():
        extension.symlink_to(preview_source)
    if extension.resolve() != preview_source:
        raise RuntimeError(f"Colab 预览扩展路径已被占用: {extension}")
    env = {**os.environ, "WORKFLOW_STUDIO_COMFY_ORIGIN": _preview_origin(output, COMFY_PORT)}
    device_args = [] if torch.cuda.is_available() else ["--cpu"]
    _start("comfyui", ["main.py", "--listen", "127.0.0.1", "--port", str(COMFY_PORT),
                     "--disable-auto-launch", *device_args], COMFY, COMFY_PORT, env=env)
    prompt = {
        "1": {"class_type": "EmptyImage", "inputs": {"width": 64, "height": 64, "batch_size": 1, "color": 0}},
        "2": {"class_type": "PreviewImage", "inputs": {"images": ["1", 0]}},
    }
    prompt_id = _comfy_api("/prompt", {"prompt": prompt})["prompt_id"]
    for _ in range(30):
        record = _comfy_api(f"/history/{prompt_id}").get(prompt_id)
        if record is not None:
            if record["status"]["status_str"] != "success" or not record["outputs"].get("2", {}).get("images"):
                raise RuntimeError(record["status"])
            break
        time.sleep(1)
    else:
        raise TimeoutError("ComfyUI 预览图自检超过 30 秒")
    devices = [device["name"] for device in _comfy_api("/system_stats")["devices"]]
    print("ComfyUI 已通过预览图自检。设备：", devices)
    output.serve_kernel_port_as_window(COMFY_PORT)


def start_studio():
    """Start the regular Studio notebook with the current Colab preview origin."""
    from google.colab import output

    origin = _preview_origin(output, STUDIO_PORT)
    env = {**os.environ, "PYTHONPATH": str(STUDIO), "WORKFLOW_COMFY_ROOT": str(COMFY),
           "WORKFLOW_MODELS_DIR": str(COMFY / "models")}
    _start("studio", ["-m", "marimo", "run", "notebook.py", "--headless", "--host", "127.0.0.1",
                      "--port", str(STUDIO_PORT), "--allow-origins", origin], STUDIO, STUDIO_PORT, env=env)
    print("Workflow Studio 已启动。")
    output.serve_kernel_port_as_window(STUDIO_PORT)
