"""安裝及 bootstrap 均以隔離目錄與假 uv 驗證，禁止下載。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

import tg_install


SOURCE = Path(__file__).resolve().parents[1]


@pytest.fixture
def installation(tmp_path):
    root = tmp_path / "fresh project with spaces"
    root.mkdir()
    for filename in ("tg-install", "tg-setup", "tg_install.py", "tg_setup.py", "tg_settings.py", "tg_i18n.py"):
        shutil.copy2(SOURCE / filename, root / filename)
    shutil.copytree(SOURCE / "languages", root / "languages")
    (root / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="0.0.0"\n')
    (root / "uv.lock").write_text("fixture lock; fake downloader only\n")
    uv = tmp_path / "fake uv executable"
    uv.write_text("#!" + sys.executable + "\n" + '''import json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(args[args.index('--project') + 1])
(root / 'uv-call.json').write_text(json.dumps({'argv': args, 'venv': os.environ.get('UV_PROJECT_ENVIRONMENT'), 'tg_keys': sorted(key for key in os.environ if key.startswith('TG_'))}))
if args[0] == 'sync':
    environment = root / '.venv'
    (environment / 'bin').mkdir(parents=True, exist_ok=True)
    (environment / 'pyvenv.cfg').write_text('version = 3.12.0\\n')
    (environment / 'bin' / 'python').write_text('fake project interpreter')
''')
    uv.chmod(0o700)
    return root, uv


def run_entry(root, uv, entry, *args, **overrides):
    env = dict(os.environ, UV_BIN=str(uv), UV_PROJECT_ENVIRONMENT=str(root.parent / "foreign"),
               TG_API_HASH="INSTALL_SECRET_MUST_NOT_FORWARD", PYTHONPATH="")
    env.update(overrides)
    return subprocess.run([sys.executable, "-S", str(root / entry), *args], cwd=root,
                          env=env, capture_output=True, text=True, timeout=10)


def test_real_install_entry_without_telegram_or_dependencies(installation):
    root, uv = installation
    assert not (root / ".venv").exists()
    assert not (root / ".env").exists()
    result = run_entry(root, uv, "tg-install", "--offline")
    assert result.returncode == 0, result.stderr
    call = json.loads((root / "uv-call.json").read_text())
    assert call["argv"] == ["sync", "--frozen", "--project", str(root), "--python", "3.12", "--offline"]
    assert call["venv"] == str(root / ".venv")
    assert call["tg_keys"] == []
    assert "尚未初始化" in result.stdout
    assert not (root / ".env").exists()
    assert not (root / ".state").exists()


def test_install_rerun_preserves_config_and_does_not_initialize(installation):
    root, uv = installation
    config = root / ".env"
    config.write_text("TG_API_HASH=PRIVATE_EXISTING_VALUE\n")
    config.chmod(0o600)
    for _ in range(2):
        result = run_entry(root, uv, "tg-install")
        assert result.returncode == 0
        assert "尚未初始化" in result.stdout
        assert "PRIVATE_EXISTING_VALUE" not in result.stdout + result.stderr
        assert config.read_text() == "TG_API_HASH=PRIVATE_EXISTING_VALUE\n"
    assert not (root / ".state").exists()


@pytest.mark.parametrize("entry", ["tg-install", "tg-setup"])
def test_help_needs_neither_uv_nor_site_packages(installation, entry):
    root, uv = installation
    result = run_entry(root, uv.parent / "absent uv", entry, "--help")
    assert result.returncode == 0, result.stderr
    assert "用法:" in result.stdout
    assert not (root / "uv-call.json").exists()


@pytest.mark.parametrize("entry", ["tg-install", "tg-setup"])
def test_missing_uv_safe_failure_and_official_guidance(installation, entry):
    root, uv = installation
    result = run_entry(root, uv.parent / "absent uv", entry)
    assert result.returncode != 0
    assert tg_install.UV_GUIDE in result.stderr
    assert "INSTALL_SECRET_MUST_NOT_FORWARD" not in result.stdout + result.stderr
    assert not (root / ".env").exists()


def test_setup_without_venv_directs_to_install(installation):
    root, uv = installation
    result = run_entry(root, uv, "tg-setup", "--non-interactive")
    assert result.returncode != 0
    assert "./tg-install" in result.stderr
    assert not (root / "uv-call.json").exists()


def test_real_setup_bootstrap_preserves_literal_arguments(installation):
    root, uv = installation
    assert run_entry(root, uv, "tg-install").returncode == 0
    env_path = root / "literal $(touch DO_NOT_CREATE).env"
    args = ["--env-path", str(env_path), "--state-dir", str(root / "state with spaces"),
            "--bot-name", "A name with spaces", "--route", "CUSTOM_NEW", "--non-interactive"]
    result = run_entry(root, uv, "tg-setup", *args)
    assert result.returncode == 0, result.stderr
    call = json.loads((root / "uv-call.json").read_text())
    assert call["argv"] == ["run", "--frozen", "--no-sync", "--project", str(root),
                            "python", str(root / "tg_setup.py"), *args]
    assert call["venv"] == str(root / ".venv")
    assert not (root / "DO_NOT_CREATE").exists()


@pytest.mark.parametrize("entry", ["tg-install", "tg-setup"])
def test_reject_secret_flags_without_echo(installation, entry):
    root, uv = installation
    result = run_entry(root, uv, entry, "--api-hash", "ARGV_SECRET_VALUE")
    assert result.returncode == 2
    assert "ARGV_SECRET_VALUE" not in result.stdout + result.stderr
    assert not (root / "uv-call.json").exists()


@pytest.mark.parametrize("kind", ["nonzero", "exception", "false-success"])
def test_download_errors_do_not_echo_private_index_credentials(tmp_path, monkeypatch, capsys, kind):
    monkeypatch.setenv("UV_BIN", sys.executable)
    calls = []
    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        if kind == "exception":
            raise OSError("https://user:PRIVATE_PASSWORD@example.invalid")
        return SimpleNamespace(returncode=0 if kind == "false-success" else 2,
                               stderr=b"PRIVATE_PASSWORD", stdout=b"PRIVATE_PASSWORD")
    assert tg_install.main([], runner=runner, project_dir=tmp_path) == 1
    output = capsys.readouterr()
    assert "PRIVATE_PASSWORD" not in output.out + output.err
    assert tg_install.UV_GUIDE in output.err
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["check"] is False


def test_install_rejects_external_venv_symlink(tmp_path, monkeypatch, capsys):
    root, external = tmp_path / "project", tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (root / ".venv").symlink_to(external, target_is_directory=True)
    monkeypatch.setenv("UV_BIN", sys.executable)
    def runner(*args, **kwargs):
        pytest.fail("不得寫入外部 venv")
    assert tg_install.main([], runner=runner, project_dir=root) == 1
    assert list(external.iterdir()) == []
    assert "symlink" in capsys.readouterr().err


def test_setup_exec_inherits_terminal_without_secret_argv(installation, monkeypatch):
    root, uv = installation
    assert run_entry(root, uv, "tg-install").returncode == 0
    monkeypatch.setenv("UV_BIN", str(uv))
    monkeypatch.setenv("TG_SETUP_BOT_TOKEN", "SECRET_NOT_ARGV")
    calls = []
    assert tg_install.setup_main(["--non-interactive"], project_dir=root,
                                 executor=lambda *args: calls.append(args)) == 0
    executable, argv, environment = calls[0]
    assert executable == str(uv)
    assert "SECRET_NOT_ARGV" not in repr(argv)
    assert environment["UV_PROJECT_ENVIRONMENT"] == str(root / ".venv")
    # execvpe 只接收 path、argv、env，未重導向 stdin 或終端。
    assert len(calls[0]) == 3
