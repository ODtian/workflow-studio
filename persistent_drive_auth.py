"""Notebook-local Drive authentication with explicit first-time setup.

Import is inert. Normal reconnect reads only the official Secrets environment
value, refreshes an existing grant, and never starts OAuth or writes credentials.
The separate setup function must be invoked by the user in the notebook during
the secure handoff. It performs a fresh OAuth flow; it never exports the SDK's
old cache or another application's grant. All credential values stay inside the
notebook runtime. Never display a cache object, credentials, or exception data.

Molab documents .env persistence and fork exclusion, not an encrypted vault:
https://marimo.io/pages/molab/storage
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading

SECRET_NAME = "MOLAB_DRIVE_AUTH_JSON"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
TOKEN_URI = "https://oauth2.googleapis.com/token"
NOTEBOOK_SECRET_PATH = Path("/marimo/.env")
_SECRET_WRITE_LOCK_PATH = Path("/tmp/.molab-drive-auth-save.lock")
MAX_SECRET_BYTES = 64 * 1024
MAX_ENV_BYTES = 1024 * 1024
_CLIENT_ID = re.compile(r"[A-Za-z0-9_.-]+\.apps\.googleusercontent\.com\Z")
_SAVE_LOCK = threading.RLock()
_SETUP_LOCK = threading.Lock()


class DriveAuthError(RuntimeError):
    """Only fixed, non-secret messages may be exposed to the UI."""


def _no_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate credential field")
        result[key] = value
    return result


def _validated_info(raw):
    """Allow only a Google authorized-user grant for the already approved scope."""
    try:
        if not isinstance(raw, str) or not 0 < len(raw.encode("utf-8")) <= MAX_SECRET_BYTES:
            raise ValueError
        value = json.loads(raw, object_pairs_hook=_no_duplicate_pairs)
        if not isinstance(value, dict) or value.get("type", "authorized_user") != "authorized_user":
            raise ValueError
        for field in ("client_id", "client_secret", "refresh_token"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError
            if any(ord(c) < 32 for c in value[field]):
                raise ValueError
        if not _CLIENT_ID.fullmatch(value["client_id"]):
            raise ValueError
        if value.get("token_uri", TOKEN_URI) != TOKEN_URI:
            raise ValueError
        scopes = value.get("scopes")
        if isinstance(scopes, str):
            scopes = scopes.split()
        if not isinstance(scopes, list) or set(scopes) != {DRIVE_SCOPE}:
            raise ValueError
        # Only long-lived fields are stored. Access tokens, custom endpoints,
        # quota projects, arbitrary credential types, and unknown fields are not.
        return {
            "type": "authorized_user",
            "client_id": value["client_id"],
            "client_secret": value["client_secret"],
            "refresh_token": value["refresh_token"],
            "token_uri": TOKEN_URI,
            "scopes": [DRIVE_SCOPE],
        }
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise DriveAuthError("Drive Secrets 配置无效，请使用首次安全连接重新配置。") from None


def has_persistent_secret(environ=None):
    """Presence only. Does not read files, parse, log, or return secret values."""
    environment = os.environ if environ is None else environ
    return bool(environment.get(SECRET_NAME))


def _credentials_from_info(info):
    from google.oauth2.credentials import Credentials
    return Credentials.from_authorized_user_info(info, scopes=[DRIVE_SCOPE])


def _env_content_with_secret(content, serialized):
    # The official Secrets file may contain multiline values for other keys.
    # Preserve each unrelated binding byte-for-byte instead of splitting lines.
    from dotenv.parser import parse_stream
    bindings = list(parse_stream(io.StringIO(content)))
    if any(binding.error for binding in bindings):
        raise DriveAuthError("现有 Secrets 文件格式无效，未修改任何配置。")
    escaped = serialized.replace("\\", "\\\\").replace("'", "\\'")
    replacement = SECRET_NAME + "='" + escaped + "'\n"
    parts, written = [], False
    for binding in bindings:
        if binding.key == SECRET_NAME:
            if not written:
                parts.append(replacement)
                written = True
        else:
            parts.append(binding.original.string)
    if not written:
        if parts and not parts[-1].endswith("\n"):
            parts.append("\n")
        parts.append(replacement)
    return "".join(parts)


def _save_official_secret(path, serialized, environ):
    """User-triggered setup only: atomically replace exactly .env.

    A 0600 temporary in a private directory is created only in ephemeral /tmp,
    outside notebook persistence. A crash may leave it until sandbox teardown. If
    /tmp and the notebook are on different devices, fail without modifying .env.
    Original credentials are never backed up. Unrelated Secrets are retained.
    A failed write is reported, never presented as a successful connection.
    """
    import fcntl
    path = Path(path).absolute()
    if path.name != ".env" or ".." in path.parts:
        raise DriveAuthError("长期授权只能保存在本 notebook 的 .env Secrets 中。")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise DriveAuthError("Secrets 路径不安全，未保存授权。")
    fd = temporary_fd = lock_fd = None
    temporary_path = temporary_directory = None
    try:
        with _SAVE_LOCK:
            # Stable, empty, runtime-local lock survives inode replacement and
            # serializes cooperating setup writers across processes. Never
            # delete a shared lock file while another writer could be waiting.
            lock_fd = os.open(_SECRET_WRITE_LOCK_PATH, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            lock_entry = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_entry.st_mode) or lock_entry.st_nlink != 1 or lock_entry.st_uid != os.geteuid():
                raise DriveAuthError("Secrets 保存锁不安全，未修改配置。")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if path.parent.stat().st_dev != Path("/tmp").stat().st_dev:
                raise DriveAuthError("Secrets 无法安全原子保存，原有配置保持不变。")
            original_identity = None
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                content = ""
            else:
                fcntl.flock(fd, fcntl.LOCK_EX)
                entry = os.fstat(fd)
                if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1 or entry.st_uid != os.geteuid():
                    raise DriveAuthError("Secrets 文件不安全，未保存授权。")
                if entry.st_size > MAX_ENV_BYTES:
                    raise DriveAuthError("Secrets 文件过大，未修改配置。")
                original_identity = (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns)
                chunks, read_size = [], 0
                while True:
                    block = os.read(fd, min(64 * 1024, MAX_ENV_BYTES + 1 - read_size))
                    if not block:
                        break
                    chunks.append(block)
                    read_size += len(block)
                    if read_size > MAX_ENV_BYTES:
                        raise DriveAuthError("Secrets 文件过大，未修改配置。")
                if read_size != entry.st_size:
                    raise DriveAuthError("Secrets 同时被修改，未覆盖配置；请重新完成安全连接。")
                content = b"".join(chunks).decode("utf-8")
            revised = _env_content_with_secret(content, serialized).encode("utf-8")
            if len(revised) > MAX_ENV_BYTES:
                raise DriveAuthError("Secrets 文件过大，未修改配置。")
            temporary_directory = tempfile.mkdtemp(prefix=".molab-drive-auth-", dir="/tmp")
            temporary_fd, temporary_path = tempfile.mkstemp(prefix=".env-", dir=temporary_directory)
            pending = memoryview(revised)
            while pending:
                count = os.write(temporary_fd, pending)
                if count <= 0:
                    raise OSError
                pending = pending[count:]
            os.fsync(temporary_fd)
            os.close(temporary_fd)
            temporary_fd = None
            # Do not clobber a change made by the official Secrets editor while
            # OAuth was finishing. The user can retry the setup if this races.
            try:
                current = path.lstat()
                current_identity = (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns)
            except FileNotFoundError:
                current_identity = None
            if current_identity != original_identity or path.is_symlink():
                raise DriveAuthError("Secrets 同时被修改，未覆盖配置；请重新完成安全连接。")
            os.replace(temporary_path, path)
            temporary_path = None
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            environ[SECRET_NAME] = serialized
    except DriveAuthError:
        raise
    except Exception:
        raise DriveAuthError("Drive 长期授权未能保存，请保持当前页面并重新完成安全配置。") from None
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
        if temporary_directory is not None:
            try:
                os.rmdir(temporary_directory)
            except FileNotFoundError:
                pass
        if fd is not None:
            os.close(fd)
        if lock_fd is not None:
            os.close(lock_fd)


class NotebookSecretsCache:
    """Public pydata-google-auth load/save cache interface; read-only by default."""

    def __init__(self, *, environ=None, secret_path=None, user_setup=False,
                 credentials_factory=None):
        self._environ = os.environ if environ is None else environ
        self._path = NOTEBOOK_SECRET_PATH if secret_path is None else Path(secret_path)
        self._user_setup = user_setup is True
        self._credentials_factory = credentials_factory or _credentials_from_info
        self.saved = False

    def __repr__(self):
        return "<NotebookSecretsCache>"

    def load(self):
        if self._user_setup:
            # First-time/replacement setup always obtains a fresh grant from the
            # user's interactive flow, never copying any cached grant.
            return None
        raw = self._environ.get(SECRET_NAME)
        if not raw:
            return None
        info = _validated_info(raw)
        try:
            return self._credentials_factory(info)
        except Exception:
            raise DriveAuthError("Drive Secrets 无法加载，请重新完成首次安全连接。") from None

    def save(self, credentials):
        if not self._user_setup:
            raise DriveAuthError("自动连接不会写入授权；请使用首次安全连接。")
        try:
            # Called only by the fresh user-run OAuth flow. Never read the old
            # SDK cache, rclone config, notebook source, or an external token.
            info = _validated_info(credentials.to_json())
            # dotenv expands ${NAME} even inside single quotes. JSON unicode
            # escaping prevents environment interpolation from altering a grant.
            serialized = json.dumps(info, ensure_ascii=True, separators=(",", ":")).replace("$", "\\u0024")
            _save_official_secret(self._path, serialized, self._environ)
            self.saved = True
        except DriveAuthError:
            raise
        except Exception:
            raise DriveAuthError("无法保存 Drive 长期授权，请重新完成安全配置。") from None


class DriveAuthorization:
    """Split the SDK's console OAuth flow into page actions."""

    def __init__(self):
        self.flow = None

    def begin(self):
        from google_auth_oauthlib.flow import InstalledAppFlow
        from pydata_google_auth import auth as sdk
        config = {'installed': {
            'client_id': sdk.WEBAPP_CLIENT_ID,
            'client_secret': sdk.WEBAPP_CLIENT_SECRET,
            'auth_uri': sdk.GOOGLE_AUTH_URI,
            'token_uri': sdk.GOOGLE_TOKEN_URI,
            'redirect_uris': [sdk.WEBAPP_REDIRECT_URI],
        }}
        self.flow = InstalledAppFlow.from_client_config(config, scopes=[DRIVE_SCOPE])
        self.flow.redirect_uri = sdk.WEBAPP_REDIRECT_URI
        url, _ = self.flow.authorization_url(**sdk.AUTH_URI_KWARGS)
        return url

    def complete(self, code):
        try:
            self.flow.fetch_token(code=code.strip())
            NotebookSecretsCache(user_setup=True).save(self.flow.credentials)
            return True
        except DriveAuthError:
            raise
        except Exception:
            raise DriveAuthError('Drive 授权码验证失败，请重新授权后提交。') from None
        finally:
            self.flow = None


