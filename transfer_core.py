"""Copy files between a Colab-mounted Drive and the current runtime."""
from __future__ import annotations

import contextlib
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import threading
import time
import uuid

CHUNK = 8 * 1024**2
MAX_PARALLEL = 4
MAX_DEPTH = 64
MAX_ENTRIES = 5000
MAX_BYTES = 512 * 1024**3
LABELS = {'models': '模型目录', 'input': '输入目录', 'output': '输出目录'}


class TransferError(Exception):
    """Only fixed, safe human-readable messages belong in this exception."""


class Cancelled(TransferError):
    pass


def cancelled(event):
    if event.is_set():
        raise Cancelled('已取消；原文件保持不变')


BLOCKED_LOCAL_PREFIXES = (Path('/proc'), Path('/sys'), Path('/dev'), Path('/run'),
    Path('/var/run'), Path('/etc/ssh'), Path('/etc/ssl/private'))


def safe_name(name):
    if (not isinstance(name, str) or not name or name in {'.', '..'}
            or '/' in name or '\\' in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or len(name.encode('utf-8')) > 230):
        raise TransferError('文件名不安全，未进行传输')
    return name


def safe_parts(parts):
    for part in parts:
        safe_name(part)
    return parts


def safe_local_path(path):
    path = Path(path)
    safe_parts(path.parts[1:])
    if any(path == prefix or path.is_relative_to(prefix) for prefix in BLOCKED_LOCAL_PREFIXES):
        raise TransferError('系统敏感目录和伪文件系统不支持读取或复制')
    return path


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextlib.contextmanager
def directory_fd(path):
    """Walk from / using openat+O_NOFOLLOW; never follow a replaced ancestor."""
    path = safe_local_path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise TransferError('本地目录不安全')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            new_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new_fd
        yield fd
    except OSError:
        raise TransferError('目录不存在、无访问权限或包含符号链接') from None
    finally:
        os.close(fd)


@contextlib.contextmanager
def local_file(root, parts, expected=None):
    if not parts or len(parts) > MAX_DEPTH:
        raise TransferError('本地文件路径不安全')
    safe_parts(parts)
    with directory_fd(Path(root).joinpath(*parts[:-1])) as fd:
        try:
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except OSError:
            raise TransferError('文件已变化或无法安全读取，请刷新列表') from None
    with os.fdopen(file_fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 <= info.st_size <= MAX_BYTES
                or (expected is not None and fingerprint(info) != expected)):
            raise TransferError('文件已变化、不是普通文件或存在硬链接，请刷新列表')
        yield stream, info


def numbered(name, number):
    p = Path(name)
    return name if number == 0 else f'{p.stem[:180]} ({number + 1}){p.suffix}'


@dataclass(frozen=True)
class Entry:
    pane: str
    parts: tuple
    kind: str
    size: int = 0
    fp: tuple | None = None

    @property
    def name(self):
        return self.parts[-1] if self.parts else ""


