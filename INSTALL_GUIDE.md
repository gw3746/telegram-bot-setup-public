# Create your own private notification bot from scratch

**English** | [正體中文](INSTALL_GUIDE.zh-TW.md)

Choose the path matching your available credentials. You may download and install before obtaining `API_ID` / `API_HASH`. An existing Bot Token also lets you send notifications directly. Automatic bot creation requires your personal account API credentials and the necessary personal authorization.

You can obtain API credentials in a phone browser. Download, installation, and execution take place in a Linux terminal. Telegram Desktop and a mandatory configuration wizard are not required.

**CLI language:** interactive `./tg-install` offers `1. 正體中文` and `2. English` before installation. First-time Enter selects English; on a later interactive run, Enter selects the saved language. Use `--language zh-TW` or `--language en` on a command, or set `TG_LANGUAGE`. Successful installation saves the chosen preference for subsequent tools. The project's own help, prompts, errors, notification prefixes, and receiving prompts are bilingual, with messages in `languages/en.ini` and `languages/zh_TW.ini`. The Chinese samples below correspond to the Traditional Chinese selection; English displays the same steps in English. Configuration-template comments and source annotations have English/Traditional Chinese counterparts; some supporting documents remain in Traditional Chinese. Commands, settings keys, JSON fields, and status codes stay unchanged. See [CLI languages](docs/LANGUAGES.md) for message-file maintenance.

