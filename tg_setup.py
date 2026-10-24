"""文件引導的首次初始化；匯入與 --help 不載入 Telegram 相依。

Guided first-run setup; import and --help do not load Telegram dependencies."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import getpass
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid
import warnings

# 套件及外部 symlink 載入時，先定位檔案實體目錄的共用模組。
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_i18n import tr, language_errors, configure_language, LanguageError, LanguageArgumentParser
from tg_settings import (BUILTIN_ROUTE_NAMES, SettingsError, absolute, custom_routes, load_env,
                         private_directory, read_json, register_route,
                         secure_lock, write_env_keys, write_json)


BUILTIN_ROUTES = BUILTIN_ROUTE_NAMES
TOKEN_RE = re.compile(r'\d{6,}:[A-Za-z0-9_-]{20,}')
STAGES = {
    'prepared', 'creation_pending', 'creation_rejected',
    'bot_created_pending_verification', 'verified', 'route_saved',
    'start_pending', 'started', 'notification_pending', 'notification_unknown',
    'notification_failed', 'notification_retry_later', 'completed',
}


class BotRejected(Exception):
    """僅供 adapter 回報 BotFather 明確拒絕，不呈現遠端文字。

Adapters report explicit BotFather rejection without displaying remote text."""
    def __init__(self, reason='rejected'):
        self.reason = reason if reason in {'taken', 'invalid', 'limit'} else 'rejected'
        super().__init__(tr('setup_creation_explicitly_rejected'))


class SetupStop(Exception):
    def __init__(self, status, hint, *, keys=()):
        self.status, self.hint, self.keys = status, hint, list(keys)


class SafeParser(LanguageArgumentParser):
    def error(self, message):
        # argparse 的原始錯誤可能回映誤放入 argv 的秘密。 / Raw argparse errors may echo secrets accidentally placed in argv.
        self.print_usage(sys.stderr)
        self.exit(2, tr('setup_arguments_invalid'))


def parser():
    result = SafeParser(description=tr('setup_help_description'))
    result.add_argument('--env-path', default=os.getenv('TG_CONFIG_ENV_PATH', str(ROOT / '.env')))
    result.add_argument('--state-dir', default=os.getenv('TG_CONFIG_STATE_DIR', str(Path.home() / '.local' / 'state' / 'telegram-bot-setup')))
    result.add_argument('--bot-name')
    result.add_argument('--bot-username')
    result.add_argument('--route')
    result.add_argument('--non-interactive', action='store_true', help=tr('setup_noninteractive_help'))
    result.add_argument('--check', action='store_true', help=tr('setup_check_help'))
    result.add_argument('--test-again', action='store_true', help=tr('setup_test_again_help'))
    result.add_argument('--confirm-started', action='store_true', help=tr('setup_confirm_started_help'))
    return result


def _positive(value):
    return type(value) is int and value > 0


def _result(record, status, hint, *, keys=()):
    stage = record.get('stage', 'not_started')
    if not isinstance(stage, str) or stage not in STAGES | {'not_started'}:
        stage = 'invalid'
    safe = {'status': status, 'stage': stage, 'hint': hint}
    for key in ('route', 'bot_username', 'suggested_username', 'bot_id', 'user_id', 'message_id'):
        if key == 'suggested_username' and status != 'username_selection_required':
            continue
        value = record.get(key)
        if key in ('route', 'bot_username', 'suggested_username'):
            pattern = r'[A-Z][A-Z0-9_]{0,31}' if key == 'route' else r'[A-Za-z0-9_]{5,32}'
            if isinstance(value, str) and re.fullmatch(pattern, value):
                safe[key] = value
        elif _positive(value):
            safe[key] = value
    if keys:
        safe['keys'] = list(keys)
    return safe


def _config(args, values):
    name = args.bot_name if args.bot_name is not None else values.get('TG_SETUP_BOT_NAME', '')
    username = args.bot_username if args.bot_username is not None else values.get('TG_SETUP_BOT_USERNAME', '')
    route = args.route if args.route is not None else values.get('TG_SETUP_ROUTE', 'PERSONAL')
    bad = []
    if not re.fullmatch(r'[1-9][0-9]*', values.get('TG_API_ID', '')):
        bad.append('TG_API_ID')
    if not re.fullmatch(r'[A-Fa-f0-9]{32}', values.get('TG_API_HASH', '')):
        bad.append('TG_API_HASH')
    if not 1 <= len(name) <= 64 or any(c in name for c in '\r\n\0'):
        bad.append('TG_SETUP_BOT_NAME')
    if not _valid_username(username):
        bad.append('TG_SETUP_BOT_USERNAME')
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,31}', route):
        bad.append('TG_SETUP_ROUTE')
    token = values.get('TG_SETUP_BOT_TOKEN', '')
    if token and not TOKEN_RE.fullmatch(token):
        bad.append('TG_SETUP_BOT_TOKEN')
    if bad:
        raise SetupStop('configuration_required', tr('setup_config_required'), keys=bad)
    if route in BUILTIN_ROUTES:
        raise SetupStop('route_conflict', tr('setup_builtin_route_conflict'))
    return name, username, route


def _session_files(session):
    # SQLite 會建立同目錄的 sidecar，也應拒絕不安全的既有目標。 / SQLite creates sibling sidecars; reject unsafe existing targets too.
    for suffix in ('.session', '.session-journal', '.session-wal', '.session-shm'):
        target = Path(str(session) + suffix)
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise SetupStop('unsafe_session', tr('setup_session_file_unsafe'))


@contextmanager
def _private_umask():
    previous = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous)


@contextmanager
def _connected_client(factory, session, api_id, api_hash):
    client = None
    with _private_umask():
        try:
            client = factory(session, api_id, api_hash)
            client.connect()
            yield client
        finally:
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass


def _default_client(session_path, api_id, api_hash):
    from telethon.sync import TelegramClient
    return TelegramClient(str(session_path), api_id, api_hash)


def _hidden_prompt(label):
    # 隱藏輸入不可用時停止，不讓 getpass 退回可見的 stdin 輸入。 / Stop when hidden input is unavailable; do not allow getpass to fall back to visible stdin.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass(label)
        except getpass.GetPassWarning:
            raise SetupStop('authorization_required', tr('setup_hidden_input_required')) from None


def _default_identity(token):
    import requests
    response = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=30)
    data = response.json()
    if response.status_code != 200 or not isinstance(data, dict) or data.get('ok') is not True:
        raise SetupStop('identity_failed', tr('setup_identity_verification_failed'))
    return data.get('result')


def _default_notification(token, chat_id, text):
    import requests
    from tg_delivery import request_with_retry
    return request_with_retry(lambda: requests.post(
        f'https://api.telegram.org/bot{token}/sendMessage',
        json={'chat_id': chat_id, 'text': text}, timeout=30), secrets=(token,))


def _default_creator(client, display_name, username):
    from provision_telegram_bot import send_and_wait_botfather_reply
    send_and_wait_botfather_reply(client, '/cancel', timeout_seconds=10)
    for step, text in enumerate(('/newbot', display_name, username)):
        message = send_and_wait_botfather_reply(client, text)
        reply = str(getattr(message, 'raw_text', '') or '')
        if step == 2:
            match = re.search(r'(?<![A-Za-z0-9_-])\d{6,}:[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])', reply)
            if match is not None:
                return match.group(0)
        lowered = reply.lower()
        if 'too many bots' in lowered or 'bot limit' in lowered:
            raise BotRejected('limit')
        if 'already taken' in lowered or 'already in use' in lowered:
            raise BotRejected('taken')
        if any(word in lowered for word in ('username is invalid', 'invalid username',
                                            'sorry, this username')):
            raise BotRejected('invalid')
    raise SetupStop('creation_unknown', tr('setup_botfather_outcome_unknown'))


def _valid_username(username):
    return (isinstance(username, str)
            and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', username) is not None
            and username.lower().endswith('bot'))


def _default_username_checker(client, username):
    from telethon.tl.functions.bots import CheckUsernameRequest
    try:
        time.sleep(0.2)
        result = client(CheckUsernameRequest(username))
    except Exception as exc:
        kind = type(exc).__name__
        code = getattr(exc, 'message', '')
        if kind in {'UsernameOccupiedError', 'UsernameInvalidError', 'UsernamePurchaseAvailableError',
                    'UsernameSuffixMissingError'} or code in {
                        'USERNAME_OCCUPIED', 'USERNAME_INVALID', 'USERNAME_PURCHASE_AVAILABLE',
                        'USERNAME_SUFFIX_MISSING'}:
            return False
        raise SetupStop('username_check_unavailable',
                        tr('setup_username_check_unavailable')) from None
    if type(result) is not bool:
        raise SetupStop('username_check_unavailable', tr('setup_username_check_unconfirmed'))
    return result


def _username_suggestion(client, username, checker):
    stem = username[:-3].rstrip('_')[:21]
    for _ in range(5):
        candidate = stem + '_' + uuid.uuid4().hex[:6] + '_bot'
        if _valid_username(candidate) and checker(client, candidate) is True:
            return candidate
    return None


def _name_prompt(label):
    print(label, end='', file=sys.stderr, flush=True)
    return input()


def _choose_username(client, current, record, save, checker, prompt, interactive):
    record.pop('suggested_username', None)
    suggestion = _username_suggestion(client, current, checker)
    if suggestion:
        record['suggested_username'] = suggestion
        save('creation_rejected')
    if not interactive:
        raise SetupStop('username_selection_required',
                        tr('setup_username_selection_required')
                        if suggestion else tr('setup_username_no_suggestion'))
    print(tr('setup_username_unavailable', p0=current), file=sys.stderr)
    if suggestion:
        print(tr('setup_username_suggestion', p0=suggestion), file=sys.stderr)
    else:
        print(tr('setup_username_manual_required'), file=sys.stderr)
    for _ in range(10):
        label = (tr('setup_username_accept_prompt')
                 if suggestion else tr('setup_username_custom_prompt'))
        answer = prompt(label).strip()
        if answer.lower() in {'q', 'quit', '取消'}:
            raise SetupStop('username_selection_required', tr('setup_username_cancelled'))
        if answer.lower() in {'y', 'yes', '是'} and suggestion:
            return suggestion
        if not answer or answer.lower() in {'n', 'no', '否'}:
            answer = prompt(tr('setup_username_custom_prompt')).strip()
            if not answer or answer.lower() in {'q', 'quit', '取消'}:
                raise SetupStop('username_selection_required', tr('setup_username_change_cancelled'))
        if not _valid_username(answer):
            print(tr('setup_username_format_help'), file=sys.stderr)
            continue
        if checker(client, answer) is True:
            return answer
        print(tr('setup_username_try_another'), file=sys.stderr)
    raise SetupStop('username_selection_required', tr('setup_username_not_selected'))


def _login(client, values, prompt, interactive):
    if client.is_user_authorized():
        return
    if not interactive:
        raise SetupStop('authorization_required', tr('setup_authorization_terminal_required'))
    phone = values.get('TG_PHONE', '')
    if not re.fullmatch(r'\+?[0-9]{5,20}', phone):
        raise SetupStop('configuration_required', tr('setup_login_config_required'), keys=('TG_PHONE',))
    response = client.send_code_request(phone)
    code = prompt(tr('setup_login_code_prompt')).strip()
    if not code:
        raise SetupStop('authorization_failed', tr('setup_login_cancelled'))
    try:
        client.sign_in(phone=phone, code=code, phone_code_hash=response.phone_code_hash)
    except Exception as exc:
        # 僅辨認 Telegram 的特定 2FA 類型，不回映錯誤內容。 / Recognize only Telegram's specific 2FA type; never echo exception contents.
        if type(exc).__name__ != 'SessionPasswordNeededError':
            raise SetupStop('authorization_failed', tr('setup_login_failed')) from None
        password = values.get('TG_2STEP_PASSWORD', '') or prompt(tr('setup_two_step_password_prompt'))
        if not password:
            raise SetupStop('authorization_failed', tr('setup_two_step_cancelled'))
        try:
            client.sign_in(password=password)
        except Exception:
            raise SetupStop('authorization_failed', tr('setup_two_step_failed')) from None
    if not client.is_user_authorized():
        raise SetupStop('authorization_failed', tr('setup_account_unauthorized'))


def _preflight_route(env, route, token=None, user_id=None):
    routes = custom_routes(env, BUILTIN_ROUTES)
    values = load_env(env, require_private=True)
    keys = ('TG_CUSTOM_' + route + '_TOKEN', 'TG_CUSTOM_' + route + '_CHAT_ID')
    if token is None:
        if route in routes or any(values.get(key) for key in keys):
            raise SetupStop('route_conflict', tr('setup_route_already_configured'))
    elif any(values.get(key) not in (None, '', wanted)
             for key, wanted in zip(keys, (token, str(user_id)))):
        raise SetupStop('route_conflict', tr('setup_route_overwrite_refused'))


def _saved_route_matches(env, record):
    routes = custom_routes(env, BUILTIN_ROUTES)
    route = record['route']
    if route not in routes:
        return False
    values = load_env(env, require_private=True)
    token_key, chat_key = routes[route]
    return (values.get(token_key) == record.get('token')
            and values.get(chat_key) == str(record.get('user_id')))


def _validate_record(record, env, name, username, route):
    if not record:
        return
    if (type(record.get('version')) is not int or record['version'] != 1
            or not isinstance(record.get('stage'), str) or record['stage'] not in STAGES):
        raise SetupStop('invalid_state', tr('setup_record_invalid'))
    if record.get('env_path') != str(env) or record.get('route') != route:
        raise SetupStop('state_conflict', tr('setup_record_path_conflict'))
    if (record.get('bot_name') != name or record.get('bot_username', '').lower() != username.lower()):
        if record.get('stage') not in ('prepared', 'creation_rejected'):
            raise SetupStop('state_conflict', tr('setup_record_name_conflict'))
        record.update(bot_name=name, bot_username=username, stage='prepared')
        record.pop('suggested_username', None)
    if record.get('token') is not None and not TOKEN_RE.fullmatch(str(record['token'])):
        raise SetupStop('invalid_state', tr('setup_saved_credentials_invalid'))
    if not _positive(record.get('user_id')):
        raise SetupStop('invalid_state', tr('setup_record_user_missing'))
    if record['stage'] not in ('prepared', 'creation_pending', 'creation_rejected') and not record.get('token'):
        raise SetupStop('invalid_state', tr('setup_record_token_missing'))
    if record['stage'] not in ('prepared', 'creation_pending', 'creation_rejected', 'bot_created_pending_verification') and not _positive(record.get('bot_id')):
        raise SetupStop('invalid_state', tr('setup_record_bot_missing'))
    if record['stage'] == 'completed' and not _positive(record.get('message_id')):
        raise SetupStop('invalid_state', tr('setup_record_receipt_missing'))


def _failure_hint(record):
    if record.get('stage') == 'creation_pending':
        return tr('setup_creation_unconfirmed')
    if record.get('stage') == 'start_pending':
        return tr('setup_start_unconfirmed')
    if record.get('stage') in ('notification_pending', 'notification_unknown'):
        return tr('setup_notification_may_have_arrived')
    return tr('setup_recovery_guidance')


def run_setup(args, *, client_factory=None, identity_lookup=None, notification_sender=None,
              bot_creator=None, secret_prompt=None, interactive=None, account_lock_dir=None,
              username_checker=None, username_prompt=None):
    """可注入完整離線 adapter；回傳僅含安全狀態，秘密只寫私有 journal。

