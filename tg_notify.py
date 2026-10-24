# -*- coding: utf-8 -*-
import os
import sys
import html
import hashlib
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any

# 套件及外部 symlink 載入時，先定位檔案實體目錄的共用模組。
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_i18n import tr, language_errors, configure_language, LanguageError
from tg_delivery import MAX_INLINE_WAIT_SECONDS, redact, request_with_retry, split_plaintext
from tg_settings import custom_routes

_ENV_LOADED = False
_ENV_PATH = os.environ.get("TG_CONFIG_ENV_PATH", str(Path(__file__).resolve().parent / ".env"))
_MAX_RETRIES = 3
_RETRY_WAIT_SECONDS = 5
_BOT_CONFIG = {
    "DEFAULT": ("TG_BOT_TOKEN", "TG_CHAT_ID"),
}

def _load_env_file(env_path: str, keys: set[str] | None = None) -> dict[str, str]:
    """Read selected notification keys without exporting the shared env file.

讀取指定通知鍵，不匯出共用設定檔。"""
    if keys is None:
        keys = {key for pair in _BOT_CONFIG.values() for key in pair}
    values: dict[str, str] = {}
    path = Path(env_path)
    if not path.exists():
        return values
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in keys:
                values[key] = value.strip().strip('"').strip("'")
    return values


def _ensure_env_loaded() -> None:
    """Compatibility hook: credentials are now selected per call, not exported.

相容入口：每次呼叫選擇憑證，不匯出環境變數。"""
    return None


def get_bot_credentials(bot_type: str) -> tuple[str, str]:
    """Preserve file-over-environment precedence and the existing Bot routing.

保留設定檔優先於環境變數的順序，以及既有 Bot 路由。"""
    normalized = bot_type.upper()
    route_config = _BOT_CONFIG if normalized in _BOT_CONFIG else custom_routes(_ENV_PATH, _BOT_CONFIG)
    if normalized not in route_config:
        raise ValueError(tr('notify_bot_type_unsupported', p0=normalized, p1=', '.join(_BOT_CONFIG)))
    token_key, chat_key = route_config[normalized]
    values = _load_env_file(_ENV_PATH, {token_key, chat_key})
    token = values.get(token_key, os.getenv(token_key, ""))
    chat_id = values.get(chat_key, os.getenv(chat_key, ""))
    if not token or not chat_id:
        raise RuntimeError(tr('notify_credentials_missing', p0=token_key, p1=chat_key))
    return token, chat_id


def _post_json(token: str, method: str, payload: dict, timeout: int,
               wait_budget: float = MAX_INLINE_WAIT_SECONDS) -> dict:
    return request_with_retry(
        lambda: requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload, timeout=timeout,
        ),
        secrets=(token,), max_attempts=_MAX_RETRIES,
        retry_wait=_RETRY_WAIT_SECONDS, sleep=time.sleep,
        wait_budget=wait_budget,
    )


def _text_result(data, accepted, total, fingerprint, results, unknown_part=None, inline_wait=0.0):
    response = dict(data)
    delivery = dict(response.get("delivery") or {})
    status = delivery.get("status", "success" if response.get("ok") else "failed")
    if not response.get("ok") and accepted and status == "failed":
        status = "partial"
    receipt = {
        "fingerprint": fingerprint,
        "accepted": [{"index": index, "message_id": ident}
                     for index, ident in sorted(accepted.items())],
    }
    if unknown_part is not None:
        receipt["unknown_part"] = unknown_part
    delivery.update(
        status=status, accepted_parts=len(accepted), total_parts=total,
        message_ids=[ident for _index, ident in sorted(accepted.items())],
        resume=receipt,
        inline_wait_seconds=inline_wait,
    )
    response["delivery"] = delivery
    if total > 1:
        response["results"] = results
    return response


