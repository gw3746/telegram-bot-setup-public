#!/usr/bin/env python3
"""經由 BotFather（/revoke）輪換明確指定設定的 Telegram bot token。

取得新值後先保存私有 journal，再驗證身份並逐檔更新。
外部撤銷與多檔更新無法形成原子交易；中斷時依 journal 及 BotFather 人工恢復。

  uv run --project . python rotate_telegram_bot_tokens.py --dry-run
  uv run --project . python rotate_telegram_bot_tokens.py --consumer-file /明確指定/consumer.env

Rotate explicitly selected Telegram bot tokens through BotFather (/revoke).

Persist a private journal before identity checks and per-file updates.
External revocation and multiple files cannot form one atomic transaction.
Recover interrupted runs manually using the journal and BotFather.

  uv run --project . python rotate_telegram_bot_tokens.py --dry-run
  uv run --project . python rotate_telegram_bot_tokens.py --consumer-file /explicit/path/consumer.env
"""
from __future__ import annotations
from tg_i18n import tr, configure_language, LanguageError, LanguageArgumentParser

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provision_telegram_bot import (  # noqa: E402
    DEFAULT_ENV_PATH,
    DEFAULT_SESSION_PATH,
    TOKEN_RE,
    load_simple_env,
    require_authorized_client,
    send_and_wait_botfather_reply,
)
from tg_delivery import redact  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent
STATE_DIR = PROJECT_DIR / ".state" / "token_rotation"
FULL_TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
RECOVERY_MESSAGE_KEY = 'rotation_recovery_required'


class RotationError(RuntimeError):
    """只包含可安全顯示的輪換診斷。

Rotation diagnostics that are safe to display."""


def get_me(token: str) -> str:
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
    except requests.Timeout:
        raise RotationError(tr('rotation_identity_timeout')) from None
    except requests.RequestException:
        raise RotationError(tr('rotation_identity_network_failed')) from None
    if response.status_code != 200:
        raise RotationError(tr('rotation_identity_http_failed'))
    try:
        payload = response.json()
    except (ValueError, requests.RequestException):
        raise RotationError(tr('rotation_identity_json_invalid')) from None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RotationError(tr('rotation_identity_api_failed'))
    result = payload.get("result")
    username = result.get("username") if isinstance(result, dict) else None
    if (not isinstance(username, str) or not USERNAME_RE.fullmatch(username)
            or result.get("is_bot") is False):
        raise RotationError(tr('rotation_identity_invalid'))
    return username


def _absolute(path: Path) -> Path:
    # 不使用 resolve，避免在檢查前跟隨來源 symlink。 / Avoid resolve so source symlinks are not followed before validation.
    return Path(os.path.abspath(path.expanduser()))


def _check_directory(path: Path) -> None:
    for directory in [*reversed(path.parents), path]:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise RotationError(tr('rotation_directory_invalid'))


def _read_source(path: Path) -> tuple[bytes, int]:
    _check_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or not metadata.st_mode & 0o444:
            raise RotationError(tr('rotation_config_not_readable'))
        return handle.read(), stat.S_IMODE(metadata.st_mode)


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    _check_directory(path.parent)
    if path.is_symlink() or (path.exists() and not stat.S_ISREG(path.lstat().st_mode)):
        raise RotationError(tr('rotation_nonregular_write_refused'))
    fd, name = tempfile.mkstemp(prefix=".rotation-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode & 0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        # 只清理本次排他建立的隨機暫存，不碰既有 .rotate_tmp。 / Clean only random temporary files exclusively created by this run, not existing .rotate_tmp files.
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, payload: dict) -> None:
    content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write(path, content)
    if _read_source(path)[0] != content:
        raise RotationError(tr('rotation_record_verification_failed'))


def replace_in_files(files: list[Path], old: str, new: str) -> list[str]:
    changed = []
    for path in dict.fromkeys(_absolute(path) for path in files):
        content, mode = _read_source(path)
        text = content.decode("utf-8")
        if old not in text:
            continue
        _atomic_write(path, text.replace(old, new).encode("utf-8"), mode)
        changed.append(str(path))
    return changed


def _private_directory(path: Path) -> None:
    if not path.exists():
        if not path.parent.exists():
            _private_directory(path.parent)
        _check_directory(path.parent)
        path.mkdir(mode=0o700)
        _sync_directory(path.parent)
    _check_directory(path)
    os.chmod(path, 0o700)


def _prepare_run(files: list[Path], sources: dict[Path, tuple[bytes, int]]) -> Path:
    for path in files:
        if not path.parent.stat().st_mode & 0o222 or not os.access(path.parent, os.W_OK):
            raise RotationError(tr('rotation_config_parent_not_writable'))
        fd, name = tempfile.mkstemp(prefix=".rotation-probe-", dir=path.parent)
        os.close(fd)
        Path(name).unlink()
    state_dir = _absolute(STATE_DIR)
    _private_directory(state_dir)
    run_dir = Path(tempfile.mkdtemp(prefix=datetime.now().strftime("%Y%m%d_%H%M%S_"), dir=state_dir))
    os.chmod(run_dir, 0o700)
    _sync_directory(state_dir)
    manifest = {"sources": []}
    for path in files:
        content, mode = sources[path]
        digest = hashlib.sha256(content).hexdigest()
        name = hashlib.sha256(str(path).encode("utf-8")).hexdigest() + ".backup"
        backup = run_dir / name
        _atomic_write(backup, content)
        if _read_source(backup)[0] != content:
            raise RotationError(tr('rotation_backup_verification_failed'))
        manifest["sources"].append({"source": str(path), "backup": str(backup),
                                    "sha256": digest, "mode": mode})
    _write_json(run_dir / "manifest.json", manifest)
    return run_dir


