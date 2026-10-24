#!/usr/bin/env python3
from __future__ import annotations
from tg_i18n import tr, language_errors, configure_language, LanguageError, LanguageArgumentParser

import argparse
import json
import os
import re
import time
import stat
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from telethon.errors import SessionPasswordNeededError
from telethon.sync import TelegramClient
from tg_delivery import redact


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = Path(os.environ.get("TG_CONFIG_ENV_PATH", str(PROJECT_DIR / ".env")))
# 新副本預設只用自己的狀態，不自動接管既有 Telegram Session。 / Use only this checkout's state; never take over an existing Telegram Session automatically.
DEFAULT_STATE_DIR = Path(os.environ.get("TG_CONFIG_STATE_DIR", str(PROJECT_DIR / ".state")))
DEFAULT_SESSION_PATH = DEFAULT_STATE_DIR / "botfather_user"
DEFAULT_LOGIN_STATE_PATH = DEFAULT_STATE_DIR / "botfather_login.json"
BOTFATHER_USERNAME = "BotFather"
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])\d{6,}:[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])")


def load_simple_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)


def safe_cli_error(error: Exception, env_path: Path) -> str:
    """沿用共用去敏，將設定與程序環境中的已知憑證一併遮蔽。"""
    try:
        values = [*load_simple_env(env_path).items(), *os.environ.items()]
        secrets = [value for key, value in values
                   if key.startswith('TG_') and any(part in key for part in ('TOKEN', 'API_HASH', 'PHONE', 'PASSWORD', 'API_ID'))]
        return redact(error, secrets)
    except Exception:
        return tr('provision_error_unavailable')


def _secure_session_files(session_path: Path) -> None:
    parent = session_path.parent
    if any(item.is_symlink() for item in (parent, *parent.parents)):
        raise RuntimeError(tr('provision_session_directory_unsafe'))
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(descriptor).st_uid != os.getuid():
            raise RuntimeError(tr('provision_session_directory_unsafe'))
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)
    name = session_path.name if session_path.name.endswith('.session') else session_path.name + '.session'
    targets = [parent / name, *(target for target in parent.iterdir()
                               if target.name.startswith(name + '-'))]
    for target in targets:
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1):
            raise RuntimeError(tr('provision_session_file_unsafe'))
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            current = os.fstat(descriptor)
            if (not stat.S_ISREG(current.st_mode) or current.st_uid != os.getuid()
                    or current.st_nlink != 1):
                raise RuntimeError(tr('provision_session_file_unsafe'))
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)


@contextmanager
def _private_session(session_path: Path):
    _secure_session_files(session_path)
    previous = os.umask(0o077)
    try:
        yield
    finally:
        try:
            _secure_session_files(session_path)
        finally:
            os.umask(previous)


class _PrivateClient:
    """每次同步 client 操作前後保護 Session，包含失敗與 disconnect。"""
    def __init__(self, session_path: Path, api_id: int, api_hash: str):
        self._session_path = session_path
        with _private_session(session_path):
            self._client = TelegramClient(str(session_path), api_id, api_hash)

    def __getattr__(self, name):
        value = getattr(self._client, name)
        if not callable(value):
            return value
        def protected(*args, **kwargs):
            with _private_session(self._session_path):
                return value(*args, **kwargs)
        return protected


def _connected_client(session_path: Path, api_id: int, api_hash: str):
    client = _PrivateClient(session_path, api_id, api_hash)
    try:
        client.connect()
    except BaseException:
        try:
            client.disconnect()
        except Exception:
            pass
        raise
    return client


def atomic_write_text(path: Path, content: str) -> None:
    ensure_parent_dir(path)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    temp_path.replace(path)


