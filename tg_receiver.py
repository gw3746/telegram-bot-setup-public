"""通用圖片／PDF 收件與存檔事件，不含個人業務處理。

Generic image/PDF reception and saved-file events without personal business logic."""
from __future__ import annotations
from tg_i18n import tr, language_errors, configure_language, LanguageError, LanguageArgumentParser

import argparse
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote
import uuid
import warnings

import requests

from tg_delivery import api_error_code, redact

try:
    import sqlite3
except ImportError:
    sqlite3 = None

from tg_notify import _BOT_CONFIG
from tg_settings import (SettingsError, custom_routes, load_env, private_directory,
                         read_bytes, read_json, secure_lock, write_json, write_private)

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 60_000_000
# 約 70 分鐘退避，避免短暫斷線就放棄收件。 / About 70 minutes of backoff so brief outages do not drop files.
MAX_JOB_ATTEMPTS = 20
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif',
                    '.bmp', '.tif', '.tiff', '.gif'}
LOG = logging.getLogger('tg_receiver')


class ReceiverError(ValueError):
    """可顯示於終端的固定診斷，不帶入憑證。

Fixed terminal diagnostics without credentials."""


class ApiError(RuntimeError):
    def __init__(self, code=0, retry_after=5):
        self.code = code
        self.retry_after = retry_after
        super().__init__(tr('receive_api_status', p0=code))


def permanent_rejection(code):
    return type(code) is int and 400 <= code < 500 and code != 429


def image_support():
    try:
        from PIL import Image, ImageOps
        from pillow_heif import register_heif_opener
    except ImportError:
        raise ReceiverError(tr('receive_image_dependencies_required')) from None
    register_heif_opener()
    return Image, ImageOps


def convert_jpeg(data: bytes) -> tuple[bytes, dict]:
    Image, ImageOps = image_support()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise ReceiverError(tr('receive_image_dimensions_exceeded'))
                frames = getattr(source, 'n_frames', 1)
                source.seek(0)
                source.load()
                upright = ImageOps.exif_transpose(source)
                if 'A' in upright.getbands() or 'transparency' in upright.info:
                    rgba = upright.convert('RGBA')
                    image = Image.new('RGB', rgba.size, 'white')
                    image.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    image = upright.convert('RGB')
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=95, subsampling=0)
                result = output.getvalue()
                if len(result) > MAX_BYTES:
                    raise ReceiverError(tr('receive_jpeg_too_large'))
                return result, {'width': image.width, 'height': image.height, 'frames': frames}
    except ReceiverError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ReceiverError(tr('receive_jpeg_conversion_failed')) from None


def attachment(message):
    photos = message.get('photo')
    if isinstance(photos, list) and photos:
        return max(photos, key=lambda p: p.get('width', 0) * p.get('height', 0)), 'image', 'photo.jpg'
    item = message.get('document')
    if not isinstance(item, dict):
        return None
    name = str(item.get('file_name', 'attachment')).replace('\\', '/').rsplit('/', 1)[-1]
    suffix = Path(name).suffix.lower()
    mime = str(item.get('mime_type', '')).lower()
    if mime == 'application/pdf' or suffix == '.pdf':
        return item, 'pdf', name
    if mime.startswith('image/') or suffix in IMAGE_EXTENSIONS:
        return item, 'image', name
    return None


def filename(message, kind, original):
    stem = re.sub(r'[^\w-]+', '_', Path(original).stem).strip('_.')[:48] or 'file'
    suffix = '.pdf' if kind == 'pdf' else Path(original).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS and kind != 'pdf':
        suffix = '.img'
    return f"{message['chat']['id']}_{message['message_id']}_{stem}{suffix}"


def publish(data: bytes, destination: Path, name: str):
    target = destination / name
    digest = hashlib.sha256(data).hexdigest()
    if target.exists() or target.is_symlink():
        if hashlib.sha256(read_bytes(target)).hexdigest() == digest:
            return target, digest
        raise ReceiverError(tr('receive_filename_conflict'))
    temporary = destination / ('.receive-' + uuid.uuid4().hex)
    try:
        write_private(temporary, data)
        if hashlib.sha256(read_bytes(temporary)).hexdigest() != digest:
            raise OSError(tr('receive_file_verification_failed'))
        try:
            os.link(temporary, target)
        except FileExistsError:
            if hashlib.sha256(read_bytes(target)).hexdigest() != digest:
                raise ReceiverError(tr('receive_filename_conflict')) from None
        fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return target, digest
    finally:
        temporary.unlink(missing_ok=True)


