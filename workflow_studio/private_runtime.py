"""Run the original Studio backend behind the encrypted widget boundary."""
from pathlib import Path

from panel import WorkflowPanel
from persistent_drive_auth import (
    DriveAuthorization, _credentials_from_info, _validated_info, connect_from_secrets,
)


class WorkspaceDriveCache:
    def load(self):
        import workspace_store
        info = workspace_store.read().get('drive_authorization')
        return _credentials_from_info(info) if info else None

    def save(self, credentials):
        import workspace_store
        info = _validated_info(credentials.to_json())
        workspace_store.edit(lambda state: state.update(drive_authorization=info))


def connect_private_drive():
    from googleapiclient.discovery import build
    from transfer_core import GoogleDriveProvider
    service = connect_from_secrets(cache=WorkspaceDriveCache(), service_factory=lambda credentials:
        build('drive', 'v3', credentials=credentials, cache_discovery=False))
    return GoogleDriveProvider(service) if service is not None else None


class EncryptedWorkflowPanel(WorkflowPanel):
    authorization_storage = '授权随工作台密码加密保存，解锁后自动重连。'

    def __init__(self, private_owner, saved, **options):
        self.private_owner = private_owner
        self.store = private_owner.store
        initial = list(saved.get('panels', []))
        if not saved.get('full_studio'):
            selected = {item['workflow'] for item in initial}
            initial = [{'workflow': name} for name in ('moss_image.py', 'minimax_h3.py', 'llama_cpp.py')
                       if name not in selected] + initial
        super().__init__(initial=initial, **options)
        self.state = {**self.state, 'password_protected': True}

    def _message(self, widget, content, buffers):
        # This internal widget receives commands only through its owner's
        # authenticated, encrypted transport.
        return

    def send(self, content, buffers=None):
        self.private_owner.send(content, buffers or ())

    def _send_widget_message(self, content, buffers=None):
        self.private_owner.send(content, buffers or ())

    def create_files_bridge(self):
        from files_bridge import FilesBridge
        return FilesBridge(self, provider_factory=connect_private_drive,
            authorization_factory=lambda: DriveAuthorization(cache=WorkspaceDriveCache()))

    def load(self, name):
        if name in self.private_owner._sources:
            return self.private_owner.load(name)
        return super().load(name)

    def refresh(self):
        super().refresh()
        available = {item['id'] for item in self.state['workflows']}
        private = [{'id': name, 'name': self.load(name).SPEC['name'],
                    'description': self.load(name).SPEC.get('description', '')}
                   for name in self.private_owner._sources if name not in available]
        self.state = {**self.state, 'workflows': self.state['workflows'] + private}
        self.publish()

    def add(self, workflow_id, params=None, session_id=None, activate=True):
        from private_probe import PrivateWorkflowSession
        session = PrivateWorkflowSession(self, workflow_id, params, session_id=session_id)
        self.sessions[session.id] = session
        if activate or not self.state['active']:
            self.state = {**self.state, 'active': session.id}
        self.save_settings()
        self.publish()
        return session

    def save_settings(self, *args, **kwargs):
        super().save_settings(*args, **kwargs)
        self.private_owner._save_workflow_vault(self)

    def receive(self, content, buffers=()):
        action = content['action']
        if action == 'import':
            name = Path(content['name']).name
            self.private_owner._load_source(name, content['source'])
            self.private_owner._sources[name] = content['source']
            self.refresh()
            self.add(name)
        elif action == 'export' and self.sessions[content['id']].state['selected'] in self.private_owner._sources:
            name = self.sessions[content['id']].state['selected']
            self.send({'type': 'workflow', 'name': name, 'source': self.private_owner._sources[name]})
        else:
            WorkflowPanel._message(self, self, content, buffers)


def open_runtime(private_owner, saved):
    from content_store import use_encryption
    use_encryption(private_owner._key)
    from studio_bootstrap import get_studio
    return get_studio(workspace=private_owner.directory.parent,
        panel_factory=lambda **options: EncryptedWorkflowPanel(private_owner, saved, **options))
