"""Shared Telegram request safety policies for the isolated integration candidate.

This is an original implementation. Design references (Telegram retry_after,
PTB rate limiting, aiogram error categories, Apprise result tracking) belong in
the integration attribution document. No upstream implementation is copied.

The helper never logs request URLs, payloads, credentials, or raw exceptions.
It reports API acceptance, not a recipient's read status. An ambiguous transport
failure is deliberately not retried: the first request may already have arrived.

整合副本共用的 Telegram 請求安全規則。此為自有實作；Telegram retry_after、PTB 限流、aiogram 錯誤分類及 Apprise 回執等設計參考列在來源文件，未複製上游實作。不記錄請求 URL、內容、憑證或原始例外；回報 API 接受狀態而非使用者已讀狀態。傳輸結果不明時不自動重試，以免重複送達。"""
from __future__ import annotations

import math
import re
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import requests

# 套件及外部 symlink 載入時，先定位檔案實體目錄的共用模組。
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_i18n import tr

# A long server-directed wait is handed back to the caller rather than blocking / 過長的伺服器指定等待交回呼叫端，
# a cron process indefinitely or retrying before Telegram permits it. / 避免排程無限阻塞或在 Telegram 允許前重試。
MAX_INLINE_WAIT_SECONDS = 30.0
_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:bot)?\d{5,}:[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"
)
_FIELD_PATTERN = re.compile(
    r"(?i)(?P<key>[\"']?\b(?:TG_)?(?:API_HASH|2STEP_PASSWORD|PHONE)\b[\"']?"
    r"|[\"']?\bSESSION(?:_PATH)?\b[\"']?)"
    r"(?P<separator>\s*[=:]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;\]}]+)"
)