class Telegram:
    def __init__(self, token):
        self.token = token

    def call(self, method, **payload):
        try:
            response = requests.post(f'https://api.telegram.org/bot{self.token}/{method}',
                                     json=payload, timeout=(10, 40))
            try:
                data = response.json()
            except ValueError:
                data = None
            if not isinstance(data, dict) or data.get('ok') is not True or response.status_code >= 400:
                code = api_error_code(response.status_code, data.get('error_code') if isinstance(data, dict) else None)
                delay = (data.get('parameters') or {}).get('retry_after', 5) if isinstance(data, dict) else 5
                raise ApiError(code or 0, delay if code == 429 and type(delay) is int and 0 < delay <= 86400 else 5)
            result = data['result']
            if not isinstance(result, list if method == 'getUpdates' else dict):
                raise ApiError()
            return result
        except (requests.RequestException, ValueError, KeyError):
            raise ApiError() from None

    def download(self, file_id):
        try:
            info = self.call('getFile', file_id=file_id)
        except ApiError as exc:
            if exc.code in (400, 404):
                raise ReceiverError(tr('receive_file_unavailable')) from None
            raise
        if info.get('file_size', 0) > MAX_BYTES:
            raise ReceiverError(tr('receive_file_too_large'))
        path = info.get('file_path', '')
        if not isinstance(path, str) or not path or path.startswith('/') or '..' in path.split('/'):
            raise ApiError()
        try:
            with requests.get(f'https://api.telegram.org/file/bot{self.token}/{quote(path, safe="/")}',
                              stream=True, timeout=(10, 60)) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ReceiverError(tr('receive_file_too_large'))
        except requests.HTTPError as exc:
            code = api_error_code(getattr(exc.response, 'status_code', None), None)
            raise ApiError(code or 0) from None
        except requests.RequestException:
            raise ApiError() from None
        if info.get('file_size') and len(data) != info['file_size']:
            raise ApiError()
        return bytes(data)


