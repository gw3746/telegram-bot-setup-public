"""以合成憑證與離線 Session 驗證帳號入口的安全邊界。"""
import io
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from telethon.sessions import SQLiteSession
from telethon.crypto import AuthKey

import provision_telegram_bot as provision
import tg_cli


TOKEN = '123456789:' + 'SYNTHETIC_TOKEN_' * 3


def config(tmp_path, **values):
    settings = {'TG_API_ID': '123456', 'TG_API_HASH': 'synthetic-api-hash',
                'TG_PHONE': '+10000000000', 'TG_2STEP_PASSWORD': 'synthetic password'}
    settings.update(values)
    path = tmp_path / 'synthetic.env'
    path.write_text(''.join(f'{key}={value}\n' for key, value in settings.items()))
    path.chmod(0o600)
    return path


@pytest.mark.parametrize('operation', ['authorized', 'request', 'complete'])
@pytest.mark.parametrize('session_name', ['account', 'account[1]'])
def test_account_session_and_sidecars_are_private_in_existing_public_directory(tmp_path, monkeypatch, operation, session_name):
    parent = tmp_path / 'state'
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    session = parent / session_name
    sidecar = Path(str(session) + '.session-journal')

    class OfflineClient:
        def __init__(self, name, *_):
            self.session = SQLiteSession(name)
            self.session.auth_key = AuthKey(bytes(range(256)))
            self.session.save()
            sidecar.write_bytes(b'synthetic journal')
            sidecar.chmod(0o644)
        def connect(self):
            pass
        def is_user_authorized(self):
            return True
        def disconnect(self):
            self.session.close()
            sidecar.write_bytes(b'synthetic journal')
            sidecar.chmod(0o644)

    monkeypatch.setattr(provision, 'TelegramClient', OfflineClient)
    state = tmp_path / 'login.json'
    state.write_text(json.dumps({'phone': '+10000000000', 'phone_code_hash': 'synthetic'}))
    previous = os.umask(0o022)
    try:
        if operation == 'authorized':
            provision.require_authorized_client(config(tmp_path), session).disconnect()
        elif operation == 'request':
            assert provision.request_login_code(config(tmp_path), session, state) == 0
        else:
            assert provision.complete_login(config(tmp_path), session, state, '12345') == 0
    finally:
        os.umask(previous)
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(Path(str(session) + '.session').stat().st_mode) == 0o600
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


@pytest.mark.parametrize('phase', ['constructor', 'connect'])
def test_session_files_are_hardened_after_client_failure(tmp_path, monkeypatch, phase):
    session = tmp_path / 'state' / 'account'
    sidecar = Path(str(session) + '.session-wal')
    class FailingClient:
        def __init__(self, *_):
            sidecar.write_bytes(b'synthetic')
            sidecar.chmod(0o644)
            if phase == 'constructor':
                raise RuntimeError('synthetic failure')
        def connect(self):
            raise RuntimeError('synthetic failure')
        def disconnect(self):
            pass
    monkeypatch.setattr(provision, 'TelegramClient', FailingClient)
    with pytest.raises(RuntimeError):
        provision.require_authorized_client(config(tmp_path), session)
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


@pytest.mark.parametrize('target', ['ancestor', 'directory', 'session', 'sidecar'])
def test_account_session_refuses_symlink_targets(tmp_path, monkeypatch, target):
    parent = tmp_path / 'state'
    parent.mkdir()
    session = parent / 'account'
    outside = tmp_path / 'outside'
    if target == 'ancestor':
        outside.mkdir()
        link = tmp_path / 'linked-root'
        link.symlink_to(outside, target_is_directory=True)
        session = link / 'state' / 'account'
    elif target == 'directory':
        outside.mkdir()
        parent.rmdir()
        parent.symlink_to(outside, target_is_directory=True)
    else:
        outside.write_text('synthetic')
        Path(str(session) + ('.session' if target == 'session' else '.session-journal')).symlink_to(outside)
    factory = Mock()
    monkeypatch.setattr(provision, 'TelegramClient', factory)
    with pytest.raises((RuntimeError, ValueError, OSError)):
        provision.require_authorized_client(config(tmp_path), session)
    factory.assert_not_called()


def test_account_cli_redacts_token_in_numeric_api_id(tmp_path, capsys):
    assert tg_cli.main(['--env-path', str(config(tmp_path, TG_API_ID=TOKEN)), 'status']) == 1
    assert TOKEN not in capsys.readouterr().err


@pytest.mark.parametrize('remote', [False, True])
def test_account_cli_redacts_local_and_remote_bot_urls(tmp_path, monkeypatch, capsys, remote):
    path = config(tmp_path, TG_BOT_TOKEN=TOKEN if remote else TOKEN + ' invalid')
    monkeypatch.setattr(tg_cli, 'DEFAULT_BOT_STATE', tmp_path / 'no-state.json')
    url = 'https://api.telegram.org/bot' + TOKEN + '/getUpdates'
    if remote:
        monkeypatch.setattr(tg_cli.request, 'urlopen', lambda *_a, **_k: io.BytesIO(json.dumps({'ok': False, 'description': url}).encode()))
    assert tg_cli.main(['--env-path', str(path), 'bot-updates']) == 1
    output = capsys.readouterr().err
    assert TOKEN not in output and url not in output


