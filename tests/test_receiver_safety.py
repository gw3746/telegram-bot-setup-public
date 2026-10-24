"""收件拒絕分類、有界重試與公開範圍的離線回歸。"""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import tg_receiver as receiver


def incoming():
    return {'update_id': 1, 'message': {'message_id': 2,
            'chat': {'type': 'private', 'id': 1001}, 'from': {'id': 1001},
            'document': {'file_id': 'synthetic-file', 'file_name': 'sample.pdf'}}}


@pytest.fixture
def worker(tmp_path):
    api = Mock()
    api.download.return_value = b'%PDF-1.7\nsynthetic'
    result = receiver.Receiver(tmp_path / 'state', tmp_path / 'files', api, [1001], 2001)
    result.ingest([incoming()])
    yield result
    result.db.close()


@pytest.mark.parametrize('code', [400, 401, 403, 404, 409, 422])
def test_permanent_download_rejection_is_terminal(worker, code):
    worker.api.download.side_effect = receiver.ApiError(code)
    worker.process()
    row = worker.db.execute('SELECT status, attempts, retry_at FROM jobs').fetchone()
    assert row['status'] == 'rejected' and row['retry_at'] == 0
    worker.process()
    worker.api.download.assert_called_once()


@pytest.mark.parametrize('failure', [receiver.ApiError(), receiver.ApiError(429, 1200),
                                    receiver.ApiError(503), OSError('synthetic storage failure')])
def test_temporary_download_errors_stop_after_max_attempts(worker, failure):
    worker.api.download.side_effect = failure
    limit = receiver.MAX_JOB_ATTEMPTS
    for attempt in range(1, limit + 1):
        worker.db.execute('UPDATE jobs SET retry_at=0')
        worker.db.commit()
        worker.process()
        row = worker.db.execute('SELECT status, attempts, retry_at FROM jobs').fetchone()
        assert row['attempts'] == attempt
        assert row['status'] == ('pending' if attempt < limit else 'rejected')
    worker.process()
    assert worker.api.download.call_count == limit and row['retry_at'] == 0


def test_exhausted_existing_pending_job_is_rejected_without_download(worker):
    schema = worker.db.execute("SELECT sql FROM sqlite_master WHERE name='jobs'").fetchone()[0]
    worker.db.execute('UPDATE jobs SET attempts=25,retry_at=9999999999')
    worker.db.commit()
    worker.process()
    row = worker.db.execute('SELECT status,attempts,retry_at FROM jobs').fetchone()
    assert tuple(row) == ('rejected', 25, 0)
    worker.api.download.assert_not_called()
    assert worker.db.execute("SELECT sql FROM sqlite_master WHERE name='jobs'").fetchone()[0] == schema


def test_existing_database_preserves_saved_events_and_resumes_pending_jobs(worker, tmp_path):
    worker.process()
    before = worker.db.execute('SELECT event FROM jobs').fetchone()[0]
    pending = incoming()
    pending['update_id'] = 3
    pending['message']['message_id'] = 4
    worker.ingest([pending])
    schema = worker.db.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    schema = [row[0] for row in schema]
    assert worker.offset == 4
    assert worker.db.execute('SELECT status FROM jobs WHERE update_id=3').fetchone()[0] == 'pending'
    worker.db.close()
    api = Mock()
    api.download.return_value = b'%PDF-1.7\nsynthetic'
    resumed = receiver.Receiver(tmp_path / 'state', tmp_path / 'files', api, [1001], 2001)
    try:
        assert resumed.offset == 4
        assert [row[0] for row in resumed.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()] == schema
        assert resumed.db.execute('SELECT event FROM jobs WHERE update_id=1').fetchone()[0] == before
        resumed.process()
        result = []
        resumed.dispatch_events(result.append)
        assert [event['event_id'] for event in result] == ['2001:1', '2001:3']
        assert all(Path(event['path']).read_bytes() == api.download.return_value for event in result)
        assert resumed.db.execute('SELECT event FROM jobs WHERE update_id=1').fetchone()[0] == before
        assert resumed.db.execute('SELECT status FROM jobs WHERE update_id=3').fetchone()[0] == 'saved'
        assert resumed.offset == 4
        api.download.assert_called_once_with('synthetic-file')
    finally:
        resumed.db.close()


