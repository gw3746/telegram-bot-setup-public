"""名稱占用後，查核、確認與安全重建的合成流程。"""
import json
from types import SimpleNamespace

import pytest

import tg_settings
import tg_setup
from test_first_run_setup import (API_HASH, PASSWORD, PHONE, TOKEN, USERNAME,
                                  FakeClient, Harness, config)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    config(tmp_path / '.env')
    harness = Harness(tmp_path, authorized=True)
    attempts = []
    def create(client, name, username):
        attempts.append((name, username))
        if len(attempts) == 1:
            raise tg_setup.BotRejected('taken')
        harness.identity['username'] = username
        return TOKEN
    def start(client, username, text):
        assert username == harness.identity['username'] and text == '/start'
        client.calls.append(('start',))
        return SimpleNamespace(id=31)
    monkeypatch.setattr(FakeClient, 'send_message', start)
    harness.username_attempts = attempts
    harness.new_creator = create
    return harness


def run_choice(flow, answers, checker=lambda client, name: True, **extra):
    answer = iter(answers)
    return flow.run(bot_creator=flow.new_creator, username_checker=checker,
                    username_prompt=lambda _: next(answer), **extra)


def test_accepts_checked_suggestion_and_saves_it_before_creation(flow, capsys):
    checked = []
    result = run_choice(flow, ['y'], lambda client, name: checked.append(name) or True)
    assert result['status'] == 'completed'
    chosen = result['bot_username']
    assert chosen != USERNAME and chosen == checked[0]
    assert len(chosen) <= 32 and chosen.lower().endswith('bot')
    assert flow.username_attempts == [('Synthetic personal notices', USERNAME),
                                      ('Synthetic personal notices', chosen)]
    assert tg_settings.load_env(flow.env)['TG_SETUP_BOT_USERNAME'] == chosen
    assert flow.journal()[1]['bot_username'] == chosen
    assert flow.run(bot_creator=flow.new_creator)['status'] == 'completed'
    assert len(flow.username_attempts) == 2 and len(flow.sent) == 1
    output = capsys.readouterr()
    assert '剛才查核可用' in output.err
    assert all(secret not in output.out + output.err for secret in (TOKEN, API_HASH, PASSWORD, PHONE))


def test_declining_suggestion_can_enter_own_checked_username(flow):
    checked = []
    result = run_choice(flow, ['n', 'MyOwnDifferentBot'], lambda c, n: checked.append(n) or True)
    assert result['status'] == 'completed' and result['bot_username'] == 'MyOwnDifferentBot'
    assert checked[-1] == 'MyOwnDifferentBot'


def test_custom_display_name_is_preserved_while_username_changes(flow):
    args = tg_setup.parser().parse_args(flow.argv('--bot-name', 'User chosen display name'))
    result = tg_setup.run_setup(args, **flow.deps(bot_creator=flow.new_creator,
                                username_checker=lambda c, n: True, username_prompt=lambda _: 'y'))
    assert result['status'] == 'completed'
    assert all(name == 'User chosen display name' for name, username in flow.username_attempts)


def test_cancel_does_not_change_environment_or_create_another_bot(flow):
    before = flow.env.read_bytes()
    result = run_choice(flow, ['q'])
    assert result['status'] == 'username_selection_required'
    assert result['stage'] == 'creation_rejected' and flow.env.read_bytes() == before
    assert len(flow.username_attempts) == 1 and flow.lookups == flow.sent == []


def test_noninteractive_offers_checked_suggestion_without_accepting(flow):
    result = flow.run('--non-interactive', bot_creator=flow.new_creator,
                      username_checker=lambda c, n: True,
                      username_prompt=lambda _: pytest.fail('非互動不可詢問'))
    assert result['status'] == 'username_selection_required'
    assert tg_setup._valid_username(result['suggested_username'])
    assert tg_settings.load_env(flow.env)['TG_SETUP_BOT_USERNAME'] == USERNAME
    assert len(flow.username_attempts) == 1


def test_manual_environment_change_after_noninteractive_rejection_can_resume(flow):
    first = flow.run('--non-interactive', bot_creator=flow.new_creator, username_checker=lambda *_: True)
    assert first['status'] == 'username_selection_required'
    tg_settings.write_env_keys(flow.env, {'TG_SETUP_BOT_USERNAME': 'ManuallySelectedBot'})
    second = flow.run(bot_creator=flow.new_creator)
    assert second['status'] == 'completed' and second['bot_username'] == 'ManuallySelectedBot'
    assert 'suggested_username' not in second


def test_bad_manual_input_is_not_sent_to_service_or_echoed(flow, capsys):
    checked = []
    invalid = 'PRIVATE_SECRET_DO_NOT_ECHO'
    result = run_choice(flow, [invalid, 'ValidReplacementBot'], lambda c, n: checked.append(n) or True)
    assert result['status'] == 'completed' and invalid not in checked
    assert invalid not in capsys.readouterr().err


def test_unavailable_manual_name_requires_another_choice(flow):
    checked = []
    def checker(client, name):
        checked.append(name)
        return name != 'AlreadyOccupiedBot'
    result = run_choice(flow, ['AlreadyOccupiedBot', 'DifferentAvailableBot'], checker)
    assert result['status'] == 'completed' and result['bot_username'] == 'DifferentAvailableBot'
    assert 'AlreadyOccupiedBot' in checked


