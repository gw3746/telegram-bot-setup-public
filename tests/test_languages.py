"""中英介面驗收：無真實 Telegram 流量 / Bilingual UI acceptance without live traffic."""
import ast
import importlib
import json
import os
import pty
from pathlib import Path
import re
import stat
import string
import subprocess
import sys
from types import SimpleNamespace

import pytest

import tg_i18n as ui
import tg_install
import tg_notify
import tg_receiver
import tg_setup
from test_first_run_install import installation, run_entry
from test_first_run_setup import Harness, config, OTP, PASSWORD, TOKEN


@pytest.fixture
def clean_language(monkeypatch, tmp_path):
    monkeypatch.delenv("TG_LANGUAGE", raising=False)
    ui._language.set(None)
    return tmp_path


def test_catalog_has_complete_pairs_and_identical_placeholders():
    english, chinese = ui.load_messages("en"), ui.load_messages("zh-TW")
    assert set(english) == set(chinese)
    catalog = {key: {"en": english[key], "zh-TW": chinese[key]} for key in english}
    formatter = string.Formatter()
    for key, pair in catalog.items():
        assert set(pair) == {"en", "zh-TW"}, key
        assert all(isinstance(value, str) and value for value in pair.values()), key
        assert not re.search(r"[\u4e00-\u9fff]", pair["en"]), key
        fields = lambda value: sorted((name, spec, conversion) for _, name, spec, conversion in formatter.parse(value) if name is not None)
        assert fields(pair["en"]) == fields(pair["zh-TW"]), key
        assert pair["en"].count("%s") == pair["zh-TW"].count("%s"), key


def test_production_message_calls_are_in_catalog_and_no_unwrapped_chinese():
    catalog = ui.load_messages("en")
    for path in ui.ROOT.glob("*.py"):
        if path.name in {"conftest.py", "tg_i18n.py"}:
            continue
        tree = ast.parse(path.read_text())
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                if node.args and isinstance(node.args[0], ast.Constant):
                    assert node.args[0].value in catalog, (path.name, node.lineno)
                    assert re.fullmatch(r"[a-z][a-z0-9_]*", node.args[0].value)
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if not re.search(r"[\u4e00-\u9fff]", node.value):
                continue
            parent = parents.get(node)
            if isinstance(parent, ast.Expr) or node.value in {"是", "否", "取消"}:
                continue
            if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "tr":
                continue
            pytest.fail(f"Untranslated project-owned message: {path.name}:{node.lineno}")


@pytest.mark.parametrize("language,flag,environment,saved", [
    ("en", [], None, None),
    ("zh-TW", [], None, "zh-TW"),
    ("en", [], "en", "zh-TW"),
    ("zh-TW", ["--language", "zh-TW"], "en", "en"),
    ("en", ["--language=en"], "INVALID_IGNORED", "zh-TW"),
])
def test_language_precedence(clean_language, monkeypatch, language, flag, environment, saved):
    if saved:
        ui.save_language(clean_language, saved)
    if environment:
        monkeypatch.setenv("TG_LANGUAGE", environment)
    assert ui.configure_language(flag + ["--check"], root=clean_language) == ["--check"]
    assert ui.language() == language


@pytest.mark.parametrize("choice,expected", [("1", "zh-TW"), ("2", "en"), ("", "en")])
def test_install_menu_order_and_selection(clean_language, capsys, choice, expected):
    ui.configure_language([], root=clean_language, menu=True, interactive=True, ask=lambda: choice)
    assert ui.language() == expected
    output = capsys.readouterr()
    assert "1. 正體中文\n2. English" in output.err and output.out == ""
    assert not list(clean_language.iterdir())


def test_menu_saved_default_and_invalid_answer_not_echoed(clean_language, capsys):
    ui.save_language(clean_language, "zh-TW")
    answers = iter(["PRIVATE_BAD_ANSWER", ""])
    ui.configure_language([], root=clean_language, menu=True, interactive=True, ask=lambda: next(answers))
    assert ui.language() == "zh-TW"
    output = capsys.readouterr().err
    assert "[1]" in output and "PRIVATE_BAD_ANSWER" not in output


