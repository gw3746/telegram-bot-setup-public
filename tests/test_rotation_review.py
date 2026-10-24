"""以合成設定獨立驗證輪換審查 R1–R5；不得接觸現用憑證與網路。"""
from __future__ import annotations

import ast
import builtins
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import rotate_telegram_bot_tokens as rotation
import tg_notify as notify


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rotation_case(monkeypatch, tmp_path):
    old = "123456789:" + "review_old_" * 4
    new = "123456789:" + "review_new_" * 4
    path = tmp_path / "main" / ".env"
    path.parent.mkdir()
    path.write_text("TG_BOT_TOKEN=" + old + "\nOWNER=main\n")
    path.chmod(0o600)
    state = tmp_path / "rotation-state"
    client = Mock()
    revoke = Mock(return_value=new)
    monkeypatch.setattr(rotation, "STATE_DIR", state)
    monkeypatch.setattr(rotation, "get_me", lambda *_: "synthetic_review_bot")
    monkeypatch.setattr(rotation, "revoke", revoke)
    monkeypatch.setattr(rotation, "require_authorized_client", lambda *_: client)
    monkeypatch.setattr(sys, "argv", ["rotation", "--env-path", str(path),
                                     "--session-path", str(tmp_path / "never-created-session")])
    return SimpleNamespace(old=old, new=new, path=path, state=state, revoke=revoke, client=client)


def run_failure():
    """同時接受公開 main 的例外契約及非零回傳，避免把原始錯誤印入報告。"""
    try:
        result = rotation.main()
    except Exception:
        return True
    return result != 0


def recovery_records(state, value):
    result = []
    for path in state.rglob("*.json"):
        data = path.read_text()
        if value in data:
            json.loads(data)
            result.append((path, data))
    return result


def test_r1_revoke_is_journaled_before_new_token_validation(monkeypatch, rotation_case):
    case = rotation_case
    observed = {}

    def get_me(token):
        if token == case.old:
            return "synthetic_review_bot"
        records = recovery_records(case.state, case.new)
        observed["durable"] = bool(records)
        observed["private"] = bool(records) and all(stat.S_IMODE(p.stat().st_mode) <= 0o600 for p, _ in records)
        observed["unchanged"] = case.old in case.path.read_text()
        observed["pending"] = any("verified" in data or "取得" in data or "pending" in data
                                  or "acquired" in data for _, data in records)
        raise requests.ConnectionError("synthetic validation offline")

    monkeypatch.setattr(rotation, "get_me", get_me)
    assert run_failure(), "新值驗證失敗必須停止並回報失敗"
    assert observed.get("durable"), "驗證呼叫之前尚未持久保存新值"
    assert observed.get("private"), "恢復紀錄必須受0600保護"
    assert observed.get("pending"), "恢復紀錄必須區分取得與完成"
    assert observed.get("unchanged"), "未驗證的新值不可套用設定"
    assert case.old in case.path.read_text(), "驗證失敗後有效設定應維持舊值"
    case.revoke.assert_called_once()


def test_r1_identity_mismatch_keeps_recoverable_new_token(monkeypatch, rotation_case):
    case = rotation_case
    monkeypatch.setattr(rotation, "get_me", Mock(side_effect=["synthetic_review_bot", "different_bot"]))
    assert run_failure(), "身份不符必須失敗"
    assert recovery_records(case.state, case.new), "身份不符仍須保存已取得的新值以供人工恢復"
    assert case.old in case.path.read_text(), "身份不符不可套用設定"


def test_r2_secret_temporary_files_are_private_from_creation(monkeypatch, rotation_case):
    case = rotation_case
    observed = []
    original_path_open = Path.open
    original_os_open = os.open

    def path_open(path, mode="r", *args, **kwargs):
        stream = original_path_open(path, mode, *args, **kwargs)
        if any(flag in mode for flag in "wax") and Path(path).parent == case.path.parent:
            observed.append(stat.S_IMODE(os.fstat(stream.fileno()).st_mode))
        return stream

    def os_open(path, flags, mode=0o777, *args, **kwargs):
        fd = original_os_open(path, flags, mode, *args, **kwargs)
        if flags & os.O_CREAT and Path(path).parent == case.path.parent:
            observed.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return fd

    monkeypatch.setattr(Path, "open", path_open)
    monkeypatch.setattr(os, "open", os_open)
    previous_umask = os.umask(0o022)
    try:
        rotation.replace_in_files([case.path], case.old, case.new)
    finally:
        os.umask(previous_umask)
    assert observed, "必須實際觀察暫存檔建立當下權限"
    assert all(mode & 0o177 == 0 for mode in observed), "含秘密暫存檔曾在建立時對其他帳號開放"
    assert stat.S_IMODE(case.path.stat().st_mode) == 0o600


