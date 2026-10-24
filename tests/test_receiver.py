"""通用收件使用合成更新、假 API 與獨立暫存目錄驗收。"""
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

import tg_receiver as receiver


class FakeApi:
    def __init__(self, data):
        self.data = data
        self.downloads = []

    def download(self, file_id):
        self.downloads.append(file_id)
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def update(ident=10, *, name='document.pdf', user=123, kind='pdf', chat_type='private'):
    item = {'file_id': 'synthetic-file', 'file_name': name,
            'mime_type': 'application/pdf' if kind == 'pdf' else 'image/png'}
    return {'update_id': ident, 'message': {'message_id': ident + 100,
            'chat': {'id': user, 'type': chat_type}, 'from': {'id': user}, 'document': item}}


def make_receiver(tmp_path, data=b'%PDF-1.7\nsynthetic', mode='original', **kwargs):
    return receiver.Receiver(tmp_path / 'state', tmp_path / 'files', FakeApi(data), {123}, 777,
                             image_mode=mode, **kwargs)


def events(worker):
    result = []
    worker.dispatch_events(result.append)
    return result


def png():
    output = io.BytesIO()
    Image.new('RGBA', (4, 3), (0, 0, 0, 0)).save(output, format='PNG')
    return output.getvalue()


def test_pdf_saved_byte_for_byte_with_durable_event_and_offset(tmp_path):
    worker = make_receiver(tmp_path)
    worker.ingest([update()])
    assert worker.offset == 11
    worker.process()
    event, = events(worker)
    assert event['schema'] == 'tg.received_file.v1' and event['event_id'] == '777:10'
    assert event['kind'] == 'pdf' and event['jpeg_path'] is None
    assert Path(event['path']).read_bytes() == worker.api.data
    assert event['sha256'] == hashlib.sha256(worker.api.data).hexdigest()
    assert Path(event['path']).stat().st_mode & 0o777 == 0o600
    worker.db.close()
    reopened = make_receiver(tmp_path)
    reopened.ingest([update()])
    reopened.process()
    assert reopened.offset == 11 and events(reopened) == [] and reopened.api.downloads == []


@pytest.mark.parametrize('user,chat_type', [(456, 'private'), (123, 'group')])
def test_unapproved_sender_or_group_never_downloads(tmp_path, user, chat_type):
    worker = make_receiver(tmp_path)
    worker.ingest([update(user=user, chat_type=chat_type)])
    worker.process()
    assert worker.offset == 11 and worker.api.downloads == [] and events(worker) == []


def test_image_original_mode_preserves_bytes_without_conversion(tmp_path, monkeypatch):
    data = png()
    worker = make_receiver(tmp_path, data)
    monkeypatch.setattr(receiver, 'convert_jpeg', lambda *_: pytest.fail('原檔模式不應轉檔'))
    worker.ingest([update(kind='image', name='sample.png')])
    worker.process()
    event, = events(worker)
    assert Path(event['path']).read_bytes() == data and event['jpeg_path'] is None


def test_jpeg_mode_keeps_original_and_adds_rgb_jpeg(tmp_path):
    data = png()
    worker = make_receiver(tmp_path, data, 'jpeg')
    worker.ingest([update(kind='image', name='sample.png')])
    worker.process()
    event, = events(worker)
    assert Path(event['path']).read_bytes() == data
    with Image.open(event['jpeg_path']) as image:
        assert image.format == 'JPEG' and image.mode == 'RGB' and image.size == (4, 3)
        assert image.getpixel((0, 0)) == (255, 255, 255)
    assert event['image']['frames'] == 1


def test_pdf_never_converted_even_when_image_mode_is_jpeg(tmp_path, monkeypatch):
    worker = make_receiver(tmp_path, mode='jpeg')
    monkeypatch.setattr(receiver, 'convert_jpeg', lambda *_: pytest.fail('PDF 不應轉 JPG'))
    worker.ingest([update()])
    worker.process()
    event, = events(worker)
    assert event['jpeg_path'] is None and Path(event['path']).suffix == '.pdf'


def test_failed_image_conversion_still_delivers_original(tmp_path):
    worker = make_receiver(tmp_path, b'not a decodable image', 'jpeg')
    worker.ingest([update(kind='image', name='damaged.png')])
    worker.process()
    event, = events(worker)
    assert Path(event['path']).read_bytes() == b'not a decodable image'
    assert event['conversion_error'] == 'jpeg_conversion_failed_original_preserved'


@pytest.mark.parametrize('data', [b'not a PDF', b'%PDF-' + b'x' * receiver.MAX_BYTES])
def test_invalid_pdf_or_oversize_is_rejected_without_event(tmp_path, data):
    worker = make_receiver(tmp_path, data)
    worker.ingest([update()])
    worker.process()
    assert events(worker) == [] and list(worker.destination.iterdir()) == []


def test_download_failure_can_resume_from_saved_offset(tmp_path):
    worker = make_receiver(tmp_path, receiver.ApiError())
    worker.ingest([update()])
    worker.process()
    assert worker.offset == 11 and events(worker) == []
    worker.db.close()
    resumed = make_receiver(tmp_path)
    resumed.db.execute('UPDATE jobs SET retry_at=0')
    resumed.db.commit()
    resumed.process()
    assert len(events(resumed)) == 1


