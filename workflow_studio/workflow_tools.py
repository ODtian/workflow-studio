"""Map Pi tool arguments onto the Studio's existing editable parameters."""
from copy import deepcopy
from math import floor, sqrt
from pathlib import PurePosixPath
from uuid import uuid4

from h3_timeline import FPS, plan_timeline


def workflow_catalog(owner):
    images, h3 = [], []
    for session in owner.sessions.values():
        spec = session.state['spec']
        fields = {field['key'] for field in spec['fields']}
        entry = {'id': session.id, 'workflow': session.state['selected'], 'name': spec['name']}
        if spec.get('output') != 'text' and {'prompt', 'width', 'height'} <= fields:
            images.append(entry)
        if session.state['selected'] == 'minimax_h3.py':
            h3.append({**entry, 'segment_seconds': session.params['segment_seconds'],
                       'references': [{key: item[key] for key in ('id', 'name', 'kind')}
                                      for item in session.params.get('references', [])],
                       'loras': next(field['options'] for field in spec['fields'] if field['key'] == 'loras')})
    return {'images': images, 'h3': h3}


def _target(owner, workflow, *, h3=False):
    sessions = list(owner.sessions.values())
    if h3:
        sessions = [session for session in sessions if session.state['selected'] == 'minimax_h3.py']
    if workflow:
        sessions = [session for session in sessions if workflow in (session.id, session.state['selected'])]
    if len(sessions) != 1:
        raise ValueError('请使用工作流面板 ID 选择目标：' + ', '.join(session.id for session in sessions))
    session = sessions[0]
    if session.state['busy']:
        raise ValueError('目标工作流正在运行，请在完成后更新参数。')
    return session


def _publish(owner, session, patch):
    owner.save_settings(panels=[{'id': session.id, 'params': patch}])
    owner.publish()
    owner.send({'type': 'workflow_parameters', 'id': session.id, 'params': patch})


def set_image_workflow(owner, workflow, prompt, aspect_ratio):
    session = _target(owner, workflow)
    spec, params = session.state['spec'], session.params
    fields = {field['key'] for field in spec['fields']}
    if spec.get('output') == 'text' or not {'prompt', 'width', 'height'} <= fields:
        raise ValueError('请选择带提示词和宽高参数的生图工作流。')
    rw, rh = map(float, aspect_ratio.split(':'))
    if rw <= 0 or rh <= 0:
        raise ValueError('画面比例使用正数，格式如 16:9。')
    presets = spec.get('size_presets', {})
    wk, hk, step = presets.get('width_key', 'width'), presets.get('height_key', 'height'), presets.get('step', 16)
    area, ratio = float(params[wk]) * float(params[hk]), rw / rh
    # Match ResolutionControls: preserve pixel area and align to the workflow grid.
    width = max(step, floor(sqrt(area * ratio) / step + .5) * step)
    height = max(step, floor(sqrt(area / ratio) / step + .5) * step)
    patch = {'prompt': prompt, wk: width, hk: height}
    if 'output_type' in fields:
        patch['output_type'] = 'image'
    _publish(owner, session, patch)
    return {'panel_id': session.id, 'workflow': session.state['selected'], 'prompt': prompt,
            'aspect_ratio': aspect_ratio, 'width': width, 'height': height}