class Receiver:
    """保存檔案後產生事件；使用者可另接自己的 Python handler。

Produce events after saving files; users may connect their own Python handler."""
    def __init__(self, state, destination, api, allowed_users, bot_id, image_mode='original'):
        if sqlite3 is None:
            raise ReceiverError(tr('receive_sqlite_support_required'))
        if (image_mode not in ('original', 'jpeg') or type(bot_id) is not int or bot_id <= 0
                or not allowed_users or any(type(x) is not int or x <= 0 for x in allowed_users)):
            raise ReceiverError(tr('receive_arguments_invalid'))
        self.state = private_directory(state)
        self.destination = private_directory(destination)
        self.spool = private_directory(self.state / 'spool')
        self.api, self.allowed, self.bot_id, self.image_mode = api, set(allowed_users), bot_id, image_mode
        if (self.state / 'receiver.sqlite3').is_symlink():
            raise ReceiverError(tr('receive_state_symlink_refused'))
        if (self.state / 'receiver.sqlite3').exists():
            read_bytes(self.state / 'receiver.sqlite3', require_private=True)
        self.db = sqlite3.connect(self.state / 'receiver.sqlite3')
        (self.state / 'receiver.sqlite3').chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                update_id INTEGER PRIMARY KEY, message TEXT NOT NULL, image_mode TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                retry_at REAL NOT NULL DEFAULT 0, event TEXT, emitted INTEGER NOT NULL DEFAULT 0
            );
        ''')
        binding = json.dumps([bot_id, str(self.destination)])
        old = self.db.execute("SELECT value FROM settings WHERE key='binding'").fetchone()
        if old and old[0] != binding:
            self.db.close()
            raise ReceiverError(tr('receive_state_binding_conflict'))
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO settings VALUES('binding',?)", (binding,))

    @property
    def offset(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='offset'").fetchone()
        return int(row[0]) if row else 0

    def ingest(self, updates):
        with self.db:
            for update in updates:
                message = update.get('message') or {}
                chat, sender = message.get('chat', {}), message.get('from', {})
                if (chat.get('type') == 'private' and type(sender.get('id')) is int
                        and sender['id'] in self.allowed and chat.get('id') == sender['id']
                        and type(message.get('message_id')) is int and attachment(message)):
                    self.db.execute('INSERT OR IGNORE INTO jobs(update_id,message,image_mode) VALUES(?,?,?)',
                                    (update['update_id'], json.dumps(message), self.image_mode))
            if updates:
                offset = max(self.offset, max(u['update_id'] for u in updates) + 1)
                self.db.execute("INSERT OR REPLACE INTO settings VALUES('offset',?)", (str(offset),))

    def process(self):
        # 舊版留下的超額工作也停止重試，不變更既有佇列 schema。 / Stop exhausted legacy jobs without changing the queue schema.
        with self.db:
            self.db.execute("UPDATE jobs SET status='rejected',retry_at=0 WHERE status='pending' AND attempts>=?", (MAX_JOB_ATTEMPTS,))
        rows = self.db.execute("SELECT * FROM jobs WHERE status='pending' AND retry_at<=? ORDER BY update_id LIMIT 20", (time.time(),)).fetchall()
        for row in rows:
            ident = row['update_id']
            message = json.loads(row['message'])
            try:
                item, kind, original = attachment(message)
                if item.get('file_size', 0) > MAX_BYTES:
                    raise ReceiverError(tr('receive_file_too_large'))
                spool = self.spool / str(ident)
                data = read_bytes(spool) if spool.exists() else self.api.download(item['file_id'])
                if len(data) > MAX_BYTES:
                    raise ReceiverError(tr('receive_file_too_large'))
                if kind == 'pdf' and not data.startswith(b'%PDF-'):
                    raise ReceiverError(tr('receive_pdf_header_invalid'))
                if not spool.exists():
                    write_private(spool, data)
                path, digest = publish(data, self.destination, filename(message, kind, original))
                event = {'schema': 'tg.received_file.v1', 'event_id': f'{self.bot_id}:{ident}',
                         'kind': kind, 'path': str(path), 'sha256': digest,
                         'chat_id': message['chat']['id'], 'message_id': message['message_id'],
                         'user_id': message['from']['id'], 'jpeg_path': None}
                if kind == 'image' and row['image_mode'] == 'jpeg':
                    try:
                        jpeg, metadata = convert_jpeg(data)
                        converted, converted_hash = publish(jpeg, self.destination, path.stem + '.converted.jpg')
                        event.update(jpeg_path=str(converted), jpeg_sha256=converted_hash, image=metadata)
                    except ReceiverError:
                        event['conversion_error'] = 'jpeg_conversion_failed_original_preserved'
                with self.db:
                    self.db.execute("UPDATE jobs SET status='saved',event=? WHERE update_id=?", (json.dumps(event), ident))
                spool.unlink(missing_ok=True)
            except ReceiverError:
                with self.db:
                    self.db.execute("UPDATE jobs SET status='rejected' WHERE update_id=?", (ident,))
                LOG.warning(tr('receive_file_rejected_log'), ident)
            except (OSError, ApiError, SettingsError) as exc:
                attempts = row['attempts'] + 1
                if ((isinstance(exc, ApiError) and permanent_rejection(exc.code))
                        or attempts >= MAX_JOB_ATTEMPTS):
                    with self.db:
                        self.db.execute("UPDATE jobs SET status='rejected',attempts=?,retry_at=0 WHERE update_id=?", (attempts, ident))
                    LOG.warning(tr('receive_file_rejected_log'), ident)
                    continue
                delay = min(300, 5 * 2 ** min(row['attempts'], 6))
                if isinstance(exc, ApiError) and exc.code == 429:
                    delay = max(delay, exc.retry_after)
                with self.db:
                    self.db.execute('UPDATE jobs SET attempts=attempts+1,retry_at=? WHERE update_id=?', (time.time() + delay, ident))
                LOG.warning(tr('receive_file_retry_log'), ident)

    def dispatch_events(self, handler):
        for row in self.db.execute("SELECT update_id,event FROM jobs WHERE status='saved' AND emitted=0 ORDER BY update_id LIMIT 20").fetchall():
            try:
                handler(json.loads(row['event']))
            except Exception:
                LOG.warning(tr('receive_handler_retry_log'), row['update_id'])
                break
            with self.db:
                self.db.execute('UPDATE jobs SET emitted=1 WHERE update_id=?', (row['update_id'],))


def select_mode(state, requested=None, *, interactive=False, ask=input):
    settings = read_json(state / 'receiver.json')
    mode = requested or settings.get('image_mode')
    if mode is None:
        mode = 'jpeg' if interactive and ask(tr('receive_jpeg_choice_prompt')).strip().lower() in ('y', 'yes', '是') else 'original'
    if mode not in ('original', 'jpeg'):
        raise ReceiverError(tr('receive_image_mode_invalid'))
    write_json(state / 'receiver.json', {'image_mode': mode})
    return mode


def credentials(env_path, bot):
    route = bot.upper()
    routes = _BOT_CONFIG if route in _BOT_CONFIG else custom_routes(env_path, _BOT_CONFIG)
    if route not in routes:
        raise ReceiverError(tr('receive_route_required'))
    try:
        values = load_env(env_path, require_private=True)
    except FileNotFoundError:
        values = {}
    token_key, chat_key = routes[route]
    token = values.get(token_key, os.getenv(token_key, ''))
    if not token:
        raise ReceiverError(tr('receive_token_missing'))
    return token


def parser():
    result = LanguageArgumentParser(description=tr('receive_help_description'))
    result.add_argument('--env-path', type=Path, default=ROOT / '.env')
    result.add_argument('--bot', default='DEFAULT')
    result.add_argument('--destination', type=Path, default=ROOT / 'received',
                        help=tr('receive_destination_help'))
    result.add_argument('--state-dir', type=Path, default=ROOT / '.state/receiver')
    result.add_argument('--allowed-user', type=int, action='append', required=True)
    result.add_argument('--image-mode', choices=('original', 'jpeg'))
    result.add_argument('--non-interactive', action='store_true')
    result.add_argument('--json-events', action='store_true')
    result.add_argument('--once', action='store_true')
    return result


@language_errors
def main(argv=None):
    try:
        argv = configure_language(argv)
    except LanguageError as error:
        print(str(error), file=sys.stderr)
        return 2
    args = parser().parse_args(argv)
    if sqlite3 is None:
        print(tr('receive_sqlite_support_guidance'), file=sys.stderr)
        return 2
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO)
    worker = None
    token = ''
    try:
        state = private_directory(args.state_dir)
        def ask_mode(prompt):
            print(prompt, end='', file=sys.stderr, flush=True)
            return input()
        mode = select_mode(state, args.image_mode,
                           interactive=not args.non_interactive and sys.stdin.isatty(), ask=ask_mode)
        if mode == 'jpeg':
            image_support()
        token = credentials(args.env_path, args.bot)
        api = Telegram(token)
        info = api.call('getMe')
        bot_id = info.get('id')
        if type(bot_id) is not int or bot_id <= 0:
            raise ReceiverError(tr('receive_identity_unverified'))
        if api.call('getWebhookInfo').get('url'):
            raise ReceiverError(tr('receive_webhook_conflict'))
        locks = Path(os.getenv('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'tg-config/receiver-locks'
        with secure_lock(state / 'worker.lock'), secure_lock(locks / f'{bot_id}.lock'):
            worker = Receiver(state, args.destination, api, args.allowed_user, bot_id, mode)
            while True:
                worker.process()
                worker.dispatch_events(lambda event: print(json.dumps(event, ensure_ascii=False) if args.json_events else tr('receive_file_saved_prefix') + event['path'], flush=True))
                try:
                    worker.ingest(api.call('getUpdates', offset=worker.offset, timeout=20, limit=100, allowed_updates=['message']))
                    worker.process()
                    worker.dispatch_events(lambda event: print(json.dumps(event, ensure_ascii=False) if args.json_events else tr('receive_file_saved_prefix') + event['path'], flush=True))
                except ApiError as exc:
                    if permanent_rejection(exc.code):
                        raise ReceiverError(tr('receive_consumer_conflict')) from None
                    if args.once:
                        raise
                    time.sleep(exc.retry_after)
                if args.once:
                    return 0
    except (ReceiverError, SettingsError) as exc:
        print(redact(exc, (token,)), file=sys.stderr)
        return 2
    except (OSError, ApiError, sqlite3.Error):
        print(tr('receive_incomplete'), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    finally:
        if worker is not None:
            worker.db.close()


if __name__ == '__main__':
    raise SystemExit(main())