| Your situation | Path |
| --- | --- |
| No API credentials yet; install first | Complete [Step 2](#step-2-download) and [Step 3](#step-3-install). You may prepare [`.env` in Step 4](#step-4-config) and fill in credentials later without reinstalling. A bot has not been created at this stage. |
| Let the program create a bot | Follow Example A below, then run setup with your credentials and authorization ready. |
| Existing Bot Token, or willing to create a bot manually in BotFather | Follow [Example B](#existing-bot-only); personal API credentials are unnecessary for this path. |

`API_ID` / `API_HASH` are account API credentials. A Bot Token authorizes one particular bot. They are not interchangeable.

<a id="example-personal-bot"></a>

## Example A: automatically create a private notification bot

Start without a project environment, configuration file, session, Token, or Chat ID. This example installs first and configures second, using these values throughout:

| Item | Example |
| --- | --- |
| Bot display name | `My Personal Notice`; choose your own, and duplicates are allowed |
| Bot username | `my_personal_notice_bot`; replace with an available, unique username |
| Notification route | `PERSONAL` |
| Recipient | Your private chat, obtained by the program |

The steps distinguish browser actions, terminal commands, configuration-file content, and sample output. Run only command blocks; do not execute settings or output examples in your shell.

<a id="step-1-api"></a>

### Step 1: obtain API_ID and API_HASH together on the official website

First register your own account using an official Telegram app. Follow [Telegram's official instructions](https://core.telegram.org/api/obtaining_api_id):

1. Open [https://my.telegram.org/apps](https://my.telegram.org/apps) in a phone or computer browser.
2. Enter your Telegram phone number in international format. Read the login code in the Telegram app and return to the browser to sign in. The website login code is not sent by SMS.
3. Open **API development tools** and complete the application form.
4. **Obtain API_ID and API_HASH together in this one application process.** Save them for your private `.env` file.

This website process can be completed on a phone, without a computer or Telegram Desktop. Website login and this project's session authorization are separate steps. Even after obtaining API credentials, your first run may still require a login code and 2FA password.

You may complete download and installation first and return here later. Automatic bot creation in Step 5 still checks your own credentials and authorization; it does not borrow another person's credentials.

<a id="step-2-download"></a>

### Step 2: download and enter the project directory

Run in a Linux terminal with Git installed:

```bash
git clone https://github.com/gw3746/telegram-bot-setup-public.git
cd telegram-bot-setup-public
```

This is the independent public-preview repository. GitHub downloads and Telegram API registration are separate processes; Telegram credentials are not GitHub login credentials.

Run subsequent commands in this project directory. If you already have a checkout, use its existing directory and retain your private `.env` and state.

<a id="step-3-install"></a>

### Step 3: install dependencies

Linux needs `python3` and uv. Check:

```bash
python3 --version
uv --version
```

If uv is missing, follow its [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/) for a user-scoped installation and make it available in your terminal.

Run in the project directory:

```bash
./tg-install
```

In an interactive terminal, choose `1. 正體中文` or `2. English`. Enter defaults to English on the first install, or to your saved language on later interactive installs. You can select explicitly with `./tg-install --language en` or `./tg-install --language zh-TW`. Non-interactive installation and `./tg-install --help` do not show a selection menu. Installation uses the existing `uv.lock` and Python 3.12 to create the project `.venv`, without global pip or sudo. You do not need `.env`, a session, or a Chat ID yet.

**Sample terminal output with Traditional Chinese selected, not a command:**

```text
安裝完成，Bot 尚未初始化；請依 INSTALL_GUIDE.zh-TW.md 填檔後執行 ./tg-setup。
```

With English selected, the corresponding message is: `Installation complete; the bot has not been initialized. Fill in configuration using INSTALL_GUIDE.md, then run ./tg-setup.` The chosen language is saved only after installation succeeds.

Installation does not log in to Telegram, create bots, or send notifications. `./tg-install --help` and `./tg-setup --help` work even before project dependencies are installed.

<a id="step-4-config"></a>

### Step 4: create a private configuration file

**Put credentials in `telegram-bot-setup-public/.env` at the project root.** This is a hidden file starting with a dot. Open it in your text editor. `.env.example` is a blank template, not the runtime configuration file.

For a new checkout without `.env`, run:

```bash
umask 077
cp -n .env.example .env
chmod 600 .env
```

The copy does not overwrite an existing file. If `.env` already exists, skip copying and edit it directly. It must be a regular file owned by you, not a symlink.

Fill in the first-run section at the top of `.env`. **This is file content, not terminal commands. Replace the angle-bracket placeholders with your own values:**

```dotenv
TG_API_ID=<YOUR_API_ID>
TG_API_HASH=<YOUR_API_HASH>
TG_PHONE=<YOUR_PHONE_WITH_COUNTRY_CODE>
TG_SETUP_BOT_NAME=My Personal Notice
TG_SETUP_BOT_USERNAME=my_personal_notice_bot
TG_SETUP_ROUTE=PERSONAL
```

| Field | Value |
| --- | --- |
| `TG_API_ID` | Numeric API_ID from Step 1; remove angle brackets. |
| `TG_API_HASH` | The 32-character hexadecimal API_HASH obtained with API_ID. |
| `TG_PHONE` | Your Telegram phone number including country code; optional only when a valid session already exists. |
| `TG_SETUP_BOT_NAME` | Your display name: 1–64 characters, no line breaks. Duplicates are allowed. Override with `--bot-name` if needed. |
| `TG_SETUP_BOT_USERNAME` | Unique public username: 5–32 characters, starting with an English letter, containing only English letters, numbers, and underscores, and ending in `bot`. Override with `--bot-username` if needed. |
| `TG_SETUP_ROUTE` | `PERSONAL` in this example; the route used to select this new bot. |

Placeholders are not credentials. Until replaced, they cause missing/invalid-setting errors. `my_personal_notice_bot` is only an example; choose an available username and use the final name shown by the program.

If you have not obtained account credentials, leave `TG_API_ID` and `TG_API_HASH` blank and later fill in **this same `.env`** before Step 5. Installation or file creation alone is not completed bot initialization.

Prefer leaving `TG_2STEP_PASSWORD` empty and entering it through a hidden terminal prompt when needed. Leave `TG_SETUP_BOT_TOKEN` empty for normal creation; it is only for recovery after manually verifying an existing bot. Built-in `DEFAULT` settings `TG_BOT_TOKEN` / `TG_CHAT_ID` may remain empty. You do not need to supply a Token or obtain a Chat ID yourself when creating `PERSONAL`.

The configuration is UTF-8 `KEY=value` data without shell variable expansion. Do not `source` or `eval` it. Keep API hashes, Tokens, phone numbers, login codes, and 2FA passwords out of command arguments and shell history.

<a id="step-5-setup"></a>

### Step 5: initialize and complete personal authorization

Save `.env`, then run:

```bash
./tg-setup
```

This command connects to Telegram. If the session is not authorized, the program requests a login code and prompts for hidden input. It asks for a 2FA password only if Telegram requires one. Obtain the code through the current Telegram login flow; do not put an old code in `.env`.

**Possible prompts, not commands:**

```text
Telegram 登入碼（隱藏輸入）：
Telegram 兩步驗證密碼（隱藏輸入）：
```

| Traditional Chinese prompt | English prompt |
| --- | --- |
| `Telegram 登入碼（隱藏輸入）：` | `Telegram login code (hidden input):` |
| `Telegram 兩步驗證密碼（隱藏輸入）：` | `Telegram two-step verification password (hidden input):` |

Valid sessions are reused. No password prompt appears if 2FA is not enabled or requested. Existing fixed settings are not asked again, and OTPs are not persisted.

Once authorized, setup creates the bot, privately saves its Token, checks its identity using `getMe`, obtains your private Chat ID, saves route `PERSONAL`, sends `/start` using your user session, and sends one initialization notification through the Bot API. The bot does not need its own `/start` reply handler; setup checks outgoing delivery and the notification receipt.

If [BotFather](https://core.telegram.org/bots/features#botfather) **explicitly rejects the username as occupied or unavailable**, interactive setup checks up to five alternatives. You can approve a checked suggestion, enter another username, or cancel with `q`. Declining a suggestion still lets you choose your own name. Custom input is format-checked locally and then checked with Telegram. Only after your approval and a successful check does setup save `TG_SETUP_BOT_USERNAME` to `.env` and its journal and retry creation.

Checks use [Telegram `bots.checkUsername`](https://core.telegram.org/method/bots.checkUsername). Checking does not reserve the name; actual creation by BotFather is decisive. If someone claims a name between checking and creation, interactive setup asks again. It never changes the name without confirmation.

**Illustrative Traditional Chinese interaction with a synthetic username, not a command:**

```text
BotFather 明確拒絕 my_personal_notice_bot：username 已占用。
查核後建議：my_personal_notice_a1b2c3_bot（此時未保留名稱）
採用建議請輸入 y；可另輸入自己的 username，或輸入 q 取消：
```

English describes the same three sample lines as: the requested username was rejected as occupied; `my_personal_notice_a1b2c3_bot` was checked but not reserved; enter `y` to accept it, another username to supply your own, or `q` to cancel. The exact runtime selection prompt is `Use the suggestion? [y/N], or enter another username; q to cancel:`. Actual candidates depend on the current response. This confirmation stays in the Terminal and is not sent to Telegram; the installer language menu itself does not log in or create a bot.

The CLI displays the final username after successful creation. If you originally supplied `--bot-username`, rerun with the accepted name or omit the override, so an old argument does not override updated `.env` settings.

`--non-interactive` neither waits for input nor automatically accepts suggestions. Explicit username rejection returns `username_selection_required` and may include a safe `suggested_username` when a candidate passed checking. Update `.env` or `--bot-username` and rerun. Check-service errors or rate limits do not establish availability. Other rejections, such as a bot-count limit, are not username conflicts. Unknown creation outcomes or connection interruptions remain `creation_pending` for manual recovery; setup does not guess that a name conflict occurred and create another bot.

<a id="step-6-check"></a>

### Step 6: confirm initialization

**Illustrative success output with Traditional Chinese selected and fake names and numbers, not commands:**

```text
初始化完成；私人通知路由已可使用。
status=completed
stage=completed
route=PERSONAL
bot_username=my_personal_notice_bot
bot_id=1234567890
user_id=987654321
message_id=42
```

The first line means initialization is complete and your private notification route is ready. Use the actual username and numbers from your run. `status=completed` means identity, route, conversation startup, and the first notification's destination/positive integer message ID have all been checked. Saving the Token alone does not mean completion.

With English selected, the first line is `Setup complete; the private notification route is ready.` The machine-readable lines retain the same keys and codes.

Open the created bot's conversation in Telegram and confirm that the initialization notification arrived. API acceptance provides a delivery receipt; it does not prove the user read the message.

**The program saves the new Bot Token automatically; you do not need to copy it back:**

| Default location | Field/content | Written by |
| --- | --- | --- |
| `telegram-bot-setup-public/.env` | `TG_API_ID`, `TG_API_HASH` | You, using credentials from the official website. |
| `telegram-bot-setup-public/.env` | `TG_CUSTOM_PERSONAL_TOKEN` | The program; this is the Token key for the `PERSONAL` bot. |
| `telegram-bot-setup-public/.env` | `TG_CUSTOM_PERSONAL_CHAT_ID` | The program; your private notification destination. |
| `telegram-bot-setup-public/.env.routes.json` | `PERSONAL` mapped to the two key names | The program; no Token value is stored here. |

Other route names use `TG_CUSTOM_<ROUTE>_TOKEN` / `TG_CUSTOM_<ROUTE>_CHAT_ID`. With `--env-path`, the program writes that configuration file and its adjacent `.routes.json` instead.

Terminal output contains safe status/identity information, not Tokens. For your own integrations, read the appropriate field from private `.env`; do not commit or paste it into a conversation. `TG_SETUP_BOT_TOKEN` is a recovery field, not normal storage for a newly created bot. A Bot Token does not belong in `TG_API_HASH`.

<a id="step-7-notify"></a>

### Step 7: send your first custom notification

Run:

```bash
./tg-message 'My first notification' PERSONAL NONE
```

Confirm that the message appears in the same bot conversation. `PERSONAL` is the route from Step 4; `NONE` means plain text.

**Completing this example normally produces two notifications:** one from initialization and one from this command. Running the notification command again sends another message.

To inspect saved local state later:

```bash
./tg-setup --check
```

A complete local record returns `status=recorded_complete`. This does not connect to Telegram and is not a live verification. A normal rerun of completed `./tg-setup` connects to verify identity and route without recreating the bot, rewriting the route, or resending notifications. Explicit `--test-again` sends another test.

To optionally receive images/PDFs using the same bot, configure `./tg-receive` using the [receiving guide, in Traditional Chinese](docs/RECEIVING.md). This is not required for the seven steps. Reception requires a positive-integer private-chat sender `user_id` allowlist (usually the same as your Chat ID in your own private chat), and only one `getUpdates` consumer for that bot. Use the configured `DEFAULT` or created `PERSONAL` Token; pure Bot API reception does not need additional account API credentials.

## Alternative order: configure before installation

Both orders use the same settings and initialization implementation; no additional wizard is needed.

| Order | Steps |
| --- | --- |
| Install first, as above | [1: credentials](#step-1-api) → [2: download](#step-2-download) → [3: install](#step-3-install) → [4: configure](#step-4-config) → [5: initialize](#step-5-setup) → [6: confirm](#step-6-check) → [7: notify](#step-7-notify) |
| Configure first | Step 1 → Step 2 → **Step 4** → **Step 3** → Step 5 → Step 6 → Step 7 |

Installation uses `uv sync --frozen`. `./tg-install --offline` uses local uv cache only and fails if required cached packages are missing. Missing tools, Python, or downloads cause nonzero exit; resolve the cause and rerun installation.

<a id="existing-bot-only"></a>

## Example B: notify with an existing Bot Token and no account API credentials

This path uses the Bot API. **Only a Bot Token and destination Chat ID are needed; API_ID, API_HASH, and a user session are unnecessary.** If you need a Token, contact official [BotFather](https://t.me/BotFather) in Telegram and follow `/newbot`. See [official Token instructions](https://core.telegram.org/bots/tutorial#obtain-your-bot-token). This creates a bot manually rather than through this project's automatic setup.

1. Download and install using Steps 2 and 3.
2. Create private `.env` using Step 4 and enter your BotFather Token. Account API fields may remain blank. Replace these placeholders; they are configuration content, not commands or usable credentials.

```dotenv
TG_BOT_TOKEN=<YOUR_BOT_TOKEN>
TG_CHAT_ID=<YOUR_PRIVATE_CHAT_ID>
```

3. Open your bot in Telegram and press **Start** or send `/start`.
4. If you do not know your private Chat ID, leave `TG_CHAT_ID` empty and run the command below. It needs only the Token, not account API credentials or a preconfigured Chat ID.

```bash
./tg bot-updates --bot DEFAULT --limit 20
```

5. Find your newly sent private message in the output. Copy its `chat_id` to `TG_CHAT_ID` in **the same `.env`**. Use the actual number, not the Bot ID or message ID. If you already know your Chat ID, fill it in and skip fetching updates.
6. Send a notification:

```bash
./tg-message 'My first notification' DEFAULT NONE
```

`DEFAULT` is the built-in route; its destination is the private Chat ID you supplied. Fetch updates only when no other consumer/webhook is using this bot. If another consumer exists, use your known Chat ID instead of competing for `getUpdates`.

Do not run `./tg-setup` for this path. It does not create a setup `completed` record; verify the notification receipt and Telegram message. You manually fill `TG_BOT_TOKEN` here, while Example A automatically saves `TG_CUSTOM_PERSONAL_TOKEN`. Account history/media tools using a user session and automatic bot creation still require account API credentials.

<a id="recovery"></a>

## Recovery: continue from recorded progress

Keep the original configuration path, state directory, bot, route, and journal. Do not delete state and create another bot merely because an outcome is unknown.

| Problem/status | Next action |
| --- | --- |
| Missing keys, invalid values, or permissions | Correct listed keys in Step 4. Secret files must be 0600 or stricter; configuration and ancestor paths must not use symlinks. |
| Explicit unavailable/occupied username; `username_selection_required` | Interactive setup lets you approve a checked suggestion, enter a valid name, or cancel. In non-interactive mode update `.env` or `--bot-username` and rerun. Failed/rate-limited checks do not prove availability. |
| Other `creation_rejected` | Inspect the actual BotFather rejection; bot-count limits and other causes are not username conflicts. |
| Incorrect/expired code, cancellation, or failed 2FA | Verify your account and rerun in a terminal supporting hidden input. No bot is created before authorization. |
| `creation_pending` / unknown creation result | Verify the bot in BotFather, place that bot's Token in private `TG_SETUP_BOT_TOKEN`, keep a matching username, and resume. Do not blindly issue another `/newbot`. |
| Token saved, but verification or route writing failed | Rerun using the same paths and bot. Manually resolve identity conflicts; do not revoke or create again. |
| `start_pending` / `start_unknown` | Manually send `/start` to this bot from Telegram, then run `./tg-setup --confirm-started`. |
| `notification_pending` / `notification_unknown` | Check the conversation first; the notification may have arrived. Only explicitly use `./tg-setup --test-again` if you accept possible duplicates. |
| `notification_retry_later` | Wait until the specified time before rerunning. `--test-again` does not bypass the wait. Without a valid deadline, stop and handle manually; do not delete/edit the journal. |
| `notification_failed` | Fix the explicit cause and rerun to test the same bot. |
| Completed, but route changed, records damaged, or account mismatched | Check the original account, route, and protected backups. A saved Token alone is not completion. |

`--confirm-started` does not bypass identity, route, or notification checks. Setup's account lock spans different configuration copies owned by the same OS user. Do not simultaneously operate BotFather manually or through other provisioning/rotation tools.

## Advanced settings and data storage

Setup reads fixed settings only from the selected configuration file. Precedence is `--env-path`, then `TG_CONFIG_ENV_PATH`, then repository `.env`. For state it is `--state-dir`, then `TG_CONFIG_STATE_DIR`, then `~/.local/state/telegram-bot-setup`. Existing users can copy the contents of repository `.state` to the new location, or set `TG_CONFIG_STATE_DIR` to the old directory. `--bot-name`, `--bot-username`, and `--route` override corresponding non-secret settings.

With a valid session, `--non-interactive` avoids interactive input. Without authorization it exits immediately without requesting a code or waiting on stdin. Explicit username rejection also avoids interactive selection. Incomplete setup exits nonzero; successful setup or a complete local record exits zero.

To use another configuration file:

```bash
./tg-setup --env-path ./private.env --state-dir ./private-state
TG_CONFIG_ENV_PATH=./private.env ./tg-message 'My private notification' PERSONAL NONE
./tg --env-path ./private.env bot-updates --bot PERSONAL
```

`DEFAULT` reads `TG_BOT_TOKEN` / `TG_CHAT_ID`; setup does not automatically configure or overwrite it. Custom route names start with an uppercase letter, contain uppercase letters/numbers/underscores only, and are at most 32 characters. Credentials use `TG_CUSTOM_<ROUTE>_TOKEN` / `TG_CUSTOM_<ROUTE>_CHAT_ID`. A private Chat ID is distinct from a Bot ID.

`.env` stores credentials. Adjacent `<config-filename>.routes.json` maps routes to key names. The session is `<state-dir>/botfather_user.session`. The Token-containing journal is `<state-dir>/setup/<SHA256-of-absolute-config-path>/journal.json`. Dedicated directories are 0700; secret files are 0600 or stricter. Configuration and route locks are adjacent to the configuration file. Cross-copy account locks use `${XDG_STATE_HOME:-~/.local/state}/tg-config-public/setup-account-locks/<user_id>.lock`. Never commit these files. Account for absolute-path binding when backing up or moving configured copies.

Legacy account/provisioning commands also tighten owned Session parent directories to 0700 and Session files plus SQLite sidecars to 0600, refusing unsafe paths or permission failures. Choose a dedicated Session directory. Their CLI errors use shared credential redaction; user-session sends require a positive integer message ID and stop without automatic resending when no valid receipt is returned. Legacy configuration writes update duplicate keys consistently with atomic 0600 replacement. Receiver download retries stop on permanent 4xx errors (except 429) or after 20 transient failures (about 70 minutes of backoff); HTTP errors take precedence over contradictory JSON. Existing receiver databases remain compatible. See the [receiving guide](docs/RECEIVING.md).

See [advanced usage, currently in Traditional Chinese](TG_USAGE.md) for Python/CLI, image, route, and rotation details. `bot-updates` must not compete with an active consumer using the same Token.

## Validation and references

The 298 offline tests for 0.1.0 are historical results. Current 0.1.1 validation, reproduction commands, and limits are in [the validation document, in Traditional Chinese](docs/VALIDATION.md). Production services and fresh real OTP/2FA authorization still require validation in your own environment. See [SECURITY.md, in Traditional Chinese](SECURITY.md) for reporting and credential protection.

Fixed sources and licenses are in the [reference report](docs/REFERENCE_REPORT.md) and [third-party notices](THIRD_PARTY_NOTICES.md), currently in Traditional Chinese. Official behavior references: [getMe](https://core.telegram.org/bots/api#getme), [sendMessage](https://core.telegram.org/bots/api#sendmessage), and [Telethon sign-in](https://docs.telethon.dev/en/stable/basic/signing-in.html).