def test_suggestion_search_skips_unavailable_candidates(flow):
    checked = []
    def checker(client, name):
        checked.append(name)
        return len(checked) == 3
    result = run_choice(flow, ['y'], checker)
    assert result['status'] == 'completed' and len(checked) == 3
    assert result['bot_username'] == checked[-1]


def test_no_available_suggestion_is_not_presented_as_available(flow):
    checked = []
    result = flow.run('--non-interactive', bot_creator=flow.new_creator,
                      username_checker=lambda c, n: checked.append(n) or False,
                      username_prompt=lambda _: pytest.fail('不可詢問'))
    assert result['status'] == 'username_selection_required' and len(checked) == 5
    assert 'suggested_username' not in result
    assert len(flow.username_attempts) == 1


def test_cannot_claim_available_if_check_service_is_unavailable(flow):
    before = flow.env.read_bytes()
    def checker(*_):
        raise tg_setup.SetupStop('username_check_unavailable', '查核暫時無法使用')
    result = run_choice(flow, [], checker)
    assert result['status'] == 'username_check_unavailable'
    assert 'suggested_username' not in result and flow.env.read_bytes() == before
    assert len(flow.username_attempts) == 1


def test_bot_limit_is_not_treated_as_username_conflict(flow):
    def creator(*_):
        raise tg_setup.BotRejected('limit')
    result = flow.run(bot_creator=creator, username_checker=lambda *_: pytest.fail('不可查建議'),
                      username_prompt=lambda _: pytest.fail('不可詢問改名'))
    assert result['status'] == 'creation_rejected'


def test_unknown_creation_never_prompts_or_retries(flow):
    attempts = []
    def creator(*_):
        attempts.append(1)
        raise RuntimeError(TOKEN)
    dependencies = dict(bot_creator=creator, username_checker=lambda *_: pytest.fail('不可查建議'),
                        username_prompt=lambda _: pytest.fail('不可詢問改名'))
    assert flow.run(**dependencies)['stage'] == 'creation_pending'
    assert flow.run(**dependencies)['status'] == 'creation_unknown'
    assert attempts == [1]


def test_name_becomes_occupied_after_check_requires_new_consent(flow):
    choices = []
    def creator(client, name, username):
        choices.append(username)
        if len(choices) < 3:
            raise tg_setup.BotRejected('taken')
        flow.identity['username'] = username
        return TOKEN
    replies = iter(['y', 'y'])
    result = flow.run(bot_creator=creator, username_checker=lambda *_: True,
                      username_prompt=lambda _: next(replies))
    assert result['status'] == 'completed' and len(choices) == 3
    assert len(set(choices)) == 3


def test_failed_environment_write_never_retries_creation(flow, monkeypatch):
    monkeypatch.setattr(tg_setup, 'write_env_keys', lambda *a: (_ for _ in ()).throw(tg_settings.SettingsError('寫入失敗')))
    result = run_choice(flow, ['y'])
    assert result['status'] == 'storage_error' and len(flow.username_attempts) == 1
    assert flow.journal()[1]['stage'] == 'creation_rejected'


@pytest.mark.parametrize('outcome,expected', [(True, True), (False, False), ('invalid', None)])
def test_default_checker_uses_telegram_bot_specific_method(monkeypatch, outcome, expected):
    calls = []
    monkeypatch.setattr(tg_setup.time, 'sleep', lambda _: None)
    def client(request):
        calls.append(request)
        return outcome
    if expected is None:
        with pytest.raises(tg_setup.SetupStop):
            tg_setup._default_username_checker(client, 'ExampleNoticeBot')
    else:
        assert tg_setup._default_username_checker(client, 'ExampleNoticeBot') is expected
    assert type(calls[0]).__name__ == 'CheckUsernameRequest'
    assert calls[0].username == 'ExampleNoticeBot'


@pytest.mark.parametrize('reason', ['UsernameOccupiedError', 'UsernameInvalidError'])
def test_default_checker_classifies_explicit_username_rejection(monkeypatch, reason):
    monkeypatch.setattr(tg_setup.time, 'sleep', lambda _: None)
    def client(_):
        raise type(reason, (Exception,), {})()
    assert tg_setup._default_username_checker(client, 'ExampleNoticeBot') is False


@pytest.mark.parametrize('reply,reason', [
    ('Sorry, this username is already taken.', 'taken'),
    ('Sorry, this username is invalid.', 'invalid'),
    ('Sorry, you have too many bots.', 'limit'),
])
def test_botfather_adapter_distinguishes_rejected_username_from_account_limit(monkeypatch, reply, reason):
    import provision_telegram_bot
    answers = iter(['Cancelled.', 'Choose name.', 'Choose username.', reply])
    monkeypatch.setattr(provision_telegram_bot, 'send_and_wait_botfather_reply',
                        lambda *a, **k: SimpleNamespace(raw_text=next(answers)))
    with pytest.raises(tg_setup.BotRejected) as result:
        tg_setup._default_creator(object(), 'Display name', 'ExampleNoticeBot')
    assert result.value.reason == reason
