"""中英介面與安裝語言偏好 / Bilingual UI and installation language preference.

Only project-owned messages are translated; payloads and protocol fields are not.
只翻譯專案自有訊息；使用者內容、通訊欄位及第三方回覆保留原文。
"""
from __future__ import annotations

import argparse
import configparser
from contextvars import ContextVar
from functools import lru_cache, wraps
import json
import os
from pathlib import Path
import stat
import re
import string
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
LANGUAGES = ("zh-TW", "en")
LANGUAGE_FILES = {"zh-TW": "zh_TW.ini", "en": "en.ini"}
PREFERENCE_FILE = ".tg-language"
_language = ContextVar("tg_ui_language", default=None)


class LanguageError(Exception):
    """固定雙語錯誤 / Fixed bilingual error without argument contents."""


def language_errors(function):
    """CLI 顯示固定診斷；函式庫保留例外 / Show safe CLI errors while libraries keep exceptions."""
    @wraps(function)
    def run(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except LanguageError as error:
            print(str(error), file=sys.stderr)
            return 2
    return run


def set_language(value):
    if value not in LANGUAGES:
        raise LanguageError("語言無效，請選 zh-TW 或 en。 / Invalid language; choose zh-TW or en.")
    _language.set(value)
    return value


def saved_language(root=ROOT):
    path = Path(root) / PREFERENCE_FILE
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        raise LanguageError("無法安全讀取語言偏好。 / Cannot safely read the language preference.") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError
        value = os.read(fd, 32).decode("ascii").strip()
        if value not in LANGUAGES:
            raise ValueError
        return value
    except (OSError, ValueError, UnicodeError):
        raise LanguageError("語言偏好無效；請核對 .tg-language 與 0600 權限。 / Invalid .tg-language; check its value and 0600 permissions.") from None
    finally:
        os.close(fd)


def language():
    selected = _language.get()
    if selected is not None:
        return selected
    value = os.environ.get("TG_LANGUAGE")
    return set_language(value if value is not None else saved_language() or "en")


@lru_cache(maxsize=len(LANGUAGES))
def _read_pack(path):
    """以鍵名讀取單一語言包，保留空白與 % / Load one keyed pack, preserving whitespace and %."""
    parser = configparser.ConfigParser(interpolation=None, strict=True, delimiters=("=",),
                                       inline_comment_prefixes=None, empty_lines_in_values=False)
    parser.optionxform = str
    try:
        parser.read_string(path.read_text(encoding="utf-8"))
        if parser.sections() != ["messages"] or parser.defaults():
            raise ValueError
        messages = {}
        for key, raw in parser.items("messages", raw=True):
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
                raise ValueError
            value = json.loads(raw)
            if not isinstance(value, str) or not value:
                raise ValueError
            for _, field, specification, conversion in string.Formatter().parse(value):
                if field is not None and (not re.fullmatch(r"[a-z][a-z0-9_]*", field)
                                          or specification or conversion not in (None, "s", "r", "a")):
                    raise ValueError
            messages[key] = value
        if not messages:
            raise ValueError
        return messages
    except (OSError, UnicodeError, configparser.Error, ValueError, TypeError):
        raise LanguageError("語言包缺失或格式無效；請核對 languages/。 / Language pack missing or invalid; check languages/.") from None


def load_messages(selected):
    if selected not in LANGUAGE_FILES:
        raise LanguageError("語言無效，請選 zh-TW 或 en。 / Invalid language; choose zh-TW or en.")
    return _read_pack(ROOT / "languages" / LANGUAGE_FILES[selected])


def tr(message_key, **values):
    """固定鍵名取文字，不使用行號或原文 / Look up stable IDs, never line numbers or source text."""
    try:
        return load_messages(language())[message_key].format(**values)
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        raise LanguageError("訊息鍵或預留欄位無效；請核對語言包。 / Invalid message key or placeholders; check the language pack.") from None


def save_language(root, selected=None):
    selected = language() if selected is None else selected
    if selected not in LANGUAGES:
        raise LanguageError("語言無效，請選 zh-TW 或 en。 / Invalid language; choose zh-TW or en.")
    root = Path(root)
    target = root / PREFERENCE_FILE
    temporary = None
    try:
        try:
            info = target.lstat()
        except FileNotFoundError:
            info = None
        if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()):
            raise OSError
        fd, temporary = tempfile.mkstemp(prefix=".tg-language-", dir=root)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(selected + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise LanguageError("相依已安裝，但無法保存語言偏好。 / Dependencies installed, but the language preference could not be saved.") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def configure_language(argv=None, *, root=ROOT, menu=False, interactive=None, ask=None):
    """解析介面選項，不接觸 Telegram / Parse UI options without contacting Telegram."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    remaining, explicit = [], None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            remaining.extend(arguments[index:])
            break
        if argument == "--language" or argument.startswith("--language="):
            if explicit is not None:
                raise LanguageError("語言只可指定一次。 / Specify the language only once.")
            if argument == "--language":
                index += 1
                if index >= len(arguments):
                    raise LanguageError("請指定 --language zh-TW 或 en。 / Specify --language zh-TW or en.")
                explicit = arguments[index]
            else:
                explicit = argument.partition("=")[2]
            set_language(explicit)
        else:
            remaining.append(argument)
        index += 1
    environment = os.environ.get("TG_LANGUAGE")
    selected = explicit if explicit is not None else environment
    if selected is None:
        selected = saved_language(root) or "en"
    set_language(selected)
    terminal = sys.stdin.isatty() if interactive is None else interactive
    if (menu and terminal and explicit is None and environment is None
            and not any(flag in remaining for flag in ("--help", "-h", "--non-interactive"))):
        print("請選擇安裝語言 / Choose installation language:\n1. 正體中文\n2. English", file=sys.stderr)
        default = "1" if selected == "zh-TW" else "2"
        for _ in range(10):
            try:
                prompt = f"請輸入 1 或 2 / Enter 1 or 2 [{default}]: "
                print(prompt, end="", file=sys.stderr, flush=True)
                choice = (ask or input)().strip() or default
            except (EOFError, KeyboardInterrupt):
                raise LanguageError("語言選擇已取消；尚未開始安裝。 / Language selection cancelled; installation has not started.") from None
            if choice in ("1", "2"):
                set_language("zh-TW" if choice == "1" else "en")
                break
            print("請輸入 1 或 2。 / Please enter 1 or 2.", file=sys.stderr)
        else:
            raise LanguageError("未選定安裝語言。 / No installation language selected.")
    load_messages(language())
    return remaining


class LanguageArgumentParser(argparse.ArgumentParser):
    """翻譯 help 外框並保護錯誤參數 / Localized help with safe argument errors."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_argument("--language", choices=LANGUAGES, help=tr('cli_language_help'))
        for action in self._actions:
            if isinstance(action, argparse._HelpAction):
                action.help = tr('cli_help_action')
        for group in self._action_groups:
            key = {"positional arguments": "cli_positional_arguments", "options": "cli_options"}.get(group.title)
            if key:
                group.title = tr(key)

    def format_usage(self):
        return super().format_usage().replace("usage: ", tr('cli_usage_prefix'), 1)

    def format_help(self):
        return super().format_help().replace("usage: ", tr('cli_usage_prefix'), 1)

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, tr('cli_arguments_invalid'))
