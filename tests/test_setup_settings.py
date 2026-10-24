"""首次設定的安全資料解析、原子儲存與自訂路由驗收。"""
import json
import os
from pathlib import Path
import stat

import pytest
import requests

import tg_notify as notify
import tg_settings as settings


@pytest.fixture
def configuration(tmp_path):
    path = tmp_path / 'synthetic.env'
    path.write_text('# 保留註解\nUNRELATED=synthetic-other\n')
    path.chmod(0o600)
    return path


def test_builtin_names_match_existing_notification_routes():
    assert settings.BUILTIN_ROUTE_NAMES == set(notify._BOT_CONFIG)


def test_config_is_data_and_never_exported(configuration, tmp_path):
    marker = tmp_path / 'must-not-execute'
    configuration.write_text('TG_API_HASH=$(touch ' + str(marker) + ')\nUNRELATED=synthetic\n')
    before = dict(os.environ)
    values = settings.load_env(configuration, require_private=True)
    assert values['TG_API_HASH'].startswith('$(touch ')
    assert not marker.exists() and dict(os.environ) == before


def test_registered_route_is_usable_by_existing_notification_api(monkeypatch, configuration):
    token = '123456789:' + 'synthetic_custom_' * 3
    settings.register_route(configuration, 'PERSONAL', token, 3123, notify._BOT_CONFIG)
    monkeypatch.setattr(notify, '_ENV_PATH', str(configuration))
    assert notify.get_bot_credentials('personal') == (token, '3123')
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs['json'])
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({'ok': True, 'result': {'message_id': 5, 'chat': {'id': 3123}}}).encode()
        return response
    monkeypatch.setattr(requests, 'post', post)
    assert notify.send_text('合成通知', 'personal', None)['ok'] is True
    assert calls == [{'chat_id': '3123', 'text': '合成通知'}]
    assert settings.load_env(configuration)['UNRELATED'] == 'synthetic-other'
    assert configuration.read_text().startswith('# 保留註解')
    assert token not in settings.route_file(configuration).read_text()


@pytest.mark.parametrize('name', sorted(settings.BUILTIN_ROUTE_NAMES))
def test_registration_never_overwrites_builtin_route(configuration, name):
    before = configuration.read_bytes()
    with pytest.raises(settings.SettingsError):
        settings.register_route(configuration, name, '123456789:' + 'a' * 35, 3123, notify._BOT_CONFIG)
    assert configuration.read_bytes() == before
    assert not settings.route_file(configuration).exists()


def test_custom_route_conflict_and_safe_rerun(configuration):
    token = '123456789:' + 'a' * 35
    settings.register_route(configuration, 'PERSONAL', token, 3123, notify._BOT_CONFIG)
    original = configuration.read_bytes()
    settings.register_route(configuration, 'PERSONAL', token, 3123, notify._BOT_CONFIG)
    assert configuration.read_bytes() == original
    with pytest.raises(settings.SettingsError):
        settings.register_route(configuration, 'PERSONAL', '123456789:' + 'b' * 35, 9999, notify._BOT_CONFIG)
    assert configuration.read_bytes() == original


def test_route_map_failure_can_resume_without_losing_verified_credentials(monkeypatch, configuration):
    token = '123456789:' + 'a' * 35
    original = settings.write_json
    monkeypatch.setattr(settings, 'write_json', lambda *_: (_ for _ in ()).throw(settings.SettingsError('synthetic map failure')))
    with pytest.raises(settings.SettingsError):
        settings.register_route(configuration, 'PERSONAL', token, 3123, notify._BOT_CONFIG)
    assert settings.load_env(configuration)['TG_CUSTOM_PERSONAL_TOKEN'] == token
    assert not settings.route_file(configuration).exists()
    monkeypatch.setattr(settings, 'write_json', original)
    settings.register_route(configuration, 'PERSONAL', token, 3123, notify._BOT_CONFIG)
    assert settings.custom_routes(configuration, notify._BOT_CONFIG)['PERSONAL'] == (
        'TG_CUSTOM_PERSONAL_TOKEN', 'TG_CUSTOM_PERSONAL_CHAT_ID')


def test_invalid_route_map_does_not_leak_unknown_values(configuration):
    sensitive = 'synthetic-value-not-for-diagnostics'
    settings.write_json(settings.route_file(configuration), {'version': 1, 'routes': {sensitive: {}}})
    with pytest.raises(settings.SettingsError) as caught:
        settings.custom_routes(configuration, notify._BOT_CONFIG)
    assert sensitive not in str(caught.value)


@pytest.mark.parametrize('kind', ['source', 'parent', 'route'])
def test_safe_files_reject_symlinks(configuration, tmp_path, kind):
    outside = tmp_path / 'untouched'
    outside.write_text('synthetic original')
    if kind == 'source':
        configuration.unlink()
        configuration.symlink_to(outside)
        target = configuration
    elif kind == 'parent':
        parent = tmp_path / 'linked-dir'
        parent.symlink_to(tmp_path, target_is_directory=True)
        target = parent / configuration.name
    else:
        target = settings.route_file(configuration)
        target.symlink_to(outside)
    with pytest.raises(settings.SettingsError):
        settings.write_private(target, b'synthetic replacement')
    assert outside.read_text() == 'synthetic original'


@pytest.mark.parametrize('mode,expected', [(0o400, 0o400), (0o600, 0o600), (0o644, 0o600)])
def test_safe_writer_keeps_restrictive_modes(configuration, mode, expected):
    configuration.chmod(mode)
    settings.write_private(configuration, b'synthetic private value')
    assert stat.S_IMODE(configuration.stat().st_mode) == expected


def test_lock_is_exclusive_and_released_after_failure(tmp_path):
    path = tmp_path / 'synthetic.lock'
    with pytest.raises(RuntimeError):
        with settings.secure_lock(path):
            with pytest.raises(settings.SettingsError):
                with settings.secure_lock(path):
                    pytest.fail('不可同時取得同一鎖')
            raise RuntimeError('synthetic body failure')
    with settings.secure_lock(path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_setup_rejects_wide_secret_configuration(configuration):
    configuration.chmod(0o644)
    with pytest.raises(settings.SettingsError, match='0600'):
        settings.load_env(configuration, require_private=True)
