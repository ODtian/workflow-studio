"""Restore ComfyUI's Git checkouts from a small manifest."""
import json
from pathlib import Path
import re
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import urlsplit


def _read_manifest(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def _public_remote(remote):
    url = urlsplit(remote)
    if url.scheme in ("http", "https") and url.hostname:
        return url._replace(netloc=url.netloc.rsplit("@", 1)[-1], query="", fragment="").geturl()
    return None


def restore_plugins(nodes, manifest):
    for name, plugin in _read_manifest(manifest).items():
        if not re.fullmatch(r"[\w.-]+", name) or name in (".", ".."):
            raise ValueError(f"无效的 ComfyUI 插件目录：{name}")
        target = nodes / name
        if target.exists() or target.is_symlink():
            continue
        remote, revision = plugin["repository"], plugin["revision"]
        if not remote or remote != _public_remote(remote) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError(f"无效的 ComfyUI 插件来源：{name}")
        with TemporaryDirectory(dir=nodes.parent) as directory:
            clone = Path(directory) / name
            _git("clone", "--quiet", "--no-checkout", "--", remote, str(clone))
            _git("checkout", "--quiet", "--detach", revision, cwd=clone)
            clone.rename(target)


def remember_plugins(nodes, manifest):
    plugins = {}
    for path in sorted(nodes.iterdir()):
        if not path.is_dir() or path.is_symlink() or not (path / ".git").exists():
            continue
        remote = _public_remote(_git("remote", "get-url", "origin", cwd=path, check=False).stdout.strip())
        revision = _git("rev-parse", "HEAD", cwd=path, check=False).stdout.strip()
        if remote and re.fullmatch(r"[0-9a-f]{40}", revision):
            plugins[path.name] = {"repository": remote, "revision": revision}
    if _read_manifest(manifest) != plugins:
        with NamedTemporaryFile(dir=manifest.parent, mode="w", encoding="utf-8", delete=False) as stream:
            temporary = Path(stream.name)
            try:
                json.dump(plugins, stream, ensure_ascii=False, indent=2)
            except BaseException:
                stream.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(manifest)
        finally:
            temporary.unlink(missing_ok=True)