def set_h3_timeline(owner, segments, workflow=None):
    session = _target(owner, workflow, h3=True)
    params = deepcopy(session.params)
    segment_frames = round(float(params['segment_seconds']) * FPS)
    if not segments or segment_frames < 1:
        raise ValueError('请提供片段列表，并在 H3 工作流中设置每段时长。')
    duration = segment_frames / FPS
    references, loras = params.get('references', []), params.get('loras', [])
    for item in [*references, *loras]:
        item.setdefault('id', uuid4().hex)
    scopes = {(kind, item['id']): {'id': item['id'], 'kind': kind, 'segments': [],
                                 **({'weights': {}} if kind == 'lora' else {})}
              for kind, items in (('reference', references), ('lora', loras)) for item in items}

    def media(source):
        if 'id' in source:
            return next(item for item in references if item['id'] == source['id'])
        path, kind = source['path'], source['kind']
        existing = next((item for item in references if item.get('path') == path and item['kind'] == kind), None)
        return existing or {'id': uuid4().hex, 'name': source.get('name', PurePosixPath(path).name),
                            'kind': kind, 'path': path,
                            **({'include_audio': source.get('include_audio', False)} if kind == 'video' else {})}

    clips, guides = [], []
    old_timeline = params.get('timeline', {})
    old_clips = old_timeline.get('clips', [])
    allowed_loras = next(field['options'] for field in session.state['spec']['fields'] if field['key'] == 'loras')
    for index, segment in enumerate(segments):
        clip_id = old_clips[index]['id'] if index < len(old_clips) else uuid4().hex
        method = params.get('long_video', 'motion')
        clip = {'id': clip_id, 'name': segment.get('name', f'分段 {index+1}'), 'duration': duration,
                'prompt': segment['prompt'], 'method': 'tail_frame' if method == 'single' else method,
                'context_frames': int(params.get('context_frames', 22)),
                'audio_context_frames': int(params.get('audio_context_frames', 18)),
                'blend_frames': 6, 'audio': params.get('audio', True)}
        for key in ('method', 'context_frames', 'audio_context_frames', 'blend_frames', 'audio'):
            if key in segment:
                clip[key] = segment[key]
        clips.append(clip)
        for source in segment.get('references', []):
            item = media(source)
            if not any(existing['id'] == item['id'] for existing in references):
                references.append(item)
            scope = scopes.setdefault(('reference', item['id']), {'id': item['id'], 'kind': 'reference', 'segments': []})
            if clip_id not in scope['segments']:
                scope['segments'].append(clip_id)
        for selected in segment.get('loras', []):
            name, strength = selected['name'], float(selected.get('strength', 1))
            if name not in allowed_loras:
                raise ValueError('请选择 H3 模型列表中的 LoRA：' + name)
            item = next((item for item in loras if item['name'] == name), None)
            if item is None:
                item = {'id': uuid4().hex, 'name': name, 'strength': strength}
                loras.append(item)
            scope = scopes.setdefault(('lora', item['id']), {'id': item['id'], 'kind': 'lora', 'segments': [], 'weights': {}})
            if clip_id not in scope['segments']:
                scope['segments'].append(clip_id)
            scope['weights'][clip_id] = strength
        for anchor in segment.get('anchors', []):
            frame = round(float(anchor['time']) * FPS)
            if not 0 <= frame < segment_frames:
                raise ValueError(f'第 {index+1} 段锚点时间应位于 0 到 {duration} 秒之间。')
            guides.append({**media(anchor['source']), 'id': uuid4().hex,
                           'time': (index * segment_frames + frame) / FPS})
    timeline = {**old_timeline, 'version': 1, 'clips': clips, 'resources': list(scopes.values())}
    patch = {'output_type': 'video', 'timeline': timeline, 'duration': len(clips) * duration,
             'references': references, 'loras': loras, 'guides': guides, 'first_frame': '', 'last_frame': ''}
    # Validate through the same planner used by H3 inference before publishing.
    plan = plan_timeline({**params, **patch})
    _publish(owner, session, patch)
    return {'panel_id': session.id, 'workflow': session.state['selected'], 'segment_seconds': duration,
            'duration': patch['duration'], 'segments': [
                {'index': index+1, 'id': clip['id'], 'prompt': clip['prompt'], 'start': part['start']/FPS,
                 'duration': duration, 'references': [item['name'] for item in part['references']],
                 'loras': [{'name': item['name'], 'strength': item['strength']} for item in part['loras']]}
                for index, (clip, part) in enumerate(zip(clips, plan))], 'anchors': len(guides)}


def apply_workflow_tool(owner, name, arguments):
    return {'set_image_workflow': set_image_workflow, 'set_h3_timeline': set_h3_timeline}[name](owner, **arguments)