@pytest.mark.parametrize('entry', ['account', 'provision'])
def test_cli_exception_redacts_all_configured_credentials(tmp_path, monkeypatch, capsys, entry):
    path = config(tmp_path, TG_BOT_TOKEN=TOKEN)
    values = provision.load_simple_env(path)
    sensitive = [value for key, value in values.items() if key != 'TG_API_ID']
    error = RuntimeError(' / '.join(sensitive))
    if entry == 'account':
        monkeypatch.setattr(tg_cli, 'command_status', Mock(side_effect=error))
        result = tg_cli.main(['--env-path', str(path), 'status'])
    else:
        monkeypatch.setattr(provision, 'request_login_code', Mock(side_effect=error))
        result = provision.main(['--env-path', str(path), 'request-login-code'])
    assert result == 1
    output = capsys.readouterr().err
    assert output and all(value not in output for value in sensitive)
    assert 'Traceback' not in output


def test_cli_redacts_file_and_environment_credentials_with_same_key(tmp_path, monkeypatch, capsys):
    path = config(tmp_path, TG_BOT_TOKEN='synthetic-file-token')
    monkeypatch.setenv('TG_BOT_TOKEN', 'synthetic-environment-token')
    monkeypatch.setenv('TG_API_HASH', '')
    error = RuntimeError('synthetic-file-token synthetic-environment-token synthetic-api-hash')
    monkeypatch.setattr(tg_cli, 'command_status', Mock(side_effect=error))
    assert tg_cli.main(['--env-path', str(path), 'status']) == 1
    output = capsys.readouterr().err
    assert all(value not in output for value in ('synthetic-file-token', 'synthetic-environment-token', 'synthetic-api-hash'))


@pytest.mark.parametrize('entry', ['account', 'provision'])
def test_cli_argument_errors_do_not_echo_sensitive_values(capsys, entry):
    main = tg_cli.main if entry == 'account' else provision.main
    with pytest.raises(SystemExit) as stopped:
        main(['--synthetic-invalid-option', TOKEN, 'synthetic-password'])
    assert stopped.value.code == 2
    output = capsys.readouterr().err
    assert TOKEN not in output and 'synthetic-password' not in output


@pytest.mark.parametrize('receipt', [None, {}, SimpleNamespace(), SimpleNamespace(id=None),
                                     SimpleNamespace(id=0), SimpleNamespace(id=-1),
                                     SimpleNamespace(id=True), SimpleNamespace(id='12')])
def test_user_send_requires_positive_integer_message_receipt(tmp_path, monkeypatch, capsys, receipt):
    client = Mock()
    client.send_message.return_value = receipt
    client.get_messages.return_value = []
    monkeypatch.setattr(provision, 'require_authorized_client', lambda *_: client)
    assert provision.send_message_via_user_session(tmp_path / 'unused.env', tmp_path / 'session', 'example_bot', 'synthetic', 0) != 0
    assert 'MESSAGE_SENT' not in capsys.readouterr().out
    client.send_message.assert_called_once()
    client.get_messages.assert_not_called()
    client.disconnect.assert_called_once()


def test_user_send_accepts_valid_message_receipt_once(tmp_path, monkeypatch, capsys):
    client = Mock()
    client.send_message.return_value = SimpleNamespace(id=12)
    client.get_messages.return_value = []
    monkeypatch.setattr(provision, 'require_authorized_client', lambda *_: client)
    assert provision.send_message_via_user_session(tmp_path / 'unused.env', tmp_path / 'session', 'example_bot', 'synthetic', 0) == 0
    assert 'MESSAGE_SENT' in capsys.readouterr().out
    client.send_message.assert_called_once()


@pytest.mark.parametrize('first,last', [('TG_BOT_TOKEN', 'TG_BOT_TOKEN'), (' TG_BOT_TOKEN ', 'TG_BOT_TOKEN '), ('TG_BOT_TOKEN ', ' TG_BOT_TOKEN')])
def test_duplicate_env_keys_load_new_value_after_atomic_update(tmp_path, first, last):
    path = tmp_path / 'synthetic.env'
    path.write_text(f'# retained\n{first}=synthetic-first\nOTHER=retained\n{last}=synthetic-last\n')
    old_inode = path.stat().st_ino
    provision.upsert_env_key(path, 'TG_BOT_TOKEN', 'synthetic-new')
    assert provision.load_simple_env(path) == {'TG_BOT_TOKEN': 'synthetic-new', 'OTHER': 'retained'}
    assert path.stat().st_ino != old_inode
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert '# retained' in path.read_text()


def test_create_bot_replaces_last_effective_duplicate_token(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'synthetic.env'
    path.write_text('TG_BOT_TOKEN=synthetic-first\nTG_BOT_TOKEN=synthetic-last\n')
    monkeypatch.setattr(provision, 'require_authorized_client', lambda *_: Mock())
    monkeypatch.setattr(provision, 'send_and_wait_botfather_reply', lambda *_a, **_k: SimpleNamespace(raw_text=TOKEN))
    assert provision.create_bot_via_botfather(path, tmp_path / 'session', 'Example', 'example_bot', 'TG_BOT_TOKEN', 'TG_CHAT_ID', 'TG_CHAT_ID') == 0
    assert 'BOT_CREATED' in capsys.readouterr().out
    assert provision.load_simple_env(path)['TG_BOT_TOKEN'] == TOKEN
