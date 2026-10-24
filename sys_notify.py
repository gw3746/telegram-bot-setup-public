# -*- coding: utf-8 -*-
import sys
from pathlib import Path

# 套件及外部 symlink 載入時，先定位檔案實體目錄的共用模組。
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_i18n import tr, language_errors, configure_language, LanguageError
from tg_notify import send_text
from tg_delivery import redact


def _print_help() -> None:
    print(tr('system_notify_usage'))
    print(tr('system_notify_parse_mode_help'))
    print(tr('cli_language_options'))


@language_errors
def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        args = configure_language(args)
    except LanguageError as error:
        print(str(error), file=sys.stderr)
        return 2
    literal = bool(args and args[0] == '--')
    if literal:
        args = args[1:]
    if not args or (not literal and args[0] in ("-h", "--help")):
        _print_help()
        return 0
    msg = args[0]
    # Preserve the previous actual default (plain text). / 保留既有實際預設（純文字）。
    parse_mode = None
    if len(args) > 1:
        parse_arg = args[1].strip().upper()
        parse_mode = None if parse_arg in ("NONE", "TEXT", "PLAIN") else parse_arg
    try:
        result = send_text(tr('system_notify_message', p0=msg), "DEFAULT", parse_mode=parse_mode)
    except (ValueError, RuntimeError, OSError):
        print(tr('system_notify_not_sent'), file=sys.stderr)
        return 2
    if result.get("ok"):
        return 0
    status = (result.get("delivery") or {}).get("status", "failed")
    print(tr('system_notify_status', p0=status, p1=redact(result.get('description', tr('common_delivery_failed')))), file=sys.stderr)
    return {"partial": 4, "unknown": 5, "retry_later": 6}.get(status, 1)


if __name__ == "__main__":
    raise SystemExit(main())
