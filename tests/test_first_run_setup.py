"""以真 parser、初始化核心及安全保存驗證文件流程；僅替換外部傳輸。"""
import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

import tg_notify
import tg_settings
import tg_setup
from test_first_run_install import installation, run_entry


API_HASH = "a1" * 16
TOKEN = "880001:" + "SYNTHETIC_TOKEN_" * 3
PHONE = "+886912345678"
OTP = "SECRET_OTP_12345"
PASSWORD = "SECRET_2FA_PASSWORD"
USER_ID = 71001
BOT_ID = 880001
USERNAME = "SyntheticPersonalBot"
ROUTE = "NEW_PERSONAL"


def config(path, *, route=ROUTE, extra=""):
    path.write_text("TG_API_ID=123456\nTG_API_HASH=" + API_HASH + "\nTG_PHONE=" + PHONE +
                    "\nTG_SETUP_BOT_NAME=Synthetic personal notices\nTG_SETUP_BOT_USERNAME=" + USERNAME +
                    "\nTG_SETUP_ROUTE=" + route + "\n" + extra)
    path.chmod(0o600)


class SessionPasswordNeededError(Exception):
    pass


class FakeClient:
    def __init__(self, session_path, *, authorized=False, twofa=False, user_id=USER_ID, bot=False):
        self.session = Path(str(session_path) + ".session")
        self.authorized = authorized or self.session.exists()
        self.twofa, self.user_id, self.bot = twofa, user_id, bot
        self.calls = []
        self.start_error = False
        self.signin_error = False
    def connect(self):
        self.calls.append(("connect",))
    def disconnect(self):
        self.calls.append(("disconnect",))
    def is_user_authorized(self):
        return self.authorized
    def send_code_request(self, phone):
        assert phone == PHONE
        self.calls.append(("code",))
        return SimpleNamespace(phone_code_hash="SYNTHETIC_CODE_HASH")
    def sign_in(self, **kwargs):
        self.calls.append(("sign_in", "password" if "password" in kwargs else "code"))
        if self.signin_error:
            raise RuntimeError(OTP + PASSWORD + API_HASH)
        if "password" not in kwargs:
            assert kwargs["code"] == OTP
            if self.twofa:
                raise SessionPasswordNeededError(PASSWORD)
        else:
            assert kwargs["password"] == PASSWORD
        self.authorized = True
        self.session.write_text("synthetic authorized session")
        self.session.chmod(0o600)
    def get_me(self):
        return SimpleNamespace(id=self.user_id, bot=self.bot, phone=PHONE.lstrip("+"))
    def send_message(self, username, text):
        assert username == USERNAME and text == "/start"
        self.calls.append(("start",))
        if self.start_error:
            raise RuntimeError(TOKEN)
        # 只有送出回執，不提供 Bot 回覆。
        return SimpleNamespace(id=31)


class Harness:
    def __init__(self, root, *, authorized=False, twofa=False):
        self.root = root
        self.env = root / ".env"
        self.state = root / "private state"
        self.clients = []
        self.created, self.sent, self.lookups, self.prompts = [], [], [], []
        self.authorized, self.twofa = authorized, twofa
        self.user_id, self.user_is_bot = USER_ID, False
        self.identity = {"id": BOT_ID, "username": USERNAME, "is_bot": True}
        self.creator_error = None
        self.sender_error = None
        self.response = {"ok": True, "result": {"message_id": 42, "chat": {"id": USER_ID}}}
        self.start_error = False
        self.signin_error = False
    def factory(self, session, api_id, api_hash):
        assert type(api_id) is int and api_id == 123456 and api_hash == API_HASH
        assert str(session).startswith(str(self.state))
        client = FakeClient(session, authorized=self.authorized, twofa=self.twofa,
                            user_id=self.user_id, bot=self.user_is_bot)
        client.start_error, client.signin_error = self.start_error, self.signin_error
        self.clients.append(client)
        return client
    def creator(self, client, name, username):
        assert client.is_user_authorized()
        assert name == "Synthetic personal notices" and username == USERNAME
        self.created.append(username)
        if self.creator_error:
            raise self.creator_error
        return TOKEN
    def lookup(self, token):
        assert token == TOKEN
        self.lookups.append(token)
        return self.identity
    def sender(self, token, chat_id, text):
        assert token == TOKEN and type(chat_id) is int and chat_id == USER_ID
        assert "初始化測試" in text
        self.sent.append((chat_id, text))
        if self.sender_error:
            raise self.sender_error
        return self.response
    def prompt(self, label):
        self.prompts.append(label)
        return PASSWORD if "密碼" in label else OTP
    def argv(self, *extra):
        return ["--env-path", str(self.env), "--state-dir", str(self.state), *extra]
    def deps(self, **updates):
        result = dict(client_factory=self.factory, identity_lookup=self.lookup,
                      notification_sender=self.sender, bot_creator=self.creator,
                      secret_prompt=self.prompt, interactive=True,
                      account_lock_dir=self.root / "account locks")
        result.update(updates)
        return result
    def run(self, *extra, **updates):
        return tg_setup.run_setup(tg_setup.parser().parse_args(self.argv(*extra)), **self.deps(**updates))
    def main(self, *extra, **updates):
        return tg_setup.main(self.argv(*extra), **self.deps(**updates))
    def journal(self):
        path = self.state / "setup" / hashlib.sha256(str(self.env).encode()).hexdigest() / "journal.json"
        return path, json.loads(path.read_text())