@pytest.mark.parametrize('code', [400, 401, 403, 404, 409, 422])
def test_download_http_permanent_status_reaches_worker(monkeypatch, code):
    api = receiver.Telegram('synthetic')
    monkeypatch.setattr(api, 'call', lambda *a, **k: {'file_path': 'documents/file.pdf'})
    response = Mock(status_code=code)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.raise_for_status.side_effect = requests.HTTPError(response=response)
    monkeypatch.setattr(receiver.requests, 'get', lambda *a, **k: response)
    with pytest.raises(receiver.ApiError) as caught:
        api.download('synthetic-file')
    assert caught.value.code == code


@pytest.mark.parametrize('code', [400, 401, 403, 404, 409, 422])
@pytest.mark.parametrize('payload', [
    {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 1}},
    {'ok': True, 'result': []},
    None,
])
def test_http_permanent_rejection_cannot_be_overridden(monkeypatch, code, payload):
    response = SimpleNamespace(status_code=code, json=lambda: payload)
    monkeypatch.setattr(receiver.requests, 'post', lambda *a, **k: response)
    with pytest.raises(receiver.ApiError) as caught:
        receiver.Telegram('synthetic').call('getUpdates')
    assert caught.value.code == code


def test_http_permanent_rejection_survives_non_json_body(monkeypatch):
    response = Mock(status_code=403)
    response.json.side_effect = ValueError('synthetic non-json')
    monkeypatch.setattr(receiver.requests, 'post', lambda *a, **k: response)
    with pytest.raises(receiver.ApiError) as caught:
        receiver.Telegram('synthetic').call('getUpdates')
    assert caught.value.code == 403


def test_json_rate_limit_under_http_success_preserves_delay(monkeypatch):
    response = SimpleNamespace(status_code=200, json=lambda: {
        'ok': False, 'error_code': 429, 'parameters': {'retry_after': 1200}})
    monkeypatch.setattr(receiver.requests, 'post', lambda *a, **k: response)
    with pytest.raises(receiver.ApiError) as caught:
        receiver.Telegram('synthetic').call('getUpdates')
    assert caught.value.code == 429 and caught.value.retry_after == 1200


def test_polling_http_permanent_rejection_stops_without_rate_limit_sleep(tmp_path, monkeypatch, capsys):
    calls = []
    def post(url, **kwargs):
        method = url.rsplit('/', 1)[-1]
        calls.append(method)
        if method == 'getMe':
            return SimpleNamespace(status_code=200, json=lambda: {'ok': True, 'result': {'id': 2001}})
        if method == 'getWebhookInfo':
            return SimpleNamespace(status_code=200, json=lambda: {'ok': True, 'result': {'url': ''}})
        assert method == 'getUpdates'
        return SimpleNamespace(status_code=403, json=lambda: {
            'ok': False, 'error_code': 429, 'parameters': {'retry_after': 1}})
    monkeypatch.setattr(receiver.requests, 'post', post)
    monkeypatch.setattr(receiver, 'credentials', lambda *args: 'synthetic')
    monkeypatch.setattr(receiver.time, 'sleep', lambda *args: pytest.fail('永久拒絕不得等待重試'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'xdg'))
    assert receiver.main(['--state-dir', str(tmp_path / 'state'), '--destination', str(tmp_path / 'files'),
                          '--allowed-user', '1001', '--non-interactive']) == 2
    assert calls == ['getMe', 'getWebhookInfo', 'getUpdates']
    assert capsys.readouterr().err


def test_receiver_cli_redacts_known_token_from_diagnostic(tmp_path, monkeypatch, capsys):
    token = 'synthetic-private-credential'
    class Api:
        def call(self, method, **kwargs):
            return {'id': 2001} if method == 'getMe' else {'url': ''}
    monkeypatch.setattr(receiver, 'credentials', lambda *a: token)
    monkeypatch.setattr(receiver, 'Telegram', lambda *a: Api())
    monkeypatch.setattr(receiver, 'Receiver', Mock(side_effect=receiver.ReceiverError(
        'https://api.telegram.org/bot' + token + '/getFile')))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'xdg'))
    assert receiver.main(['--state-dir', str(tmp_path / 'state'), '--destination', str(tmp_path / 'files'),
                          '--allowed-user', '1001', '--once', '--non-interactive']) == 2
    assert token not in capsys.readouterr().err


def test_public_scope_cases_use_only_synthetic_route_names():
    tree = ast.parse(Path(__file__).with_name('test_public_scope.py').read_text())
    route_cases = [node.args[1] for node in ast.walk(tree)
                   if isinstance(node, ast.Call) and len(node.args) > 1
                   and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'route']
    assert len(route_cases) == 1
    assert all(value.startswith('UNREGISTERED_') for value in ast.literal_eval(route_cases[0]))
