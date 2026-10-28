"""Editable durable copy recipes; every replay uses current guarded entries."""
import hashlib
import os
from pathlib import Path
import re
import time
import uuid
import workspace_store as store

def remember(controller, source, target):
    local=target if source.pane=='drive' else source
    remote=source if source.pane=='drive' else target
    path=str(controller.local_roots['root'].joinpath(*local.parts))
    direction='download' if source.pane=='drive' else 'upload'
    key=(direction,remote.remote_id,path)
    def save(state):
        old=next((r for r in state['copies'] if (r['direction'],r['drive_id'],r['local_path'])==key),None)
        if old is None:
            old={'id':uuid.uuid4().hex,'label':source.name,'direction':direction,
                 'drive_id':remote.remote_id,'local_path':path,'enabled':True,'name':source.name}
            state['copies'].append(old)
        old['source_kind']=source.kind
        return old['id']
    return store.edit(save)

def drive_id(value):
    value=str(value).strip()
    if value.startswith('https://drive.google.com/'):
        match=re.search(r'/(?:d|folders)/([A-Za-z0-9_-]+)',value) or re.search(r'[?&]id=([A-Za-z0-9_-]+)',value)
        value=match.group(1) if match else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',value): raise ValueError('请填写 Drive 文件或目录链接')
    return value

def save_recipe(value):
    from transfer_core import safe_local_path
    path=Path(str(value.get('local_path','')).strip())
    if not path.is_absolute(): raise ValueError('服务器路径需要以 / 开头')
    safe_local_path(path)
    direction=value.get('direction')
    if direction not in ('download','upload'): raise ValueError('请选择复制方向')
    remote=drive_id(value.get('drive_id',''))
    label=str(value.get('label','')).strip()[:230]
    if not label: raise ValueError('请填写记录名称')
    def save(state):
        old=next((r for r in state['copies'] if r['id']==value.get('id')),None)
        if old is None:
            old={'id':uuid.uuid4().hex}
            state['copies'].append(old)
        old.update(label=label,direction=direction,drive_id=remote,local_path=str(path),enabled=bool(value.get('enabled',True)),source_kind=value.get('source_kind','file'))
    store.edit(save)

def remote_entry(controller, file_id, kind):
    from transfer_core import Entry, FOLDER, TransferError, MAX_BYTES
    controller._connected()
    meta=controller.provider.metadata(file_id)
    if kind=='directory':
        return controller._resolve_bookmark(Entry('drive','saved',(),'directory','',remote_id=file_id))
    if (meta.get('mimeType','').startswith('application/vnd.google-apps.')
            or meta.get('capabilities',{}).get('canDownload') is not True or meta.get('trashed') is not False):
        raise TransferError('该 Drive 文件需要下载权限')
    parents=meta.get('parents',[])
    if len(parents)!=1: raise TransferError('Drive 文件需要位于可访问目录')
    parent=controller._resolve_bookmark(Entry('drive','saved',(),'directory','',remote_id=parents[0]))
    size=int(meta.get('size',0))
    if not 0<=size<=MAX_BYTES: raise TransferError('文件大小超出范围')
    return Entry('drive','root',parent.parts+(meta['name'],),'file',meta['name'],file_id,size,chain=parent.chain+(file_id,))

def resolve(controller, recipe):
    from transfer_core import Entry, directory_fd, local_file, fingerprint, safe_local_path, safe_parts
    path=safe_local_path(Path(recipe['local_path']))
    parts=path.relative_to(controller.local_roots['root']).parts
    safe_parts(parts)
    if recipe['direction']=='download':
        source=remote_entry(controller,recipe['drive_id'],recipe.get('source_kind','file'))
        # Explicitly edited destination paths may create directories beneath a
        # verified existing ancestor. Each component is opened without symlinks.
        parent=controller.local_roots['root']
        for part in parts:
            with directory_fd(parent) as fd:
                try: os.mkdir(part,dir_fd=fd)
                except FileExistsError: pass
            parent=parent/part
        with directory_fd(path): pass
        target=Entry('local','root',parts,'directory',path.name)
    else:
        if recipe.get('source_kind')=='directory':
            with directory_fd(path): pass
            source=Entry('local','root',parts,'directory',path.name)
        else:
            with local_file(controller.local_roots['root'],parts) as (stream, info):
                pass
            source=Entry('local','root',parts,'file',path.name,size=info.st_size,fp=fingerprint(info))
        target=remote_entry(controller,recipe['drive_id'],'directory')
    return source,target

def replay(controller, ids, *, skip_existing=True):
    from transfer_core import local_file, checksum_matches, TransferError
    selected=[r for r in store.read()['copies'] if r['id'] in ids and r.get('enabled',True)]
    if not selected: raise ValueError('请选择复制记录')
    skipped=0
    for recipe in selected:
        while True:
            with controller.lock:
                if controller.closed: raise ValueError('复制会话已结束')
                active=sum(t['status'] in ('queued','running') for t in controller.tasks)
            if active<16: break
            time.sleep(.3)
        source,target=resolve(controller,recipe)
        if source.kind=='file' and skip_existing and recipe['direction']=='download':
            meta=controller._validate_drive(source)
            try:
                with local_file(controller.local_roots['root'],target.parts+(source.name,)) as (stream, info):
                    size=info.st_size
                    if size==source.size:
                        md5,sha=hashlib.md5(),hashlib.sha256()
                        while block:=stream.read(8*1024*1024): md5.update(block);sha.update(block)
                        if checksum_matches(meta,size,md5.hexdigest(),sha.hexdigest()):
                            skipped+=1
                            continue
            except TransferError: pass
        controller._enqueue({'entry_ids':[controller._register(source)],'target_id':controller._register(target)})
    return f'已加入复制队列；{skipped} 个完整文件已复用。' if skipped else '已加入复制队列。'