@pytest.fixture
def harness(tmp_path):
    config(tmp_path / ".env")
    return Harness(tmp_path)


def assert_private_tree(harness):
    for path in harness.state.rglob("*"):
        assert stat.S_IMODE(path.stat().st_mode) & (0o077 if path.is_file() else 0o077) == 0
    assert stat.S_IMODE(harness.env.stat().st_mode) == 0o600
    assert stat.S_IMODE(Path(str(harness.env) + ".routes.json").stat().st_mode) == 0o600


@pytest.mark.parametrize("order", ["config_then_install", "install_then_config"])
def test_documented_sequences_from_empty_to_usable_route(installation, monkeypatch, capsys, order):
    root, uv = installation
    flow = Harness(root)
    assert not (root / ".venv").exists() and not flow.state.exists() and not flow.env.exists()
    builtin_before = dict(tg_notify._BOT_CONFIG)
    assert set(builtin_before) == {"DEFAULT"}
    if order == "config_then_install":
        config(flow.env)
    result = run_entry(root, uv, "tg-install")
    assert result.returncode == 0, result.stderr
    assert "尚未初始化" in result.stdout
    assert not flow.state.exists()
    if order == "install_then_config":
        assert not flow.env.exists()
        config(flow.env)
    assert "CHAT_ID" not in flow.env.read_text()
    assert not Path(str(flow.env) + ".routes.json").exists()
    assert flow.main() == 0
    journal_path, journal = flow.journal()
    assert journal["stage"] == "completed"
    assert journal["user_id"] == USER_ID and journal["bot_id"] == BOT_ID
    assert journal["message_id"] == 42
    assert len(flow.created) == len(flow.sent) == len(flow.prompts) == 1
    assert_private_tree(flow)
    monkeypatch.setattr(tg_notify, "_ENV_PATH", str(flow.env))
    assert tg_notify.get_bot_credentials(ROUTE) == (TOKEN, str(USER_ID))
    outgoing = []
    def post(token, method, payload, timeout, **kwargs):
        outgoing.append((token, method, payload))
        return {"ok": True, "result": {"message_id": 43, "chat": {"id": USER_ID}}}
    monkeypatch.setattr(tg_notify, "_post_json", post)
    response = tg_notify.send_text("新自訂路由直接通知", bot_type=ROUTE, parse_mode=None)
    assert response["ok"] is True and outgoing[0][0] == TOKEN
    assert str(outgoing[0][2]["chat_id"]) == str(USER_ID)
    assert tg_notify._BOT_CONFIG == builtin_before
    assert flow.main() == 0
    assert len(flow.created) == len(flow.sent) == 1
    assert len(flow.prompts) == 1
    output = capsys.readouterr()
    for secret in (TOKEN, API_HASH, PHONE, OTP, PASSWORD):
        assert secret not in output.out + output.err + result.stdout + result.stderr


def test_valid_session_reused_without_otp_or_password(harness):
    harness.authorized = True
    assert harness.main("--non-interactive") == 0
    assert harness.prompts == []
    assert not any(call[0] == "code" for call in harness.clients[0].calls)


@pytest.mark.parametrize("twofa", [False, True])
def test_password_only_when_service_requires_it(harness, twofa):
    harness.twofa = twofa
    assert harness.main() == 0
    assert len(harness.prompts) == (2 if twofa else 1)
    assert sum("密碼" in label for label in harness.prompts) == int(twofa)
    assert OTP not in harness.journal()[0].read_text()
    assert PASSWORD not in harness.journal()[0].read_text()


def test_noninteractive_missing_session_does_not_wait_or_send_code(harness):
    result = harness.run("--non-interactive")
    assert result["status"] == "authorization_required"
    assert harness.prompts == harness.created == harness.sent == []
    assert not any(call[0] == "code" for call in harness.clients[0].calls)


