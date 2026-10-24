"""獨立語言包與固定鍵契約 / Independent language packs and stable message IDs."""
import ast
import importlib
import json
from pathlib import Path
import shutil

import pytest

import tg_i18n as ui
import tg_install
from test_first_run_install import installation, run_entry


@pytest.fixture
def packs(tmp_path, monkeypatch):
    shutil.copytree(ui.ROOT / "languages", tmp_path / "languages")
    monkeypatch.setattr(ui, "ROOT", tmp_path)
    ui._read_pack.cache_clear()
    yield tmp_path
    ui._read_pack.cache_clear()


def test_language_keys_match_all_runtime_references():
    used = {"cli_positional_arguments", "cli_options"}
    for path in ui.ROOT.glob("*.py"):
        if path.name == "conftest.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "tr" and node.args and isinstance(node.args[0], ast.Constant)):
                used.add(node.args[0].value)
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                    and any(isinstance(target, ast.Name) and target.id == "RECOVERY_MESSAGE_KEY" for target in node.targets)):
                used.add(node.value.value)
    assert used == set(ui.load_messages("en")) == set(ui.load_messages("zh-TW"))


def test_reordering_file_and_editing_text_do_not_change_ids(packs):
    ui.set_language("en")
    path = packs / "languages/en.ini"
    lines = path.read_text().splitlines()
    entries = [line for line in lines if " = " in line]
    key = "setup_username_suggestion"
    entries = [key + ' = "Edited suggestion: @{p0}"' if line.startswith(key + " = ") else line for line in entries]
    path.write_text("[messages]\n" + "\n".join(reversed(entries)) + "\n")
    assert ui.tr(key, p0="ChosenBot") == "Edited suggestion: @ChosenBot"
    assert ui.tr("install_complete").startswith("Installation complete")


def test_only_selected_pack_is_loaded_and_switch_uses_cache(packs, monkeypatch):
    original = Path.read_text
    opened = []
    def read(path, *args, **kwargs):
        if path.suffix == ".ini":
            opened.append(path.name)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    ui.set_language("en")
    assert "Installation complete" in ui.tr("install_complete")
    assert "Installation complete" in ui.tr("install_complete")
    assert opened == ["en.ini"]
    ui.set_language("zh-TW")
    assert "安裝完成" in ui.tr("install_complete")
    ui.set_language("en")
    assert "Installation complete" in ui.tr("install_complete")
    assert opened == ["en.ini", "zh_TW.ini"]


def test_unselected_missing_pack_does_not_break_selected_language(packs):
    (packs / "languages/zh_TW.ini").unlink()
    ui.set_language("en")
    assert "Installation complete" in ui.tr("install_complete")
    ui.set_language("zh-TW")
    with pytest.raises(ui.LanguageError, match="Language pack missing"):
        ui.tr("install_complete")


def test_ini_strings_preserve_whitespace_unicode_percent_and_literal_braces(packs):
    value = '  正體中文 🖥️\n100% %s "quoted" \\ path {{literal}} {p0}  '
    (packs / "languages/en.ini").write_text("[messages]\nexample = " + json.dumps(value, ensure_ascii=False) + "\n")
    ui.set_language("en")
    assert ui.tr("example", p0="user {text}") == value.replace("{{literal}}", "{literal}").replace("{p0}", "user {text}")


@pytest.mark.parametrize("content", [
    '[messages]\nexample = "first"\nexample = "PRIVATE_BAD_VALUE"\n',
    '[messages]\nexample = "PRIVATE_BAD_VALUE"\n[messages]\nother = "value"\n',
    '[messages]\nexample = PRIVATE_BAD_VALUE\n',
    '[messages]\nexample = 123\n',
    '[messages]\nexample = ""\n',
    '[messages]\nBadKey = "PRIVATE_BAD_VALUE"\n',
    '[messages]\nexample = "{p0.__class__} PRIVATE_BAD_VALUE"\n',
    '[messages]\nexample = "{p0:{p1}} PRIVATE_BAD_VALUE"\n',
    '[DEFAULT]\nexample = "PRIVATE_BAD_VALUE"\n[messages]\n',
    '[other]\nexample = "PRIVATE_BAD_VALUE"\n',
    '[messages]\n',
    '[messages]\nexample = "PRIVATE_BAD_VALUE {"\n',
])
def test_invalid_pack_fails_with_safe_bilingual_diagnostic(packs, content):
    (packs / "languages/en.ini").write_text(content)
    ui.set_language("en")
    with pytest.raises(ui.LanguageError) as exc:
        ui.tr("example")
    assert "語言包" in str(exc.value) and "Language pack" in str(exc.value)
    assert "PRIVATE_BAD_VALUE" not in str(exc.value)


def test_invalid_utf8_is_safe(packs):
    (packs / "languages/en.ini").write_bytes(b"[messages]\nexample = \xff\n")
    with pytest.raises(ui.LanguageError):
        ui.load_messages("en")


@pytest.mark.parametrize("values", [{}, {"wrong": "PRIVATE_ARGUMENT"}])
def test_missing_placeholder_does_not_echo_values(packs, values):
    ui.set_language("en")
    with pytest.raises(ui.LanguageError) as exc:
        ui.tr("setup_username_suggestion", **values)
    assert "PRIVATE_ARGUMENT" not in str(exc.value)


def test_unknown_message_id_never_becomes_display_text(packs):
    with pytest.raises(ui.LanguageError) as exc:
        ui.tr("PRIVATE_UNKNOWN_MESSAGE")
    assert "PRIVATE_UNKNOWN_MESSAGE" not in str(exc.value)


def test_unknown_language_cannot_select_an_arbitrary_path():
    with pytest.raises(ui.LanguageError):
        ui.load_messages("../../PRIVATE_PATH")


@pytest.mark.parametrize("language,filename", [("en", "en.ini"), ("zh-TW", "zh_TW.ini")])
def test_bootstrap_missing_pack_stops_before_install(installation, language, filename):
    root, uv = installation
    (root / "languages" / filename).unlink()
    result = run_entry(root, uv, "tg-install", "--language", language)
    assert result.returncode == 2
    assert "Language pack missing" in result.stderr and "語言包" in result.stderr
    assert not (root / "uv-call.json").exists()
    assert not (root / ".tg-language").exists()


@pytest.mark.parametrize("module,key", [
    ("tg_install", "install_help_description"),
    ("tg_setup", "setup_help_description"),
    ("tg_cli", "account_help_description"),
    ("tg_receiver", "receive_help_description"),
    ("tg_notify", "notify_usage"),
    ("sys_notify", "system_notify_usage"),
    ("provision_telegram_bot", "provision_help_description"),
    ("rotate_telegram_bot_tokens", "rotation_help_description"),
])
def test_missing_requested_key_gives_clean_cli_diagnostic(packs, module, key, capsys):
    path = packs / "languages/en.ini"
    path.write_text("\n".join(line for line in path.read_text().splitlines() if not line.startswith(key + " = ")) + "\n")
    tool = importlib.import_module(module)
    main = tool.cli if module == "rotate_telegram_bot_tokens" else tool.main
    assert main(["--language", "en", "--help"]) in (1, 2)
    output = capsys.readouterr().err
    assert "Invalid message key" in output and "Traceback" not in output