def test_r2_existing_rotate_tmp_symlink_is_never_followed(rotation_case):
    case = rotation_case
    target = case.path.parent / "unrelated-target"
    target.write_text("synthetic independent target\n")
    legacy = case.path.with_name(case.path.name + ".rotate_tmp")
    legacy.symlink_to(target)
    try:
        rotation.replace_in_files([case.path], case.old, case.new)
    except OSError:
        pass
    assert target.read_text() == "synthetic independent target\n", "既有symlink目標遭覆寫"
    assert legacy.is_symlink(), "不可刪除其他執行者的暫存symlink"


def test_r2_replace_failure_cleans_only_its_own_temporary(monkeypatch, rotation_case):
    case = rotation_case
    legacy = case.path.with_name(case.path.name + ".rotate_tmp")
    legacy.write_text("synthetic other process temporary\n")
    before = set(case.path.parent.iterdir())
    original_path_replace = Path.replace
    original_os_replace = os.replace

    def path_replace(source, destination):
        if Path(destination) == case.path:
            raise OSError("synthetic replace failure")
        return original_path_replace(source, destination)

    def os_replace(source, destination, *args, **kwargs):
        if Path(destination) == case.path:
            raise OSError("synthetic replace failure")
        return original_os_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", path_replace)
    monkeypatch.setattr(os, "replace", os_replace)
    with pytest.raises(Exception):
        rotation.replace_in_files([case.path], case.old, case.new)
    assert case.old in case.path.read_text(), "替換失敗必須保護原設定"
    assert legacy.read_text() == "synthetic other process temporary\n", "不得覆寫他人暫存"
    assert set(case.path.parent.iterdir()) == before, "失敗後只應清理本次建立的暫存"


def test_r3_same_basename_sources_have_distinct_backups_and_manifest(monkeypatch, rotation_case):
    case = rotation_case
    consumer = case.path.parent.parent / "consumer" / ".env"
    consumer.parent.mkdir()
    consumer.write_text("TOKEN=" + case.old + "\nOWNER=consumer\n")
    consumer.chmod(0o600)
    originals = {case.path: case.path.read_bytes(), consumer: consumer.read_bytes()}
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--consumer-file", str(consumer)])
    assert rotation.main() == 0
    backups = {}
    for source, content in originals.items():
        backups[source] = [p for p in case.state.rglob("*") if p.is_file() and p.read_bytes() == content]
    assert all(backups.values()), "不同目錄同名設定必須各自保留原始備份"
    assert len({backups[source][0] for source in originals}) == 2, "備份不得互相覆蓋"
    manifests = [p for p in case.state.rglob("*.json") if "manifest" in p.name]
    assert manifests, "必須保存來源到備份的manifest"
    manifest_text = "\n".join(json.dumps(json.loads(p.read_text())) for p in manifests)
    assert all(str(source) in manifest_text and backups[source][0].name in manifest_text
               for source in originals), "manifest必須能對應完整來源與獨立備份"


def test_r3_backup_read_failure_prevents_every_revoke(monkeypatch, rotation_case):
    case = rotation_case
    consumer = case.path.parent.parent / "blocked-consumer.env"
    consumer.write_text("TOKEN=" + case.old + "\n")
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--consumer-file", str(consumer)])
    original_path_open, original_open, original_copy = Path.open, builtins.open, shutil.copy2
    original_os_open = os.open

    def path_open(path, *args, **kwargs):
        if Path(path) == consumer:
            raise OSError("synthetic required backup unavailable")
        return original_path_open(path, *args, **kwargs)

    def file_open(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)) and Path(path) == consumer:
            raise OSError("synthetic required backup unavailable")
        return original_open(path, *args, **kwargs)

    def copy(source, destination, *args, **kwargs):
        if Path(source) == consumer:
            raise OSError("synthetic required backup unavailable")
        return original_copy(source, destination, *args, **kwargs)

    def os_open(path, flags, mode=0o777, *args, **kwargs):
        if Path(path) == consumer and not flags & os.O_CREAT:
            raise OSError("synthetic required backup unavailable")
        return original_os_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", path_open)
    monkeypatch.setattr(builtins, "open", file_open)
    monkeypatch.setattr(shutil, "copy2", copy)
    monkeypatch.setattr(os, "open", os_open)
    assert run_failure(), "必要備份失敗必須停止"
    case.revoke.assert_not_called()


