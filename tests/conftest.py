"""Deny real network access throughout the notification test suite."""
import socket

import pytest
import requests
import tg_i18n


@pytest.fixture(autouse=True)
def traditional_chinese_regressions(monkeypatch):
    """原有中文斷言保留；語言專屬測試自行覆寫 / Preserve existing Chinese assertions."""
    monkeypatch.setenv("TG_LANGUAGE", "zh-TW")
    token = tg_i18n._language.set("zh-TW")
    yield
    tg_i18n._language.reset(token)


@pytest.fixture(autouse=True)
def deny_real_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Offline regression: real network access is forbidden")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