def revoke(client, username: str) -> str:
    try:
        send_and_wait_botfather_reply(client, "/cancel", timeout_seconds=10)
    except Exception:
        pass
    try:
        send_and_wait_botfather_reply(client, "/revoke")
        reply = send_and_wait_botfather_reply(client, f"@{username}")
        match = TOKEN_RE.search(str(getattr(reply, "raw_text", "") or ""))
    except Exception:
        raise RotationError(tr('rotation_revocation_unknown')) from None
    if not match:
        raise RotationError(tr('rotation_new_token_missing'))
    return match.group(0)


def _run(args) -> int:
    files = list(dict.fromkeys(_absolute(path) for path in [args.env_path, *args.consumer_file]))
    sources = {path: _read_source(path) for path in files}
    for content, _mode in sources.values():
        content.decode("utf-8")
    env = load_simple_env(files[0])
    keys = sorted(k for k, v in env.items() if FULL_TOKEN_RE.fullmatch(v) and (not args.only or k in args.only))
    bots = {}
    for key in keys:
        bots[key] = get_me(env[key])
        print(redact(f"{key} @{bots[key]}", env.values()))
    if args.dry_run or not keys:
        return 0

    run_dir = _prepare_run(files, sources)
    journal_path = run_dir / "journal.json"
    mapping_path = run_dir / "old_to_new.json"
    journal = {"run_id": run_dir.name, "stage": "prepared", "rotations": []}
    journal_failed = False

    def save_journal():
        nonlocal journal_failed
        try:
            _write_json(journal_path, journal)
        except Exception:
            journal_failed = True
            raise RotationError(tr('rotation_journal_failed_prefix') + tr(RECOVERY_MESSAGE_KEY)) from None

    save_journal()
    mapping = {}
    client = require_authorized_client(files[0], args.session_path)
    entry = None
    try:
        for key in keys:
            old = env[key]
            if old in mapping:
                continue
            entry = {"keys": [name for name in keys if env[name] == old], "username": bots[key],
                     "old_token": old, "stage": "revoking", "last_successful_stage": "prepared",
                     "files": {str(path): {"stage": "pending"} for path in files}}
            journal["rotations"].append(entry)
            journal["stage"] = "revoking"
            save_journal()
            new = revoke(client, bots[key])
            entry.update(new_token=new, stage="obtained_pending_verification",
                         last_successful_stage="obtained_pending_verification")
            journal["stage"] = entry["stage"]
            save_journal()
            if not isinstance(new, str) or not FULL_TOKEN_RE.fullmatch(new):
                raise RotationError(tr('rotation_token_invalid_prefix') + tr(RECOVERY_MESSAGE_KEY))
            if get_me(new) != bots[key]:
                raise RotationError(tr('rotation_identity_mismatch_prefix') + tr(RECOVERY_MESSAGE_KEY))
            entry.update(stage="verified", last_successful_stage="verified")
            journal["stage"] = "verified"
            save_journal()
            mapping[old] = new
            _write_json(mapping_path, mapping)
            changed = []
            for path in files:
                entry["stage"] = journal["stage"] = "updating"
                entry["files"][str(path)]["stage"] = "updating"
                save_journal()
                updated = replace_in_files([path], old, new)
                changed.extend(updated)
                entry["files"][str(path)]["stage"] = "completed" if updated else "unchanged"
                save_journal()
            entry.update(stage="completed", last_successful_stage="completed")
            journal["stage"] = "completed"
            save_journal()
            print(redact(f"ROTATED {key} @{bots[key]} files={len(changed)}", [old, new]))
    except (Exception, KeyboardInterrupt) as error:
        if entry is not None and not journal_failed:
            entry["stage"] = journal["stage"] = "needs_manual_recovery"
            try:
                save_journal()
            except RotationError:
                pass
        print(redact(f"RECOVERY_DIR={run_dir}"), file=sys.stderr)
        diagnosis = str(error) + "；" if isinstance(error, RotationError) else tr('rotation_incomplete_prefix')
        raise RotationError(diagnosis + tr(RECOVERY_MESSAGE_KEY)) from None
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
    print(redact(f"BACKUP_DIR={run_dir}"))
    print(redact(f"MAPPING={mapping_path}"))
    return 0


def main(argv=None) -> int:
    argv = configure_language(argv)
    class SafeParser(LanguageArgumentParser):
        def error(self, message):
            raise RotationError(tr('rotation_arguments_invalid'))

    parser = SafeParser(description=tr('rotation_help_description'), formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--session-path", type=Path, default=DEFAULT_SESSION_PATH)
    parser.add_argument("--only", action="append", help=tr('rotation_only_key_help'))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--consumer-file", type=Path, action="append", default=[],
                        help=tr('rotation_consumer_file_help'))
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except RotationError:
        raise
    except Exception:
        raise RotationError(tr('rotation_preflight_failed')) from None


def cli(argv=None) -> int:
    try:
        return main(argv)
    except (RotationError, LanguageError) as error:
        print(redact(error), file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(tr(RECOVERY_MESSAGE_KEY), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