Injectable offline adapters; return safe status only and store secrets in a private journal."""
    record = {}
    client = None
    try:
        env = absolute(args.env_path)
        values = load_env(env, require_private=True)
        name, username, route = _config(args, values)
        state = absolute(args.state_dir)
        journal = state / 'setup' / hashlib.sha256(str(env).encode()).hexdigest() / 'journal.json'
        record = read_json(journal) if journal.exists() or journal.is_symlink() else {}
        _validate_record(record, env, name, username, route)
        if args.check:
            if not record:
                return _result(record, 'not_started', tr('setup_record_missing'))
            # --check 只查保存內容與路由，不建立目錄或連網。 / --check reads saved state and routes without creating directories or connecting.
            _preflight_route(env, route, record.get('token'), record.get('user_id'))
            complete = (record.get('stage') == 'completed' and _positive(record.get('message_id'))
                        and _positive(record.get('bot_id')) and _positive(record.get('user_id'))
                        and _saved_route_matches(env, record))
            return _result(record, 'recorded_complete' if complete else 'incomplete',
                           tr('setup_local_record_checked'))
        private_directory(state)
        private_directory(journal.parent)
        with secure_lock(str(env) + '.setup.lock'):
            # 取得互斥後重新讀取，避免以等待前的狀態覆蓋新進度。 / Reread after acquiring the lock to avoid overwriting new progress with stale state.
            record = read_json(journal)
            _validate_record(record, env, name, username, route)
            if not record:
                record = {'version': 1, 'env_path': str(env), 'route': route,
                          'bot_name': name, 'bot_username': username, 'stage': 'prepared',
                          'setup_id': uuid.uuid4().hex}
            def save(stage):
                previous_stage = record['stage']
                record['stage'] = stage
                try:
                    write_json(journal, record)
                except Exception:
                    # 對外階段保守停留在上一個已確認寫入點。 / Keep the reported stage at the last confirmed write point.
                    record['stage'] = previous_stage
                    raise
            _preflight_route(env, route, record.get('token'), record.get('user_id'))
            # 在 BotFather 副作用前確定預設 adapters 的相依已安裝。 / Verify default adapter dependencies before BotFather side effects.
            if client_factory is None:
                from telethon.sync import TelegramClient  # noqa: F401
            if identity_lookup is None or notification_sender is None:
                import requests  # noqa: F401
            if bot_creator is None:
                from provision_telegram_bot import send_and_wait_botfather_reply  # noqa: F401
            if notification_sender is None:
                from tg_delivery import request_with_retry  # noqa: F401
            session = state / 'botfather_user'
            _session_files(session)
            can_prompt = (sys.stdin.isatty() and sys.stderr.isatty()) if interactive is None else bool(interactive)
            can_prompt = can_prompt and not args.non_interactive
            factory = client_factory or _default_client
            with _connected_client(factory, session, int(values['TG_API_ID']), values['TG_API_HASH']) as client:
                _login(client, values, secret_prompt or _hidden_prompt, can_prompt)
                _session_files(session)
                me = client.get_me()
                user_id = getattr(me, 'id', None)
                if not _positive(user_id) or getattr(me, 'bot', False):
                    raise SetupStop('account_mismatch', tr('setup_session_user_invalid'))
                phone = values.get('TG_PHONE', '')
                actual_phone = getattr(me, 'phone', None)
                if phone and actual_phone and re.sub(r'\D', '', phone) != re.sub(r'\D', '', str(actual_phone)):
                    raise SetupStop('account_mismatch', tr('setup_session_login_mismatch'))
                if record.get('user_id') not in (None, user_id):
                    raise SetupStop('account_mismatch', tr('setup_session_record_mismatch'))
                record['user_id'] = user_id
                locks = account_lock_dir
                if locks is None:
                    locks = Path(os.getenv('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'tg-config-public/setup-account-locks'
                locks = private_directory(locks)
                with secure_lock(locks / (str(user_id) + '.lock')):
                    return _setup_authorized(args, values, env, record, save, client,
                                             identity_lookup or _default_identity,
                                             notification_sender or _default_notification,
                                             bot_creator or _default_creator,
                                             interactive=can_prompt,
                                             username_checker=username_checker or _default_username_checker,
                                             username_prompt=username_prompt or _name_prompt)
    except SetupStop as exc:
        return _result(record, exc.status, exc.hint, keys=exc.keys)
    except (ImportError, ModuleNotFoundError):
        return _result(record, 'dependencies_required', tr('setup_dependencies_required'))
    except (KeyboardInterrupt, EOFError):
        return _result(record, 'cancelled', tr('setup_cancelled_resume'))
    except SettingsError:
        return _result(record, 'storage_error',
                       tr('setup_storage_error_prefix') + _failure_hint(record))
    except Exception:
        return _result(record, 'setup_failed', _failure_hint(record))
def _setup_authorized(args, values, env, record, save, client, lookup, sender, creator, *,
                      interactive=False, username_checker=None, username_prompt=None):
    stage = record['stage']
    token = record.get('token')
    recovery = values.get('TG_SETUP_BOT_TOKEN')
    if token and recovery and token != recovery:
        raise SetupStop('identity_conflict', tr('setup_recovery_token_conflict'))
    if not token:
        if recovery:
            token = recovery
        elif stage == 'creation_pending':
            raise SetupStop('creation_unknown', tr('setup_creation_outcome_unknown'))
        else:
            for attempt in range(5):
                save('creation_pending')
                try:
                    token = creator(client, record['bot_name'], record['bot_username'])
                    break
                except BotRejected as exc:
                    save('creation_rejected')
                    if exc.reason not in ('taken', 'invalid'):
                        raise SetupStop('creation_rejected', tr('setup_creation_rejected')) from None
                    if attempt == 4:
                        raise SetupStop('username_selection_required', tr('setup_username_attempts_exceeded')) from None
                    chosen = _choose_username(client, record['bot_username'], record, save,
                                              username_checker, username_prompt, interactive)
                    # 只在使用者確認後保存；若其中一段失敗，仍停留於已確認的拒絕階段。 / Save only after confirmation; on failure remain at the confirmed rejection stage.
                    write_env_keys(env, {'TG_SETUP_BOT_USERNAME': chosen})
                    record['bot_username'] = chosen
                    args.bot_username = chosen
                    record.pop('suggested_username', None)
                    save('prepared')
        if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
            raise SetupStop('creation_unknown', tr('setup_creation_token_invalid'))
        record['token'] = token
        save('bot_created_pending_verification')
    identity = lookup(token)
    if (not isinstance(identity, dict) or not _positive(identity.get('id'))
            or identity.get('is_bot') is not True
            or not isinstance(identity.get('username'), str)
            or identity['username'].lower() != record['bot_username'].lower()
            or record.get('bot_id') not in (None, identity['id'])):
        raise SetupStop('identity_failed', tr('setup_bot_identity_mismatch'))
    record['bot_id'] = identity['id']
    record['bot_username'] = identity['username']
    if record['stage'] in ('prepared', 'creation_pending', 'creation_rejected', 'bot_created_pending_verification'):
        save('verified')
    _preflight_route(env, record['route'], token, record['user_id'])
    if record['stage'] == 'completed' and not _saved_route_matches(env, record):
        raise SetupStop('incomplete', tr('setup_completed_route_mismatch'))
    if record['stage'] == 'completed' and not args.test_again:
        return _result(record, 'completed', tr('setup_already_complete'))
    register_route(env, record['route'], token, record['user_id'], BUILTIN_ROUTES)
    if record['stage'] == 'verified':
        save('route_saved')
    if record['stage'] == 'start_pending':
        if not args.confirm_started:
            raise SetupStop('start_unknown', tr('setup_start_unknown_phone'))
        save('started')
    if record['stage'] == 'route_saved':
        save('start_pending')
        message = client.send_message(record['bot_username'], '/start')
        if not _positive(getattr(message, 'id', None)):
            raise SetupStop('start_unknown', tr('setup_start_unknown'))
        save('started')
    stage = record['stage']
    if stage in ('notification_pending', 'notification_unknown') and not args.test_again:
        raise SetupStop('notification_unknown', tr('setup_test_again_required'))
    if stage == 'notification_retry_later':
        not_before = record.get('not_before')
        if not isinstance(not_before, (int, float)) or isinstance(not_before, bool) or not math.isfinite(not_before):
            raise SetupStop('notification_retry_later', tr('setup_retry_deadline_missing'))
        if time.time() < not_before:
            raise SetupStop('notification_retry_later', tr('setup_retry_deadline_pending'))
    record['notification_id'] = uuid.uuid4().hex
    record.pop('message_id', None)
    save('notification_pending')
    response = sender(token, record['user_id'], tr('setup_test_notification_prefix') + record['notification_id'])
    message = response.get('result') if isinstance(response, dict) else None
    chat = message.get('chat') if isinstance(message, dict) else None
    if (isinstance(response, dict) and response.get('ok') is True and isinstance(message, dict)
            and _positive(message.get('message_id')) and isinstance(chat, dict)
            and type(chat.get('id')) is int and chat['id'] == record['user_id']):
        record['message_id'] = message['message_id']
        record.pop('not_before', None)
        save('completed')
        return _result(record, 'completed', tr('setup_complete'))
    delivery = response.get('delivery') if isinstance(response, dict) else None
    delivery = delivery if isinstance(delivery, dict) else {}
    outcome = delivery.get('status')
    if outcome == 'retry_later' or (isinstance(response, dict) and response.get('error_code') == 429):
        delay = delivery.get('retry_after')
        if delay is None and isinstance(response.get('parameters'), dict):
            delay = response['parameters'].get('retry_after')
        if isinstance(delay, (int, float)) and not isinstance(delay, bool) and math.isfinite(delay) and delay >= 0:
            record['not_before'] = time.time() + delay
        else:
            record.pop('not_before', None)
        save('notification_retry_later')
        raise SetupStop('notification_retry_later', tr('setup_notification_retry_saved'))
    if (isinstance(response, dict) and response.get('ok') is False
            and (outcome == 'failed' or (outcome is None and type(response.get('error_code')) is int
                                      and 400 <= response['error_code'] < 500))):
        save('notification_failed')
        raise SetupStop('notification_failed', tr('setup_notification_failed'))
    save('notification_unknown')
    raise SetupStop('notification_unknown', tr('setup_first_notification_unknown'))


@language_errors
def main(argv=None, **dependencies):
    try:
        argv = configure_language(argv)
    except LanguageError as error:
        print(str(error), file=sys.stderr)
        return 2
    args = parser().parse_args(argv)
    runner = dependencies.pop('run_setup', run_setup)
    try:
        result = runner(args, **dependencies)
    except (KeyboardInterrupt, EOFError):
        result = {'status': 'cancelled', 'hint': tr('setup_cancelled')}
    except Exception:
        result = {'status': 'setup_failed', 'hint': tr('setup_incomplete')}
    # 只印核心產生的固定診斷及白名單欄位，不印 adapter 原始回傳。 / Print fixed core diagnostics and allowed fields, never raw adapter responses.
    print(result.get('hint', tr('setup_incomplete')))
    if result.get('keys'):
        print(tr('setup_config_keys_prefix') + ', '.join(result['keys']))
    for key in ('status', 'stage', 'route', 'bot_username', 'suggested_username', 'bot_id', 'user_id', 'message_id'):
        if key in result:
            print(key + '=' + str(result[key]))
    return 0 if result.get('status') in ('completed', 'recorded_complete') else 1


if __name__ == '__main__':
    raise SystemExit(main())
