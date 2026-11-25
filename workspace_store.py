"""Store Studio settings and resources in the Colab runtime filesystem."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
from tempfile import NamedTemporaryFile
from content_store import pack, unpack

RUNTIME_DIR = Path(os.environ.get('WORKFLOW_WORKSPACE', str(Path(tempfile.gettempdir()) / 'workflow-studio-runtime')))
CONTENT_DIR = RUNTIME_DIR / 'content'
LOCK = globals().get('LOCK') or threading.RLock()
STORE = Path(os.environ.get('WORKFLOW_STUDIO_STATE_DIR', RUNTIME_DIR / 'settings')).resolve()
KEY = 'state.json.gz'


def _state_path(key, directory=None):
    root = Path(directory).resolve() if directory is not None else STORE
    path = (root / key).resolve()
    if not path.is_relative_to(root):
        raise ValueError('设置资源路径超出 Studio 设置目录')
    return path


def _get(key, directory=None):
    try:
        return unpack(_state_path(key, directory).read_bytes())
    except FileNotFoundError:
        return None


def _put(key, blob, directory=None):
    target = _state_path(key, directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(pack(blob))
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
            path = Path(path).resolve()
            relative = path.relative_to(RUNTIME_DIR).as_posix()
            _put('files/' + relative, path.read_bytes())
            if relative not in saved:
                saved.append(relative)
        _put(KEY, json.dumps(state, ensure_ascii=False).encode('utf-8'))


def restore_files():
    with LOCK:
        for relative in read().get('resource_files', []):
            path = (RUNTIME_DIR / relative).resolve()
            if not path.is_relative_to(RUNTIME_DIR.resolve()):
                raise ValueError('资源路径超出 Studio 工作目录')
            data = _get('files/' + relative)
            if data is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
