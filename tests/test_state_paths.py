"""以合成家目錄驗證狀態預設及覆寫，不建立真實帳號 Session。

Validate state defaults and overrides with a synthetic home and no real sessions.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tools(monkeypatch, tmp_path):
    home = tmp_path / 'synthetic-home'
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.delenv('TG_CONFIG_STATE_DIR', raising=False)
    monkeypatch.setenv('TG_CONFIG_ENV_PATH', str(tmp_path / 'synthetic.env'))

    def forbidden_client(*_args, **_kwargs):
        raise AssertionError('狀態路徑驗證不可建立 Telegram client 或 Session')

    package = types.ModuleType('telethon')
    errors = types.ModuleType('telethon.errors')
    errors.SessionPasswordNeededError = type('SyntheticPasswordNeeded', (Exception,), {})
    sync = types.ModuleType('telethon.sync')
    sync.TelegramClient = forbidden_client
    for name, module in [('telethon', package), ('telethon.errors', errors), ('telethon.sync', sync)]:
        monkeypatch.setitem(sys.modules, name, module)

    def load(state=None):
        if state is not None:
            monkeypatch.setenv('TG_CONFIG_STATE_DIR', str(state))
        modules = {}
        for name in ('provision_telegram_bot', 'tg_cli', 'rotate_telegram_bot_tokens', 'tg_setup', 'tg_receiver'):
            spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            monkeypatch.setitem(sys.modules, name, module)
            spec.loader.exec_module(module)
            modules[name] = module
        return types.SimpleNamespace(home=home, state=home / '.local/state/telegram-bot-setup',
                                     provision=modules['provision_telegram_bot'], cli=modules['tg_cli'],
                                     rotation=modules['rotate_telegram_bot_tokens'],
                                     setup=modules['tg_setup'], receiver=modules['tg_receiver'])

    return load


def assert_state_paths(selected, state):
    assert selected.provision.DEFAULT_STATE_DIR == state
    assert selected.provision.DEFAULT_SESSION_PATH == state / 'botfather_user'
    assert selected.provision.DEFAULT_LOGIN_STATE_PATH == state / 'botfather_login.json'
    assert selected.cli.DEFAULT_BOT_STATE == state / 'tg-cli-bot-updates.json'
    assert selected.rotation.STATE_DIR == state / 'token_rotation'
    assert Path(selected.setup.parser().parse_args([]).state_dir) == state
    assert selected.receiver.parser().parse_args(['--allowed-user', '123']).state_dir == state / 'receiver'


def test_state_defaults_use_synthetic_home_without_creating_files(tools):
    selected = tools()
    assert_state_paths(selected, selected.state)
    assert not selected.home.exists()


def test_state_directory_environment_override_applies_to_all_tools(tools, tmp_path):
    state = tmp_path / 'selected-state'
    selected = tools(state)
    assert_state_paths(selected, state)
    assert not state.exists()
    assert not selected.home.exists()


def test_individual_cli_paths_override_shared_state_directory(tools, tmp_path):
    selected = tools(tmp_path / 'shared-state')
    session, login, state = [tmp_path / value for value in ('separate-session', 'separate-login.json', 'separate-state')]
    provision = selected.provision.parse_args(['--session-path', str(session), '--login-state-path', str(login),
                                              'request-login-code'])
    assert Path(provision.session_path) == session
    assert Path(provision.login_state_path) == login
    assert Path(selected.cli.parser().parse_args(['--session-path', str(session), 'status']).session_path) == session
    assert Path(selected.setup.parser().parse_args(['--state-dir', str(state)]).state_dir) == state
    assert selected.receiver.parser().parse_args(['--state-dir', str(state), '--allowed-user', '123']).state_dir == state
    assert not selected.home.exists()
    assert not state.exists()


@pytest.mark.parametrize('override', [False, True])
def test_bot_update_ack_persists_offset_in_selected_state_root(tools, tmp_path, monkeypatch, override):
    state = tmp_path / 'selected-state' if override else None
    selected = tools(state)
    state = state or selected.state
    env = tmp_path / 'synthetic.env'
    env.write_text('TG_BOT_TOKEN=synthetic-offline-token\nTG_CHAT_ID=123\n', encoding='utf-8')
    env.chmod(0o600)
    requests = []

    def fake_api(token, method, payload):
        assert token == 'synthetic-offline-token' and method == 'getUpdates'
        requests.append(payload)
        return {'ok': True, 'result': [{'update_id': 41, 'message': {'message_id': 7, 'text': 'synthetic'}}]}

    monkeypatch.setattr(selected.cli, 'bot_api', fake_api)
    assert selected.cli.main(['--env-path', str(env), 'bot-updates']) == 0
    assert not state.exists()
    assert selected.cli.main(['--env-path', str(env), 'bot-updates', '--ack']) == 0
    assert json.loads((state / 'tg-cli-bot-updates.json').read_text())['offsets'] == {'DEFAULT': 42}
    assert selected.cli.main(['--env-path', str(env), 'bot-updates']) == 0
    assert [request['offset'] for request in requests] == [0, 0, 42]
