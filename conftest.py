"""所有通知與圖片回歸一律阻擋真實網路。"""
import socket
from urllib import request

import pytest
import requests


@pytest.fixture(autouse=True)
def deny_live_io(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("離線驗證禁止真實網路")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(request, "urlopen", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