def sdk_capabilities():
    """Return booleans/version strings only; never touch credential storage."""
    import inspect
    from importlib.metadata import PackageNotFoundError, version
    from gdrive_fsspec import GoogleDriveFileSystem
    import pydata_google_auth
    result = {
        "fsspec_auth_kwargs": "auth_kwargs" in inspect.signature(GoogleDriveFileSystem.__init__).parameters,
        "pydata_credentials_cache": "credentials_cache" in inspect.signature(pydata_google_auth.get_user_credentials).parameters,
    }
    for name in ("gdrive-fsspec", "pydata-google-auth", "google-auth"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = "unknown"
    return result


def complete_user_setup():
    """USER-RUN HANDOFF STEP. Complete fresh OAuth and persist inside Molab.

    The user starts this action, completes Google consent, and submits the
    one-time code directly in Molab. Do not run this on their behalf through
    final submission. It returns only a success boolean, never credentials.
    """
    if not _SETUP_LOCK.acquire(blocking=False):
        raise DriveAuthError("首次安全连接已在进行，请完成当前授权页面。")
    try:
        return _complete_user_setup()
    finally:
        _SETUP_LOCK.release()


def _complete_user_setup(*, secret_path=None, environ=None):
    """Private implementation; path/env injection exists only for offline tests."""
    import pydata_google_auth
    cache = NotebookSecretsCache(secret_path=secret_path, environ=environ, user_setup=True)
    try:
        credentials = pydata_google_auth.get_user_credentials(
            [DRIVE_SCOPE], credentials_cache=cache, use_local_webserver=False)
        # PyData normally saves a new grant through cache.save. Verify presence
        # only; no payload is returned or displayed in the notebook.
        if not cache.saved or not has_persistent_secret(cache._environ) or credentials is None:
            raise DriveAuthError("Drive 授权尚未保存，请完成页面中的安全配置。")
        return True
    except DriveAuthError:
        raise
    except Exception:
        raise DriveAuthError("Drive 安全连接未完成，请重试；没有改动模型或生成结果。") from None


def connect_from_secrets(*, cache=None, request_factory=None, service_factory=None):
    """Reconnect an existing Secrets grant, with no OAuth or write fallback."""
    cache = NotebookSecretsCache() if cache is None else cache
    credentials = cache.load()
    if credentials is None:
        return None
    try:
        if not credentials.has_scopes([DRIVE_SCOPE]):
            raise DriveAuthError("Drive 授权范围不足，请使用首次安全连接。")
        if not credentials.valid:
            if request_factory is None:
                from google.auth.transport.requests import Request
                def request_factory():
                    transport = Request()
                    def bounded_request(*args, **kwargs):
                        kwargs["timeout"] = 30
                        return transport(*args, **kwargs)
                    return bounded_request
            credentials.refresh(request_factory())
        if not credentials.valid:
            raise DriveAuthError("Drive 授权未能恢复，请使用首次安全连接。")
        if service_factory is None:
            from googleapiclient.discovery import build
            service_factory = lambda cred: build("drive", "v3", credentials=cred, cache_discovery=False)
        return service_factory(credentials)
    except DriveAuthError:
        raise
    except Exception:
        raise DriveAuthError("Drive 自动连接未完成；可检查连接或重新完成首次安全连接。") from None
