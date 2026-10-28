"""Apply the official Spark-H3 Comfy patch in the notebook process."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


REPOSITORY = 'https://github.com/zechengtang/Spark-H3.git'
REVISION = '2eb2dc1be261490f86a57c93904551a5bf456af7'
PACKAGE = 'workflow_spark_h3'
SOURCE = Path(os.environ.get('WORKFLOW_WORKSPACE', '.')) / '.cache/workflow-studio/spark-h3'
ARCHITECTURES = {(8, 6): 'SM86', (8, 9): 'SM89', (12, 0): 'SM120'}


def fields():
    active = {'attention': ['auto', 'spark']}
    return [dict(area='advanced', section='Spark-H3', when=active, **field) for field in [
        {'key': 'spark_mode', 'label': 'Spark-H3 模式', 'type': 'select', 'default': 'fidelity',
         'options': [{'label': '保真 · 20% 预热', 'value': 'fidelity'},
                     {'label': '速度 · 直接稀疏', 'value': 'speed'},
                     {'label': '自定义预热', 'value': 'custom'}]},
        {'key': 'spark_topk_ratio', 'label': 'Spark-H3 精确计算比例', 'type': 'number',
         'default': 0.2, 'min': 0.01, 'max': 1, 'step': 0.01,
         'hint': '视频块中精确计算的比例；其余部分使用重加权近似。'},
        {'key': 'spark_warmup_ratio', 'label': 'Spark-H3 自定义预热比例', 'type': 'number',
         'default': 0.2, 'min': 0, 'max': 1, 'step': 0.01,
         'hint': '选择自定义预热时生效。'},
        {'key': 'spark_sparse_scope', 'label': 'Spark-H3 稀疏范围', 'type': 'select',
         'default': 'target-video', 'options': [
             {'label': '生成视频', 'value': 'target-video'},
             {'label': '参考视频与生成视频', 'value': 'joint-video'}],
         'hint': '文本、静态参考图和音频保持精确注意力。'},
        {'key': 'spark_producer_chunk', 'label': 'Spark-H3 QKV 分块', 'type': 'number',
         'default': 16384, 'min': 64, 'step': 64,
         'hint': '减小分块可降低临时显存用量。'},
    ]]


def supported():
    import torch
    return (torch.cuda.is_available()
            and tuple(torch.cuda.get_device_capability()) in ARCHITECTURES
            and tuple(map(int, torch.version.cuda.split('.')[:2])) >= (13, 0))


def prepare_backend(ctx):
    """Install the shared kitchen backend before Comfy imports its CUDA extension."""
    if not supported():
        return
    if not (SOURCE / 'comfyui_nodes.py').is_file():
        ctx.status('准备 Spark-H3 推理代码…')
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'init', str(SOURCE)], check=True, capture_output=True, text=True)
        subprocess.run(['git', '-C', str(SOURCE), 'fetch', '--depth', '1', REPOSITORY, REVISION],
                       check=True, capture_output=True, text=True)
        subprocess.run(['git', '-C', str(SOURCE), 'checkout', '--detach', 'FETCH_HEAD'],
                       check=True, capture_output=True, text=True)
    ctx.status('准备 Spark-H3 CUDA 内核…')
    subprocess.run([sys.executable, str(SOURCE / 'comfyui/install.py'), '--skip-dependencies'],
                   check=True)


def apply(model, params, ctx):
    import torch
    if not supported():
        raise ValueError('Spark-H3 使用 CUDA 13 的 SM86、SM89 或 SM120 GPU。')
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, SOURCE / '__init__.py', submodule_search_locations=[str(SOURCE)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = module
        spec.loader.exec_module(module)
    nodes = sys.modules[PACKAGE + '.comfyui_nodes']
    architecture = ARCHITECTURES[tuple(torch.cuda.get_device_capability())]
    mode = params.get('spark_mode', 'fidelity')
    warmup = {'fidelity': 0.2, 'speed': 0.0}.get(mode, float(params.get('spark_warmup_ratio', 0.2)))
    topk = float(params.get('spark_topk_ratio', 0.2))
    scope = params.get('spark_sparse_scope', 'target-video')
    patched = nodes.NODE_CLASS_MAPPINGS['MiniMaxH3SparkAttention' + architecture]().patch(
        model=model, mode=mode, steps=int(params['steps']), warmup_mode='warmup_ratio',
        warmup_ratio=warmup, warmup_steps=0, topk_ratio=topk, dense_layers=0,
        min_tokens=12288, strict=True, sparse_scope=scope,
        producer_chunk=int(params.get('spark_producer_chunk', 16384)),
    )[0]
    ctx.metadata(Attention='Spark-H3 · ' + architecture, Spark模式=mode,
                 Spark预热比例=warmup, Spark精确比例=topk, Spark稀疏范围=scope)
    return patched
