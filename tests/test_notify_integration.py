"""Offline regressions for the existing tg_config notification entry points.

Every credential is synthetic. Real Session.send/socket connect calls are denied.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import socket
import sys

import pytest
import requests

CANDIDATE = Path(__file__).resolve().parents[1]
if str(CANDIDATE) not in sys.path:
    sys.path.insert(0, str(CANDIDATE))

import tg_notify as notify
import sys_notify


EXPECTED_CONFIG = {"DEFAULT": ("TG_BOT_TOKEN", "TG_CHAT_ID")}


@pytest.fixture(autouse=True)
def isolated_credentials_and_network(monkeypatch, tmp_path):
    def denied(*_args, **_kwargs):
        raise AssertionError("A real network operation was attempted")

    monkeypatch.setattr(requests.sessions.Session, "send", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    values = {}
    for number, (_kind, (token_key, chat_key)) in enumerate(EXPECTED_CONFIG.items(), 1):
        values.setdefault(token_key, "123456789:" + hashlib.sha256(token_key.encode()).hexdigest()[:35])
        values[chat_key] = str(1000 + number)
    values.update(TG_API_HASH="FAKE_HASH_MUST_NOT_BE_EXPORTED", TG_PHONE="+886900000000",
                  TG_2STEP_PASSWORD="FAKE_PASSWORD_MUST_NOT_BE_EXPORTED")
    for key in values:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "synthetic.env"
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    monkeypatch.setattr(notify, "_ENV_PATH", str(path))
    waits = []
    monkeypatch.setattr(notify.time, "sleep", waits.append)
    return {"values": values, "path": path, "waits": waits}


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    result.headers["Content-Type"] = "application/json"
    return result


def accepted(ident=101):
    return response({"ok": True, "result": {"message_id": ident, "text": "synthetic"}})


def reject(code, **parameters):
    payload = {"ok": False, "error_code": code, "description": "synthetic rejection"}
    if parameters:
        payload["parameters"] = parameters
    return response(payload, code)


def install_post(monkeypatch, replies):
    calls = []
    sequence = iter(replies)

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        result = next(sequence)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(notify.requests, "post", fake_post)
    return calls


@pytest.mark.parametrize("kind", list(EXPECTED_CONFIG))
@pytest.mark.parametrize("lowercase", [False, True])
def test_generic_route_sends_to_configured_destination(monkeypatch, isolated_credentials_and_network, kind, lowercase):
    assert notify._BOT_CONFIG == EXPECTED_CONFIG
    token_key, chat_key = EXPECTED_CONFIG[kind]
    values = isolated_credentials_and_network["values"]
    selected = kind.lower() if lowercase else kind
    assert notify.get_bot_credentials(selected) == (values[token_key], values[chat_key])
    calls = install_post(monkeypatch, [accepted()])
    result = notify.send_text("route check", selected)
    assert result["ok"] is True and result["result"]["message_id"] == 101
    assert calls[0][0] == f"https://api.telegram.org/bot{values[token_key]}/sendMessage"
    assert calls[0][1]["json"]["chat_id"] == values[chat_key]


def test_file_still_overrides_process_environment(monkeypatch, isolated_credentials_and_network):
    monkeypatch.setenv("TG_BOT_TOKEN", "wrong-process-token")
    monkeypatch.setenv("TG_CHAT_ID", "wrong-process-chat")
    expected = isolated_credentials_and_network["values"]
    assert notify.get_bot_credentials("DEFAULT") == (expected["TG_BOT_TOKEN"], expected["TG_CHAT_ID"])


def test_only_selected_keys_are_retained_and_nothing_exported(monkeypatch, isolated_credentials_and_network):
    seen = []
    original = notify._load_env_file

    def observe(path, keys=None):
        result = original(path, keys)
        seen.append((keys, set(result)))
        return result

    monkeypatch.setattr(notify, "_load_env_file", observe)
    before = dict(os.environ)
    notify.get_bot_credentials("DEFAULT")
    selected = {"TG_BOT_TOKEN", "TG_CHAT_ID"}
    assert seen == [(selected, selected)]
    assert dict(os.environ) == before
    assert "TG_API_HASH" not in os.environ and "TG_2STEP_PASSWORD" not in os.environ


def test_missing_file_can_use_process_environment(monkeypatch, isolated_credentials_and_network):
    isolated_credentials_and_network["path"].unlink()
    monkeypatch.setenv("TG_BOT_TOKEN", "synthetic-process-token")
    monkeypatch.setenv("TG_CHAT_ID", "42")
    assert notify.get_bot_credentials("default") == ("synthetic-process-token", "42")


@pytest.mark.parametrize("mode,text,expected", [
    ("HTML", '<b>a & "b"</b>', '&lt;b&gt;a &amp; &quot;b&quot;&lt;/b&gt;'),
    (None, "a < b & c", "a < b & c"),
    ("MarkdownV2", "*bold*", "*bold*"),
])
def test_short_text_retains_legacy_payload_and_result(monkeypatch, mode, text, expected):
    calls = install_post(monkeypatch, [accepted()])
    result = notify.send_text(text, "DEFAULT", mode)
    payload = calls[0][1]["json"]
    assert payload["text"] == expected
    assert payload.get("parse_mode") == mode
    assert ("parse_mode" in payload) == (mode is not None)
    assert result["ok"] is True and result["result"] == {"message_id": 101, "text": "synthetic"}
    assert "results" not in result
    assert calls[0][1]["timeout"] == 10


def test_long_literal_html_is_split_before_escaping_and_preserves_emoji(monkeypatch):
    source = ('<b>工廠 & 報告 😀</b>\n' * 500)
    replies = [accepted(number) for number in range(1, 100)]
    calls = install_post(monkeypatch, replies)
    result = notify.send_text(source)
    chunks = [html.unescape(kwargs["json"]["text"]) for _url, kwargs in calls]
    assert len(chunks) > 1
    assert "".join(chunks) == source
    assert all(len(part.encode("utf-16-le")) // 2 <= 4096 for part in chunks)
    assert all(kwargs["json"]["text"] == html.escape(part)
               for (_url, kwargs), part in zip(calls, chunks))
    assert result["ok"] is True
    assert len(result["results"]) == len(chunks)


def test_long_markdown_is_explicitly_rejected_before_network(monkeypatch):
    calls = install_post(monkeypatch, [])
    result = notify.send_text("*" + "x" * 5000 + "*", parse_mode="MarkdownV2")
    assert result["ok"] is False
    assert result["delivery"]["error_kind"] == "unsupported_format"
    assert calls == []


def test_partial_text_resume_skips_accepted_piece(monkeypatch):
    source = "甲" * 4097
    first = install_post(monkeypatch, [accepted(101), reject(403)])
    result = notify.send_text(source, "DEFAULT", None)
    assert len(first) == 2 and result["ok"] is False
    assert result["delivery"]["status"] == "partial"
    receipt = result["delivery"]["resume"]
    second = install_post(monkeypatch, [accepted(202)])
    resumed = notify.send_text(source, "default", None, resume=receipt)
    assert len(second) == 1 and second[0][1]["json"]["text"] == "甲"
    assert resumed["ok"] is True
    assert resumed["delivery"]["message_ids"] == [101, 202]


@pytest.mark.parametrize("changed", ["destination", "content", "format"])
def test_resume_rejects_changed_operation(monkeypatch, isolated_credentials_and_network, changed):
    source = "甲" * 4097
    install_post(monkeypatch, [accepted(101), reject(403)])
    receipt = notify.send_text(source, "DEFAULT", None)["delivery"]["resume"]
    calls = install_post(monkeypatch, [])
    if changed == "destination":
        with isolated_credentials_and_network["path"].open("a") as handle:
            handle.write("\nTG_CHAT_ID=9999\n")
    with pytest.raises(ValueError, match="不符"):
        notify.send_text(source + ("乙" if changed == "content" else ""),
                         "DEFAULT",
                         "HTML" if changed == "format" else None, resume=receipt)
    assert calls == []


def test_unknown_receipt_never_blindly_resends(monkeypatch):
    calls = install_post(monkeypatch, [requests.ReadTimeout("synthetic ambiguous failure")])
    result = notify.send_text("first report")
    assert len(calls) == 1 and result["delivery"]["status"] == "unknown"
    after = install_post(monkeypatch, [])
    retried = notify.send_text("first report", resume=result["delivery"]["resume"])
    assert retried["ok"] is False and retried["delivery"]["status"] == "unknown"
    assert after == []


def test_photo_reopens_upload_on_retry_and_preserves_caption(monkeypatch, tmp_path, isolated_credentials_and_network):
    path = tmp_path / "sample.jpg"
    path.write_bytes(b"synthetic photo bytes")
    handles, contents, payloads = [], [], []

    def fake_post(url, **kwargs):
        name, handle, content_type = kwargs["files"]["photo"]
        assert name == path.name and content_type == "image/jpeg"
        assert not handle.closed
        handles.append(handle)
        contents.append(handle.read())
        payloads.append(kwargs)
        return reject(429, retry_after=2) if len(handles) == 1 else accepted()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    caption = "說明" * 700
    result = notify.send_photo(path, caption, "DEFAULT")
    assert result["ok"] is True
    assert len(handles) == 2 and handles[0] is not handles[1]
    assert all(handle.closed for handle in handles)
    assert contents == [b"synthetic photo bytes"] * 2
    assert all(kwargs["data"]["caption"] == caption[:1024] for kwargs in payloads)
    assert all(kwargs["timeout"] == 30 for kwargs in payloads)
    assert isolated_credentials_and_network["waits"] == [2]


@pytest.mark.parametrize("entry", [notify, sys_notify])
@pytest.mark.parametrize("status,code", [("success", 0), ("failed", 1), ("partial", 4),
                                         ("unknown", 5), ("retry_later", 6)])
def test_cli_exit_codes_reflect_delivery_outcome(monkeypatch, capsys, entry, status, code):
    monkeypatch.setattr(entry, "send_text", lambda *_args, **_kwargs: {
        "ok": status == "success", "description": "safe failure", "delivery": {"status": status}})
    assert entry.main(["test"]) == code
    captured = capsys.readouterr()
    assert (status in captured.err) == (status != "success")


@pytest.mark.parametrize("entry", [notify, sys_notify])
@pytest.mark.parametrize("args", [[], ["-h"], ["--help"]])
def test_cli_help_never_loads_credentials_or_sends(monkeypatch, entry, args):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Help tried to load credentials/send")

    monkeypatch.setattr(entry, "send_text", forbidden)
    monkeypatch.setattr(notify, "get_bot_credentials", forbidden)
    assert entry.main(args) == 0


@pytest.mark.parametrize("entry", [notify, sys_notify])
def test_cli_configuration_failure_is_safe_and_nonzero(monkeypatch, capsys, entry):
    fake_secret = "123456789:" + "Z" * 35

    def failed(*_args, **_kwargs):
        raise RuntimeError("config problem " + fake_secret)

    monkeypatch.setattr(entry, "send_text", failed)
    assert entry.main(["test"]) == 2
    assert fake_secret not in capsys.readouterr().err


def test_sys_notify_preserves_prefix_route_and_actual_plain_default(monkeypatch):
    calls = []

    def fake_send(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True}

    monkeypatch.setattr(sys_notify, "send_text", fake_send)
    assert sys_notify.main(["server up"]) == 0
    assert calls == [(("🖥️ 伺服器通知：\nserver up", "DEFAULT"), {"parse_mode": None})]


@pytest.mark.parametrize("flag,expected", [("NONE", None), ("text", None), ("plain", None), ("html", "HTML")])
def test_cli_parse_mode_aliases_are_preserved(monkeypatch, flag, expected):
    calls = []
    monkeypatch.setattr(notify, "send_text", lambda *args, **kwargs: calls.append(args) or {"ok": True})
    assert notify.main(["text", "DEFAULT", flag]) == 0
    assert calls[0] == ("text", "DEFAULT", expected)
