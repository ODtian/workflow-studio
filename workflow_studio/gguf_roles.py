"""Read GGUF file roles and embedded MTP metadata for the model selectors."""
from functools import lru_cache
from pathlib import Path
import struct

_FORMATS = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i', 6: 'f',
            7: '?', 10: 'Q', 11: 'q', 12: 'd'}


def _number(stream, fmt):
    return struct.unpack('<' + fmt, stream.read(struct.calcsize(fmt)))[0]


def _text(stream):
    return stream.read(_number(stream, 'Q')).decode('utf-8')


def _value(stream, kind, keep):
    if kind == 8:
        size = _number(stream, 'Q')
        if keep:
            return stream.read(size).decode('utf-8')
        stream.seek(size, 1)
    elif kind == 9:
        subtype, count = _number(stream, 'I'), _number(stream, 'Q')
        if subtype in _FORMATS:
            stream.seek(struct.calcsize(_FORMATS[subtype]) * count, 1)
        else:
            for _ in range(count):
                _value(stream, subtype, False)
    else:
        result = _number(stream, _FORMATS[kind])
        if keep:
            return result


@lru_cache(maxsize=128)
def _profile(path, modified, size):
    with Path(path).open('rb') as stream:
        magic, version, tensors, fields = struct.unpack('<4sIQQ', stream.read(24))
        if magic != b'GGUF' or version not in (2, 3):
            raise ValueError(f'{Path(path).name}：请选择 GGUF v2/v3 文件。')
        metadata = {}
        for _ in range(fields):
            key = _text(stream)
            keep = key in {'general.architecture', 'general.type', 'tokenizer.chat_template'} or key.endswith(
                ('.block_count', '.nextn_predict_layers'))
            result = _value(stream, _number(stream, 'I'), keep)
            if keep:
                metadata[key] = result
        architecture = metadata.get('general.architecture', '')
        if metadata.get('general.type') == 'mmproj' or architecture == 'clip':
            return {'role': 'mmproj', 'has_mtp': False, 'chat_template': ''}
        nextn = metadata.get(architecture + '.nextn_predict_layers', 0)
        role = 'model'
        if nextn:
            # A separate MTP head contains only the final NextN blocks.
            first_mtp = metadata[architecture + '.block_count'] - nextn
            has_main_blocks = False
            for _ in range(tensors):
                name = _text(stream)
                if name.startswith('blk.') and int(name.split('.')[1]) < first_mtp:
                    has_main_blocks = True
                stream.seek(8 * _number(stream, 'I') + 12, 1)
            role = 'model' if has_main_blocks else 'mtp'
        return {'role': role, 'has_mtp': nextn > 0,
                'chat_template': metadata.get('tokenizer.chat_template', '')}


def profile(path):
    path = Path(path)
    stat = path.stat()
    return _profile(str(path), stat.st_mtime_ns, stat.st_size)


def validate_files(model, mmproj=None, mtp=None, embedded=False):
    labels = {'model': '主模型', 'mmproj': '图像投影器 mmproj', 'mtp': 'MTP 草稿权重'}
    for field, path in [('model', model), ('mmproj', mmproj), ('mtp', mtp)]:
        if path is None:
            continue
        if not path.is_file():
            raise FileNotFoundError(f"缺少本地{labels[field]}文件：{path}")
        info = profile(path)
        matches = info['has_mtp'] if field == 'mtp' else info['role'] == field
        if not matches:
            actual = labels[info['role']] + ('（内嵌 MTP）' if info['role'] == 'model' and info['has_mtp'] else '')
            raise ValueError(f'{labels[field]}：{path.name} 是{actual}。请选择{labels[field]}文件。')
    if embedded and not profile(model)['has_mtp']:
        raise ValueError('主模型内嵌 MTP 需要 GGUF 包含 MTP 权重。请选择配套 MTP 文件或关闭 MTP。')