def test_download_rate_limit_persists_full_required_wait(tmp_path, monkeypatch):
    worker = make_receiver(tmp_path, receiver.ApiError(429, 1200))
    worker.ingest([update()])
    monkeypatch.setattr(receiver.time, 'time', lambda: 100)
    worker.process()
    row = worker.db.execute('SELECT retry_at FROM jobs').fetchone()
    assert row['retry_at'] == 1300
    worker.process()
    assert worker.api.downloads == ['synthetic-file']


def test_pending_spool_resumes_without_redownload(tmp_path, monkeypatch):
    worker = make_receiver(tmp_path)
    worker.ingest([update()])
    publish = receiver.publish
    monkeypatch.setattr(receiver, 'publish', lambda *_: (_ for _ in ()).throw(OSError()))
    worker.process()
    assert len(worker.api.downloads) == 1
    monkeypatch.setattr(receiver, 'publish', publish)
    worker.api.data = AssertionError('不應重新下載')
    worker.db.execute('UPDATE jobs SET retry_at=0')
    worker.db.commit()
    worker.process()
    assert len(events(worker)) == 1 and len(worker.api.downloads) == 1


def test_personal_handler_failure_retains_same_event_for_retry(tmp_path):
    worker = make_receiver(tmp_path)
    worker.ingest([update()])
    worker.process()
    worker.dispatch_events(lambda _: (_ for _ in ()).throw(RuntimeError('synthetic handler failure')))
    event, = events(worker)
    assert event['event_id'] == '777:10' and events(worker) == []


def test_same_name_conflict_never_overwrites_existing_data(tmp_path):
    worker = make_receiver(tmp_path)
    incoming = update(name='../../unsafe.pdf')
    name = receiver.filename(incoming['message'], 'pdf', '../../unsafe.pdf')
    assert '/' not in name and '\\' not in name
    target = worker.destination / name
    target.write_bytes(b'keep existing file')
    worker.ingest([incoming])
    worker.process()
    assert target.read_bytes() == b'keep existing file' and events(worker) == []


def test_existing_state_cannot_switch_bot_or_destination(tmp_path):
    worker = make_receiver(tmp_path)
    worker.db.close()
    with pytest.raises(receiver.ReceiverError, match='綁定'):
        receiver.Receiver(tmp_path / 'state', tmp_path / 'other', FakeApi(b''), {123}, 777)


