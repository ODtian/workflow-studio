"""Source-backed settings: Molab persists Python source across sandboxes."""
import ast
import copy
import json
import os
from pathlib import Path
import threading
import uuid

PATH = Path(os.environ.get('WORKFLOW_WORKSPACE', str(Path(__file__).parent))) / 'workspace_saved.py'
LOCK = globals().get('LOCK') or threading.RLock()

def read():
    with LOCK:
        try:
            tree = ast.parse(PATH.read_text(encoding='utf-8'))
            assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                              and any(isinstance(t, ast.Name) and t.id == 'STATE' for t in n.targets))
            state = ast.literal_eval(assignment.value)
        except FileNotFoundError:
            state = {'schema': 1, 'nodes': [], 'copies': []}
        if state.get('schema') != 1 or not all(isinstance(state.get(k), list) for k in ('nodes','copies')):
            raise ValueError('保存的清单格式需要修复')
        return copy.deepcopy(state)

def edit(callback):
    with LOCK:
        state = read()
        result = callback(state)
        # JSON round-trip restricts settings to inert, serializable data.
        state = json.loads(json.dumps(state, ensure_ascii=False))
        source = '# 节点与复制清单，由 notebook 面板维护。\nSTATE = ' + repr(state) + '\n'
        temporary = PATH.with_name('workspace_saved_' + uuid.uuid4().hex + '.py')
        with temporary.open('w', encoding='utf-8') as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, PATH)
        return result
