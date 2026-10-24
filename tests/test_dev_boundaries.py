"""獨立離線邊界案例：依使用情境驗證，禁止讀取現用設定或發出真網請求。"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import types

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tg_notify as notify


@pytest.fixture(autouse=True)
def sandbox(monkeypatch, tmp_path):
    def blocked(*_args, **_kwargs):
        raise AssertionError("獨立審查禁止真實網路")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(requests.sessions.Session, "send", blocked)
    monkeypatch.setattr(notify.requests, "post", blocked)
    for pair in notify._BOT_CONFIG.values():
        for key in pair:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("TG_API_HASH", raising=False)
    for key in ("TG_CONFIG_ENV_PATH", "TG_CONFIG_STATE_DIR", "TG_LEGACY_CONFIG_PATH", "TG_SAVED_SESSION_PATH"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "synthetic.env"
    values = {
        "TG_BOT_TOKEN": "123456789:" + "SYNTHETIC_ONLY_A" * 3,
        "TG_CHAT_ID": "1001",
        "TG_API_HASH": "SYNTHETIC_UNRELATED_HASH",
    }
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    monkeypatch.setattr(notify, "_ENV_PATH", str(path))
    waits = []
    monkeypatch.setattr(notify.time, "sleep", waits.append)
    return {"path": path, "values": values, "waits": waits}


def reply(payload, status=200, raw=None):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(payload).encode() if raw is None else raw
    return response


def success(ident=1):
    return reply({"ok": True, "result": {"message_id": ident}})


def rejection(code, retry_after=None):
    payload = {"ok": False, "error_code": code, "description": "synthetic rejection"}
    if retry_after is not None:
        payload["parameters"] = {"retry_after": retry_after}
    return reply(payload, code)


def install(monkeypatch, replies):
    calls = []
    queue = iter(replies)

    def post(url, **kwargs):
        calls.append((url, kwargs))
        item = next(queue)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(notify.requests, "post", post)
    return calls


def test_rotated_credential_invalidates_receipt_even_with_same_route_and_chat(monkeypatch, sandbox):
    source = "甲" * 4097
    install(monkeypatch, [success(11), rejection(403)])
    receipt = notify.send_text(source, "DEFAULT", None)["delivery"]["resume"]
    old_token = sandbox["values"]["TG_BOT_TOKEN"]
    sandbox["path"].write_text(sandbox["path"].read_text().replace(old_token, "222222222:" + "NEW_SYNTHETIC_C" * 3))
    calls = install(monkeypatch, [])
    with pytest.raises(ValueError, match="不符"):
        notify.send_text(source, "DEFAULT", None, resume=receipt)
    assert calls == []
    assert old_token not in json.dumps(receipt)


def test_wait_budget_is_shared_by_all_text_parts(monkeypatch, sandbox):
    calls = install(monkeypatch, [rejection(429, 20), success(11), rejection(429, 20)])
    result = notify.send_text("甲" * 4097, parse_mode=None)
    assert len(calls) == 3
    assert sandbox["waits"] == [20]
    assert result["delivery"]["status"] == "retry_later"
    assert result["delivery"]["accepted_parts"] == 1
    assert result["delivery"]["retry_after"] == 20
    assert result["delivery"]["inline_wait_seconds"] == 20


def test_exact_shared_budget_allows_retry_without_early_send(monkeypatch, sandbox):
    calls = install(monkeypatch, [rejection(429, 15), success(11), rejection(429, 15), success(12)])
    result = notify.send_text("甲" * 4097, parse_mode=None)
    assert len(calls) == 4 and result["ok"] is True
    assert sandbox["waits"] == [15, 15]
    assert result["delivery"]["inline_wait_seconds"] == 30


def test_server_backoff_and_rate_limit_spend_same_text_budget(monkeypatch, sandbox):
    calls = install(monkeypatch, [rejection(429, 20), success(11), rejection(503), rejection(429, 10)])
    result = notify.send_text("甲" * 4097, parse_mode=None)
    assert len(calls) == 4 and sandbox["waits"] == [20, 5]
    assert result["delivery"]["status"] == "retry_later"
    assert result["delivery"]["inline_wait_seconds"] == 25


@pytest.mark.parametrize("http_code,api_code", [(503, 403), (429, 503), (403, 429), (500, 502)])
def test_contradictory_failure_codes_stop_before_retry(monkeypatch, sandbox, http_code, api_code):
    calls = install(monkeypatch, [reply({"ok": False, "error_code": api_code,
                                       "parameters": {"retry_after": 1}}, http_code)])
    result = notify.send_text("結果矛盾")
    assert len(calls) == 1 and sandbox["waits"] == []
    assert result["delivery"]["status"] == "unknown"
    assert result["delivery"]["resume"]["unknown_part"] == 0


@pytest.mark.parametrize("http_code", [500, 502, 503])
def test_non_json_server_response_does_not_duplicate_potential_acceptance(monkeypatch, sandbox, http_code):
    calls = install(monkeypatch, [reply(None, http_code, raw=b"untrusted proxy body")])
    result = notify.send_text("可能已到達")
    assert len(calls) == 1 and sandbox["waits"] == []
    assert result["delivery"]["status"] == "unknown"
    assert "untrusted proxy body" not in str(result)


@pytest.mark.parametrize("invalid_result", [None, [], "accepted", {}, {"message_id": True}, {"message_id": 0}])
def test_photo_requires_usable_acceptance_receipt(monkeypatch, sandbox, tmp_path, invalid_result):
    calls = install(monkeypatch, [reply({"ok": True, "result": invalid_result})])
    image = tmp_path / "synthetic.jpg"
    image.write_bytes(b"synthetic upload")
    result = notify.send_photo(image)
    assert len(calls) == 1 and sandbox["waits"] == []
    assert result["ok"] is False and result["delivery"]["status"] == "unknown"


def test_unknown_after_first_acceptance_blocks_all_automatic_resume(monkeypatch, sandbox):
    source = "甲" * 8193
    calls = install(monkeypatch, [success(11), requests.ReadTimeout("sensitive ambiguous URL")])
    first = notify.send_text(source, parse_mode=None)
    assert len(calls) == 2
    assert first["delivery"]["status"] == "unknown"
    assert first["delivery"]["accepted_parts"] == 1
    assert first["delivery"]["resume"]["unknown_part"] == 1
    calls = install(monkeypatch, [])
    second = notify.send_text(source, parse_mode=None, resume=first["delivery"]["resume"])
    assert calls == [] and second["delivery"]["status"] == "unknown"
    assert second["delivery"]["message_ids"] == [11]


@pytest.mark.parametrize("entries,unknown", [
    ([{"index": True, "message_id": 11}], None),
    ([{"index": 0, "message_id": True}], None),
    ([{"index": 0, "message_id": 11}, {"index": 0, "message_id": 12}], None),
    ([{"index": 2, "message_id": 11}], None),
    ([{"index": 0, "message_id": 11}], 0),
    ([], True),
    ([], -1),
])
def test_malformed_resume_never_issues_request(monkeypatch, sandbox, entries, unknown):
    source = "甲" * 4097
    install(monkeypatch, [success(11), rejection(403)])
    receipt = copy.deepcopy(notify.send_text(source, parse_mode=None)["delivery"]["resume"])
    receipt["accepted"] = entries
    if unknown is not None:
        receipt["unknown_part"] = unknown
    calls = install(monkeypatch, [])
    with pytest.raises(ValueError):
        notify.send_text(source, parse_mode=None, resume=receipt)
    assert calls == []


def test_explicit_blank_file_value_never_falls_back_to_process_credential(monkeypatch, sandbox):
    sandbox["path"].write_text("TG_BOT_TOKEN=\nTG_CHAT_ID=1001\n")
    monkeypatch.setenv("TG_BOT_TOKEN", "synthetic-process-fallback")
    with pytest.raises(RuntimeError, match="缺少"):
        notify.send_text("不可錯用程序設定")


def test_reloading_settings_observes_file_change_without_exporting_unrelated_values(monkeypatch, sandbox):
    install(monkeypatch, [success(11)])
    notify.send_text("第一筆")
    sandbox["path"].write_text("TG_BOT_TOKEN=synthetic-rotated\nTG_CHAT_ID=2001\nTG_API_HASH=unrelated\n")
    calls = install(monkeypatch, [success(12)])
    notify.send_text("第二筆")
    assert calls[0][0].endswith("botsynthetic-rotated/sendMessage")
    assert calls[0][1]["json"]["chat_id"] == "2001"
    assert "TG_API_HASH" not in notify.os.environ


@pytest.mark.parametrize("failure", ["exception", "api"])
def test_known_credential_never_escapes_failure_or_cli_output(monkeypatch, sandbox, capsys, failure):
    token = sandbox["values"]["TG_BOT_TOKEN"]
    leak = f"https://api.telegram.org/bot{token}/sendMessage"
    response = (requests.ConnectionError(leak) if failure == "exception" else
                reply({"ok": False, "error_code": 403, "description": leak,
                       "parameters": {"nested": {"token": token}}}, 403))
    calls = install(monkeypatch, [response])
    result = notify.send_text("去敏案例")
    assert token not in json.dumps(result)
    assert len(calls) == 1
    install(monkeypatch, [response])
    assert notify.main(["去敏案例"]) in (1, 5)
    captured = capsys.readouterr()
    assert token not in captured.out + captured.err


@pytest.mark.parametrize("override", [False, True])
def test_fresh_import_defaults_to_clone_config_and_honors_explicit_override(monkeypatch, sandbox, override):
    if override:
        monkeypatch.setenv("TG_CONFIG_ENV_PATH", str(sandbox["path"]))
    spec = importlib.util.spec_from_file_location("independent_notify_probe", ROOT / "tg_notify.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    expected = sandbox["path"] if override else ROOT / ".env"
    assert Path(probe._ENV_PATH).resolve() == expected.resolve()
    # 匯入只核對預設位置，不呼叫 probe 的設定載入器；之後仍強制合成設定。
    monkeypatch.setattr(probe, "_ENV_PATH", str(sandbox["path"]))


def test_success_nested_fields_remove_only_known_credentials(monkeypatch, sandbox):
    token = sandbox["values"]["TG_BOT_TOKEN"]
    install(monkeypatch, [reply({"ok": True, "result": {
        "message_id": 11, "text": "正常訊息與欄位保留",
        "diagnostic": [token, {"authorization": token, "counter": 7}],
    }, "extra": {"token": token}})])
    result = notify.send_text("正常訊息與欄位保留")
    assert result["ok"] is True and token not in json.dumps(result)
    assert result["result"]["text"] == "正常訊息與欄位保留"
    assert result["result"]["diagnostic"][1]["counter"] == 7


@pytest.mark.parametrize("name", ["tg-message", "tg-send", "tgsend", "tg", "tgbots"])
def test_launchers_execute_checkout_local_target_with_literal_arguments(monkeypatch, sandbox, tmp_path, name):
    checkout = tmp_path / "independent checkout with spaces"
    checkout.mkdir()
    filenames = {name, "tg"}
    if name in {"tg-send", "tgsend"}:
        filenames.add("tg-message")
    for filename in filenames:
        source = (ROOT / filename).read_text()
        # 在啟動前先拒絕舊launcher，避免錯誤版本繞過假的uv而發出真實請求。
        assert str(Path.home() / "tg_config") not in source
        assert str(Path.home() / ".local/bin/tg") not in source
        if filename in {"tg", "tg-message"}:
            assert "UV_BIN" in source
        shutil.copyfile(ROOT / filename, checkout / filename)
        (checkout / filename).chmod(0o700)
    record = tmp_path / "launcher-args.json"
    fake_uv = tmp_path / "fake-uv"
    fake_uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['RECORD']).write_text(json.dumps(sys.argv[1:]))\n"
    )
    fake_uv.chmod(0o700)
    marker = "literal argument with spaces $(must-not-run)"
    result = subprocess.run(
        [sys.executable if name == "tg" else "bash", str(checkout / name), marker], cwd=tmp_path,
        env={"PATH": ":".join((str(Path(sys.executable).parent), "/usr/bin", "/bin")),
             "UV_BIN": str(fake_uv), "RECORD": str(record)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    args = json.loads(record.read_text())
    target = "tg_notify.py" if name in {"tg-message", "tg-send", "tgsend"} else "tg_cli.py"
    assert args[:5] == ["run", "--project", str(checkout), "python", str(checkout / target)]
    assert args[-1] == marker
    assert not any(str(Path.home() / "tg_config") in value for value in args)


def test_legacy_python_tg_help_runs_without_configuration_or_network(monkeypatch, sandbox, tmp_path):
    uv_bin = notify.os.environ.get("UV_BIN") or shutil.which("uv")
    if not uv_bin or not shutil.which(uv_bin):
        pytest.skip("此help案例需要可執行的uv；請設定UV_BIN或將uv加入PATH")
    checkout = tmp_path / "independent help checkout with spaces"
    checkout.mkdir()
    for filename in ("tg", "tg_cli.py", "tg_notify.py", "tg_delivery.py", "tg_settings.py", "provision_telegram_bot.py", "tg_i18n.py", "pyproject.toml", "uv.lock"):
        shutil.copyfile(ROOT / filename, checkout / filename)
    shutil.copytree(ROOT / "languages", checkout / "languages")
    guard = tmp_path / "sitecustomize.py"
    guard.write_text(
        "import socket, urllib.request\n"
        "def blocked(*args, **kwargs):\n"
        "    raise AssertionError('legacy tg help must stay offline')\n"
        "socket.socket.connect = blocked\n"
        "socket.socket.connect_ex = blocked\n"
        "socket.create_connection = blocked\n"
        "urllib.request.urlopen = blocked\n"
    )
    env = {key: value for key, value in notify.os.environ.items() if not key.startswith("TG_")}
    env.update(PYTHONPATH=str(tmp_path), TG_CONFIG_ENV_PATH=str(tmp_path / "must-not-exist.env"),
               TG_CONFIG_STATE_DIR=str(tmp_path / "must-not-exist-state"), UV_BIN=uv_bin,
               UV_OFFLINE="1", UV_PROJECT_ENVIRONMENT=sys.prefix)
    result = subprocess.run(
        [sys.executable, str(checkout / "tg"), "--help"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
    assert not (tmp_path / "must-not-exist.env").exists()
    assert not (tmp_path / "must-not-exist-state").exists()
    assert not list(checkout.rglob("*.session*"))


SYNTHETIC_HOME = Path("/nonexistent-synthetic-home")


def load_tool_without_telethon(monkeypatch, filename):
    def forbidden_client(*_args, **_kwargs):
        raise AssertionError("工具預設值檢查不可建立Telegram client或Session")

    package = types.ModuleType("telethon")
    errors = types.ModuleType("telethon.errors")
    errors.SessionPasswordNeededError = type("SyntheticPasswordNeeded", (Exception,), {})
    sync = types.ModuleType("telethon.sync")
    sync.TelegramClient = forbidden_client
    monkeypatch.setitem(sys.modules, "telethon", package)
    monkeypatch.setitem(sys.modules, "telethon.errors", errors)
    monkeypatch.setitem(sys.modules, "telethon.sync", sync)
    # 合成家目錄只供路徑計算，不建立真實 Session。 / Use a synthetic home for path calculations only.
    monkeypatch.setattr(Path, "home", lambda: SYNTHETIC_HOME)
    spec = importlib.util.spec_from_file_location("independent_tool_probe", ROOT / filename)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    return probe


@pytest.mark.parametrize("override", [False, True])
def test_bot_provision_defaults_cannot_reuse_original_config_or_session(monkeypatch, sandbox, tmp_path, override):
    state = tmp_path / "synthetic-state"
    monkeypatch.delenv("TG_CONFIG_STATE_DIR", raising=False)
    if override:
        monkeypatch.setenv("TG_CONFIG_ENV_PATH", str(sandbox["path"]))
        monkeypatch.setenv("TG_CONFIG_STATE_DIR", str(state))
    probe = load_tool_without_telethon(monkeypatch, "provision_telegram_bot.py")
    assert Path(probe.DEFAULT_ENV_PATH) == (sandbox["path"] if override else ROOT / ".env")
    selected_state = state if override else Path(probe.DEFAULT_STATE_DIR)
    assert Path(probe.DEFAULT_SESSION_PATH).is_relative_to(selected_state)
    assert Path(probe.DEFAULT_LOGIN_STATE_PATH).is_relative_to(selected_state)
    if not override:
        assert selected_state == SYNTHETIC_HOME / ".local" / "state" / "telegram-bot-setup"
    assert not state.exists()
