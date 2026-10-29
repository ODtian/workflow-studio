"""Local parameter mapping and real Pi SDK/JSONL round-trip checks."""
from copy import deepcopy
import importlib
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'workflow_studio'), str(ROOT)]
from h3_timeline import plan_timeline
from workflow_tools import apply_workflow_tool


class Owner:
    def __init__(self):
        self.messages, self.saved, self.publications = [], [], 0
        self.sessions = {}
        self.add('image', 'moss_image.py', {
            'name': 'MOSS', 'size_presets': {'step': 16},
            'fields': [{'key': key} for key in ('prompt', 'width', 'height', 'steps')]},
            {'prompt': 'original image', 'width': 1024, 'height': 1024, 'steps': 50})
        self.add('h3', 'minimax_h3.py', {
            'name': 'H3', 'output': 'media',
            'fields': [{'key': key} for key in ('prompt', 'width', 'height')]
                      + [{'key': 'loras', 'options': ['style.safetensors']}]},
            {'prompt': 'a city', 'width': 768, 'height': 1344, 'duration': 2,
             'segment_seconds': 5, 'long_video': 'motion', 'context_frames': 22,
             'audio_context_frames': 18, 'audio': True,
             'references': [{'id': 'reference-a', 'kind': 'image', 'name': 'city.png', 'path': '/tmp/city.png'}],
             'loras': [], 'first_frame': '/tmp/old-first.png', 'last_frame': '/tmp/old-last.png',
             'guides': [{'id': 'old-anchor', 'time': 1}],
             'timeline': {'version': 1, 'clips': [{'id': 'old-clip', 'duration': 2}],
                          'resources': [], 'layout': {'inspector_width': 300}}})

    def add(self, id, workflow, spec, params):
        session = SimpleNamespace(id=id, owner=self, params=params,
                                  state={'selected': workflow, 'spec': spec, 'busy': False, 'params': params})
        session.update = lambda **values: session.state.update(values)
        self.sessions[id] = session
        return session

    def save_settings(self, panels):
        self.saved.append(deepcopy(panels))
        for item in panels:
            session = self.sessions[item['id']]
            session.params = {**session.params, **item['params']}
            session.state['params'] = session.params

    def publish(self):
        self.publications += 1

    def send(self, message):
        self.messages.append(deepcopy(message))