def save_json(path: Path, payload: dict[str, str]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_telegram_user_config(env_path: Path) -> tuple[int, str, str, str]:
    env_values = load_simple_env(env_path)
    api_id_raw = os.getenv("TG_API_ID", "").strip() or env_values.get("TG_API_ID", "").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip() or env_values.get("TG_API_HASH", "").strip()
    phone = os.getenv("TG_PHONE", "").strip() or env_values.get("TG_PHONE", "").strip()
    password = os.getenv("TG_2STEP_PASSWORD", "").strip() or env_values.get("TG_2STEP_PASSWORD", "").strip()
    if not api_id_raw or not api_hash or not phone:
        raise RuntimeError(tr('provision_api_credentials_missing', p0=env_path))
    return int(api_id_raw), api_hash, phone, password


def mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def upsert_env_key(env_path: Path, key: str, value: str) -> None:
    ensure_parent_dir(env_path)
    lines: list[str] = []
    replaced = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updated = []
    for raw in lines:
        line = raw.strip()
        if line and not line.startswith('#') and '=' in line and line.split('=', 1)[0].strip() == key:
            if not replaced:
                updated.append(f"{key}={value}")
                replaced = True
        else:
            updated.append(raw)
    lines = updated

    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")

    atomic_write_text(env_path, "\n".join(lines) + "\n")


def request_login_code(env_path: Path, session_path: Path, login_state_path: Path) -> int:
    api_id, api_hash, phone, _password = get_telegram_user_config(env_path)
    client = _connected_client(session_path, api_id, api_hash)
    try:
        if client.is_user_authorized():
            print("ALREADY_AUTHORIZED")
            return 0
        result = client.send_code_request(phone)
        save_json(login_state_path, {"phone": phone, "phone_code_hash": result.phone_code_hash})
    finally:
        client.disconnect()
    print(f"LOGIN_CODE_SENT phone={phone} state={login_state_path}")
    return 0


def complete_login(env_path: Path, session_path: Path, login_state_path: Path, code: str) -> int:
    api_id, api_hash, _phone, password = get_telegram_user_config(env_path)
    state = load_json(login_state_path)
    phone = str(state.get("phone") or "").strip()
    phone_code_hash = str(state.get("phone_code_hash") or "").strip()
    if not phone or not phone_code_hash:
        raise RuntimeError(tr('provision_login_state_missing', p0=login_state_path))

    client = _connected_client(session_path, api_id, api_hash)
    try:
        if client.is_user_authorized():
            print("ALREADY_AUTHORIZED")
            return 0
        try:
            client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                raise RuntimeError(tr('provision_two_step_password_required'))
            client.sign_in(password=password)
    finally:
        client.disconnect()

    print(f"LOGIN_COMPLETED session={session_path}")
    return 0


def require_authorized_client(env_path: Path, session_path: Path) -> TelegramClient:
    api_id, api_hash, _phone, _password = get_telegram_user_config(env_path)
    client = _connected_client(session_path, api_id, api_hash)
    try:
        if client.is_user_authorized():
            return client
        raise RuntimeError(tr('provision_session_required'))
    except BaseException:
        try:
            client.disconnect()
        except Exception:
            pass
        raise


def latest_message_id(client: TelegramClient, peer: str) -> int:
    messages = client.get_messages(peer, limit=1)
    if not messages:
        return 0
    return int(messages[0].id)


def send_and_wait_botfather_reply(client: TelegramClient, text: str, *, timeout_seconds: int = 30):
    marker = latest_message_id(client, BOTFATHER_USERNAME)
    client.send_message(BOTFATHER_USERNAME, text)
    deadline = time.time() + max(timeout_seconds, 1)
    while time.time() < deadline:
        messages = client.get_messages(BOTFATHER_USERNAME, limit=5)
        for message in messages:
            if int(message.id) > marker and not message.out:
                return message
        time.sleep(1)
    raise RuntimeError(tr('provision_botfather_timeout', p0=text))


def create_bot_via_botfather(
    env_path: Path,
    session_path: Path,
    display_name: str,
    username: str,
    token_env_key: str,
    chat_id_env_key: str,
    chat_id_source_key: str,
) -> int:
    client = require_authorized_client(env_path, session_path)
    env_values = load_simple_env(env_path)
    chat_id_source_value = os.getenv(chat_id_source_key, "").strip() or env_values.get(chat_id_source_key, "").strip()

    try:
        try:
            send_and_wait_botfather_reply(client, "/cancel", timeout_seconds=10)
        except Exception:
            pass
        send_and_wait_botfather_reply(client, "/newbot")
        send_and_wait_botfather_reply(client, display_name)
        final_reply = send_and_wait_botfather_reply(client, username)
    finally:
        client.disconnect()

    reply_text = str(getattr(final_reply, "raw_text", "") or "").strip()
    token_match = TOKEN_RE.search(reply_text)
    if not token_match:
        raise RuntimeError(tr('provision_bot_creation_failed', p0=reply_text))

    token = token_match.group(0)
    upsert_env_key(env_path, token_env_key, token)
    if chat_id_source_value:
        upsert_env_key(env_path, chat_id_env_key, chat_id_source_value)

    print(f"BOT_CREATED username={username} token={mask_secret(token)} env={env_path}")
    if chat_id_source_value:
        print(f"ENV_UPDATED {chat_id_env_key}<-{chat_id_source_key}")
    else:
        print(tr('provision_chat_id_source_missing', p0=token_env_key, p1=chat_id_source_key))
    return 0


def send_message_via_user_session(
    env_path: Path,
    session_path: Path,
    peer: str,
    text: str,
    wait_seconds: float,
) -> int:
    client = require_authorized_client(env_path, session_path)
    try:
        sent = client.send_message(peer, text)
        message_id = getattr(sent, 'id', None)
        if type(message_id) is not int or message_id <= 0:
            import sys
            print(tr('provision_message_receipt_unknown'), file=sys.stderr)
            return 1
        time.sleep(max(wait_seconds, 0.0))
        replies = []
        for message in client.get_messages(peer, limit=3):
            if not message.out:
                replies.append((message.message or "").replace("\n", " ")[:160])
        print("MESSAGE_SENT")
        print("LATEST_REPLIES=" + " || ".join(replies))
    finally:
        client.disconnect()
    return 0


def parse_args(argv=None) -> argparse.Namespace:
    parser = LanguageArgumentParser(description=tr('provision_help_description'))
    parser.add_argument("--env-path", default=str(DEFAULT_ENV_PATH), help=tr('provision_env_path_help'))
    parser.add_argument("--session-path", default=str(DEFAULT_SESSION_PATH), help=tr('provision_session_path_help'))
    parser.add_argument("--login-state-path", default=str(DEFAULT_LOGIN_STATE_PATH), help=tr('provision_login_state_path_help'))

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("request-login-code", help=tr('provision_request_code_help'))

    complete_login_parser = subparsers.add_parser("complete-login", help=tr('provision_complete_login_help'))
    complete_login_parser.add_argument("--code", required=True, help=tr('provision_login_code_help'))

    create_bot_parser = subparsers.add_parser("create-bot", help=tr('provision_create_bot_help'))
    create_bot_parser.add_argument("--display-name", required=True, help=tr('provision_display_name_help'))
    create_bot_parser.add_argument("--username", required=True, help=tr('provision_username_help'))
    create_bot_parser.add_argument("--token-env-key", default="TG_BOT_TOKEN", help=tr('provision_token_key_help'))
    create_bot_parser.add_argument("--chat-id-env-key", default="TG_CHAT_ID", help=tr('provision_chat_id_key_help'))
    create_bot_parser.add_argument("--chat-id-source-key", default="TG_CHAT_ID", help=tr('provision_chat_id_source_help'))

    send_message_parser = subparsers.add_parser("send-message", help=tr('provision_send_message_help'))
    send_message_parser.add_argument("--peer", required=True, help=tr('provision_peer_help'))
    send_message_parser.add_argument("--text", required=True, help=tr('provision_text_help'))
    send_message_parser.add_argument("--wait-seconds", type=float, default=4.0, help=tr('provision_wait_seconds_help'))
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> int:
    env_path = Path(args.env_path).expanduser()
    session_path = Path(args.session_path).expanduser()
    login_state_path = Path(args.login_state_path).expanduser()

    if args.command == "request-login-code":
        return request_login_code(env_path, session_path, login_state_path)
    if args.command == "complete-login":
        return complete_login(env_path, session_path, login_state_path, args.code)
    if args.command == "create-bot":
        return create_bot_via_botfather(
            env_path=env_path,
            session_path=session_path,
            display_name=args.display_name,
            username=args.username,
            token_env_key=args.token_env_key,
            chat_id_env_key=args.chat_id_env_key,
            chat_id_source_key=args.chat_id_source_key,
        )
    if args.command == "send-message":
        return send_message_via_user_session(
            env_path=env_path,
            session_path=session_path,
            peer=args.peer,
            text=args.text,
            wait_seconds=args.wait_seconds,
        )
    raise RuntimeError(tr('provision_command_unsupported', p0=args.command))


@language_errors
def main(argv=None) -> int:
    import sys
    env_path = DEFAULT_ENV_PATH
    try:
        argv = configure_language(argv)
        args = parse_args(argv)
        env_path = Path(args.env_path).expanduser()
        return _run(args)
    except LanguageError:
        raise
    except Exception as error:
        print('ERROR: ' + safe_cli_error(error, env_path), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
