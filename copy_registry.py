"""Save explicit shortcuts for mounted Drive and Hugging Face."""
import json
import os
from pathlib import Path
import time
import uuid

import workspace_store as store
from transfer_core import Entry, directory_fd, fingerprint, local_file, safe_local_path, safe_parts


def _filename(record_id):
    return uuid.UUID(record_id).hex + '.json.gz'


def sync(drive_root):
    if drive_root is None or not Path(drive_root).is_dir():
        return 'runtime'
    directory = Path(drive_root) / 'Workflow Studio' / 'shortcuts'

    def merge(state):
        local = {item['id']: {**item, 'deleted': deleted}
                 for key, deleted in [('copies', False), ('copy_trash', True)]
                 for item in state.get(key, [])}
        remote = {}
        for path in directory.glob('*.json.gz'):
            try:
                record = json.loads(store._get(path.name, directory))
                record_id = record['id']
                if (_filename(record_id) != path.name or not isinstance(record.get('label'), str)
                        or not isinstance(record.get('updated_at', 0), int)):
                    continue
                remote[record_id] = record
                previous = local.get(record_id)
                if previous is None or record.get('updated_at', 0) > previous.get('updated_at', 0):
                    local[record_id] = record
            except (ValueError, TypeError, KeyError, OSError, EOFError, AttributeError):
                continue
        for key, deleted in [('copies', False), ('copy_trash', True)]:
            state[key] = [{name: value for name, value in item.items() if name != 'deleted'}
                          for item in local.values() if bool(item.get('deleted')) == deleted]
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if not os.access(directory, os.W_OK):
                return 'runtime'
            for record_id, record in local.items():
                if remote.get(record_id) != record:
                    store._put(_filename(record_id), json.dumps(record, ensure_ascii=False).encode(), directory)
        except (OSError, ValueError):
            return 'runtime'
        return 'drive'

    try:
        return store.edit(merge)
    except (OSError, ValueError):
        return 'runtime'


def remember(controller, source, target):
    local = target if source.pane == 'drive' else source
    drive = source if source.pane == 'drive' else target
    local_path = str(controller.root('local').joinpath(*local.parts))
    drive_path = '/'.join(drive.parts) or '.'
    direction = 'download' if source.pane == 'drive' else 'upload'

    def save(state):
        for record in state['copies']:
            if (record.get('direction'), record.get('drive_path'), record.get('local_path')) == (direction, drive_path, local_path):
                return
        state['copies'].append({'id': uuid.uuid4().hex, 'label': source.name, 'source_provider': 'drive',
                                'direction': direction, 'drive_path': drive_path, 'source_kind': source.kind,
                                'local_path': local_path, 'updated_at': time.time_ns()})
    store.edit(save)


def drive_parts(value):
    value = str(value or '').strip()
    path = Path(value)
    if not value or path.is_absolute():
        raise ValueError('请填写从已挂载 Drive 根目录开始的相对路径')
    return safe_parts(path.parts)


def save_recipe(value):
    path = Path(str(value.get('local_path', '')).strip())
    if not path.is_absolute():
        raise ValueError('运行时路径需要以 / 开头')
    safe_local_path(path)
    if value.get("source_provider") == "huggingface":
        from hf_downloads import source_from_recipe
        source=source_from_recipe(value)
        def save_hf(state):
            old=next((r for r in state["copies"] if r["id"]==value.get("id")),None)
            if old is None:
                old={"id":uuid.uuid4().hex}
                state["copies"].append(old)
            companions=old.get("hf_sources",[])[1:] if old.get("source_provider")=="huggingface" else []
            old.update(label=value.get("label","").strip() or source["repo_id"],
                       source_provider="huggingface",direction="download",
                       source_kind="directory",repo_id=source["repo_id"],
                       hf_url=value.get("hf_url",source["repo_id"]),local_path=str(path),
                       hf_sources=[source,*companions],updated_at=time.time_ns())
            return old["id"]
        return store.edit(save_hf)
    direction = value.get('direction')
    if direction not in ('download', 'upload'):
        raise ValueError('请选择复制方向')
    parts = drive_parts(value.get('drive_path'))
    label = str(value.get('label', '')).strip()[:230]
    if not label:
        raise ValueError('请填写记录名称')

    def save(state):
        record = next((item for item in state['copies'] if item['id'] == value.get('id')), None)
        if record is None:
            record = {'id': uuid.uuid4().hex}
            state['copies'].append(record)
        record.update(label=label, source_provider='drive', direction=direction, drive_path='/'.join(parts) or '.',
                      local_path=str(path), source_kind=value.get('source_kind', 'file'), updated_at=time.time_ns())
        record.pop('drive_id', None)
        return record['id']
    return store.edit(save)


def resolve(controller, recipe):
    if not recipe.get('drive_path'):
        raise ValueError('请编辑快捷项，填入已挂载 Drive 的相对路径')
    remote = drive_parts(recipe['drive_path'])
    local_root = controller.root('local')
    local = safe_parts(safe_local_path(Path(recipe['local_path'])).relative_to(local_root).parts)
    kind = recipe.get('source_kind', 'file')
    downloading = recipe['direction'] == 'download'
    source_side, target_side = ('drive', 'local') if downloading else ('local', 'drive')
    source_parts, target_parts = (remote, local) if downloading else (local, remote)
    if not source_parts or kind not in ('file', 'directory'):
        raise ValueError('请选择具体文件或子目录')
    if downloading:
        parent = local_root
        for part in local:
            with directory_fd(parent) as fd:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
            parent = parent / part
    with directory_fd(controller.root(target_side).joinpath(*target_parts)):
        pass
    source = Entry(source_side, source_parts, kind)
    if kind == 'file':
        with local_file(controller.root(source_side), source_parts) as (_, info):
            source = Entry(source_side, source_parts, kind, info.st_size, fingerprint(info))
    else:
        with directory_fd(controller.root(source_side).joinpath(*source_parts)):
            pass
    return source, Entry(target_side, target_parts, 'directory')
