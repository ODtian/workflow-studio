"""Bounded ordered range reads; the caller retains checksum and atomic publish."""
from concurrent.futures import ThreadPoolExecutor

def download(provider, file_id, stream, size, progress, cancel):
    from transfer_core import CHUNK, TransferError, cancelled
    request = provider.service.files().get_media(fileId=file_id,supportsAllDrives=True)
    uri = request.uri
    def fetch(start):
        end = min(size-1,start+CHUNK-1)
        for attempt in range(3):
            cancelled(cancel)
            try:
                response, block = provider._thread_http().request(uri,method='GET',headers={
                    'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'})
                status = int(response.status)
                expected = f'bytes {start}-{end}/{size}'
                if status == 206 and response.get('content-range','') == expected and len(block) == end-start+1:
                    return block
                if start == 0 and end == size-1 and status == 200 and len(block) == size:
                    return block
                if status not in (429,500,502,503,504):
                    raise TransferError('Drive 分段响应校验失败')
            except TransferError: raise
            except Exception:
                if attempt == 2: raise TransferError('Drive 分段下载中断，请重试') from None
            if cancel.wait(.5*(attempt+1)): cancelled(cancel)
        raise TransferError('Drive 分段下载暂时繁忙，请重试')
    if size == 0: progress(0); return
    starts = iter(range(0,size,CHUNK))
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix='drive-range') as workers:
        pending = []
        try:
            for _ in range(3):
                start = next(starts,None)
                if start is not None: pending.append(workers.submit(fetch,start))
            count = 0
            while pending:
                cancelled(cancel)
                block = pending.pop(0).result()
                cancelled(cancel)
                stream.write(block); count += len(block); progress(count)
                start = next(starts,None)
                if start is not None: pending.append(workers.submit(fetch,start))
            if count != size: raise TransferError('Drive 下载大小校验失败')
        finally:
            for future in pending: future.cancel()
