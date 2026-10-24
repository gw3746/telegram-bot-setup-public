"""首次設定共用的安全檔案及資料路由，不載入 Telegram 相依。

Shared secure setup files and routes without importing Telegram dependencies."""
from __future__ import annotations
from tg_i18n import tr

from contextlib import contextmanager
from collections.abc import Collection
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import tempfile


ROOT = Path(__file__).resolve().parent
BUILTIN_ROUTE_NAMES = frozenset({'DEFAULT'})
ROUTE_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,31}")
ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class SettingsError(ValueError):
    """僅包含固定、安全診斷，不包含原始秘密或例外。

Fixed safe diagnostics only; no raw secrets or exceptions."""


def absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(Path(path).expanduser()))


def _directories(path: Path, *, create: bool = False) -> None:
    try:
        for part in [*reversed(path.parents), path]:
            try:
                info = part.lstat()
            except FileNotFoundError:
                if not create:
                    raise
                part.mkdir(mode=0o700)
                info = part.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise SettingsError(tr('settings_directory_symlink_refused'))
    except OSError:
        raise SettingsError(tr('settings_directory_unavailable')) from None


def private_directory(path: str | Path) -> Path:
    target = absolute(path)
    if target in {ROOT, *ROOT.parents, Path.home(), Path('/tmp'), Path('/var/tmp')}:
        raise SettingsError(tr('settings_dedicated_directory_required'))
    _directories(target, create=True)
    try:
        if target.stat().st_uid != os.getuid():
            raise SettingsError(tr('settings_directory_owner_invalid'))
        target.chmod(0o700)
    except OSError:
        raise SettingsError(tr('settings_directory_protection_failed')) from None
    return target


def read_bytes(path: str | Path, *, require_private: bool = False) -> bytes:
    target = absolute(path)
    _directories(target.parent)
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise SettingsError(tr('settings_regular_file_required'))
            if require_private and stat.S_IMODE(info.st_mode) & 0o077:
                raise SettingsError(tr('settings_private_permissions_required'))
            return handle.read()
    except FileNotFoundError:
        raise
    except OSError:
        raise SettingsError(tr('settings_config_read_failed')) from None


def write_private(path: str | Path, content: bytes) -> None:
    target = absolute(path)
    _directories(target.parent, create=True)
    temp = None
    try:
        mode = 0o600
        if target.is_symlink():
            raise SettingsError(tr('settings_symlink_write_refused'))
        if target.exists():
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise SettingsError(tr('settings_nonregular_write_refused'))
            mode &= stat.S_IMODE(info.st_mode)
        fd, name = tempfile.mkstemp(prefix='.tg-setup-', dir=target.parent)
        temp = Path(name)
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        raise SettingsError(tr('settings_write_failed')) from None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def read_json(path: str | Path, default=None) -> dict:
    try:
        raw = read_bytes(path, require_private=True)
    except FileNotFoundError:
        return {} if default is None else default
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise SettingsError(tr('settings_state_format_invalid')) from None
    if not isinstance(value, dict):
        raise SettingsError(tr('settings_object_required'))
    return value


def write_json(path: str | Path, value: dict) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    write_private(path, data)
    if read_bytes(path, require_private=True) != data:
        raise SettingsError(tr('settings_state_verification_failed'))


def load_env(path: str | Path, *, require_private: bool = False) -> dict[str, str]:
    try:
        text = read_bytes(path, require_private=require_private).decode('utf-8')
    except FileNotFoundError:
        return {}
    except UnicodeError:
        raise SettingsError(tr('settings_utf8_required')) from None
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not ENV_KEY.fullmatch(key):
            raise SettingsError(tr('settings_key_invalid'))
        values[key] = value.strip().strip('\"').strip("'")
    return values


def write_env_keys(path: str | Path, updates: dict[str, str]) -> None:
    if any(not ENV_KEY.fullmatch(key) or not isinstance(value, str)
           or any(char in value for char in '\r\n\0') for key, value in updates.items()):
        raise SettingsError(tr('settings_update_invalid'))
    try:
        text = read_bytes(path).decode('utf-8')
    except FileNotFoundError:
        text = ''
    except UnicodeError:
        raise SettingsError(tr('settings_utf8_required')) from None
    seen, lines = set(), []
    for line in text.splitlines():
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
        if key in updates:
            lines.append(key + '=' + updates[key])
            seen.add(key)
        else:
            lines.append(line)
    lines.extend(key + '=' + value for key, value in updates.items() if key not in seen)
    write_private(path, ('\n'.join(lines) + '\n').encode('utf-8'))


@contextmanager
def secure_lock(path: str | Path):
    target = absolute(path)
    _directories(target.parent, create=True)
    fd = None
    try:
        try:
            fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise SettingsError(tr('settings_regular_lock_required'))
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SettingsError(tr('settings_setup_already_running')) from None
        except OSError:
            raise SettingsError(tr('settings_lock_failed')) from None
        yield
    finally:
        if fd is not None:
            os.close(fd)


def route_file(env_path: str | Path) -> Path:
    path = absolute(env_path)
    return path.with_name(path.name + '.routes.json')


def custom_routes(env_path: str | Path, builtin: Collection[str]) -> dict[str, tuple[str, str]]:
    payload = read_json(route_file(env_path))
    if not payload:
        return {}
    if type(payload.get('version')) is not int or payload['version'] != 1 or not isinstance(payload.get('routes'), dict):
        raise SettingsError(tr('settings_custom_routes_invalid'))
    result = {}
    for name, keys in payload['routes'].items():
        if (not isinstance(name, str) or not ROUTE_NAME.fullmatch(name) or name in builtin
                or not isinstance(keys, dict) or set(keys) != {'token_key', 'chat_id_key'}):
            raise SettingsError(tr('settings_custom_route_conflict'))
        expected = ('TG_CUSTOM_' + name + '_TOKEN', 'TG_CUSTOM_' + name + '_CHAT_ID')
        if (keys['token_key'], keys['chat_id_key']) != expected:
            raise SettingsError(tr('settings_route_mapping_invalid'))
        result[name] = expected
    return result


def register_route(env_path: str | Path, name: str, token: str, chat_id: int, builtin: Collection[str]) -> dict:
    name = name.upper()
    if not ROUTE_NAME.fullmatch(name) or name in builtin:
        raise SettingsError(tr('settings_custom_route_name_required'))
    if not isinstance(token, str) or not re.fullmatch(r'\d{6,}:[A-Za-z0-9_-]{20,}', token):
        raise SettingsError(tr('settings_route_token_invalid'))
    if type(chat_id) is not int or chat_id <= 0:
        raise SettingsError(tr('settings_private_user_required'))
    keys = ('TG_CUSTOM_' + name + '_TOKEN', 'TG_CUSTOM_' + name + '_CHAT_ID')
    with secure_lock(str(route_file(env_path)) + '.lock'):
        routes = custom_routes(env_path, builtin)
        values = load_env(env_path, require_private=True)
        wanted = {keys[0]: token, keys[1]: str(chat_id)}
        if any(values.get(key) not in (None, '', value) for key, value in wanted.items()):
            raise SettingsError(tr('settings_route_overwrite_refused'))
        if name in routes and any(values.get(key) != value for key, value in wanted.items()):
            raise SettingsError(tr('settings_route_state_inconsistent'))
        write_env_keys(env_path, wanted)
        routes[name] = keys
        write_json(route_file(env_path), {'version': 1, 'routes': {
            route: {'token_key': pair[0], 'chat_id_key': pair[1]} for route, pair in routes.items()}})
    return {'route': name, 'token_key': keys[0], 'chat_id_key': keys[1]}