def test_sqlite_symlink_is_rejected(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    (state / 'receiver.sqlite3').symlink_to(tmp_path / 'other.sqlite3')
    with pytest.raises(receiver.ReceiverError, match='symlink'):
        make_receiver(tmp_path)
    assert not (tmp_path / 'other.sqlite3').exists()


def test_first_interactive_choice_is_persisted_and_explicit_mode_can_change_it(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    assert receiver.select_mode(state, interactive=True, ask=lambda _: 'y') == 'jpeg'
    assert receiver.select_mode(state, interactive=True, ask=lambda _: pytest.fail('不應重問')) == 'jpeg'
    assert receiver.select_mode(state, 'original') == 'original'


def test_noninteractive_default_preserves_original(tmp_path):
    assert receiver.select_mode(tmp_path, ask=lambda _: pytest.fail('非互動不可詢問')) == 'original'


def test_missing_sqlite_stops_before_settings_or_network(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(receiver, 'sqlite3', None)
    state = tmp_path / 'state'
    assert receiver.main(['--destination', str(tmp_path / 'files'), '--state-dir', str(state),
                          '--allowed-user', '123', '--once']) == 2
    assert 'sqlite3' in capsys.readouterr().err and not state.exists()


def test_receiver_credentials_use_registered_route_without_chat_dependency(tmp_path):
    from tg_settings import register_route
    path = tmp_path / 'notifications.env'
    path.write_text('')
    path.chmod(0o600)
    register_route(path, 'PERSONAL', '123456789:' + 'x' * 35, 123, {'DEFAULT'})
    assert receiver.credentials(path, 'personal') == '123456789:' + 'x' * 35


def test_api_error_never_exposes_token(monkeypatch):
    import requests
    monkeypatch.setattr(receiver.requests, 'post', lambda *a, **k: (_ for _ in ()).throw(requests.ReadTimeout('secret url')))
    with pytest.raises(receiver.ApiError) as result:
        receiver.Telegram('synthetic-private-token').call('getMe')
    assert 'synthetic-private-token' not in str(result.value) and 'secret url' not in str(result.value)


def test_cli_once_receives_pdf_and_outputs_personal_integration_event(tmp_path, monkeypatch, capsys):
    class Api(FakeApi):
        def call(self, method, **kwargs):
            if method == 'getMe':
                return {'id': 777}
            if method == 'getWebhookInfo':
                return {'url': ''}
            assert method == 'getUpdates' and kwargs['offset'] == 0
            return [update()]
    monkeypatch.setattr(receiver, 'Telegram', lambda _: Api(b'%PDF-1.7\noriginal'))
    monkeypatch.setattr(receiver, 'credentials', lambda *_: 'synthetic')
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'xdg'))
    monkeypatch.setattr(receiver.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda: '')
    code = receiver.main(['--destination', str(tmp_path / 'files'), '--state-dir', str(tmp_path / 'state'),
                          '--allowed-user', '123', '--json-events', '--once'])
    captured = capsys.readouterr()
    event = json.loads(captured.out)
    assert '另存 JPG' in captured.err
    assert code == 0 and event['kind'] == 'pdf' and event['event_id'] == '777:10'
    assert Path(event['path']).read_bytes() == b'%PDF-1.7\noriginal'


def test_cli_existing_webhook_stops_before_polling(tmp_path, monkeypatch, capsys):
    class Api:
        def call(self, method, **kwargs):
            if method == 'getMe':
                return {'id': 777}
            assert method == 'getWebhookInfo'
            return {'url': 'https://example.invalid/existing'}
    monkeypatch.setattr(receiver, 'Telegram', lambda _: Api())
    monkeypatch.setattr(receiver, 'credentials', lambda *_: 'synthetic')
    assert receiver.main(['--destination', str(tmp_path / 'files'), '--state-dir', str(tmp_path / 'state'),
                          '--allowed-user', '123', '--non-interactive', '--once']) == 2
    assert 'webhook' in capsys.readouterr().err and not (tmp_path / 'files').exists()


def test_cli_without_destination_saves_inside_project_from_other_working_directory(tmp_path, monkeypatch, capsys):
    project = tmp_path / 'project'
    elsewhere = tmp_path / 'elsewhere'
    home = tmp_path / 'synthetic-home'
    state = home / '.local/state/telegram-bot-setup/receiver'
    project.mkdir()
    elsewhere.mkdir()
    class Api(FakeApi):
        def call(self, method, **kwargs):
            if method == 'getMe':
                return {'id': 777}
            if method == 'getWebhookInfo':
                return {'url': ''}
            assert method == 'getUpdates'
            return [update()]
    monkeypatch.setattr(receiver, 'ROOT', project)
    monkeypatch.setattr(receiver, 'Telegram', lambda _: Api(b'%PDF-1.7\noriginal'))
    monkeypatch.setattr(receiver, 'credentials', lambda *_: 'synthetic')
    # 預設狀態與帳號鎖分別隔離，避免重跑沿用其他目的地的綁定。 / Isolate default state and account locks across runs.
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.delenv('TG_CONFIG_STATE_DIR', raising=False)
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'xdg'))
    monkeypatch.chdir(elsewhere)
    assert receiver.main(['--allowed-user', '123', '--non-interactive', '--json-events', '--once']) == 0
    event = json.loads(capsys.readouterr().out)
    assert Path(event['path']).parent == project / 'received'
    assert Path(event['path']).read_bytes() == b'%PDF-1.7\noriginal'
    assert not (elsewhere / 'received').exists()
    assert (state / 'receiver.sqlite3').is_file()
    assert not (project / '.state').exists()


@pytest.mark.parametrize('chunks,size,expected', [
    ([b'abc', b'def'], 6, b'abcdef'),
    ([b'abc'], 6, receiver.ApiError),
    ([b'x' * 6, b'y' * 6], 0, receiver.ReceiverError),
])
def test_download_stream_size_and_completeness(monkeypatch, chunks, size, expected):
    api = receiver.Telegram('synthetic')
    monkeypatch.setattr(api, 'call', lambda *a, **k: {'file_path': 'documents/file.pdf', 'file_size': size})
    monkeypatch.setattr(receiver, 'MAX_BYTES', 10)
    class Download:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def raise_for_status(self):
            pass
        def iter_content(self, size):
            return iter(chunks)
    monkeypatch.setattr(receiver.requests, 'get', lambda *a, **k: Download())
    if isinstance(expected, bytes):
        assert api.download('file-id') == expected
    else:
        with pytest.raises(expected):
            api.download('file-id')


def test_download_rejects_unsafe_remote_path_before_request(monkeypatch):
    api = receiver.Telegram('synthetic')
    monkeypatch.setattr(api, 'call', lambda *a, **k: {'file_path': '../other'})
    monkeypatch.setattr(receiver.requests, 'get', lambda *a, **k: pytest.fail('不應請求無效路徑'))
    with pytest.raises(receiver.ApiError):
        api.download('file-id')


def test_animation_preserves_original_and_reports_first_frame_conversion(tmp_path):
    output = io.BytesIO()
    Image.new('RGB', (3, 2), 'red').save(output, format='GIF', save_all=True,
                                       append_images=[Image.new('RGB', (3, 2), 'blue')])
    worker = make_receiver(tmp_path, output.getvalue(), 'jpeg')
    worker.ingest([update(kind='image', name='animation.gif')])
    worker.process()
    event, = events(worker)
    assert Path(event['path']).read_bytes() == output.getvalue()
    assert event['image']['frames'] == 2
    with Image.open(event['jpeg_path']) as image:
        assert image.format == 'JPEG' and getattr(image, 'n_frames', 1) == 1
