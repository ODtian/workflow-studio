"""Prepare previews off the inference thread and send each frame once."""
from collections import deque
import io
from pathlib import Path
import threading
import time

import anywidget
from PIL import Image
from content_store import open_image, read_bytes


def jpeg(image, *, final=False):
    if isinstance(image, (str, Path)):
        image = open_image(image)
    image = image.convert('RGB')
    image.thumbnail((1280, 1280) if final else (512, 512))
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=80 if final else 60, optimize=True)
    return memoryview(buffer.getvalue())


class WidgetTransport:
    def __init__(self, owner):
        self.owner = owner
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.preview_ready = threading.Event()
        self.closed = False
        self.attributes = {}
        self.payloads = {}
        self.latest = {}
        self.messages = deque()
        self.frames = {}
        self.jobs = {}
        self.last_error = None
        self.sent_frames = 0
        self.sent_preview_bytes = 0
        self.sender = threading.Thread(target=self._send, daemon=True)
        self.encoder = threading.Thread(target=self._encode, daemon=True)
        self.sender.start()
        self.encoder.start()

    def attribute(self, name, value):
        with self.lock:
            self.attributes[name] = value
        self.ready.set()

    def payload(self, name, panel_id, value):
        with self.lock:
            self.payloads[name, panel_id] = value
        self.ready.set()

    def send(self, content, buffers=None):
        with self.lock:
            if content.get('type') in ('image_progress', 'chat_delta'):
                self.latest[content['type'], content['id']] = content, buffers
            else:
                self.messages.append((content, buffers))
        self.ready.set()

    def preview(self, panel_id, source, *, video=False, final=False, run_id=None, started=None, response=None):
        with self.lock:
            self.jobs[panel_id, response['request'] if response else None] = source, video, final, run_id, started, response
        self.preview_ready.set()

    def _encode(self):
        while True:
            self.preview_ready.wait()
            with self.lock:
                self.preview_ready.clear()
                if self.closed:
                    return
                jobs, self.jobs = self.jobs, {}
            for (panel_id, request), (source, video, final, run_id, started, response) in jobs.items():
                session = self.owner.sessions.get(panel_id)
                if session is None or run_id and session.state.get('run_id') != run_id:
                    continue
                try:
                    data = memoryview(read_bytes(source)) if video else jpeg(source, final=final)
                except Exception as error:
                    self.last_error = str(error)
                    continue
                frame = {'type': 'preview_frame', 'id': panel_id, 'run_id': run_id, 'final': final,
                         'mime': 'video/mp4' if video else 'image/jpeg',
                         'server_ms': round((time.monotonic() - started) * 1000) if started else 0}
                if response:
                    frame.update(response)
                with self.lock:
                    if run_id and session.state.get('run_id') != run_id:
                        continue
                    self.frames[panel_id, request] = frame, [data]
                self.ready.set()

    def _send(self):
        while True:
            self.ready.wait()
            with self.lock:
                self.ready.clear()
                if self.closed:
                    return
                attributes, self.attributes = self.attributes, {}
                payloads, self.payloads = self.payloads, {}
                messages, self.messages = self.messages, deque()
                latest, self.latest = self.latest, {}
                frames, self.frames = self.frames, {}
            for name, value in attributes.items():
                setattr(self.owner, name, value)
            grouped = {}
            for (name, panel_id), value in payloads.items():
                grouped.setdefault(name, dict(getattr(self.owner, name)))[panel_id] = value
            for name, value in grouped.items():
                setattr(self.owner, name, value)
            for content, buffers in [*messages, *latest.values(), *frames.values()]:
                anywidget.AnyWidget.send(self.owner, content, buffers=buffers)
                if content.get('type') == 'preview_frame':
                    self.sent_frames += 1
                    self.sent_preview_bytes += sum(len(buffer) for buffer in buffers)

    def close(self):
        with self.lock:
            self.closed = True
            self.jobs.clear()
            self.frames.clear()
            self.messages.clear()
        self.ready.set()
        self.preview_ready.set()