@pytest.mark.parametrize("arguments,interactive", [(["--help"], True), (["-h"], True), ([], False), (["--language", "en"], True)])
def test_no_menu_for_help_explicit_or_noninteractive(clean_language, arguments, interactive, capsys):
    ui.configure_language(arguments, root=clean_language, menu=True, interactive=interactive,
                          ask=lambda: pytest.fail("No prompt expected"))
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("arguments", [["--language"], ["--language", "PRIVATE_INVALID"], ["--language="], ["--language", "en", "--language", "en"]])
def test_invalid_language_is_safe_and_has_no_files(clean_language, arguments):
    with pytest.raises(ui.LanguageError) as exc:
        ui.configure_language(arguments, root=clean_language)
    assert "PRIVATE_INVALID" not in str(exc.value)
    assert not list(clean_language.iterdir())


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_cancel_menu_prevents_installation(clean_language, error):
    def cancelled():
        raise error
    with pytest.raises(ui.LanguageError, match="cancelled"):
        ui.configure_language([], root=clean_language, menu=True, interactive=True, ask=cancelled)
    assert not list(clean_language.iterdir())


def test_preference_private_atomic_and_symlink_rejected(clean_language):
    ui.save_language(clean_language, "zh-TW")
    path = clean_language / ui.PREFERENCE_FILE
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert ui.saved_language(clean_language) == "zh-TW"
    path.chmod(0o644)
    with pytest.raises(ui.LanguageError):
        ui.saved_language(clean_language)
    path.unlink()
    target = clean_language / "other"
    target.write_text("PRIVATE_CONTENT")
    path.symlink_to(target)
    with pytest.raises(ui.LanguageError):
        ui.saved_language(clean_language)
    with pytest.raises(ui.LanguageError):
        ui.save_language(clean_language, "en")
    assert target.read_text() == "PRIVATE_CONTENT"


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_fresh_install_and_setup_bootstrap_language(installation, language):
    root, uv = installation
    result = run_entry(root, uv, "tg-install", "--language", language)
    assert result.returncode == 0
    assert (root / ui.PREFERENCE_FILE).read_text().strip() == language
    assert stat.S_IMODE((root / ui.PREFERENCE_FILE).stat().st_mode) == 0o600
    expected = "Installation complete" if language == "en" else "安裝完成"
    assert expected in result.stdout
    help_result = run_entry(root, uv, "tg-setup", "--help", TG_LANGUAGE=language)
    assert ("First-run setup" if language == "en" else "首次初始化") in help_result.stdout
    override = "zh-TW" if language == "en" else "en"
    explicit = run_entry(root, uv, "tg-setup", "--language", override, "--help", TG_LANGUAGE=language)
    assert ("First-run setup" if override == "en" else "首次初始化") in explicit.stdout
    assert (root / ui.PREFERENCE_FILE).read_text().strip() == language


@pytest.mark.parametrize("choice,language", [("1", "zh-TW"), ("2", "en")])
def test_real_terminal_menu_persists_and_next_entry_inherits(installation, choice, language):
    root, uv = installation
    environment = {key: value for key, value in os.environ.items() if not key.startswith("TG_")}
    environment.update(UV_BIN=str(uv), PYTHONPATH="")
    master, slave = pty.openpty()
    process = None
    try:
        process = subprocess.Popen([sys.executable, "-S", str(root / "tg-install")],
                                   stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=environment, cwd=root, text=True)
        os.close(slave)
        slave = None
        os.write(master, (choice + "\n").encode())
        out, err = process.communicate(timeout=10)
        assert process.returncode == 0, err
        assert "1. 正體中文\n2. English" in err
        assert ("Installation complete" if language == "en" else "安裝完成") in out
        assert ui.saved_language(root) == language
        following = subprocess.run([sys.executable, "-S", str(root / "tg-setup"), "--help"],
                                   env=environment, cwd=root, capture_output=True, text=True, timeout=10)
        assert following.returncode == 0
        assert ("First-run setup" if language == "en" else "首次初始化") in following.stdout
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        if slave is not None:
            os.close(slave)


def test_failed_install_does_not_change_preference(installation):
    root, uv = installation
    ui.save_language(root, "zh-TW")
    result = run_entry(root, uv.parent / "absent", "tg-install", "--language", "en")
    assert result.returncode == 1
    assert ui.saved_language(root) == "zh-TW"


def test_setup_exec_forwards_language_without_changing_argv(installation, monkeypatch):
    root, uv = installation
    assert run_entry(root, uv, "tg-install").returncode == 0
    monkeypatch.setenv("UV_BIN", str(uv))
    calls = []
    assert tg_install.setup_main(["--language", "en", "--non-interactive"], project_dir=root,
                                 executor=lambda *args: calls.append(args)) == 0
    assert calls[0][2]["TG_LANGUAGE"] == "en"
    assert calls[0][1][-1] == "--non-interactive" and "--language" not in calls[0][1]