def add_second_bot(case):
    other = "987654321:" + "review_other_" * 4
    case.path.write_text(case.path.read_text() + "TG_Z_OTHER_TOKEN=" + other + "\n")
    return other


@pytest.mark.parametrize("operation", ["write", "fsync"])
def test_r1_journal_io_failure_stops_before_next_bot(monkeypatch, rotation_case, capsys, operation):
    case = rotation_case
    add_second_bot(case)
    original_fsync, original_write, original_replace = os.fsync, os.write, os.replace
    triggered = []

    def should_fail(fd):
        if not case.revoke.called:
            return False
        destination = Path(os.readlink(f"/proc/self/fd/{fd}"))
        return destination.is_relative_to(case.state)

    def fsync(fd):
        if operation == "fsync" and should_fail(fd):
            triggered.append(True)
            raise OSError("synthetic journal persistence unavailable")
        return original_fsync(fd)

    def write(fd, content):
        if operation == "write" and should_fail(fd):
            triggered.append(True)
            raise OSError("synthetic journal persistence unavailable")
        return original_write(fd, content)

    def replace(source, destination, *args, **kwargs):
        # TextIO寫入不經os.write時，在原子發布點注入同樣的寫入失敗。
        if operation == "write" and case.revoke.called and Path(destination).is_relative_to(case.state):
            triggered.append(True)
            raise OSError("synthetic journal publish unavailable")
        return original_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "write", write)
    monkeypatch.setattr(os, "replace", replace)
    assert run_failure(), "取得新值後journal寫入失敗不可回報成功"
    assert triggered, "必須確實注入取得新值後的journal故障"
    assert case.revoke.call_count == 1, "journal失敗後不得繼續撤銷其他Bot"
    assert case.old in case.path.read_text(), "journal未安全保存時不可更新設定"
    output = capsys.readouterr()
    assert "ROTATED" not in output.out, "持久化失敗不可輸出完成訊息"
    assert case.old not in output.out + output.err and case.new not in output.out + output.err
    case.client.disconnect.assert_called_once()


def test_r1_second_consumer_failure_retains_progress_and_stops_next_bot(monkeypatch, rotation_case):
    case = rotation_case
    add_second_bot(case)
    consumers = [case.path.parent.parent / name for name in ("consumer-one.env", "consumer-two.env")]
    for path in consumers:
        path.write_text("TOKEN=" + case.old + "\n")
        path.chmod(0o600)
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--consumer-file", str(consumers[0]),
                                     "--consumer-file", str(consumers[1])])
    original_replace = os.replace
    injected = []

    def replace(source, destination, *args, **kwargs):
        if Path(destination) == consumers[1]:
            injected.append(True)
            raise OSError("synthetic second consumer publish failure")
        return original_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    assert run_failure(), "部分consumer更新失敗必須停止"
    assert injected, "必須實際到達第二個consumer更新"
    assert case.revoke.call_count == 1, "部分失敗後不得繼續撤銷下一Bot"
    assert case.new in case.path.read_text() and case.new in consumers[0].read_text()
    assert case.old in consumers[1].read_text()
    journals = [(p, text) for p, text in recovery_records(case.state, case.new) if "journal" in p.name]
    assert journals, "部分更新失敗必須保留已驗證新值的恢復journal"
    text = "\n".join(text for _, text in journals)
    assert all(str(path) in text for path in [case.path, *consumers]), "journal必須記錄每檔更新進度"
    assert "verified" in text and ("manual" in text or "人工" in text), "須保留已驗證及需人工恢復狀態"
    entry = json.loads(journals[0][1])["rotations"][0]
    assert entry["files"][str(case.path)]["stage"] == "completed"
    assert entry["files"][str(consumers[0])]["stage"] == "completed"
    assert entry["files"][str(consumers[1])]["stage"] != "completed", "失敗檔案不可被標記為已完成"


