"""未註冊的合成路由不應自動載入憑證或觸發通知。"""
import pytest

import tg_notify as notify


@pytest.mark.parametrize('route', [
    'UNREGISTERED_ALPHA', 'UNREGISTERED_BETA', 'UNREGISTERED_GAMMA',
    'UNREGISTERED_DELTA', 'UNREGISTERED_EPSILON', 'UNREGISTERED_ZETA',
    'UNREGISTERED_ETA', 'UNREGISTERED_THETA', 'UNREGISTERED_IOTA',
])
def test_unregistered_synthetic_route_never_sends(monkeypatch, tmp_path, route):
    configuration = tmp_path / 'notifications.env'
    configuration.write_text('TG_BOT_TOKEN=synthetic\nTG_CHAT_ID=123\n')
    configuration.chmod(0o600)
    monkeypatch.setattr(notify, '_ENV_PATH', str(configuration))
    monkeypatch.setenv('TG_' + route + '_TOKEN', 'synthetic-legacy')
    monkeypatch.setenv('TG_' + route + '_CHAT_ID', '456')
    calls = []
    monkeypatch.setattr(notify.requests, 'post', lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ValueError, match='不支援'):
        notify.send_text('合成通知', route)
    assert calls == []
