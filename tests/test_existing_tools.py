"""用假對話及暫存設定核對原有 Bot 維運能力。"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import provision_telegram_bot as provision
import rotate_telegram_bot_tokens as rotation


def test_botfather_ignores_old_and_outgoing_messages():
    old = SimpleNamespace(id=10, out=False)
    outgoing = SimpleNamespace(id=12, out=True)
    incoming = SimpleNamespace(id=11, out=False)
    client = Mock()
    client.get_messages.side_effect = [[old], [outgoing, old, incoming]]
    assert provision.send_and_wait_botfather_reply(client, "/newbot") is incoming
    client.send_message.assert_called_once_with("BotFather", "/newbot")


@pytest.mark.parametrize("ending", ["-", "_", "x"])
def test_botfather_keeps_complete_token_suffix(ending):
    token = "123456789:" + "a" * 34 + ending
    assert provision.TOKEN_RE.search("token: " + token + "\n").group() == token


def test_setting_update_preserves_unrelated_keys_and_private_mode(tmp_path):
    path = tmp_path / "private" / "synthetic.env"
    provision.upsert_env_key(path, "TG_BOT_TOKEN", "synthetic-old")
    provision.upsert_env_key(path, "OTHER", "synthetic-other")
    provision.upsert_env_key(path, "TG_BOT_TOKEN", "synthetic-new")
    assert provision.load_simple_env(path) == {"TG_BOT_TOKEN": "synthetic-new", "OTHER": "synthetic-other"}
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_rotation_rejects_new_token_for_different_bot(monkeypatch, tmp_path):
    path = tmp_path / "synthetic.env"
    old, new = "123456789:" + "a" * 35, "123456789:" + "b" * 35
    path.write_text("TG_BOT_TOKEN=" + old + "\n")
    monkeypatch.setattr(rotation, "load_simple_env", lambda _: {"TG_BOT_TOKEN": old})
    monkeypatch.setattr(rotation, "get_me", Mock(side_effect=["original_bot", "wrong_bot"]))
    monkeypatch.setattr(rotation, "revoke", lambda *_: new)
    monkeypatch.setattr(rotation, "require_authorized_client", lambda *_: Mock())
    monkeypatch.setattr(rotation, "STATE_DIR", tmp_path / "rotation")
    monkeypatch.setattr("sys.argv", ["rotation", "--env-path", str(path)])
    replace = Mock()
    monkeypatch.setattr(rotation, "replace_in_files", replace)
    with pytest.raises(RuntimeError, match="不符"):
        rotation.main()
    replace.assert_not_called()
    assert path.read_text() == "TG_BOT_TOKEN=" + old + "\n"


def test_rotation_updates_only_explicit_consumer_and_private_mapping(monkeypatch, tmp_path):
    path, consumer, untouched = (tmp_path / name for name in ["synthetic.env", "consumer.env", "unrelated.env"])
    old, new = "123456789:" + "a" * 35, "123456789:" + "b" * 35
    path.write_text("TG_BOT_TOKEN=" + old + "\n")
    consumer.write_text("TOKEN=" + old + "\n")
    untouched.write_text("TOKEN=" + old + "\n")
    monkeypatch.setattr(rotation, "get_me", lambda *_: "same_bot")
    monkeypatch.setattr(rotation, "revoke", lambda *_: new)
    monkeypatch.setattr(rotation, "require_authorized_client", lambda *_: Mock())
    monkeypatch.setattr(rotation, "STATE_DIR", tmp_path / "rotation")
    monkeypatch.setattr("sys.argv", ["rotation", "--env-path", str(path), "--consumer-file", str(consumer)])
    assert rotation.main() == 0
    assert new in path.read_text() and new in consumer.read_text()
    assert old in untouched.read_text() and new not in untouched.read_text()
    mapping = next((tmp_path / "rotation").glob("*/old_to_new.json"))
    assert mapping.stat().st_mode & 0o777 == 0o600