def test_r3_duplicate_source_and_same_time_runs_keep_independent_backups(monkeypatch, rotation_case):
    case = rotation_case
    later = "123456789:" + "review_later_" * 4
    case.revoke.side_effect = [case.new, later]
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--consumer-file", str(case.path),
                                     "--consumer-file", str(case.path)])
    fixed_now = rotation.datetime.now()
    monkeypatch.setattr(rotation, "datetime", SimpleNamespace(now=lambda: fixed_now))
    assert rotation.main() == 0
    assert rotation.main() == 0
    run_dirs = [path for path in case.state.iterdir() if path.is_dir()]
    assert len(run_dirs) == 2, "同秒執行必須建立兩個獨立run目錄"
    manifests = [path for path in case.state.rglob("*.json") if "manifest" in path.name]
    assert len(manifests) == 2
    for path in manifests:
        data = json.loads(path.read_text())
        assert len(data["sources"]) == 1, "同一來源重複指定必須先去重"
    assert later in case.path.read_text()


def test_r3_backup_publish_failure_prevents_every_revoke(monkeypatch, rotation_case):
    case = rotation_case
    original_replace = os.replace
    injected = []

    def replace(source, destination, *args, **kwargs):
        target = Path(destination)
        if target.is_relative_to(case.state) and target.suffix != ".json":
            injected.append(True)
            raise OSError("synthetic required backup destination unwritable")
        return original_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    assert run_failure(), "必要備份發布失敗必須停止"
    assert injected, "必須實際注入備份發布故障"
    case.revoke.assert_not_called()


def test_r3_source_symlink_is_rejected_before_revoke(rotation_case):
    case = rotation_case
    target = case.path.parent.parent / "synthetic-external.env"
    content = case.path.read_text()
    target.write_text(content)
    case.path.unlink()
    case.path.symlink_to(target)
    assert run_failure(), "來源設定symlink必須在任何revoke前安全拒絕"
    case.revoke.assert_not_called()
    assert case.path.is_symlink() and target.read_text() == content


@pytest.mark.parametrize("failure", ["connect_timeout", "read_timeout", "connection", "json", "http", "api"])
def test_r4_real_cli_safely_handles_getme_failures(tmp_path, failure):
    old = "123456789:" + "review_old_" * 4
    new = "123456789:" + "review_new_" * 4
    path = tmp_path / "synthetic.env"
    path.write_text("TG_BOT_TOKEN=" + old + "\n")
    # 在子程序修補requests後經__main__入口執行；任何未預期真網仍由socket阻擋。
    script = """
import json, runpy, socket, sys
from pathlib import Path
from types import SimpleNamespace
import requests
def blocked(*args, **kwargs):
    raise AssertionError('synthetic subprocess forbids live network')
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
requests.sessions.Session.request = blocked
tool, env_path, failure = sys.argv[1:]
old = '123456789:' + 'review_old_' * 4
new = '123456789:' + 'review_new_' * 4
raw = 'https://api.telegram.org/bot' + old + '/getMe ' + new
def fake_get(*args, **kwargs):
    errors = {'connect_timeout': requests.ConnectTimeout,
              'read_timeout': requests.ReadTimeout, 'connection': requests.ConnectionError}
    if failure in errors:
        raise errors[failure](raw)
    response = requests.Response()
    response.status_code = 503 if failure == 'http' else 200
    response._content = (raw.encode() if failure == 'json' else
        json.dumps({'ok': failure == 'http', 'result': {'username': 'synthetic_review_bot'},
                    'description': raw, 'error_code': 400}).encode())
    return response
requests.get = fake_get
sys.path.insert(0, str(Path(tool).parent))
sys.argv = [tool, '--env-path', env_path, '--dry-run']
runpy.run_path(tool, run_name='__main__')
"""
    env = {key: value for key, value in os.environ.items() if not key.startswith("TG_")}
    env.update(TG_CONFIG_ENV_PATH=str(path), TG_CONFIG_STATE_DIR=str(tmp_path / "state"))
    result = subprocess.run([sys.executable, "-c", script, str(ROOT / "rotate_telegram_bot_tokens.py"),
                             str(path), failure], env=env, capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr
    assert result.returncode != 0, "getMe失敗不得回報CLI成功"
    assert old not in output and new not in output, "CLI失敗輸出包含已知憑證"
    assert "https://api.telegram.org/bot" not in output, "CLI失敗輸出包含完整API網址"
    assert "Traceback" not in output, "CLI已知故障必須提供安全出口"


def invoke_existing_help_case(monkeypatch, tmp_path):
    """執行既有help案例本身，攔截最後子程序以獨立核對選用uv的行為。"""
    source = ROOT / "tests" / "test_dev_boundaries.py"
    node = next(node for node in ast.parse(source.read_text()).body if isinstance(node, ast.FunctionDef)
                and node.name == "test_legacy_python_tg_help_runs_without_configuration_or_network")
    node.decorator_list = []
    namespace = dict(ROOT=ROOT, Path=Path, shutil=shutil, sys=sys, notify=notify,
                     subprocess=subprocess, pytest=pytest)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    captured = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
                        captured.append(kwargs) or SimpleNamespace(returncode=0, stdout="usage: synthetic", stderr=""))
    namespace[node.name](monkeypatch, None, tmp_path)
    return captured[0]["env"]