def test_missing_keys_safe_and_no_client(tmp_path, capsys):
    flow = Harness(tmp_path)
    flow.env.write_text("TG_API_HASH=" + API_HASH + "\n")
    flow.env.chmod(0o600)
    assert flow.main("--non-interactive") == 1
    output = capsys.readouterr()
    assert "TG_API_ID" in output.out and "INSTALL_GUIDE.zh-TW.md" in output.out
    assert API_HASH not in output.out + output.err
    assert flow.clients == []


@pytest.mark.parametrize("user_id,is_bot", [(0, False), (USER_ID, True)])
def test_wrong_account_cannot_create(harness, user_id, is_bot):
    harness.user_id, harness.user_is_bot = user_id, is_bot
    assert harness.run()["status"] == "account_mismatch"
    assert harness.created == []


def test_saved_setup_rejects_different_authorized_user(harness):
    assert harness.run()["status"] == "completed"
    harness.user_id = USER_ID + 1
    assert harness.run()["status"] == "account_mismatch"
    assert len(harness.created) == len(harness.sent) == 1


@pytest.mark.parametrize("identity", [
    {"id": BOT_ID, "username": "OtherBot", "is_bot": True},
    {"id": BOT_ID, "username": USERNAME, "is_bot": False},
    {"id": 0, "username": USERNAME, "is_bot": True},
])
def test_wrong_bot_identity_preserves_created_token(harness, identity):
    harness.identity = identity
    assert harness.run()["status"] == "identity_failed"
    assert harness.journal()[1]["token"] == TOKEN
    assert harness.sent == []
    harness.identity = {"id": BOT_ID, "username": USERNAME, "is_bot": True}
    assert harness.run()["status"] == "completed"
    assert len(harness.created) == 1


@pytest.mark.parametrize("kind", ["rejected", "unknown"])
def test_botfather_rejection_or_unknown_never_blindly_recreates(harness, kind):
    harness.creator_error = tg_setup.BotRejected() if kind == "rejected" else RuntimeError(TOKEN)
    result = harness.run()
    assert result["status"] == ("creation_rejected" if kind == "rejected" else "setup_failed")
    assert harness.journal()[1]["stage"] == ("creation_rejected" if kind == "rejected" else "creation_pending")
    if kind == "unknown":
        harness.creator_error = None
        assert harness.run()["status"] == "creation_unknown"
        assert len(harness.created) == 1
        config(harness.env, extra="TG_SETUP_BOT_TOKEN=" + TOKEN + "\n")
        assert harness.run()["status"] == "completed"
        assert len(harness.created) == 1


def test_token_save_failure_retains_unknown_creation_checkpoint(harness, monkeypatch):
    original = tg_setup.write_json
    def fail_token(path, record):
        if record.get("stage") == "bot_created_pending_verification":
            raise tg_settings.SettingsError("固定測試故障")
        return original(path, record)
    monkeypatch.setattr(tg_setup, "write_json", fail_token)
    assert harness.run()["status"] == "storage_error"
    assert harness.journal()[1]["stage"] == "creation_pending"
    monkeypatch.setattr(tg_setup, "write_json", original)
    assert harness.run()["status"] == "creation_unknown"
    assert len(harness.created) == 1
    config(harness.env, extra="TG_SETUP_BOT_TOKEN=" + TOKEN + "\n")
    assert harness.run()["status"] == "completed"
    assert len(harness.created) == 1


def test_route_save_failure_resumes_same_bot(harness, monkeypatch):
    original = tg_setup.register_route
    def fail(*args, **kwargs):
        raise tg_settings.SettingsError("固定測試故障")
    monkeypatch.setattr(tg_setup, "register_route", fail)
    assert harness.run()["status"] == "storage_error"
    assert harness.journal()[1]["stage"] == "verified"
    monkeypatch.setattr(tg_setup, "register_route", original)
    assert harness.run()["status"] == "completed"
    assert len(harness.created) == 1


def test_start_unknown_requires_manual_confirmation(harness):
    harness.start_error = True
    assert harness.run()["stage"] == "start_pending"
    harness.start_error = False
    assert harness.run()["status"] == "start_unknown"
    assert harness.sent == []
    assert harness.run("--confirm-started")["status"] == "completed"
    assert len(harness.created) == 1
    assert sum(call[0] == "start" for client in harness.clients for call in client.calls) == 1


