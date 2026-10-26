"""Studio user state in marimo's default persistent-cache store."""
import ast
import copy
import json
import os
from pathlib import Path
import threading
from marimo._runtime.context import get_context

PATH = Path(os.environ.get('WORKFLOW_WORKSPACE', str(Path(__file__).parent))) / 'workspace_saved.py'
LOCK = globals().get('LOCK') or threading.RLock()
STORE = get_context().cache.store
KEY = 'workflow_studio/state.json'

def read():
    with LOCK:
        blob = STORE.get(KEY)
        if blob is not None:
            state = json.loads(blob)
        elif PATH.exists():
            tree = ast.parse(PATH.read_text(encoding='utf-8'))
            assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                              and any(isinstance(t, ast.Name) and t.id == 'STATE' for t in n.targets))
            state = ast.literal_eval(assignment.value)
        else:
            state = {'schema': 1, 'nodes': [], 'copies': []}
        if state.get('schema') != 1 or not all(isinstance(state.get(k), list) for k in ('nodes','copies')):
            raise ValueError('保存的清单格式需要修复')
        if blob is None:
            STORE.put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))
        return copy.deepcopy(state)

def edit(callback):
    with LOCK:
        state = read()
        result = callback(state)
        STORE.put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))
        return result


def save_files(paths):
    with LOCK:
        state = read()
        saved = state.setdefault('resource_files', [])
        for path in paths:
            path = Path(path)
            relative = path.relative_to(PATH.parent).as_posix()
            STORE.put('workflow_studio/files/' + relative, path.read_bytes())
            if relative not in saved:
                saved.append(relative)
        STORE.put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))


def restore_files():
    with LOCK:
        for relative in read().get('resource_files', []):
            path = PATH.parent / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(STORE.get('workflow_studio/files/' + relative))