@pytest.mark.parametrize("module", ["tg_install", "tg_setup", "tg_cli", "tg_receiver", "tg_notify", "sys_notify", "provision_telegram_bot", "rotate_telegram_bot_tokens"])
@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_every_cli_help_has_language_support_and_selected_text(module, language, capsys):
    main = importlib.import_module(module).main
    try:
        result = main(["--language", language, "--help"])
    except SystemExit as exc:
        result = exc.code
    assert result == 0
    output = capsys.readouterr().out
    assert "--language" in output
    if language == "en":
        assert not re.search(r"[\u4e00-\u9fff]", output), module
    else:
        assert re.search(r"[\u4e00-\u9fff]", output), module


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_setup_flow_hidden_prompts_success_and_machine_fields(tmp_path, language, monkeypatch, capsys):
    config(tmp_path / ".env")
    harness = Harness(tmp_path, twofa=True)
    prompts, sent = [], []
    def prompt(label):
        prompts.append(label)
        return PASSWORD if "password" in label or "密碼" in label else OTP
    def sender(token, chat_id, text):
        sent.append(text)
        assert token == TOKEN
        return harness.response
    result = harness.main("--language", language, secret_prompt=prompt, notification_sender=sender)
    assert result == 0
    output = capsys.readouterr().out
    assert "status=completed" in output and "route=NEW_PERSONAL" in output
    assert ("Setup complete" if language == "en" else "初始化完成") in output
    assert len(prompts) == 2
    if language == "en":
        assert "hidden input" in prompts[0] and "password" in prompts[1]
        assert "setup test" in sent[0]
    else:
        assert "隱藏輸入" in prompts[0] and "密碼" in prompts[1]
        assert "初始化測試" in sent[0]
    assert all(secret not in output for secret in (TOKEN, OTP, PASSWORD))


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_username_conflict_prompt_in_selected_language(language, capsys):
    ui.set_language(language)
    record = {}
    labels = []
    def ask(label):
        labels.append(label)
        return "y"
    selected = tg_setup._choose_username(None, "ExistingNameBot", record, lambda _: None,
                                         lambda *_: True, ask, True)
    assert selected != "ExistingNameBot" and tg_setup._valid_username(selected)
    output = capsys.readouterr().err
    assert ("not reserved" if language == "en" else "尚未保留") in output
    assert ("Use the suggestion" if language == "en" else "要採用建議") in labels[0]


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_receiver_mode_and_notification_prefix_keep_user_content(tmp_path, language, monkeypatch):
    import sys_notify
    ui.set_language(language)
    labels = []
    def ask(label):
        labels.append(label)
        return "y"
    assert tg_receiver.select_mode(tmp_path, interactive=True, ask=ask) == "jpeg"
    assert ("JPG copies" if language == "en" else "另存 JPG") in labels[0]
    messages = []
    monkeypatch.setattr(sys_notify, "send_text", lambda text, *a, **k: messages.append(text) or {"ok": True})
    payload = "使用者原文 User text {unchanged}"
    assert sys_notify.main(["--language", language, payload]) == 0
    assert messages[0].endswith(payload)
    assert ("Server notification" if language == "en" else "伺服器通知") in messages[0]


def test_double_dash_preserves_language_like_user_payload(clean_language):
    payload = ["--", "--language", "PRIVATE_USER_TEXT"]
    assert ui.configure_language(payload, root=clean_language) == payload


@pytest.mark.parametrize("module", ["tg_notify", "sys_notify"])
def test_double_dash_sends_help_like_message_literally(module, monkeypatch):
    target = importlib.import_module(module)
    messages = []
    monkeypatch.setattr(target, "send_text", lambda text, *a, **k: messages.append(text) or {"ok": True})
    assert target.main(["--language", "en", "--", "--help"]) == 0
    assert messages[0].endswith("--help")


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_notification_error_language_preserves_delivery_codes(language, monkeypatch):
    ui.set_language(language)
    monkeypatch.setattr(tg_notify, "get_bot_credentials", lambda _: ("synthetic", 123))
    result = tg_notify.send_text("")
    assert result["delivery"]["status"] == "failed" and result["error_code"] == 400
    assert ("nonempty" if language == "en" else "非空") in result["description"]


def test_telegram_error_text_is_not_translated(monkeypatch):
    import tg_delivery
    ui.set_language("zh-TW")
    original = "Bad Request: custom Telegram server explanation"
    response = SimpleNamespace(status_code=400, json=lambda: {"ok": False, "error_code": 400, "description": original})
    result = tg_delivery.request_with_retry(lambda: response)
    assert result["description"] == original
