"""主代理獨立驗收：真 adapter 接線、完成判斷及互斥邊界。"""
from types import SimpleNamespace

import pytest
import requests

import provision_telegram_bot
import tg_settings
import tg_setup
from test_first_run_setup import Harness, TOKEN, USERNAME, USER_ID, BOT_ID, config


@pytest.fixture
def flow(tmp_path):
    config(tmp_path / '.env')
    return Harness(tmp_path)


def test_default_adapters_complete_through_fake_botfather_and_http(flow, monkeypatch):
    calls = []

    def botfather(client, text, **kwargs):
        calls.append(text)
        reply = ('Done! invalid username is the display name. Token: ' + TOKEN
                 if text == USERNAME else 'Please continue')
        return SimpleNamespace(raw_text=reply)

    def get(url, **kwargs):
        assert url == 'https://api.telegram.org/bot' + TOKEN + '/getMe'
        return SimpleNamespace(status_code=200, json=lambda: {
            'ok': True, 'result': {'id': BOT_ID, 'username': USERNAME, 'is_bot': True}})

    def post(url, **kwargs):
        assert url == 'https://api.telegram.org/bot' + TOKEN + '/sendMessage'
        assert kwargs['json']['chat_id'] == USER_ID
        calls.append('notice')
        return SimpleNamespace(status_code=200, json=lambda: flow.response)

    monkeypatch.setattr(tg_setup, '_default_client', flow.factory)
    monkeypatch.setattr(provision_telegram_bot, 'send_and_wait_botfather_reply', botfather)
    monkeypatch.setattr(requests, 'get', get)
    monkeypatch.setattr(requests, 'post', post)
    assert flow.main(client_factory=None, bot_creator=None, identity_lookup=None,
                     notification_sender=None) == 0
    assert calls == ['/cancel', '/newbot', 'Synthetic personal notices', USERNAME, 'notice']
    assert flow.journal()[1]['message_id'] == 42


def test_completed_rerun_does_not_rewrite_configuration(flow, monkeypatch):
    assert flow.run()['status'] == 'completed'
    paths = (flow.env, tg_settings.route_file(flow.env), flow.journal()[0])
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]

    def forbidden(*args, **kwargs):
        pytest.fail('完成重跑不得重寫設定或進度')

    monkeypatch.setattr(tg_setup, 'register_route', forbidden)
    monkeypatch.setattr(tg_setup, 'write_json', forbidden)
    assert flow.run()['status'] == 'completed'
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths] == before
    assert len(flow.created) == len(flow.sent) == 1


@pytest.mark.parametrize('field,value', [('version', True), ('message_id', None),
                                         ('message_id', True), ('message_id', 0)])
def test_invalid_completed_record_stops_before_client(flow, field, value):
    assert flow.run()['status'] == 'completed'
    path, record = flow.journal()
    record[field] = value
    tg_settings.write_json(path, record)
    count = len(flow.clients)
    assert flow.run()['status'] == 'invalid_state'
    assert len(flow.clients) == count
    assert len(flow.created) == len(flow.sent) == 1


def test_account_lock_blocks_other_configuration(flow, tmp_path):
    other_root = tmp_path / 'other copy'
    other_root.mkdir()
    config(other_root / '.env')
    other = Harness(other_root)
    attempts = []

    def create(client, name, username):
        attempts.append(other.run(account_lock_dir=flow.root / 'account locks'))
        return flow.creator(client, name, username)

    assert flow.run(bot_creator=create)['status'] == 'completed'
    assert attempts[0]['status'] == 'storage_error'
    assert not other.created and not other.sent


def test_configuration_lock_stops_before_client(flow):
    with tg_settings.secure_lock(str(flow.env) + '.setup.lock'):
        assert flow.run()['status'] == 'storage_error'
    assert not flow.clients and not flow.created


@pytest.mark.parametrize('target', ['state', 'session'])
def test_setup_refuses_unsafe_session_paths(flow, tmp_path, target):
    external = tmp_path / 'outside'
    if target == 'state':
        external.mkdir()
        flow.state.symlink_to(external, target_is_directory=True)
    else:
        flow.state.mkdir(mode=0o700)
        external.write_text('do not modify')
        external.chmod(0o600)
        (flow.state / 'botfather_user.session').symlink_to(external)
    assert flow.run()['status'] in ('unsafe_session', 'storage_error')
    assert not flow.clients and not flow.created
    if target == 'session':
        assert external.read_text() == 'do not modify'


def test_invalid_stage_cannot_echo_secret_from_corrupt_journal(flow, capsys):
    assert flow.main() == 0
    capsys.readouterr()
    path, record = flow.journal()
    record['stage'] = TOKEN
    tg_settings.write_json(path, record)
    assert flow.main() != 0
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
