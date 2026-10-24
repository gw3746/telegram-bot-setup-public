#!/usr/bin/env python3
# 由同目錄 tg launcher 透過本專案 uv 環境啟動。 / Started by the sibling tg launcher using this project's uv environment.
from __future__ import annotations
from tg_i18n import tr, language_errors, configure_language, LanguageError, LanguageArgumentParser

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from provision_telegram_bot import DEFAULT_ENV_PATH, DEFAULT_SESSION_PATH, load_simple_env, require_authorized_client, safe_cli_error
from tg_delivery import redact
from tg_notify import _BOT_CONFIG
from tg_settings import custom_routes


DEFAULT_BOT_STATE = ROOT / ".state" / "tg-cli-bot-updates.json"


def json_print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def peer_value(value: str) -> str | int:
    text = value.strip()
    return int(text) if text.lstrip("-").isdigit() else text


def sender_label(message: Any) -> str:
    sender = getattr(message, "sender", None)
    if sender is None:
        return str(getattr(message, "sender_id", "") or "-")
    name = " ".join(filter(None, [getattr(sender, "first_name", None), getattr(sender, "last_name", None)])).strip()
    return name or str(getattr(sender, "title", None) or getattr(sender, "username", None) or getattr(message, "sender_id", "-") or "-")


def message_row(message: Any, dialog_name: str = "") -> dict[str, Any]:
    text = str(getattr(message, "message", "") or "").replace("\n", " ").strip()
    return {
        "dialog": dialog_name,
        "id": int(message.id),
        "date": message.date.astimezone().isoformat() if message.date else "",
        "sender": sender_label(message),
        "outgoing": bool(message.out),
        "text": text,
        "has_media": bool(message.media),
    }


def command_status(args: argparse.Namespace) -> int:
    client = require_authorized_client(Path(args.env_path), Path(args.session_path))
    try:
        me = client.get_me()
        payload = {
            "authorized": bool(client.is_user_authorized()),
            "user_id": int(me.id),
            "username": getattr(me, "username", None),
            "session_path": str(Path(args.session_path)),
        }
    finally:
        client.disconnect()
    json_print(payload)
    return 0


def command_dialogs(args: argparse.Namespace) -> int:
    client = require_authorized_client(Path(args.env_path), Path(args.session_path))
    try:
        rows = [
            {
                "id": int(dialog.id),
                "name": dialog.name,
                "username": getattr(dialog.entity, "username", None),
                "is_bot": bool(getattr(dialog.entity, "bot", False)),
                "unread_count": int(dialog.unread_count or 0),
            }
            for dialog in client.get_dialogs(limit=args.limit)
        ]
        if args.bots_only:
            rows = [row for row in rows if row["is_bot"]]
    finally:
        client.disconnect()
    json_print(rows) if args.json else [print(f"{row['id']}\t{row['unread_count']}\t{row['name']}\t@{row['username'] or '-'}") for row in rows]
    return 0


def command_history(args: argparse.Namespace) -> int:
    client = require_authorized_client(Path(args.env_path), Path(args.session_path))
    try:
        peer = client.get_entity(peer_value(args.peer))
        name = str(getattr(peer, "title", None) or getattr(peer, "first_name", None) or getattr(peer, "username", None) or args.peer)
        rows = [message_row(message, name) for message in client.get_messages(peer, limit=args.limit)]
    finally:
        client.disconnect()
    json_print(rows) if args.json else [print(f"{row['date']}\t{row['sender']}\t{(tr('account_media_marker') if row['has_media'] else '')}{row['text']}") for row in rows]
    return 0


def command_recent(args: argparse.Namespace) -> int:
    client = require_authorized_client(Path(args.env_path), Path(args.session_path))
    rows: list[dict[str, Any]] = []
    try:
        if args.peer:
            targets = []
            for value in args.peer:
                entity = client.get_entity(peer_value(value))
                name = str(getattr(entity, "title", None) or getattr(entity, "first_name", None) or getattr(entity, "username", None) or value)
                targets.append((entity, name))
        else:
            targets = [(dialog.entity, dialog.name) for dialog in client.get_dialogs(limit=args.dialog_limit)]
        for entity, name in targets:
            for message in client.get_messages(entity, limit=args.per_dialog):
                rows.append(message_row(message, name))
        rows.sort(key=lambda row: row["date"], reverse=True)
        rows = rows[: args.limit]
    finally:
        client.disconnect()
    json_print(rows) if args.json else [print(f"{row['date']}\t{row['dialog']}\t{row['sender']}\t{(tr('account_media_marker') if row['has_media'] else '')}{row['text']}") for row in rows]
    return 0


