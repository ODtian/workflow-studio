"""Bounded, explicit server-side Drive/Molab copies. No UI credentials or sync.

Only transfer/retry custom messages enqueue writes. Listing and construction are
read-only. Roots and bookmarks do not create directories or constrain copy direction.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import mimetypes
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

SCHEMA = 'general-files-v2'
DRIVE_ROOTS = {'root': 'root', 'models': '15hWuax1e3-jKpYMRR8JlnbFpC6huMbAe',
               'results': '1XedAN9O0OzkdFvkqqeWdXHMZ08qXXmht'}
LOCAL_ROOTS = {'root': Path('/'), 'models': Path('/tmp/molab-comfy-runtime/models'),
               'input': Path('/tmp/workflow-studio-runtime/input'),
               'output': Path('/tmp/workflow-studio-runtime/content/media')}
LABELS = {'root': '/', 'models': '模型目录', 'results': '结果目录', 'input': '输入目录', 'output': '输出目录'}
FOLDER = 'application/vnd.google-apps.folder'
CHUNK = 32 * 1024 * 1024
MAX_PARALLEL = 4
MAX_ENTRIES = 5000
MAX_DEPTH = 64
MAX_BYTES = 512 * 1024**3
ID_RE = re.compile(r'[A-Za-z0-9_-]{1,200}\Z')
FIELDS = ('id,name,size,mimeType,parents,trashed,version,md5Checksum,sha256Checksum,'
          'modifiedTime,ownedByMe,shared,capabilities(canDownload,canAddChildren)')


class TransferError(Exception):
    """Only fixed, safe human-readable messages belong in this exception."""


class Cancelled(TransferError):
    pass


def cancelled(event):
    if event.is_set():
        raise Cancelled('已取消；原文件保持不变')


BLOCKED_LOCAL_PREFIXES = (Path('/proc'), Path('/sys'), Path('/dev'), Path('/run'),
    Path('/var/run'), Path('/etc/ssh'), Path('/etc/ssl/private'),
    Path('/tmp/molab-comfy-runtime/tunnel'))


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
    root: str
    parts: tuple
    kind: str
    name: str
    remote_id: str = ''
    size: int = 0
    fp: tuple | None = None
    # Ancestor ids are discovered from bounded listing; revalidated before use.
    chain: tuple = ()


class GoogleDriveProvider:
    """Accept an existing authenticated Resource, never a token or auth JSON."""
    def __init__(self, service):
        if service is None:
            raise TransferError('Drive 连接待授权，请在本 Notebook 完成 Google Drive 安全连接后刷新')
        self.service = service
        self.lock = threading.RLock()
        self._thread_transports = threading.local()

    def _thread_http(self):
        http = getattr(self._thread_transports, 'http', None)
        if http is None:
            import httplib2
            from google_auth_httplib2 import AuthorizedHttp
            original = self.service._http
            http = AuthorizedHttp(original.credentials,
                                  http=httplib2.Http(timeout=original.http.timeout or 30))
            http.http.redirect_codes = http.http.redirect_codes - {308}
            self._thread_transports.http = http
        return http

    def _execute(self, request):
        return request.execute(http=self._thread_http(), num_retries=0)

    def metadata(self, file_id, missing_ok=False):
        if not ID_RE.fullmatch(str(file_id)):
            raise TransferError('Drive 文件标识无效')
        try:
            return self._execute(self.service.files().get(fileId=file_id, fields=FIELDS,
                                                         supportsAllDrives=True))
        except Exception as exc:
            if missing_ok and getattr(getattr(exc, 'resp', None), 'status', None) == 404:
                return None
            raise TransferError('无法读取 Drive 文件，请检查连接后重试') from None

    def children(self, parent_id):
        if not ID_RE.fullmatch(str(parent_id)):
            raise TransferError('Drive 目录标识无效')
        values, seen, token = [], set(), None
        try:
            while True:
                opts = dict(q=f"'{parent_id}' in parents and trashed = false", spaces='drive',
                            fields=f'nextPageToken,incompleteSearch,files({FIELDS})', pageSize=1000,
                            supportsAllDrives=True, includeItemsFromAllDrives=True)
                if token:
                    opts['pageToken'] = token
                page = self._execute(self.service.files().list(**opts))
                if page.get('incompleteSearch'):
                    raise TransferError('Drive 列表不完整，请重试')
                values.extend(page.get('files', []))
                if len(values) > MAX_ENTRIES:
                    raise TransferError('此目录文件过多，请改用更小的子目录')
                token = page.get('nextPageToken')
                if not token:
                    return values
                if token in seen:
                    raise TransferError('Drive 列表分页异常，请重试')
                seen.add(token)
        except TransferError:
            raise
        except Exception:
            raise TransferError('无法列出 Drive 目录，请重试') from None

    def download(self, file_id, stream, size, progress, cancel):
        from drive_parallel_download import download
        return download(self, file_id, stream, size, progress, cancel)

    def create_folder(self, parent_id, name):
        return self._execute(self.service.files().create(
            body={'name': name, 'mimeType': FOLDER, 'parents': [parent_id]},
            fields=FIELDS, supportsAllDrives=True))

    def reserve_id(self):
        try:
            values = self._execute(self.service.files().generateIds(count=1, space='drive', type='files'))['ids']
            if len(values) != 1 or not ID_RE.fullmatch(values[0]):
                raise ValueError
            return values[0]
        except Exception:
            raise TransferError('无法预留上传标识，请重试') from None

    def upload(self, file_id, parent_id, name, stream, size, progress, cancel):
        """Pre-generated IDs make uncertain retries safe without duplicates.

        https://developers.google.com/workspace/drive/api/guides/manage-uploads
        """
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(stream, mimetype=mimetypes.guess_type(name)[0] or 'application/octet-stream',
                                  chunksize=CHUNK, resumable=True)
        request = self.service.files().create(body={'id': file_id, 'name': name, 'parents': [parent_id]},
                                               media_body=media, fields=FIELDS, supportsAllDrives=True)
        try:
            for _ in range((size + CHUNK - 1) // CHUNK + 10):
                cancelled(cancel)
                status, response = request.next_chunk(http=self._thread_http(), num_retries=2)
                if status is not None:
                    progress(status.resumable_progress)
                if response is not None:
                    progress(size)
                    return response
            raise TransferError('上传未完成，请重试；重试不会重复创建文件')
        except TransferError:
            raise
        except Exception:
            # The caller reconciles this exact reserved ID before another try.
            raise TransferError('上传中断或结果待核验；点击重试可安全核验') from None


class GuardedReader:
    """Validate mutable local uploads before returning each block to the SDK."""
    def __init__(self, stream, expected, cancel):
        self.stream, self.expected, self.cancel = stream, expected, cancel

    def _check(self):
        cancelled(self.cancel)
        if fingerprint(os.fstat(self.stream.fileno())) != self.expected:
            raise TransferError('源文件发生变化，已停止上传；请刷新后重新选择')

    def read(self, size=-1):
        self._check()
        data = self.stream.read(size)
        self._check()
        return data

    def seek(self, offset, whence=0):
        self._check()
        return self.stream.seek(offset, whence)

    def tell(self):
        return self.stream.tell()


class HashingWriter:
    def __init__(self, stream, limit):
        self.stream, self.limit, self.count = stream, limit, 0
        self.md5 = hashlib.md5(usedforsecurity=False)
        self.sha256 = hashlib.sha256()

    def write(self, data):
        if self.count + len(data) > self.limit:
            raise TransferError('下载超过已验证大小，未保存文件')
        result = self.stream.write(data)
        if result != len(data):
            raise TransferError('本地写入不完整')
        self.count += result
        self.md5.update(data)
        self.sha256.update(data)
        return result

    def tell(self):
        return self.count


def checksum_matches(metadata, size, md5, sha256):
    try:
        if int(metadata.get('size', -1)) != size:
            return False
    except (ValueError, TypeError):
        return False
    available = False
    for field, actual in [('md5Checksum', md5), ('sha256Checksum', sha256)]:
        value = metadata.get(field)
        if value:
            available = True
            if value.lower() != actual:
                return False
    return available


class TransferController:
    def __init__(self, provider, *, local_roots=None, on_change=None, provider_factory=None):
        self.schema = SCHEMA
        self.provider = provider
        self.provider_factory = provider_factory
        supplied = dict(local_roots or LOCAL_ROOTS)
        if 'root' not in supplied:
            # Compatibility for old offline fixtures; production always uses /.
            common = os.path.commonpath([str(Path(v).absolute()) for v in supplied.values()])
            supplied = {'root': Path(common), **supplied}
        self.local_roots = {k: Path(v).absolute() for k, v in supplied.items()}
        if not all(path.is_relative_to(self.local_roots['root']) for path in self.local_roots.values()):
            raise TransferError('常用地址必须位于服务器根目录内')
        self.on_change = on_change or (lambda state: None)
        self.lock = threading.RLock()
        self.entries, self.entry_keys, self.tasks, self.task_internal = {}, {}, [], {}
        self._bookmarks, self._directory_writable = {'drive': {}, 'local': {}}, {}
        self.seen_requests = set()
        self.closed = False
        self.transfers = ThreadPoolExecutor(max_workers=MAX_PARALLEL, thread_name_prefix='molab-transfer')
        self.reads = ThreadPoolExecutor(max_workers=2, thread_name_prefix='molab-file-list')
        self._transfer_slots = threading.Semaphore(MAX_PARALLEL)
        self._legacy_tasks = set()
        self._speed_samples = {}
        self.state = {'revision': 0, 'connected': provider is not None, 'error': '', 'notice': '', 'panes': {}, 'tasks': []}
        self.positions = {}
        self.nav_generation = {'drive': 0, 'local': 0}
        for bookmark, remote_id in DRIVE_ROOTS.items():
            entry = Entry('drive', 'root' if bookmark == 'root' else 'bookmark:' + bookmark,
                          (), 'directory', '我的云端硬盘' if bookmark == 'root' else LABELS[bookmark],
                          remote_id=remote_id, chain=('root',) if bookmark == 'root' else ())
            self._bookmarks['drive'][bookmark] = entry
            self._register(entry)
        for bookmark, path in self.local_roots.items():
            parts = path.relative_to(self.local_roots['root']).parts
            entry = Entry('local', 'root', parts, 'directory', path.name if parts else '/')
            self._bookmarks['local'][bookmark] = entry
            self._register(entry)
        for pane in ('drive', 'local'):
            self.positions[pane] = self._root(pane, 'root')
            self.state['panes'][pane] = self._pane_state(self.positions[pane], [], loading=True)

    def _root(self, pane, root):
        return self._bookmarks[pane][root]

    def _register(self, entry):
        key = (entry.pane, entry.root, entry.parts, entry.remote_id)
        with self.lock:
            token = self.entry_keys.get(key)
            if token is None:
                if len(self.entries) >= 50000:
                    raise TransferError('本次会话浏览记录较多，请重开面板继续')
                token = uuid.uuid4().hex
                self.entry_keys[key] = token
            self.entries[token] = entry
        return token

    def _token(self, entry):
        return self._register(entry)

    def _pane_state(self, entry, children, *, loading=False):
        pane = entry.pane
        roots = DRIVE_ROOTS if pane == 'drive' else self.local_roots
        root_label = '我的云端硬盘' if pane == 'drive' else '/'
        crumbs = [{'id': self._token(self._root(pane, 'root')), 'label': root_label}]
        for depth, name in enumerate(entry.parts, 1):
            parent = Entry(pane, 'root', entry.parts[:depth], 'directory', name,
                           remote_id=entry.chain[depth] if pane == 'drive' else '',
                           chain=entry.chain[:depth + 1] if pane == 'drive' else ())
            crumbs.append({'id': self._token(parent), 'label': name})
        token = self._token(entry)
        writable, reason = self._directory_writable.get(token, (False, '正在检查目标目录'))
        return {'root': 'root', 'roots': [{'id': root, 'label': root_label if root == 'root' else LABELS.get(root, root)} for root in roots],
                'directory_id': token, 'breadcrumbs': crumbs, 'entries': children,
                'loading': loading, 'canReceive': writable, 'readonly_reason': reason}

    def snapshot(self):
        with self.lock:
            state = copy.deepcopy(self.state)
            state['tasks'] = copy.deepcopy(self.tasks[-64:])
            state['parallelism'] = MAX_PARALLEL
            return state

    def _publish(self):
        if not self.closed:
            with self.lock:
                now = time.monotonic()
                for task in self.tasks:
                    if task['id'] in self._legacy_tasks and task['status'] != 'running':
                        self._legacy_tasks.remove(task['id'])
                        self._transfer_slots.release()
                    task['percent'] = round(100 * task['bytes'] / task['total'], 1) if task['total'] else 0
                    if task['status'] == 'running':
                        samples = self._speed_samples.setdefault(task['id'], deque(maxlen=64))
                        samples.append((now, task['bytes']))
                        while len(samples) > 2 and now - samples[0][0] > 4:
                            samples.popleft()
                        elapsed = now - samples[0][0]
                        task['speed'] = max(0, task['bytes'] - samples[0][1]) / elapsed if elapsed > 0 else 0
                        task['eta_seconds'] = (task['total'] - task['bytes']) / task['speed'] if task['speed'] > 0 else None
                    else:
                        self._speed_samples.pop(task['id'], None)
                        task['eta_seconds'] = None
                self.state['revision'] += 1
                value = self.snapshot()
            try:
                self.on_change(value)
            except Exception:
                # Widget teardown must never leak an exception containing internals.
                pass
            for listener in list(getattr(self, 'tools_listeners', [])):
                try: listener()
                except Exception: pass

    def start(self):
        """Read-only listing; no transfer and no saved command replay."""
        for pane in ('drive', 'local'):
            self._schedule_navigation(pane, self.positions[pane])

    def _connected(self):
        if self.provider is None and self.provider_factory is not None:
            try:
                self.provider = self.provider_factory()
            except Exception:
                raise TransferError('Drive 连接待更新，请点击“连接 Google Drive”重新授权。') from None
            with self.lock:
                self.state['connected'] = self.provider is not None
        if self.provider is None:
            raise TransferError('点击“连接 Google Drive”完成首次授权。')

    def _resolve_bookmark(self, entry):
        if entry.pane != 'drive' or entry.chain:
            return entry
        self._connected()
        root_meta = self.provider.metadata('root')
        root_id = root_meta.get('id')
        names, ids, seen = [], [], set()
        current = entry.remote_id
        for _ in range(MAX_DEPTH):
            if current == root_id or current == 'root':
                break
            if current in seen:
                raise TransferError('Drive 目录层级异常')
            seen.add(current)
            item = self.provider.metadata(current)
            if item.get('id') != current or item.get('trashed') is not False or item.get('mimeType') != FOLDER:
                raise TransferError('常用地址不再是可访问的目录')
            safe_parts((item.get('name'),))
            parents = item.get('parents', [])
            if len(parents) != 1:
                raise TransferError('常用地址无法从我的云端硬盘根目录定位')
            names.append(item['name']); ids.append(current)
            current = parents[0]
        else:
            raise TransferError('Drive 目录层级过深')
        names.reverse(); ids.reverse()
        resolved = Entry('drive', 'root', tuple(names), 'directory', names[-1] if names else '我的云端硬盘',
                         remote_id=ids[-1] if ids else 'root', chain=('root', *ids))
        self._register(resolved)
        return resolved

    def _validate_drive(self, entry, *, writable=False):
        self._connected()
        safe_parts(entry.parts)
        if not entry.chain or entry.chain[0] != 'root' or len(entry.chain) > MAX_DEPTH + 2:
            raise TransferError('Drive 路径无效，请重新从根目录打开')
        previous, current = None, None
        for index, file_id in enumerate(entry.chain):
            current = self.provider.metadata(file_id)
            actual = current.get('id')
            if (not ID_RE.fullmatch(str(actual)) or (not (index == 0 and file_id == 'root') and actual != file_id)
                    or current.get('trashed') is not False):
                raise TransferError('Drive 项目已变化，请刷新目录')
            if previous is not None and current.get('parents') != [previous]:
                raise TransferError('Drive 项目已移动，未进行传输')
            if index < len(entry.chain) - 1 and current.get('mimeType') != FOLDER:
                raise TransferError('Drive 路径不再是目录')
            if index > 0 and current.get('name') != entry.parts[index - 1]:
                raise TransferError('Drive 项目已重命名，请刷新目录')
            if writable:
                if current.get('ownedByMe') is not True or current.get('shared') is not False:
                    raise TransferError('共享或公开的 Drive 目标需要单独分享授权；当前仅写入自有私有目录')
                if current.get('mimeType') == FOLDER and current.get('capabilities', {}).get('canAddChildren') is not True:
                    raise TransferError('Drive 目标目录不可写')
            previous = actual
        if entry.kind == 'directory' and current.get('mimeType') != FOLDER:
            raise TransferError('Drive 目标不再是目录')
        return current

    def _list(self, entry):
        result = []
        safe_parts(entry.parts)
        if entry.pane == 'local':
            path = safe_local_path(self.local_roots['root'].joinpath(*entry.parts))
            with directory_fd(path) as fd:
                names = os.listdir(fd)
                writable = os.access('.', os.W_OK | os.X_OK, dir_fd=fd, effective_ids=True)
                self._directory_writable[self._token(entry)] = (writable, '' if writable else '当前目录只读；可浏览并选择其他可写目录')
                if len(names) > MAX_ENTRIES:
                    raise TransferError('目录文件过多，请改用更小的子目录')
                for name in names:
                    try:
                        safe_parts((name,))
                        safe_local_path(path / name)
                        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode) or (not stat.S_ISDIR(info.st_mode) and
                                (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
                            continue
                        kind = 'directory' if stat.S_ISDIR(info.st_mode) else 'file'
                        if info.st_size > MAX_BYTES:
                            continue
                        child = Entry('local', 'root', entry.parts + (name,), kind, name,
                                      size=info.st_size if kind == 'file' else 0, fp=fingerprint(info))
                        result.append({'id': self._token(child), 'name': name, 'kind': kind,
                                       'size': child.size, 'modified': '', 'extension': Path(name).suffix.lower(),
                                       'copyable': True,
                                       'canReceive': kind == 'directory' and os.access(name, os.W_OK | os.X_OK, dir_fd=fd, effective_ids=True)})
                    except (TransferError, OSError, UnicodeError):
                        continue
        else:
            meta = self._validate_drive(entry)
            try:
                self._validate_drive(entry, writable=True)
                writable, reason = True, ''
            except TransferError as exc:
                writable, reason = False, str(exc)
            self._directory_writable[self._token(entry)] = (writable, reason)
            for item in self.provider.children(meta['id']):
                try:
                    name = safe_name(item.get('name'))
                    safe_parts((name,))
                    file_id = item.get('id')
                    if not ID_RE.fullmatch(str(file_id)) or item.get('parents') != [meta['id']] or item.get('trashed'):
                        continue
                    mime = item.get('mimeType', '')
                    if mime == 'application/vnd.google-apps.shortcut':
                        continue
                    kind = 'directory' if mime == FOLDER else 'file'
                    size = int(item.get('size', 0))
                    if not 0 <= size <= MAX_BYTES:
                        continue
                    child = Entry('drive', 'root', entry.parts + (name,), kind, name,
                                  file_id, size, chain=entry.chain + (file_id,))
                    copyable = kind == 'directory' or (not mime.startswith('application/vnd.google-apps.') and item.get('capabilities', {}).get('canDownload') is True)
                    child_writable = writable and kind == 'directory' and item.get('ownedByMe') is True and item.get('shared') is False and item.get('capabilities', {}).get('canAddChildren') is True
                    result.append({'id': self._token(child), 'name': name, 'kind': kind, 'size': size,
                                   'modified': item.get('modifiedTime', ''), 'extension': Path(name).suffix.lower(),
                                   'copyable': copyable, 'canReceive': child_writable})
                except (TransferError, ValueError, TypeError, UnicodeError):
                    continue
        return sorted(result, key=lambda x: (x['kind'] != 'directory', x['name'].casefold()))

    def _schedule_navigation(self, pane, entry):
        if entry.kind != 'directory' or entry.pane != pane or len(entry.parts) > MAX_DEPTH:
            raise TransferError('只能进入已列出的安全目录')
        with self.lock:
            self.positions[pane] = entry
            self.nav_generation[pane] += 1
            generation = self.nav_generation[pane]
            self.state['panes'][pane] = self._pane_state(entry, [], loading=True)
        self._publish()
        def work():
            try:
                resolved = self._resolve_bookmark(entry)
                children = self._list(resolved)
                error = ''
            except TransferError as exc:
                resolved, children, error = entry, [], str(exc)
            except Exception:
                resolved, children, error = entry, [], '目录读取失败，请重试'
            with self.lock:
                if generation != self.nav_generation[pane] or self.closed:
                    return
                self.positions[pane] = resolved
                self.state['panes'][pane] = self._pane_state(resolved, children)
                self.state['panes'][pane]['error'] = error
            self._publish()
        self.reads.submit(work)

    def handle(self, message):
        """Accept only ephemeral custom messages, never synced trait commands."""
        if not isinstance(message, dict) or self.closed:
            return
        request_id = message.get('request_id')
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
            return
        with self.lock:
            if request_id in self.seen_requests:
                return
            if len(self.seen_requests) >= 10000:
                self.state['notice'] = '本次会话操作较多，请重开面板后继续'
                self._publish()
                return
            self.seen_requests.add(request_id)
        try:
            action = message.get('action')
            if action in {'root', 'refresh', 'navigate'}:
                pane = message.get('pane')
                if pane not in self.positions:
                    raise TransferError('面板无效')
                if action == 'root':
                    roots = DRIVE_ROOTS if pane == 'drive' else self.local_roots
                    if message.get('root') not in roots:
                        raise TransferError('目录超出授权范围')
                    entry = self._root(pane, message['root'])
                elif action == 'navigate':
                    entry = self.entries.get(message.get('entry_id'))
                    if entry is None:
                        raise TransferError('目录已失效，请刷新')
                else:
                    entry = self.positions[pane]
                self._schedule_navigation(pane, entry)
            elif action == 'transfer':
                self._enqueue(message)
            elif action in {'cancel', 'retry'}:
                self._task_action(action, message.get('task_id'))
            else:
                raise TransferError('不支持此操作')
        except TransferError as exc:
            with self.lock:
                self.state['notice'] = str(exc)
            self._publish()
        except Exception:
            with self.lock:
                self.state['notice'] = '操作未完成，请刷新后重试'
            self._publish()

    def _enqueue(self, message):
        source_ids = message.get('entry_ids')
        if not isinstance(source_ids, list) or not 1 <= len(source_ids) <= 16 or len(set(source_ids)) != len(source_ids):
            raise TransferError('每次请选择 1–16 个文件或文件夹')
        target = self.entries.get(message.get('target_id'))
        if target is None or target.kind != 'directory':
            raise TransferError('目标目录已失效，请刷新')
        sources = []
        for token in source_ids:
            source = self.entries.get(token)
            if source is None or source.kind not in {'file', 'directory'}:
                raise TransferError('请选择列表中的文件或文件夹')
            safe_parts(source.parts)
            safe_parts(target.parts)
            if (source.pane, target.pane) not in {('drive', 'local'), ('local', 'drive')}:
                raise TransferError('请在 Drive 与服务器两侧之间复制文件')
            sources.append(source)
        with self.lock:
            active = sum(t['status'] in {'queued', 'running'} for t in self.tasks)
            if len(self.tasks) + len(sources) > 64:
                finished = [t for t in self.tasks if t['status'] not in {'queued', 'running'}]
                for task in finished[:len(self.tasks) + len(sources) - 64]:
                    self.tasks.remove(task)
                    self.task_internal.pop(task['id'], None)
            if active + len(sources) > 16:
                raise TransferError('传输队列已满，请等待完成后重开面板')
            for source in sources:
                key = (source.pane, source.root, source.parts, source.remote_id, target.pane, target.root, target.parts, target.remote_id)
                if any(v['key'] == key and v['task']['status'] in {'queued', 'running'} for v in self.task_internal.values()):
                    continue
                task = {'id': uuid.uuid4().hex, 'name': source.name, 'kind': source.kind,
                        'direction': 'download' if source.pane == 'drive' else 'upload',
                        'status': 'queued', 'bytes': 0, 'total': source.size, 'speed': 0, 'error': ''}
                internal = {'task': task, 'source': source, 'target': target, 'cancel': threading.Event(),
                            'remote_upload_id': None, 'destination_name': None, 'key': key}
                from copy_registry import remember
                remember(self, source, target)
                self.tasks.append(task)
                self.task_internal[task['id']] = internal
                self.transfers.submit(self._run, internal)
            self.state['notice'] = ''
        self._publish()

    def _task_action(self, action, task_id):
        with self.lock:
            item = self.task_internal.get(task_id)
            if item is None:
                raise TransferError('传输任务已失效')
            task = item['task']
            if action == 'cancel':
                if task['status'] in {'queued', 'running'}:
                    item['cancel'].set()
                    if task['status'] == 'queued':
                        task['status'] = 'cancelled'
                    else:
                        task['error'] = '正在停止，当前数据块完成后取消'
            elif task['status'] in {'failed', 'cancelled'}:
                if any(other is not item and other['key'] == item['key']
                        and other['task']['status'] in {'queued', 'running'}
                        for other in self.task_internal.values()):
                    raise TransferError('同一文件已在传输队列中，请等待当前任务')
                if sum(t['status'] in {'queued', 'running'} for t in self.tasks) >= 16:
                    raise TransferError('传输队列已满，请等待完成后重试')
                # One retry, one explicit new message, same reserved upload id.
                item['cancel'] = threading.Event()
                task.update(status='queued', bytes=0, speed=0, error='')
                self.transfers.submit(self._run, item)
        self._publish()

    def _run(self, item):
        if item['source'].kind == 'directory':
            self._run_transfer(item)
        else:
            with self._transfer_slots:
                self._run_transfer(item)

    def _run_transfer(self, item):
        task, cancel = item['task'], item['cancel']
        with self.lock:
            if cancel.is_set() or self.closed or task['status'] != 'queued':
                return
            task['status'] = 'running'
        started, last_emit = time.monotonic(), [0.0]
        def progress(amount):
            with self.lock:
                task['bytes'] = max(0, min(int(amount), task['total']))
                task['speed'] = task['bytes'] / max(time.monotonic() - started, 0.01)
            now = time.monotonic()
            if now - last_emit[0] >= 0.25:
                last_emit[0] = now
                self._publish()
        self._publish()
        try:
            if item['source'].kind == 'directory':
                self._copy_folder(item, progress, cancel)
            elif task['direction'] == 'download':
                self._download(item, progress, cancel)
            else:
                self._upload(item, progress, cancel)
            with self.lock:
                task.update(status='completed', bytes=task['total'], speed=0, error='')
        except Cancelled as exc:
            with self.lock:
                task.update(status='cancelled', speed=0, error=str(exc))
        except TransferError as exc:
            with self.lock:
                task.update(status='failed', speed=0, error=str(exc))
        except Exception:
            with self.lock:
                task.update(status='failed', speed=0, error='传输未完成，请重试')
        self._publish()
        target = item['target']
        if not self.closed and self.positions[target.pane] == target:
            self._schedule_navigation(target.pane, target)

    def _folder_target(self, source, target):
        safe_parts((source.name,))
        parts = target.parts + (source.name,)
        if target.pane == 'local':
            parent = self.local_roots['root'].joinpath(*target.parts)
            with directory_fd(parent) as fd:
                try:
                    os.mkdir(source.name, dir_fd=fd)
                except FileExistsError:
                    pass
            with directory_fd(parent / source.name):
                pass
            folder = Entry('local', 'root', parts, 'directory', source.name)
        else:
            parent = self._validate_drive(target, writable=True)
            existing = next((child for child in self.provider.children(parent['id'])
                             if child.get('name') == source.name and child.get('mimeType') == FOLDER), None)
            remote = existing or self.provider.create_folder(parent['id'], source.name)
            folder = Entry('drive', 'root', parts, 'directory', source.name,
                           remote_id=remote['id'], chain=target.chain + (remote['id'],))
        self._register(folder)
        return folder

    def _copy_folder(self, item, progress, cancel):
        if 'folder_children' not in item:
            children = [self.entries[entry['id']] for entry in self._list(item['source'])
                        if entry['kind'] == 'file' and entry['copyable']]
            folder = self._folder_target(item['source'], item['target'])
            item['folder_children'] = [
                {'source': source, 'target': folder,
                 'task': {**item['task'], 'id': uuid.uuid4().hex,
                          'name': source.name, 'total': source.size, 'bytes': 0},
                 'remote_upload_id': None, 'destination_name': None, 'completed': False}
                for source in children]
            item['task']['total'] = sum(source.size for source in children)
            item['task']['file_count'] = len(children)
        children = item['folder_children']
        amounts = {child['task']['id']: child['source'].size if child['completed'] else 0
                   for child in children}
        progress(sum(amounts.values()))

        def report(child, amount):
            with self.lock:
                amounts[child['task']['id']] = amount
                progress(sum(amounts.values()))

        def copy_child(child):
            with self._transfer_slots:
                cancelled(cancel)
                on_progress = lambda amount: report(child, amount)
                if child['source'].pane == 'drive':
                    self._download(child, on_progress, cancel)
                else:
                    self._upload(child, on_progress, cancel)
                child['completed'] = True
                report(child, child['source'].size)

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL, thread_name_prefix='molab-folder') as workers:
            futures = [workers.submit(copy_child, child) for child in children if not child['completed']]
            for future in as_completed(futures):
                future.result()

    def _download(self, item, progress, cancel):
        source, target = item['source'], item['target']
        meta = self._validate_drive(source)
        if (meta.get('name') != source.name or meta.get('capabilities', {}).get('canDownload') is not True
                or meta.get('mimeType', '').startswith('application/vnd.google-apps.')):
            raise TransferError('该文件不可下载或已变化；Google 原生文档不支持直接二进制复制')
        if int(meta.get('size', -1)) != source.size or not (meta.get('md5Checksum') or meta.get('sha256Checksum')):
            raise TransferError('文件大小已变化或缺少校验值，请刷新目录')
        temporary = '.molab-transfer-' + item['task']['id'] + '.part'
        destination = safe_local_path(self.local_roots['root'].joinpath(*target.parts))
        with directory_fd(destination) as fd:
            # O_EXCL never truncates a user's file, even if a previous task crashed.
            try:
                out_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise TransferError('此前的临时下载仍存在；请刷新并重新拖动') from None
            created_info = os.fstat(out_fd)
            try:
                with os.fdopen(out_fd, 'wb') as stream:
                    writer = HashingWriter(stream, source.size)
                    self.provider.download(source.remote_id, writer, source.size, progress, cancel)
                    cancelled(cancel)
                    fresh = self._validate_drive(source)
                    if (fresh.get('version') != meta.get('version') or fresh.get('name') != meta.get('name')
                            or not checksum_matches(fresh, writer.count, writer.md5.hexdigest(), writer.sha256.hexdigest())):
                        raise TransferError('文件校验未通过，未保存到目标目录')
                    stream.flush()
                    os.fsync(stream.fileno())
                    pinned = os.fstat(stream.fileno())
                    named = os.stat(temporary, dir_fd=fd, follow_symlinks=False)
                    if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1
                            or (named.st_dev, named.st_ino) != (pinned.st_dev, pinned.st_ino)):
                        raise TransferError('临时文件被外部修改，未保存下载')
                    # Publish from our still-open descriptor, not the mutable
                    # temp pathname. Following this /proc fd symlink is safe:
                    # we created and hold this exact non-secret file descriptor.
                    for number in range(1000):
                        name = numbered(source.name, number)
                        try:
                            os.link(f'/proc/self/fd/{stream.fileno()}', name,
                                    dst_dir_fd=fd, follow_symlinks=True)
                            published = os.stat(name, dir_fd=fd, follow_symlinks=False)
                            if (not stat.S_ISREG(published.st_mode) or
                                    (published.st_dev, published.st_ino) != (pinned.st_dev, pinned.st_ino)):
                                raise TransferError('本地目标发生变化，请检查目标目录')
                            item['destination_name'] = name
                            item['task']['saved_name'] = name
                            break
                        except FileExistsError:
                            continue
                    else:
                        raise TransferError('同名文件过多，未覆盖任何文件')
            finally:
                # Remove only our own inode, never a replaced pathname.
                try:
                    remaining = os.stat(temporary, dir_fd=fd, follow_symlinks=False)
                    if (remaining.st_dev, remaining.st_ino) == (created_info.st_dev, created_info.st_ino):
                        os.unlink(temporary, dir_fd=fd)
                except FileNotFoundError:
                    pass

    def _upload(self, item, progress, cancel):
        source, target = item['source'], item['target']
        safe_parts(source.parts)
        target_meta = self._validate_drive(target, writable=True)
        item['target_remote_id'] = target_meta['id']
        with local_file(self.local_roots['root'], source.parts, source.fp) as (stream, before):
            md5, sha256 = hashlib.md5(usedforsecurity=False), hashlib.sha256()
            while block := stream.read(CHUNK):
                cancelled(cancel)
                md5.update(block)
                sha256.update(block)
            if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
                raise TransferError('本地输出正在变化，未上传；请生成完成后重试')
            stream.seek(0)
            if item['remote_upload_id'] is None:
                item['remote_upload_id'] = self.provider.reserve_id()
            file_id = item['remote_upload_id']
            existing = self.provider.metadata(file_id, missing_ok=True)
            if existing is not None:
                self._validate_drive(target, writable=True)
                self._verify_uploaded(existing, item, before.st_size, md5.hexdigest(), sha256.hexdigest())
                if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
                    raise TransferError('核验期间源文件发生变化，请刷新后检查')
                item['task']['saved_name'] = item['destination_name']
                progress(before.st_size)
                return
            if item['destination_name'] is None:
                names = {x.get('name') for x in self.provider.children(item['target_remote_id'])}
                with self.lock:
                    names.update(other['destination_name'] for other in self.task_internal.values()
                                 if other is not item and other.get('target_remote_id') == item['target_remote_id']
                                 and other.get('destination_name'))
                    for number in range(1000):
                        name = numbered(source.name, number)
                        if name not in names:
                            item['destination_name'] = name
                            break
                    else:
                        raise TransferError('同名文件过多，未覆盖任何文件')
            cancelled(cancel)
            fresh_target = self._validate_drive(target, writable=True)
            if fresh_target['id'] != item['target_remote_id']:
                raise TransferError('目标目录发生变化，未上传')
            if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
                raise TransferError('本地文件已变化，未上传；请刷新后重新选择')
            guarded_stream = GuardedReader(stream, fingerprint(before), cancel)
            try:
                self.provider.upload(file_id, item['target_remote_id'], item['destination_name'], guarded_stream,
                                     before.st_size, progress, cancel)
            except (TransferError, Cancelled):
                # A final chunk may have committed despite an interrupted response.
                existing = self.provider.metadata(file_id, missing_ok=True)
                if existing is None:
                    raise
            fresh = self.provider.metadata(file_id)
            self._validate_drive(target, writable=True)
            self._verify_uploaded(fresh, item, before.st_size, md5.hexdigest(), sha256.hexdigest())
            if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
                raise TransferError('上传期间源文件发生变化；已保留远端文件，请核验')
            item['task']['saved_name'] = item['destination_name']

    def _verify_uploaded(self, meta, item, size, md5, sha256):
        if (meta.get('id') != item['remote_upload_id'] or meta.get('parents') != [item.get('target_remote_id', item['target'].remote_id)]
                or meta.get('name') != item['destination_name'] or meta.get('trashed') is not False
                or meta.get('ownedByMe') is not True or meta.get('shared') is not False
                or not checksum_matches(meta, size, md5, sha256)):
            raise TransferError('上传结果未通过完整性或私有性核验；未覆盖或删除任何文件')

    def close(self):
        with self.lock:
            self.closed = True
            for item in self.task_internal.values():
                item['cancel'].set()
        self.reads.shutdown(wait=False, cancel_futures=True)
        self.transfers.shutdown(wait=False, cancel_futures=True)
