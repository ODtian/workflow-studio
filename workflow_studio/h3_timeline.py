"""Resolve the editable timeline into H3 sampling calls and per-segment resources."""
FPS = 24
MAX_FRAMES = 362
CONTEXT_GRID = (124, 107, 90, 73, 56, 39, 22, 5, 1)


def sampling_frames(frames):
    return max(5, frames) + (5 - max(5, frames)) % 17


def plan_timeline(params):
    timeline = params['timeline']
    resources = {(item['kind'], item['id']): item for item in timeline['resources']}
    segments, start = [], 0
    for index, clip in enumerate(timeline['clips']):
        frames = round(float(clip['duration']) * FPS)
        method = clip['method']
        carry = 0
        if index and method == 'tail_frame':
            carry = 1
        elif index and method in ('motion', 'overlap'):
            available = min(int(clip['context_frames']), segments[-1]['frames'])
            carry = next(value for value in CONTEXT_GRID if value <= available)
        sample = sampling_frames(frames + carry)
        if sample > MAX_FRAMES:
            raise ValueError(f'第 {index+1} 段实际计算 {sample} 帧，单次窗口上限为 {MAX_FRAMES} 帧')
        selected = {}
        for kind, key in (('reference', 'references'), ('lora', 'loras')):
            selected[key] = []
            for item in params.get(key, []):
                scope = resources[kind, item['id']]
                if clip['id'] in scope['segments']:
                    value = dict(item)
                    if kind == 'lora':
                        value['strength'] = float(scope['weights'].get(clip['id'], item['strength']))
                    selected[key].append(value)
        segments.append({
            'id': clip['id'], 'start': start, 'frames': frames, 'sample_frames': sample,
            'carry': carry, 'padding': sample - carry - frames, 'method': method,
            'prompt': clip.get('prompt', params['prompt']),
            'continuation': 'motion' if carry and method in ('motion', 'overlap') else 'tail' if carry else 'none',
            'audio_context_frames': int(clip.get('audio_context_frames', 18)),
            'blend_frames': min(frames, int(clip.get('blend_frames', 6))) if carry and method == 'overlap' else 0,
            'audio': bool(clip.get('audio', params.get('audio', True))), **selected,
        })
        start += frames
    return segments