def command_download(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    client = require_authorized_client(Path(args.env_path), Path(args.session_path))
    try:
        peer = client.get_entity(peer_value(args.peer))
        messages = client.get_messages(peer, ids=[args.message_id])
        message = messages[0] if messages else None
        if message is None or not message.media:
            raise RuntimeError(tr('account_media_missing'))
        downloaded = client.download_media(message, file=str(output_dir))
    finally:
        client.disconnect()
    json_print({"downloaded": bool(downloaded), "path": str(downloaded or "")})
    return 0


def bot_api(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(redact(result.get("description") or tr('account_bot_api_failed'), [token]))
    return result


def command_bot_updates(args: argparse.Namespace) -> int:
    bot_type = args.bot.upper()
    routes = _BOT_CONFIG if bot_type in _BOT_CONFIG else custom_routes(Path(args.env_path), _BOT_CONFIG)
    if bot_type not in routes:
        raise RuntimeError(tr('account_bot_type_unsupported', p0=bot_type))
    env = load_simple_env(Path(args.env_path))
    token_key, _chat_key = routes[bot_type]
    token = env.get(token_key, "").strip()
    if not token:
        raise RuntimeError(tr('account_key_missing', p0=token_key))
    state = json.loads(DEFAULT_BOT_STATE.read_text()) if DEFAULT_BOT_STATE.exists() else {}
    offset = int((state.get("offsets") or {}).get(bot_type) or 0)
    result = bot_api(token, "getUpdates", {"offset": offset, "limit": args.limit, "timeout": 0})
    updates = list(result.get("result") or [])
    rows = []
    for update in updates:
        message = update.get("message") or update.get("edited_message") or update.get("channel_post") or {}
        rows.append({
            "update_id": update.get("update_id"),
            "message_id": message.get("message_id"),
            "date": datetime.fromtimestamp(message["date"]).astimezone().isoformat() if message.get("date") else "",
            "chat_id": (message.get("chat") or {}).get("id"),
            "sender": (message.get("from") or {}).get("username") or (message.get("from") or {}).get("first_name"),
            "text": message.get("text") or message.get("caption") or "",
            "has_photo": bool(message.get("photo")),
            "file_id": ((message.get("photo") or [{}])[-1]).get("file_id") if message.get("photo") else None,
        })
    if args.ack and updates:
        offsets = dict(state.get("offsets") or {})
        offsets[bot_type] = max(int(row["update_id"]) for row in updates) + 1
        DEFAULT_BOT_STATE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_BOT_STATE.write_text(json.dumps({"offsets": offsets, "updated_at": datetime.now().astimezone().isoformat()}, ensure_ascii=False, indent=2) + "\n")
    json_print(rows)
    return 0


def parser() -> LanguageArgumentParser:
    root = LanguageArgumentParser(description=tr('account_help_description'))
    root.add_argument("--env-path", default=str(DEFAULT_ENV_PATH))
    root.add_argument("--session-path", default=str(DEFAULT_SESSION_PATH))
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    dialogs = sub.add_parser("dialogs")
    dialogs.add_argument("--limit", type=int, default=30)
    dialogs.add_argument("--bots-only", action="store_true", help=tr('account_bots_only_help'))
    dialogs.add_argument("--json", action="store_true")
    history = sub.add_parser("history")
    history.add_argument("peer")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--json", action="store_true")
    recent = sub.add_parser("recent")
    recent.add_argument("--limit", type=int, default=20)
    recent.add_argument("--dialog-limit", type=int, default=30)
    recent.add_argument("--per-dialog", type=int, default=5)
    recent.add_argument("--peer", action="append", default=[], help=tr('account_selected_chat_help'))
    recent.add_argument("--json", action="store_true")
    download = sub.add_parser("download")
    download.add_argument("peer")
    download.add_argument("message_id", type=int)
    download.add_argument("--output-dir", default=str(Path.home() / "Downloads/telegram"))
    updates = sub.add_parser("bot-updates")
    updates.add_argument("--bot", default="DEFAULT")
    updates.add_argument("--limit", type=int, default=20)
    updates.add_argument("--ack", action="store_true")
    return root


@language_errors
def main(argv=None) -> int:
    try:
        argv = configure_language(argv)
    except LanguageError as error:
        print(str(error), file=sys.stderr)
        return 2
    args = parser().parse_args(argv)
    commands = {
        "status": command_status,
        "dialogs": command_dialogs,
        "history": command_history,
        "recent": command_recent,
        "download": command_download,
        "bot-updates": command_bot_updates,
    }
    try:
        return commands[args.command](args)
    except Exception as exc:
        print('ERROR: ' + safe_cli_error(exc, Path(args.env_path)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
