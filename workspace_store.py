"""Studio user state in marimo's default persistent-cache store."""
import ast
import copy
import json
import os
from pathlib import Path
import threading
import secrets
from marimo._runtime.context import get_context
from content_store import enabled, pack, unpack, MAGIC, write_bytes

PATH = Path(os.environ.get('WORKFLOW_WORKSPACE', str(Path(__file__).parent))) / 'workspace_saved.py'
LOCK = globals().get('LOCK') or threading.RLock()
STORE = get_context().cache.store
KEY = 'workflow_studio/state.json'
CONTENT_DIR = STORE.save_path / 'workflow_studio/content'

def _get(key):
    blob = STORE.get(key)
    if blob is not None:
        if enabled() and not blob.startswith(MAGIC):
            STORE.put(key, pack(blob))
        return unpack(blob)
    return None


def _put(key, blob):
    return STORE.put(key, pack(blob))

def read():
    with LOCK:
        blob = _get(KEY)
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
            _put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))
        return copy.deepcopy(state)

def edit(callback):
    with LOCK:
        state = read()
        result = callback(state)
        _put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))
        return result


def save_files(paths):
    with LOCK:
        state = read()
        saved = state.setdefault('resource_files', [])
        for path in paths:
            path = Path(path)
            if enabled() and path.is_relative_to(STORE.save_path):
                continue
            relative = path.relative_to(PATH.parent).as_posix()
            keys = state.setdefault('resource_keys', {})
            key = keys.setdefault(relative, 'workflow_studio/objects/' + secrets.token_hex(12)) if enabled() else 'workflow_studio/files/' + relative
            _put(key, path.read_bytes())
            if relative not in saved:
                saved.append(relative)
        _put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))


def restore_files():
    with LOCK:
        state = read()
        for relative in state.get('resource_files', []):
            path = PATH.parent / relative
            legacy = 'workflow_studio/files/' + relative
            key = state.get('resource_keys', {}).get(relative, legacy)
            if enabled() and relative.startswith('.pi/agent/sessions/'):
                target = CONTENT_DIR / relative
                write_bytes(target, _get(key))
                path.unlink(missing_ok=True)
                STORE.clear(key)
                for preferences in state.get('pi_preferences', {}).values():
                    if preferences.get('saved_session') == str(path):
                        preferences['saved_session'] = str(target)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_get(key))
            if enabled() and key == legacy:
                key = 'workflow_studio/objects/' + secrets.token_hex(12)
                _put(key, path.read_bytes())
                state.setdefault('resource_keys', {})[relative] = key
                STORE.clear(legacy)
        if enabled():
            state['resource_files'] = [relative for relative in state.get('resource_files', [])
                                       if not relative.startswith('.pi/agent/sessions/')]
            state['resource_keys'] = {relative:key for relative,key in state.get('resource_keys', {}).items()
                                      if relative in state['resource_files']}
        _put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))