@pytest.mark.parametrize("selection", ["override", "path"])
def test_r5_existing_help_case_respects_portable_uv_selection(monkeypatch, tmp_path, selection):
    uv = tmp_path / "portable uv bin" / "uv"
    uv.parent.mkdir()
    uv.write_text("#!/bin/sh\nexit 0\n")
    uv.chmod(0o700)
    monkeypatch.setenv("PATH", str(uv.parent))
    if selection == "override":
        override = tmp_path / "explicit override uv"
        override.write_text("#!/bin/sh\nexit 0\n")
        override.chmod(0o700)
        monkeypatch.setenv("UV_BIN", str(override))
        expected = str(override)
    else:
        monkeypatch.delenv("UV_BIN", raising=False)
        expected = str(uv)
    env = invoke_existing_help_case(monkeypatch, tmp_path)
    assert env["UV_BIN"] == expected, "help案例必須尊重UV_BIN或PATH，不得強制改成個人路徑"


def test_r5_missing_uv_skips_only_help_case_with_explicit_reason(monkeypatch, tmp_path):
    monkeypatch.delenv("UV_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    with pytest.raises(pytest.skip.Exception, match="uv"):
        invoke_existing_help_case(monkeypatch, tmp_path)


@pytest.mark.parametrize("source_mode,expected", [(0o400, 0o400), (0o600, 0o600), (0o644, 0o600), (0o666, 0o600)])
def test_acceptance_replacement_never_broadens_private_file_mode(rotation_case, source_mode, expected):
    case = rotation_case
    case.path.chmod(source_mode)
    assert rotation.replace_in_files([case.path], case.old, case.new) == [str(case.path)]
    assert stat.S_IMODE(case.path.stat().st_mode) == expected
    assert case.new in case.path.read_text()


def test_acceptance_published_journal_survives_directory_sync_failure(monkeypatch, rotation_case, capsys):
    case = rotation_case
    add_second_bot(case)
    original_fsync = os.fsync
    injected = []

    def fsync(fd):
        if (not injected and case.revoke.called and stat.S_ISDIR(os.fstat(fd).st_mode)
                and recovery_records(case.state, case.new)):
            injected.append(True)
            raise OSError("synthetic directory sync failure after journal publication")
        return original_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    assert rotation.cli() != 0
    assert injected and case.revoke.call_count == 1
    records = recovery_records(case.state, case.new)
    assert records and all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path, _ in records)
    assert case.old in case.path.read_text()
    assert any("obtained_pending_verification" in text for _, text in records)
    output = capsys.readouterr()
    assert case.old not in output.out + output.err and case.new not in output.out + output.err
    assert "RECOVERY_DIR=" in output.err and "ROTATED" not in output.out


def test_acceptance_unknown_revoke_is_not_retried(monkeypatch, rotation_case, capsys):
    case = rotation_case
    add_second_bot(case)
    case.revoke.side_effect = requests.ReadTimeout("synthetic unknown external outcome")
    assert rotation.cli() != 0
    assert case.revoke.call_count == 1 and case.old in case.path.read_text()
    journals = [json.loads(path.read_text()) for path in case.state.rglob("journal.json")]
    assert len(journals) == 1 and journals[0]["stage"] == "needs_manual_recovery"
    assert "new_token" not in journals[0]["rotations"][0]
    output = capsys.readouterr()
    assert "Traceback" not in output.err and "ROTATED" not in output.out


def test_acceptance_getme_accepts_user_identity_without_message_receipt(monkeypatch):
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps({"ok": True, "result": {
        "id": 42, "is_bot": True, "username": "synthetic_review_bot"}}).encode()
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: response)
    assert rotation.get_me("synthetic-token") == "synthetic_review_bot"