def send_text(
    text: str,
    bot_type: str = "DEFAULT",
    parse_mode: Optional[str] = "HTML",
    *,
    resume: dict | None = None,
) -> Dict[str, Any]:
    """Send through existing routes; split plain and literal-HTML text.

    Default HTML keeps the previous literal-text escaping behavior. A receipt
    skips acknowledged pieces; it is not a durable outbox.

透過既有路由送出，支援純文字與按字面處理的 HTML 拆段。預設 HTML 保留原有文字跳脫行為；回執可略過已確認片段，但不是持久化待送佇列。"""
    token, chat_id = get_bot_credentials(bot_type)
    if not isinstance(text, str) or not text:
        return {"ok": False, "error_code": 400, "description": tr('notify_message_empty'),
                "delivery": {"status": "failed", "attempts": 0, "error_kind": "invalid_input"}}
    pieces = split_plaintext(text)
    if len(pieces) > 1 and parse_mode not in (None, "HTML"):
        return {"ok": False, "error_code": 400,
                "description": tr('notify_long_format_unsupported'),
                "delivery": {"status": "failed", "attempts": 0, "error_kind": "unsupported_format"}}
    fingerprint = hashlib.sha256(
        json.dumps([bot_type.upper(), hashlib.sha256(token.encode()).hexdigest(),
                    chat_id, parse_mode, pieces], ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    accepted: dict[int, int] = {}
    results: list = []
    inline_wait = 0.0
    if resume is not None:
        if not isinstance(resume, dict) or resume.get("fingerprint") != fingerprint:
            raise ValueError(tr('notify_resume_mismatch'))
        entries = resume.get("accepted", [])
        if not isinstance(entries, list):
            raise ValueError(tr('notify_resume_invalid'))
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(tr('notify_resume_invalid'))
            index, ident = entry.get("index"), entry.get("message_id")
            if (type(index) is not int or type(ident) is not int
                    or not 0 <= index < len(pieces) or ident < 1 or index in accepted):
                raise ValueError(tr('notify_resume_invalid'))
            accepted[index] = ident
        if resume.get("unknown_part") is not None:
            unknown = resume["unknown_part"]
            if type(unknown) is not int or not 0 <= unknown < len(pieces) or unknown in accepted:
                raise ValueError(tr('notify_resume_invalid'))
            return _text_result(
                {"ok": False, "description": tr('notify_previous_part_unknown'),
                 "delivery": {"status": "unknown", "attempts": 0, "error_kind": "previous_unknown"}},
                accepted, len(pieces), fingerprint, results, unknown,
            )
    last = {"ok": True, "result": None, "delivery": {"status": "success", "attempts": 0}}
    for index, piece in enumerate(pieces):
        if index in accepted:
            continue
        payload = {"chat_id": chat_id, "text": html.escape(piece) if parse_mode == "HTML" else piece}
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        last = _post_json(token, "sendMessage", payload, timeout=10,
                          wait_budget=MAX_INLINE_WAIT_SECONDS - inline_wait)
        inline_wait += (last.get("delivery") or {}).get("waited_seconds", 0.0)
        if not last.get("ok"):
            unknown = index if (last.get("delivery") or {}).get("status") == "unknown" else None
            return _text_result(last, accepted, len(pieces), fingerprint, results, unknown,
                                inline_wait=inline_wait)
        message = last.get("result")
        ident = message.get("message_id") if isinstance(message, dict) else None
        if type(ident) is not int or ident < 1:
            return _text_result(
                {"ok": False, "description": tr('notify_receipt_invalid'),
                 "delivery": {"status": "unknown", "attempts": (last.get("delivery") or {}).get("attempts", 1),
                              "error_kind": "invalid_success_response"}},
                accepted, len(pieces), fingerprint, results, index, inline_wait=inline_wait,
            )
        accepted[index] = ident
        results.append(message)
    return _text_result(last, accepted, len(pieces), fingerprint, results, inline_wait=inline_wait)


def send_photo(
    photo_path: str | Path,
    caption: str = "",
    bot_type: str = "DEFAULT",
) -> Dict[str, Any]:
    """Reopen the photo for every permitted retry, preserving the old fields.

每次允許的重試重新開啟圖片，保留既有欄位。"""
    token, chat_id = get_bot_credentials(bot_type)
    path = Path(photo_path)

    def send():
        with path.open("rb") as photo:
            return requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"photo": (path.name, photo, "image/jpeg")}, timeout=30,
            )

    try:
        return request_with_retry(
            send, secrets=(token,), max_attempts=_MAX_RETRIES,
            retry_wait=_RETRY_WAIT_SECONDS, sleep=time.sleep,
        )
    except OSError:
        return {"ok": False, "description": tr('notify_photo_unreadable'),
                "delivery": {"status": "failed", "attempts": 0, "error_kind": "local_file"}}






@language_errors
def main(argv: list[str] | None = None) -> int:
    import sys
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
        print(tr('notify_usage'))
        print("bot_type: " + " / ".join(_BOT_CONFIG))
        print(tr('notify_parse_mode_help'))
        print(tr('cli_language_options'))
        return 0
    bot_type = args[1] if len(args) > 1 else "DEFAULT"
    parse_mode = "HTML"
    if len(args) > 2:
        parse_mode = None if args[2].strip().upper() in ("NONE", "TEXT", "PLAIN") else args[2].strip().upper()
    try:
        response = send_text(args[0], bot_type, parse_mode)
    except (ValueError, RuntimeError, OSError):
        print(tr('notify_not_sent'), file=sys.stderr)
        return 2
    if response.get("ok"):
        return 0
    status = (response.get("delivery") or {}).get("status", "failed")
    print(tr('notify_delivery_status', p0=status, p1=redact(response.get('description', tr('common_delivery_failed')))), file=sys.stderr)
    return {"partial": 4, "unknown": 5, "retry_later": 6}.get(status, 1)


if __name__ == "__main__":
    raise SystemExit(main())
