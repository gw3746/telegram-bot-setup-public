"""Offline behavioral tests for tg_delivery; no real Telegram requests."""
from __future__ import annotations

import json
import math
import unittest
from unittest.mock import Mock

import requests

from tg_delivery import MAX_INLINE_WAIT_SECONDS, redact, request_with_retry, split_plaintext


def response(status: int = 200, payload=None, raw: bytes | None = None):
    result = requests.Response()
    result.status_code = status
    result._content = raw if raw is not None else json.dumps(payload if payload is not None else {"ok": True, "result": {"message_id": 7}}).encode()
    result.url = "https://api.telegram.org/bot123456789:" + "X" * 35 + "/sendMessage"
    return result


def rejected(code, wait=None, description="synthetic rejection"):
    payload = {"ok": False, "error_code": code, "description": description}
    if wait is not None:
        payload["parameters"] = {"retry_after": wait}
    return response(code, payload)


class RedactionTests(unittest.TestCase):
    def test_token_in_api_url_and_standalone(self):
        token = "123456789:" + "x" * 34 + "-"
        for value in [token, "https://api.telegram.org/bot" + token + "/sendMessage"]:
            self.assertNotIn(token, redact(value))

    def test_token_ending_underscore(self):
        token = "123456789:" + "x" * 34 + "_"
        self.assertNotIn(token, redact(token))

    def test_known_unstructured_secret(self):
        self.assertEqual(redact("before FAKE_HASH after", ["FAKE_HASH"]), "before [REDACTED] after")

    def test_longer_known_secret_first(self):
        self.assertEqual(redact("longsecret", ["long", "longsecret"]), "[REDACTED]")

    def test_one_secret_string(self):
        self.assertEqual(redact("fake secret", "fake secret"), "[REDACTED]")

    def test_structured_credentials_in_assignment_json_and_repr(self):
        for key in ["TG_API_HASH", "TG_PHONE", "TG_2STEP_PASSWORD", "session_path"]:
            for text in [f"{key}=FAKE_VALUE", f'{{"{key}": "FAKE_VALUE"}}', f"{{'{key}': 'FAKE_VALUE'}}"]:
                self.assertNotIn("FAKE_VALUE", redact(text))

    def test_quoted_password_with_spaces(self):
        self.assertNotIn("fake password", redact("TG_2STEP_PASSWORD='fake password'"))

    def test_empty_secret_does_not_change_text(self):
        self.assertEqual(redact("HTTP 403", [""]), "HTTP 403")


