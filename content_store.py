"""Gzip persisted content; runtime objects use their original values."""
import gzip
import io
import os
from pathlib import Path

GZIP_MAGIC = b'\x1f\x8b'


def enabled():
    return os.environ.get('WORKFLOW_GZIP_CONTENT', '1' if Path('/marimo').is_dir() else '0') == '1'


def pack(data):
    return gzip.compress(data, compresslevel=6, mtime=0) if enabled() else data


def unpack(data):
    if data.startswith(GZIP_MAGIC):
        return gzip.decompress(data)
    return data


def read_bytes(path):
    return unpack(Path(path).read_bytes())


def write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack(data))


def read_text(path):
    return read_bytes(path).decode('utf-8')


def write_text(path, text):
    write_bytes(path, text.encode('utf-8'))


def open_image(path):
    from PIL import Image
    return Image.open(io.BytesIO(read_bytes(path)))


def save_image(image, path, format, **options):
    output = io.BytesIO()
    image.save(output, format=format, **options)
    write_bytes(path, output.getvalue())


def migrate_file(source, target):
    source, target = Path(source), Path(target)
    if source == target:
        return
    if not target.exists():
        write_bytes(target, read_bytes(source))
    source.unlink()