@pytest.mark.parametrize("outcome", ["unknown", "exception", "malformed-success", "wrong-chat"])
def test_uncertain_notice_requires_explicit_test_again(harness, outcome):
    if outcome == "exception":
        harness.sender_error = RuntimeError(TOKEN + PASSWORD)
    elif outcome == "unknown":
        harness.response = {"ok": False, "delivery": {"status": "unknown"}}
    elif outcome == "malformed-success":
        harness.response = {"ok": True, "result": {"message_id": 0, "chat": {"id": USER_ID}}}
    else:
        harness.response = {"ok": True, "result": {"message_id": 42, "chat": {"id": BOT_ID}}}
    assert harness.run()["stage"] in {"notification_pending", "notification_unknown"}
    assert harness.run()["status"] == "notification_unknown"
    assert len(harness.sent) == len(harness.created) == 1
    harness.sender_error = None
    harness.response = {"ok": True, "result": {"message_id": 44, "chat": {"id": USER_ID}}}
    assert harness.run("--test-again")["status"] == "completed"
    assert len(harness.sent) == 2 and len(harness.created) == 1


def test_known_send_failure_resumes_without_rebuild(harness):
    harness.response = {"ok": False, "error_code": 403}
    assert harness.run()["status"] == "notification_failed"
    harness.response = {"ok": True, "result": {"message_id": 44, "chat": {"id": USER_ID}}}
    assert harness.run()["status"] == "completed"
    assert len(harness.sent) == 2 and len(harness.created) == 1


def test_429_not_before_respected_even_test_again(harness, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(tg_setup.time, "time", lambda: clock[0])
    harness.response = {"ok": False, "error_code": 429, "parameters": {"retry_after": 60}}
    assert harness.run()["status"] == "notification_retry_later"
    assert harness.journal()[1]["not_before"] == 1060
    assert harness.run("--test-again")["status"] == "notification_retry_later"
    assert len(harness.sent) == 1
    clock[0] = 1061
    harness.response = {"ok": True, "result": {"message_id": 44, "chat": {"id": USER_ID}}}
    assert harness.run()["status"] == "completed"
    assert len(harness.sent) == 2 and len(harness.created) == 1


def test_completed_rerun_and_explicit_test_again(harness):
    assert harness.run()["status"] == "completed"
    assert harness.run()["status"] == "completed"
    assert len(harness.sent) == 1
    assert harness.run("--test-again")["status"] == "completed"
    assert len(harness.sent) == 2 and len(harness.created) == 1


def test_route_name_clash_does_not_overwrite_or_create(harness):
    original_token = "990001:" + "OTHER_SYNTHETIC_TOKEN_" * 2
    tg_settings.register_route(harness.env, ROUTE, original_token, 99999, tg_setup.BUILTIN_ROUTES)
    before = harness.env.read_bytes()
    assert harness.run()["status"] == "route_conflict"
    assert harness.env.read_bytes() == before
    assert harness.created == []


def test_all_external_exception_content_is_redacted(harness, capsys):
    harness.signin_error = True
    assert harness.main() == 1
    output = capsys.readouterr()
    for secret in (API_HASH, TOKEN, OTP, PASSWORD, PHONE):
        assert secret not in output.out + output.err
    assert harness.created == []


@pytest.mark.parametrize("failure", ["empty", "cancel", "expired"])
def test_login_failure_never_enters_bot_creation(harness, failure):
    def prompt(label):
        if failure == "cancel":
            raise KeyboardInterrupt()
        return "" if failure == "empty" else OTP
    harness.signin_error = failure == "expired"
    result = harness.run(secret_prompt=prompt)
    assert result["status"] == ("cancelled" if failure == "cancel" else "authorization_failed")
    assert harness.created == harness.sent == []
    assert len([call for call in harness.clients[0].calls if call[0] == "code"]) == 1


def test_twofa_wrong_password_is_safe_and_does_not_persist(harness, monkeypatch, capsys):
    harness.twofa = True
    original = FakeClient.sign_in
    def fail_password(client, **kwargs):
        if "password" in kwargs:
            raise RuntimeError(PASSWORD + API_HASH)
        return original(client, **kwargs)
    monkeypatch.setattr(FakeClient, "sign_in", fail_password)
    assert harness.main() == 1
    assert len(harness.prompts) == 2 and harness.created == []
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err
    for file in harness.state.rglob("*"):
        if file.is_file():
            assert PASSWORD not in file.read_text()


def test_no_interactive_terminal_never_reads_stdin(harness):
    assert harness.run(interactive=False)["status"] == "authorization_required"
    assert harness.prompts == harness.created == []
    assert not any(call[0] == "code" for call in harness.clients[0].calls)


def test_check_is_read_only_and_does_not_claim_online_acceptance(harness):
    assert harness.run()["status"] == "completed"
    clients, sent = len(harness.clients), len(harness.sent)
    before = {path: path.read_bytes() for path in harness.root.rglob("*") if path.is_file()}
    result = harness.run("--check")
    assert result["status"] == "recorded_complete"
    assert "未執行線上" in result["hint"]
    assert (len(harness.clients), len(harness.sent)) == (clients, sent)
    assert before == {path: path.read_bytes() for path in harness.root.rglob("*") if path.is_file()}