class SplittingTests(unittest.TestCase):
    def test_chinese_emoji_whitespace_roundtrip(self):
        text = "報告 😀\n\n內容 & <>  " * 1000
        pieces = split_plaintext(text)
        self.assertEqual("".join(pieces), text)
        self.assertTrue(all(len(piece.encode("utf-16-le")) // 2 <= 4096 for piece in pieces))

    def test_emoji_conservative_budget(self):
        self.assertEqual([len(x) for x in split_plaintext("😀" * 4096)], [2048, 2048])

    def test_exact_limit_and_short_text(self):
        self.assertEqual(split_plaintext("x" * 4096), ["x" * 4096])
        self.assertEqual(split_plaintext("短訊息"), ["短訊息"])

    def test_boundary_prefers_newline(self):
        pieces = split_plaintext("123456\nabcdefgh", 10)
        self.assertIn("\n", pieces[0])
        self.assertEqual("".join(piece.strip() for piece in pieces), "123456\nabcdefgh")

    def test_no_whitespace_is_lost(self):
        text = "a  b\n\n" * 100
        self.assertEqual("".join(split_plaintext(text, 12)), text)

    def test_invalid_inputs_rejected(self):
        for limit in [0, 1, -1, 2.5, True]:
            with self.assertRaises(ValueError):
                split_plaintext("text", limit)
        with self.assertRaises(ValueError):
            split_plaintext("")
        with self.assertRaises(TypeError):
            split_plaintext(None)


class RequestPolicyTests(unittest.TestCase):
    def test_success_preserves_telegram_result(self):
        result = request_with_retry(Mock(return_value=response()), sleep=self.fail)
        self.assertEqual(result["result"], {"message_id": 7})
        self.assertEqual(result["delivery"]["status"], "success")
        self.assertEqual(result["delivery"]["attempts"], 1)

    def test_429_reads_json_and_waits_server_seconds(self):
        send = Mock(side_effect=[rejected(429, 27), response()])
        waits = []
        result = request_with_retry(send, sleep=waits.append)
        self.assertTrue(result["ok"])
        self.assertEqual(waits, [27])
        self.assertEqual(send.call_count, 2)

    def test_long_server_wait_is_not_shortened(self):
        send, waits = Mock(return_value=rejected(429, 120)), []
        result = request_with_retry(send, sleep=waits.append)
        self.assertEqual(result["delivery"]["status"], "retry_later")
        self.assertEqual(result["parameters"]["retry_after"], 120)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(waits, [])

    def test_total_wait_budget(self):
        send, waits = Mock(return_value=rejected(429, 20)), []
        result = request_with_retry(send, sleep=waits.append)
        self.assertEqual(waits, [20])
        self.assertLessEqual(sum(waits), MAX_INLINE_WAIT_SECONDS)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(result["delivery"]["status"], "retry_later")

    def test_zero_wait_still_has_attempt_limit(self):
        send, waits = Mock(return_value=rejected(429, 0)), []
        result = request_with_retry(send, max_attempts=3, sleep=waits.append)
        self.assertEqual(send.call_count, 3)
        self.assertEqual(waits, [0, 0])
        self.assertFalse(result["ok"])

    def test_invalid_or_missing_retry_after_does_not_guess(self):
        for wait in [None, "2", -1, math.inf, True, 10 ** 400]:
            send = Mock(return_value=rejected(429, wait))
            result = request_with_retry(send, sleep=self.fail)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(result["delivery"]["status"], "retry_later")

    def test_permanent_errors_are_not_retried(self):
        for code, kind in [(400, "bad_request"), (401, "unauthorized"), (403, "forbidden"), (409, "conflict")]:
            send = Mock(return_value=rejected(code))
            result = request_with_retry(send, sleep=self.fail)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(result["delivery"]["error_kind"], kind)
            self.assertEqual(result["delivery"]["status"], "failed")

    def test_migration_parameter_preserved(self):
        payload = {"ok": False, "error_code": 400, "parameters": {"migrate_to_chat_id": -10012345}}
        result = request_with_retry(Mock(return_value=response(400, payload)), sleep=self.fail)
        self.assertEqual(result["delivery"]["error_kind"], "chat_migrated")
        self.assertEqual(result["parameters"]["migrate_to_chat_id"], -10012345)

    def test_explicit_server_error_retries_with_backoff(self):
        send, waits = Mock(side_effect=[rejected(503), rejected(503), response()]), []
        result = request_with_retry(send, retry_wait=2, sleep=waits.append)
        self.assertTrue(result["ok"])
        self.assertEqual(waits, [2, 4])
        self.assertEqual(result["delivery"]["attempts"], 3)

    def test_connect_timeout_can_retry_without_raw_exception(self):
        error = requests.exceptions.ConnectTimeout("SENSITIVE_FAKE_VALUE")
        send, waits = Mock(side_effect=[error, response()]), []
        result = request_with_retry(send, sleep=waits.append)
        self.assertTrue(result["ok"])
        self.assertEqual(waits, [5])

    def test_ambiguous_transport_outcomes_not_retried(self):
        for kind in [requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError, requests.exceptions.Timeout]:
            send = Mock(side_effect=kind("SENSITIVE_FAKE_VALUE"))
            result = request_with_retry(send, sleep=self.fail)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(result["delivery"]["status"], "unknown")
            self.assertNotIn("SENSITIVE_FAKE_VALUE", str(result))

    def test_http_error_exception_not_leaked(self):
        error = requests.exceptions.HTTPError("https://api.telegram.org/bot123456789:" + "X" * 35)
        result = request_with_retry(Mock(side_effect=error), sleep=self.fail)
        self.assertEqual(result["delivery"]["status"], "unknown")
        self.assertNotIn("123456789", str(result))

    def test_non_json_success_is_unknown_not_resent(self):
        send = Mock(return_value=response(200, raw=b"not JSON"))
        result = request_with_retry(send, sleep=self.fail)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result["delivery"]["error_kind"], "invalid_response")
        self.assertEqual(result["delivery"]["status"], "unknown")

    def test_non_json_permanent_http_error_is_safe(self):
        result = request_with_retry(Mock(return_value=response(403, raw=b"SENSITIVE_FAKE_VALUE")), sleep=self.fail)
        self.assertEqual(result["error_code"], 403)
        self.assertEqual(result["delivery"]["status"], "failed")
        self.assertNotIn("SENSITIVE_FAKE_VALUE", str(result))

    def test_json_array_and_missing_ok_are_unknown(self):
        for payload in [[], {"result": {"message_id": 1}}, {"ok": "true"}]:
            result = request_with_retry(Mock(return_value=response(200, payload)), sleep=self.fail)
            self.assertEqual(result["delivery"]["status"], "unknown")

    def test_success_without_result_is_unknown(self):
        send = Mock(return_value=response(200, {"ok": True}))
        result = request_with_retry(send, sleep=self.fail)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result["delivery"]["status"], "unknown")

    def test_conflicting_success_and_http_failure_is_not_resent(self):
        send = Mock(return_value=response(503, {"ok": True, "result": {"message_id": 7}}))
        result = request_with_retry(send, sleep=self.fail)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result["delivery"]["status"], "unknown")

    def test_api_error_in_http_200_is_classified(self):
        result = request_with_retry(Mock(return_value=response(200, {"ok": False, "error_code": 403})), sleep=self.fail)
        self.assertEqual(result["delivery"]["error_kind"], "forbidden")

    def test_error_description_and_success_description_redacted(self):
        for ok, code in [(False, 403), (True, 200)]:
            payload = {"ok": ok, "description": "FAKE_SECRET", "result": {"message_id": 1}, "error_code": code}
            result = request_with_retry(Mock(return_value=response(code, payload)), secrets=(x for x in ["FAKE_SECRET"]), sleep=self.fail)
            self.assertNotIn("FAKE_SECRET", result["description"])

    def test_invalid_policy_arguments(self):
        for attempts in [0, -1, True, 2.5]:
            with self.assertRaises(ValueError):
                request_with_retry(Mock(), max_attempts=attempts)
        for wait in [-1, math.nan, math.inf, True, "5"]:
            with self.assertRaises(ValueError):
                request_with_retry(Mock(), retry_wait=wait)


if __name__ == "__main__":
    unittest.main()
