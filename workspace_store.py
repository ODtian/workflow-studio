"""Gzip UI configuration in the notebook cache; runtime content in /tmp."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
from marimo._runtime.context import get_context
from content_store import pack, unpack

RUNTIME_DIR = Path(os.environ.get('WORKFLOW_WORKSPACE', str(Path(tempfile.gettempdir()) / 'workflow-studio-runtime')))
CONTENT_DIR = RUNTIME_DIR / 'content'
LOCK = globals().get('LOCK') or threading.RLock()
STORE = get_context().cache.store
KEY = 'workflow_studio/state.json'


def _get(key):
    blob = STORE.get(key)
    return unpack(blob) if blob is not None else None


def _put(key, blob):
    return STORE.put(key, pack(blob))


def read():
    with LOCK:
        blob = _get(KEY)
        state = json.loads(blob) if blob is not None else {'schema': 1, 'nodes': [], 'copies': []}
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
            relative = path.relative_to(RUNTIME_DIR).as_posix()
            _put('workflow_studio/files/' + relative, path.read_bytes())
            if relative not in saved:
                saved.append(relative)
        _put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))


def restore_files():
    with LOCK:
        for relative in read().get('resource_files', []):
            path = RUNTIME_DIR / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_get('workflow_studio/files/' + relative))