def redact(value: object, secrets: Iterable[str] = ()) -> str:
    """Return diagnostic text with known credentials and common fields removed.

    This is defense in depth, not a way to recognize every arbitrary secret.
    Callers should supply all credentials used for the request and avoid logging
    sensitive payloads in the first place. The argument may also be one secret.

移除診斷文字中的已知憑證及常見秘密欄位。這是額外防護，無法辨認所有任意秘密。呼叫端應提供本次所有憑證並避免記錄敏感內容；參數亦可為單一秘密字串。"""
    text = str(value)
    values = (secrets,) if isinstance(secrets, str) else secrets
    known = {item for item in values if isinstance(item, str) and item}
    for secret in sorted(known, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = _TOKEN_PATTERN.sub("[REDACTED_TOKEN]", text)
    return _FIELD_PATTERN.sub(
        lambda match: match.group("key") + match.group("separator") + "[REDACTED]",
        text,
    )


def _units(character: str) -> int:
    return 2 if ord(character) > 0xFFFF else 1


def _redact_known(value: Any, secrets: Iterable[str]) -> Any:
    """成功回應保留結構，但不讓遠端反映當次憑證。

Preserve success response structure without reflecting request credentials."""
    if isinstance(value, dict):
        return {_redact_known(key, secrets): _redact_known(item, secrets)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_known(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def split_plaintext(text: str, limit: int = 4096) -> list[str]:
    """Split plain text without dropping characters, using a UTF-16 budget.

    Boundaries stay near newlines/spaces, but avoid putting whitespace at an
    internal edge when possible: Telegram trims it on delivery. This does not
    parse HTML or Markdown and does not split a Python Unicode code point.
    The caller owns formatting: escape each plain chunk separately for HTML.

以 UTF-16 單位預算拆分純文字，不丟失字元。優先在換行或空白附近分界，並避免 Telegram 裁掉段落邊緣空白。不解析 HTML／Markdown，也不拆開 Python Unicode 字元；HTML 格式與逐段跳脫由呼叫端處理。"""
    if not isinstance(text, str):
        raise TypeError(tr('delivery_text_type_invalid'))
    if not text:
        raise ValueError(tr('delivery_text_empty'))
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 2:
        raise ValueError(tr('delivery_limit_invalid'))
    # 短訊息直接核對 UTF-16 長度，避免每次逐字走 Python 迴圈。 / Check short-message UTF-16 length directly, avoiding a per-character Python loop.
    if len(text.encode("utf-16-le")) // 2 <= limit:
        return [text]
    pieces: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        used = 0
        end = start
        while end < length:
            cost = _units(text[end])
            if used + cost > limit:
                break
            used += cost
            end += 1
        if end < length:
            boundary = max(text.rfind("\n", start, end), text.rfind(" ", start, end)) + 1
            if boundary > start + (end - start) // 2:
                preferred = boundary
            else:
                preferred = end
            # 將分界空白留在片段內，避免 Telegram 裁掉原文換行或空格。 / Keep boundary whitespace inside chunks to avoid Telegram trimming original whitespace.
            # 找不到這類切點時依長度上限切分；服務端空白正規化仍有限制。 / Fall back to the length limit; server whitespace normalization still has limits.
            safe = next((index for index in range(preferred, end + 1)
                         if not text[index - 1].isspace() and not text[index].isspace()), None)
            if safe is None:
                safe = next((index for index in range(preferred - 1, start, -1)
                             if not text[index - 1].isspace() and not text[index].isspace()), None)
            end = safe if safe is not None else end
        pieces.append(text[start:end])
        start = end
    return pieces


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def api_error_code(http_code: Any, api_code: Any) -> int | None:
    """HTTP 拒絕優先，避免 JSON 錯誤碼覆蓋傳輸層拒絕。 / Prefer HTTP rejections over JSON codes."""
    http_status = _integer(http_code)
    return http_status if http_status is not None and http_status >= 400 else _integer(api_code)


def _wait_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _failure(
    *, description: object, secrets: Iterable[str], code: int | None,
    attempt: int, kind: str, status: str = "failed", retry_after: float | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    delivery: dict[str, Any] = {"status": status, "attempts": attempt, "error_kind": kind}
    result: dict[str, Any] = {
        "ok": False,
        "description": redact(description, secrets),
        "delivery": delivery,
    }
    if code is not None:
        result["error_code"] = code
    safe_parameters = {}
    migration = _integer((parameters or {}).get("migrate_to_chat_id"))
    if migration is not None:
        safe_parameters["migrate_to_chat_id"] = migration
    if retry_after is not None:
        delivery["retry_after"] = retry_after
        safe_parameters["retry_after"] = retry_after
    if safe_parameters:
        result["parameters"] = safe_parameters
    return result


def _kind(code: int | None, parameters: dict[str, Any]) -> str:
    if code == 429:
        return "rate_limited"
    if code == 401:
        return "unauthorized"
    if code == 403:
        return "forbidden"
    if code == 409:
        return "conflict"
    if code == 400 and _integer(parameters.get("migrate_to_chat_id")) is not None:
        return "chat_migrated"
    if code is not None and 400 <= code < 500:
        return "bad_request"
    if code is not None and 500 <= code < 600:
        return "server_error"
    return "api_error"


def request_with_retry(
    send: Callable[[], requests.Response], *, secrets: Iterable[str] = (),
    max_attempts: int = 3, retry_wait: float = 5,
    sleep: Callable[[float], None] | None = None,
    wait_budget: float = MAX_INLINE_WAIT_SECONDS,
) -> dict[str, Any]:
    """Execute one Bot API operation with bounded, classified retry behavior.

    ``send`` must create a fresh request and reopen uploads on every call. The
    response is parsed before handling HTTP status so ``retry_after`` survives.
    429 and definite 5xx rejections may retry. ConnectTimeout is safe to retry;
    ReadTimeout, ConnectionError and unclassified RequestException are unknown
    outcomes and are not resent. A total inline wait budget bounds blocking.

    Successful Telegram fields remain intact, with an additional ``delivery``
    object. Failures expose only safe diagnostic fields; they never expose the
    raw response object, request URL or exception string.

執行有界且依錯誤分類的 Bot API 重試。send 每次須建立新請求並重新開啟上傳檔；先解析回應以保留 retry_after。429 與明確的 5xx 拒絕可重試；ConnectTimeout 可安全重試，ReadTimeout、ConnectionError 及未分類 RequestException 結果不明、不重送。總等待預算限制阻塞時間。成功欄位保留並新增 delivery；失敗只回傳安全診斷，不回傳原始回應、URL 或例外。"""
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise ValueError(tr('delivery_max_attempts_invalid'))
    base_wait = _wait_value(retry_wait)
    if base_wait is None:
        raise ValueError(tr('delivery_retry_wait_invalid'))
    budget = _wait_value(wait_budget)
    if budget is None or budget > MAX_INLINE_WAIT_SECONDS:
        raise ValueError(tr('delivery_wait_budget_invalid'))
    pause = time.sleep if sleep is None else sleep
    # Materialize once: redaction remains effective if a caller gave a generator. / 先實體化一次，確保呼叫端傳入產生器時去敏仍有效。
    secret_values = (secrets,) if isinstance(secrets, str) else tuple(secrets)
    waited = 0.0

    def failure(**fields):
        result = _failure(**fields)
        result["delivery"]["waited_seconds"] = waited
        return result

    for attempt in range(1, max_attempts + 1):
        try:
            response = send()
        except requests.exceptions.ConnectTimeout:
            wait = min(base_wait * (2 ** (attempt - 1)), MAX_INLINE_WAIT_SECONDS)
            if attempt < max_attempts and waited + wait <= budget:
                pause(wait)
                waited += wait
                continue
            return failure(description=tr('delivery_connect_timeout'),
                            secrets=secret_values, code=None, attempt=attempt, kind="connect_timeout")
        except requests.exceptions.RequestException:
            return failure(description=tr('delivery_transport_unknown'),
                            secrets=secret_values, code=None, attempt=attempt,
                            kind="transport_unknown", status="unknown")

        http_code = _integer(getattr(response, "status_code", None))
        try:
            payload = response.json()
        except (ValueError, TypeError):
            payload = None
        valid = isinstance(payload, dict) and isinstance(payload.get("ok"), bool)
        message = payload.get("result") if isinstance(payload, dict) else None
        valid_message = (isinstance(message, dict)
                         and type(message.get("message_id")) is int
                         and message["message_id"] > 0)
        if (valid and payload["ok"] and valid_message
                and http_code is not None and 200 <= http_code < 300):
            result = _redact_known(payload, secret_values)
            if "description" in result:
                result["description"] = redact(result["description"], secret_values)
            result["delivery"] = {"status": "success", "attempts": attempt,
                                  "error_kind": None, "waited_seconds": waited}
            return result

        if valid and payload["ok"]:
            return failure(description=tr('delivery_success_inconsistent'),
                            secrets=secret_values, code=http_code, attempt=attempt,
                            kind="invalid_response", status="unknown")

        parameters = payload.get("parameters") if isinstance(payload, dict) else None
        parameters = parameters if isinstance(parameters, dict) else {}
        api_code = _integer(payload.get("error_code")) if valid and not payload["ok"] else None
        # 矛盾回應與非 JSON 5xx 無法證明未收件，停止自動重送。 / Inconsistent responses and non-JSON 5xx cannot prove rejection; stop automatic resending.
        if ((http_code is not None and http_code >= 400 and api_code is not None
             and api_code != http_code)
                or (not valid and http_code is not None and http_code >= 500)):
            return failure(description=tr('delivery_response_ambiguous'),
                           secrets=secret_values, code=http_code, attempt=attempt,
                           kind="invalid_response", status="unknown")
        code = api_error_code(http_code, api_code)
        if code is None or code < 400:
            return failure(description=tr('delivery_response_invalid'),
                            secrets=secret_values, code=None, attempt=attempt,
                            kind="invalid_response", status="unknown")

        description = payload.get("description") if isinstance(payload, dict) else None
        if not isinstance(description, str) or not description:
            description = tr('delivery_request_rejected', p0=code)
        kind = _kind(code, parameters)
        server_wait = _wait_value(parameters.get("retry_after")) if code == 429 else None
        if code == 429:
            if server_wait is None:
                return failure(description=description, secrets=secret_values, code=code,
                                attempt=attempt, kind=kind, status="retry_later", parameters=parameters)
            if attempt >= max_attempts or waited + server_wait > budget:
                return failure(description=description, secrets=secret_values, code=code,
                                attempt=attempt, kind=kind, status="retry_later",
                                retry_after=server_wait, parameters=parameters)
            pause(server_wait)
            waited += server_wait
            continue
        if 500 <= code < 600 and attempt < max_attempts:
            wait = min(base_wait * (2 ** (attempt - 1)), MAX_INLINE_WAIT_SECONDS)
            if waited + wait <= budget:
                pause(wait)
                waited += wait
                continue
            return failure(description=description, secrets=secret_values, code=code,
                            attempt=attempt, kind=kind, status="retry_later",
                            retry_after=wait, parameters=parameters)
        return failure(description=description, secrets=secret_values, code=code,
                        attempt=attempt, kind=kind, parameters=parameters)

    # The range is nonempty, and each final attempt returns above. / 迴圈範圍非空，最後一次嘗試一定於上方回傳。
    raise AssertionError(tr('delivery_unreachable_state'))