class TransferController:
    def __init__(self, drive_directory, *, local_roots, on_change=None):
        self.drive_directory = Path(drive_directory) if drive_directory is not None else None
        self.local_roots = {name: Path(path).absolute() for name, path in local_roots.items()}
        self.on_change = on_change or (lambda state: None)
        self.lock = threading.RLock()
        self.transfers = ThreadPoolExecutor(max_workers=MAX_PARALLEL, thread_name_prefix='studio-transfer')
        self.reads = ThreadPoolExecutor(max_workers=2, thread_name_prefix='studio-files')
        self.entries = {}
        self.tokens = {}
        self.tasks = []
        self.jobs = {}
        self.positions = {side: Entry(side, (), 'directory') for side in ('drive', 'local')}
        self.navigation = dict.fromkeys(self.positions, 0)
        self.closed = False
        self.state = {'connected': self.connected(), 'notice': '', 'panes': {}}
        for side, folder in self.positions.items():
            self.state['panes'][side] = self._pane(folder, [], loading=True)

    def connected(self):
        return self.drive_directory is not None and self.drive_directory.is_dir()

    def root(self, pane):
        if pane == 'local':
            return self.local_roots['root']
        if pane == 'drive' and self.connected():
            return self.drive_directory
        raise TransferError('请先在 Colab 挂载 Google Drive')

    def _register(self, entry):
        key = (entry.pane, entry.parts)
        with self.lock:
            token = self.tokens.get(key)
            if token is None:
                if len(self.entries) >= 50000:
                    raise TransferError('目录浏览记录过多，请重新打开工作台')
                token = uuid.uuid4().hex
                self.tokens[key] = token
            self.entries[token] = entry
        return token

    def _pane(self, folder, children, *, writable=False, loading=False, error=''):
        side = folder.pane
        label = '我的云端硬盘' if side == 'drive' else str(self.local_roots['root'])
        roots = ['root'] if side == 'drive' else self.local_roots
        path = str(self.root(side).joinpath(*folder.parts)) if side == 'local' or self.connected() else ''
        crumbs = []
        for index in range(len(folder.parts) + 1):
            ancestor = Entry(side, folder.parts[:index], 'directory')
            crumbs.append({'id': self._register(ancestor), 'label': ancestor.name or label})
        return {'roots': [{'id': key, 'label': label if key == 'root' else LABELS.get(key, key)} for key in roots],
                'directory_id': self._register(folder), 'breadcrumbs': crumbs, 'path': path,
                'entries': children, 'loading': loading, 'canReceive': writable, 'error': error}

    def snapshot(self):
        with self.lock:
            return {**copy.deepcopy(self.state), 'tasks': copy.deepcopy(self.tasks[-64:])}

    def _publish(self):
        if not self.closed:
            try:
                self.on_change(self.snapshot())
            except Exception:
                pass

    def start(self):
        for side, entry in self.positions.items():
            self._schedule_navigation(side, entry)

    def _list(self, folder):
        path = safe_local_path(self.root(folder.pane).joinpath(*folder.parts))
        entries = []
        with directory_fd(path) as fd:
            readonly = bool(os.fstatvfs(fd).f_flag & os.ST_RDONLY)
            for name in os.listdir(fd):
                if name.startswith('.studio-transfer-'):
                    continue
                try:
                    safe_name(name)
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        entry = Entry(folder.pane, (*folder.parts, name), 'directory')
                    elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_BYTES:
                        entry = Entry(folder.pane, (*folder.parts, name), 'file', info.st_size, fingerprint(info))
                    else:
                        continue
                    if len(entries) >= MAX_ENTRIES:
                        raise OverflowError('目录中文件过多，请打开更小的目录')
                    entries.append(entry)
                except (OSError, TransferError):
                    continue
        return sorted(entries, key=lambda item: (item.kind != 'directory', item.name.casefold())), not readonly and os.access(path, os.W_OK)

    def _schedule_navigation(self, side, entry):
        if entry.pane != side or entry.kind != 'directory' or len(entry.parts) > MAX_DEPTH:
            raise TransferError('请选择已列出的目录')
        with self.lock:
            self.positions[side] = entry
            self.navigation[side] += 1
            generation = self.navigation[side]
            self.state['connected'] = self.connected()
            self.state['panes'][side] = self._pane(entry, [], loading=True)
        self._publish()

        def read():
            error = ''
            try:
                rows, writable = self._list(entry)
            except (TransferError, OverflowError) as exc:
                rows, writable, error = [], False, str(exc)
            with self.lock:
                if self.closed or self.navigation[side] != generation:
                    return
                children = [{ 'id': self._register(row), 'kind': row.kind, 'name': row.name,
                              'size': row.size, 'copyable': True} for row in rows]
                self.state['panes'][side] = self._pane(entry, children, writable=writable, error=error)
            self._publish()

        self.reads.submit(read)

    def handle(self, message):
        if self.closed:
            return
        try:
            action = message.get('action')
            if action == 'transfer':
                self._enqueue(message)
            elif action in ('retry', 'cancel'):
                job = self.jobs.get(message.get('task_id'))
                if job is None:
                    raise TransferError('任务已失效')
                with self.lock:
                    if action == 'cancel':
                        job['cancel'].set()
                        if job['task']['status'] == 'queued':
                            job['task']['status'] = 'cancelled'
                    elif job['task']['status'] in ('failed', 'cancelled'):
                        job['cancel'] = threading.Event()
                        job['task'].update(status='queued', error='')
                        self.transfers.submit(self._run, job)
            elif action in ('refresh', 'root', 'navigate'):
                side = message.get('pane')
                if side not in self.positions:
                    raise TransferError('面板无效')
                item = self.positions[side]
                if action == 'root':
                    name = message.get('root')
                    roots = {'root': self.drive_directory} if side == 'drive' else self.local_roots
                    if name not in roots:
                        raise TransferError('目录无效')
                    parts = () if name == 'root' else roots[name].relative_to(self.root(side)).parts
                    item = Entry(side, parts, 'directory')
                elif action == 'navigate':
                    item = self.entries.get(message.get('entry_id'))
                    if item is None:
                        raise TransferError('目录已失效，请刷新')
                self._schedule_navigation(side, item)
            else:
                raise TransferError('不支持此操作')
        except (TransferError, ValueError) as exc:
            with self.lock:
                self.state['notice'] = str(exc)
        self._publish()

    def _enqueue(self, message):
        target = self.entries.get(message.get('target_id'))
        sources = [self.entries.get(key) for key in message.get('entry_ids', ())]
        if target is None or target.kind != 'directory' or not sources or any(row is None for row in sources):
            raise TransferError('请选择已列出的文件和目标目录')
        if not self.connected() or any(source.pane == target.pane for source in sources):
            raise TransferError('请在 Colab 运行时与已挂载 Drive 之间复制')
        with self.lock:
            active = sum(row['status'] in ('queued', 'running') for row in self.tasks)
            if active + len(sources) > 16:
                raise TransferError('队列已满，请等待当前任务完成')
            finished = [row for row in self.tasks if row['status'] not in ('queued', 'running')]
            for row in finished[:max(0, len(self.tasks) + len(sources) - 64)]:
                self.tasks.remove(row)
                self.jobs.pop(row['id'], None)
            for source in sources:
                if any(job['source'] == source and job['target'] == target
                       and job['task']['status'] in ('queued', 'running') for job in self.jobs.values()):
                    continue
                task = {'id': uuid.uuid4().hex, 'name': source.name, 'kind': source.kind,
                        'direction': 'download' if source.pane == 'drive' else 'upload',
                        'status': 'queued', 'bytes': 0, 'total': 0, 'speed': 0, 'error': ''}
                job = {'task': task, 'source': source, 'target': target, 'cancel': threading.Event(), 'copied': {}}
                if message.get('save_shortcut'):
                    from copy_registry import remember
                    remember(self, source, target)
                self.tasks.append(task)
                self.jobs[task['id']] = job
                self.transfers.submit(self._run, job)
            self.state['notice'] = ''
        self._publish()

    def _plan(self, entry):
        files, directories, pending = [], [], [entry]
        while pending:
            item = pending.pop()
            if len(item.parts) > MAX_DEPTH or len(files) + len(directories) >= MAX_ENTRIES:
                raise TransferError('目录过深或项目过多，请分批复制')
            if item.kind == 'directory':
                directories.append(item)
                children, _ = self._list(item)
                pending.extend(reversed(children))
            else:
                files.append(item)
        return files, directories

    def _run(self, job):
        task = job['task']
        if job['cancel'].is_set() or self.closed:
            return
        started, last = time.monotonic(), 0.0
        with self.lock:
            task.update(status='running', error='')
        self._publish()
        try:
            source, target = job['source'], job['target']
            source_root, target_root = self.root(source.pane), self.root(target.pane)
            source_path = source_root.joinpath(*source.parts)
            target_path = target_root.joinpath(*target.parts)
            if target_path.is_relative_to(source_path) or target_path / source.name == source_path:
                raise TransferError('源和目标目录重叠')
            files, directories = self._plan(source)
            offset = len(source.parts) - 1
            with self.lock:
                task['total'] = sum(file.size for file in files)
                task['bytes'] = sum(job['copied'].values())
            for directory in directories:
                cancelled(job['cancel'])
                parent = target_path.joinpath(*directory.parts[offset:-1])
                with directory_fd(parent) as fd:
                    try:
                        os.mkdir(directory.name, dir_fd=fd)
                    except FileExistsError:
                        pass
                with directory_fd(parent / directory.name):
                    pass

            for file in files:
                cancelled(job['cancel'])
                if file.parts in job['copied']:
                    continue
                before = sum(job['copied'].values())
                def progress(amount):
                    nonlocal last
                    now = time.monotonic()
                    with self.lock:
                        task['bytes'] = before + amount
                        task['speed'] = task['bytes'] / max(now - started, 0.01)
                    if now - last >= 0.5:
                        last = now
                        self._publish()

                parent = target_path.joinpath(*file.parts[offset:-1])
                self._copy_file(source_root, file, parent, job['cancel'], progress)
                job['copied'][file.parts] = file.size
            with self.lock:
                task.update(status='completed', bytes=task['total'], speed=0)
        except Cancelled as exc:
            with self.lock:
                task.update(status='cancelled', error=str(exc), speed=0)
        except (OSError, TransferError, OverflowError) as exc:
            with self.lock:
                error = str(exc) if isinstance(exc, (TransferError, OverflowError)) else '复制失败，请检查 Colab 的挂载和剩余空间'
                task.update(status='failed', error=error, speed=0)
        self._publish()
        target = job['target']
        if not self.closed and self.positions[target.pane] == target:
            self._schedule_navigation(target.pane, target)

    def _copy_file(self, root, entry, parent, cancel, progress):
        with local_file(root, entry.parts, entry.fp) as (stream, info), directory_fd(parent) as folder:
            temporary = '.studio-transfer-' + uuid.uuid4().hex + '.part'
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            fd = os.open(temporary, flags, 0o600, dir_fd=folder)
            reserved = None
            try:
                with os.fdopen(fd, 'wb') as output:
                    copied = 0
                    while block := stream.read(CHUNK):
                        cancelled(cancel)
                        output.write(block)
                        copied += len(block)
                        progress(copied)
                    output.flush()
                    os.fsync(output.fileno())
                cancelled(cancel)
                if copied != entry.size or fingerprint(os.fstat(stream.fileno())) != fingerprint(info):
                    raise TransferError('复制期间源文件发生变化，请刷新后重试')
                for number in range(1000):
                    name = numbered(entry.name, number)
                    try:
                        placeholder = os.open(name, flags, 0o600, dir_fd=folder)
                    except FileExistsError:
                        continue
                    with os.fdopen(placeholder, 'wb') as target:
                        reserved = name, fingerprint(os.fstat(target.fileno()))
                    if fingerprint(os.stat(name, dir_fd=folder, follow_symlinks=False)) != reserved[1]:
                        raise TransferError('目标文件在发布前发生变化')
                    os.replace(temporary, name, src_dir_fd=folder, dst_dir_fd=folder)
                    reserved = None
                    return
                raise TransferError('同名文件过多')
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temporary, dir_fd=folder)
                if reserved is not None:
                    with contextlib.suppress(FileNotFoundError):
                        name, previous = reserved
                        if fingerprint(os.stat(name, dir_fd=folder, follow_symlinks=False)) == previous:
                            os.unlink(name, dir_fd=folder)

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                job['cancel'].set()
        self.reads.shutdown(wait=False, cancel_futures=True)
        self.transfers.shutdown(wait=False, cancel_futures=True)
