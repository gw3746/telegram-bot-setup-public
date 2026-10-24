"""獨立阻網程序以合成 API 驗證 CLI、外部套件與 symlink 載入。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = (
    "tg_notify", "sys_notify", "tg_cli", "provision_telegram_bot",
    "rotate_telegram_bot_tokens", "tg_setup", "tg_install", "tg_receiver",
    "tg_settings", "tg_delivery",
)


@pytest.fixture
def isolated_process(tmp_path):
    # 子程序不繼承 pytest monkeypatch，啟動時另裝阻網與合成 API。
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text('''
import json
import os
from pathlib import Path
import socket
from urllib import request
import requests

def blocked(*args, **kwargs):
    raise AssertionError("禁止真實網路呼叫")

socket.create_connection = blocked
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
request.urlopen = blocked
requests.sessions.Session.request = blocked
requests.sessions.Session.send = blocked

def fake_post(url, **kwargs):
    assert url == "https://api.telegram.org/botoffline-fake-token/sendMessage"
    assert kwargs["json"]["chat_id"] == "offline-fake-chat"
    assert kwargs["json"]["text"]
    with Path(os.environ["FAKE_API_CALLS"]).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(kwargs["json"], ensure_ascii=False) + "\\n")
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"ok":true,"result":{"message_id":731}}'
    return response

requests.post = fake_post
''', encoding="utf-8")
    calls = tmp_path / "api-calls.jsonl"
    env = {key: value for key, value in os.environ.items() if not key.startswith("TG_")}
    env.update(
        PYTHONPATH=str(guard), PYTHONDONTWRITEBYTECODE="1", HOME=str(tmp_path),
        TG_CONFIG_ENV_PATH=str(tmp_path / "absent.env"),
        TG_CONFIG_STATE_DIR=str(tmp_path / "synthetic-state"), TG_LANGUAGE="en",
        TG_BOT_TOKEN="offline-fake-token", TG_CHAT_ID="offline-fake-chat",
        FAKE_API_CALLS=str(calls),
    )

    def run(*args):
        uv = env.get("UV_BIN") or shutil.which("uv", path=env.get("PATH"))
        assert uv, "測試需要 uv"
        command = [uv, "run", "--project", str(ROOT), "--frozen", "--no-sync",
                   "--", "python", *args]
        result = subprocess.run(command, cwd=tmp_path, env=env, text=True,
                                capture_output=True, timeout=30, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        return [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []

    return run


@pytest.mark.parametrize("entry", ["tg_notify", "sys_notify"])
def test_direct_notify_cli_sends_via_fake_api(isolated_process, entry):
    args = ("入口驗證", "DEFAULT", "NONE") if entry == "tg_notify" else ("入口驗證",)
    calls = isolated_process(str(ROOT / (entry + ".py")), *args)
    assert len(calls) == 1
    assert "入口驗證" in calls[0]["text"]
    assert "parse_mode" not in calls[0]


@pytest.mark.parametrize("mode", ["package", "symlink"])
@pytest.mark.parametrize("entry", ENTRYPOINTS)
def test_external_imports_resolve_real_directory_once(tmp_path, isolated_process, mode, entry):
    package = "external_tools"
    directory = tmp_path / package
    if mode == "package":
        directory.symlink_to(ROOT, target_is_directory=True)
    else:
        directory.mkdir()
        (directory / (entry + ".py")).symlink_to(ROOT / (entry + ".py"))
    # 起始 sys.path 不含 repo，讓真正的外部載入驗證 bootstrap。
    script = f'''
import importlib
from pathlib import Path
import sys

root = {str(ROOT)!r}
assert root not in sys.path
sys.path.insert(0, {str(tmp_path)!r})
module = importlib.import_module({(package + "." + entry)!r})
assert Path(module.__file__).resolve() == Path(root) / {entry + ".py"!r}
assert sys.path.count(root) == 1
importlib.reload(module)
assert sys.path.count(root) == 1
'''
    if entry == "tg_notify":
        script += '''
result = module.send_text("入口驗證", "DEFAULT", parse_mode=None)
assert result["ok"] is True
assert result["result"]["message_id"] == 731
assert result["delivery"]["status"] == "success"
assert result["delivery"]["message_ids"] == [731]
'''
    elif entry == "sys_notify":
        script += '\nassert module.main(["入口驗證"]) == 0\n'
    elif entry == "tg_install":
        script += '\nassert module.setup_main(["--help"]) == 0\n'
    calls = isolated_process("-c", script)
    if entry in ("tg_notify", "sys_notify"):
        assert len(calls) == 1
        assert "入口驗證" in calls[0]["text"]
    else:
        assert calls == []


def test_external_subprocess_guard_blocks_live_network(isolated_process):
    calls = isolated_process("-c", '''
import socket
from urllib import request
import requests

operations = (
    lambda: socket.create_connection(("127.0.0.1", 9)),
    lambda: socket.socket().connect(("127.0.0.1", 9)),
    lambda: socket.socket().connect_ex(("127.0.0.1", 9)),
    lambda: request.urlopen("https://api.telegram.org/"),
    lambda: requests.get("https://api.telegram.org/"),
)
for operation in operations:
    try:
        operation()
    except AssertionError as error:
        assert str(error) == "禁止真實網路呼叫"
    else:
        raise AssertionError("子程序阻網未生效")
''')
    assert calls == []