class WorkflowToolTests(unittest.TestCase):
    def test_image_updates_only_target_parameters(self):
        owner = Owner()
        h3_before = deepcopy(owner.sessions['h3'].params)
        result = apply_workflow_tool(owner, 'set_image_workflow', {
            'workflow': 'image', 'prompt': 'A sunlit mountain landscape', 'aspect_ratio': '16:9'})
        self.assertEqual((result['width'], result['height']), (1360, 768))
        self.assertEqual(owner.sessions['image'].params['steps'], 50)
        self.assertEqual(owner.sessions['h3'].params, h3_before)
        self.assertEqual(owner.messages[-1]['type'], 'workflow_parameters')
        self.assertEqual(owner.messages[-1]['params']['prompt'], 'A sunlit mountain landscape')

    def test_h3_segments_resources_anchors_and_length(self):
        owner = Owner()
        result = apply_workflow_tool(owner, 'set_h3_timeline', {'segments': [
            {'prompt': 'An adult walks into the city', 'references': [{'id': 'reference-a'}],
             'loras': [{'name': 'style.safetensors', 'strength': .6}],
             'anchors': [{'time': 0, 'source': {'id': 'reference-a'}}]},
            {'prompt': 'The adult enters a cafe',
             'references': [{'path': '/tmp/cafe.mp4', 'kind': 'video', 'include_audio': True}],
             'loras': [{'name': 'style.safetensors', 'strength': 1.2}],
             'anchors': [{'time': 1, 'source': {'path': '/tmp/door.png', 'kind': 'image'}}]},
            {'prompt': 'A wide view of the skyline', 'audio': False}]})
        params = owner.sessions['h3'].params
        plan = plan_timeline(params)
        self.assertEqual(result['duration'], 15)
        self.assertEqual([clip['duration'] for clip in params['timeline']['clips']], [5, 5, 5])
        self.assertEqual([part['start'] for part in plan], [0, 120, 240])
        self.assertEqual([guide['time'] for guide in params['guides']], [0, 6])
        self.assertEqual([part['loras'][0]['strength'] for part in plan[:2]], [.6, 1.2])
        self.assertEqual(plan[0]['references'][0]['id'], 'reference-a')
        self.assertTrue(plan[1]['references'][0]['include_audio'])
        self.assertEqual(plan[2]['references'], [])
        self.assertFalse(plan[2]['audio'])
        self.assertEqual(params['timeline']['layout'], {'inspector_width': 300})
        self.assertEqual((params['first_frame'], params['last_frame']), ('', ''))
        apply_workflow_tool(owner, 'set_h3_timeline', {'segments': [{'prompt': 'A quiet square'}]})
        self.assertEqual(owner.sessions['h3'].params['duration'], 5)
        self.assertEqual(len(owner.sessions['h3'].params['timeline']['clips']), 1)
        self.assertEqual(owner.sessions['h3'].params['guides'], [])

    def test_real_pi_sdk_and_python_jsonl_round_trip(self):
        owner = Owner()
        pi_panel = owner.add('pi-test', 'llama_cpp.py', {'name': 'Pi', 'output': 'text', 'fields': []}, {})
        native_requests = []

        def native_model(values, ctx):
            native_requests.append(values)
            names = {tool['function']['name'] for tool in values['tools']}
            self.assertTrue({'set_image_workflow', 'set_h3_timeline'} <= names)
            if len(native_requests) == 1:
                ctx.tool_calls([
                    {'id': 'image-call', 'name': 'set_image_workflow', 'arguments': {
                        'workflow': 'image', 'prompt': 'A mountain lake', 'aspect_ratio': '3:4'}},
                    {'id': 'h3-call', 'name': 'set_h3_timeline', 'arguments': {
                        'segments': [{'prompt': 'An adult waves'}, {'prompt': 'The adult smiles'}]}}])
            else:
                ctx.response('Parameters updated.', final=True)
                ctx.tool_calls([])
            ctx.metadata(输出tokens=10, 输入tokens=100)

        store = {'pi_preferences': {pi_panel.id: {'saved_tools': ['read']}}}
        workspace = ModuleType('workspace_store')
        workspace.read = lambda: deepcopy(store)
        workspace.edit = lambda update: update(store)
        llama = ModuleType('llama_runner')
        llama.run_llama = native_model
        marimo = ModuleType('marimo')
        marimo.Thread = threading.Thread
        with tempfile.TemporaryDirectory(prefix='pi-workflow-tools-') as directory, patch.dict(
                os.environ, {'WORKFLOW_WORKSPACE': directory, 'WORKFLOW_GZIP_CONTENT': '1'}), patch.dict(
                sys.modules, {'llama_runner': llama, 'workspace_store': workspace, 'marimo': marimo}):
            sys.modules.pop('pi_runner', None)
            runner = importlib.import_module('pi_runner')
            ctx = SimpleNamespace(panel=pi_panel, cancel=threading.Event(),
                                  check_cancelled=lambda: None, status=lambda message: None,
                                  metadata=lambda **values: None)
            params = {'model': 'local-test-model', 'n_ctx': 32768, 'max_tokens': 512,
                      'thinking': 'off', 'system_prompt': 'Update workflow parameters.',
                      'pi_request': {'action': 'prompt', 'text': 'Set an image and two video segments.'}}
            pi_panel.params = params
            try:
                result = runner.run_pi(params, ctx)
                self.assertEqual(result, 'Parameters updated.')
                self.assertEqual(owner.sessions['image'].params['prompt'], 'A mountain lake')
                self.assertEqual(owner.sessions['h3'].params['duration'], 10)
                self.assertEqual([clip['prompt'] for clip in owner.sessions['h3'].params['timeline']['clips']],
                                 ['An adult waves', 'The adult smiles'])
                self.assertEqual([message['type'] for message in owner.messages].count('workflow_parameters'), 2)
                self.assertEqual(store['pi_preferences'][pi_panel.id]['workflow_tools_version'], 1)
                self.assertIn('set_image_workflow', store['pi_preferences'][pi_panel.id]['saved_tools'])
                self.assertEqual(len(native_requests), 2)
            finally:
                if runner._client:
                    runner._client.close()
                    runner._client.process.wait(timeout=10)
                    runner._client = None


if __name__ == '__main__':
    unittest.main()
