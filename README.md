# telegram-bot-setup-public — Create and configure Telegram bots

**English** | [正體中文](README.zh-TW.md)

Currently a **0.1.1 public preview**. Refer to main for current features and validation results.

Prepare your Telegram `API_ID` and `API_HASH`, fill in your private settings, and complete the required sign-in verification for your own Telegram account. This verifies your own Telegram account; no approval from the project author is needed. The program can then create a private notification bot, save its credentials, obtain your Chat ID, register a route, and verify the first notification. Telegram Desktop is not required.

The project provides Bot API notifications, Telethon account tools, and bot creation/token rotation through BotFather. Original project code is [MIT licensed](LICENSE); external references and dependencies retain their own licenses. See [third-party notices](THIRD_PARTY_NOTICES.md), [validation and limits](docs/VALIDATION.md), and [security reporting](SECURITY.md). Those supporting documents currently remain in Traditional Chinese.

**Language support:** this README and the [installation guide](INSTALL_GUIDE.md) are available in English and Traditional Chinese. The project's own CLI help, prompts, errors, notification prefixes, and receiving prompts can use either language, with messages in `languages/en.ini` and `languages/zh_TW.ini`. Interactive `./tg-install` offers `1. 正體中文` or `2. English`; English is the first-install default. Use `--language zh-TW` or `--language en` for one command, or set `TG_LANGUAGE`; subsequent tools otherwise use the language saved by a successful installation. Configuration-template comments and source annotations also have bilingual counterparts; some supporting documents remain in Traditional Chinese. Commands, option names, configuration keys, JSON fields, and status codes stay the same. See [CLI languages](docs/LANGUAGES.md) for precedence, persistence, and message-file maintenance.

| What you have | Where to start |
| --- | --- |
| No API credentials for your own Telegram account yet | [Download](INSTALL_GUIDE.md#step-2-download) and [install](INSTALL_GUIDE.md#step-3-install) first, then fill in `.env` later. Account history access and automatic bot creation remain unavailable until credentials are ready and sign-in verification is complete. |
| An existing Bot Token and Chat ID, without API credentials for your own Telegram account | Follow the [existing-bot example](INSTALL_GUIDE.md#existing-bot-only). Set `TG_BOT_TOKEN` and `TG_CHAT_ID` in `telegram-bot-setup-public/.env` to use the `DEFAULT` route. This does not create a bot. |
| You want the program to create a bot | Follow the seven steps below, supply `TG_API_ID` and `TG_API_HASH` in [your private `.env`](INSTALL_GUIDE.md#step-4-config), and complete sign-in verification for your own Telegram account. |

## Use cases: separate bots for separate tasks

Create a dedicated bot for each task, with its own Token and notification route. When a Linux job finishes, that job selects the appropriate route and sends its result through the corresponding bot. One person can view each bot in a separate Telegram conversation, keeping different tasks organized.

| Task | Example bot | Workflow |
| --- | --- | --- |
| Scheduled and background jobs | Job notification bot | A Linux program sends completion or failure results through the corresponding bot. |
| Different projects or business tasks | One bot per task | Each bot has its own Token; multiple bots can notify the same person. |
| PDF printing | Document printing bot | Send a PDF to a dedicated bot, save the incoming file, then hand it to your own backend and printer. |
| Image recognition and archiving | Image OCR bot | Send images to a dedicated bot, run OCR in your own backend, and save the images and extracted text for later use. |

PDF processing and OCR are examples of integrations you can build. This public project supplies bot creation, notifications, image/PDF reception and storage, and generic file events. Connect your own processing tools, OCR engine, database storage, and business workflows. See the [receiving guide, currently in Traditional Chinese](docs/RECEIVING.md).

## Quick start

These seven steps automatically create a private notification bot on Linux. See the [complete My Personal Notice example](INSTALL_GUIDE.md#example-personal-bot) for commands, settings, prompt translations, and recovery instructions.

| Step | Action |
| --- | --- |
| 1. [Obtain API credentials for your own Telegram account](INSTALL_GUIDE.md#step-1-api) | Register a Telegram account first. Open [my.telegram.org/apps](https://my.telegram.org/apps) in a phone or computer browser and use **API development tools** to obtain `API_ID` and `API_HASH` together. The website login code arrives in the Telegram app. No Telegram Desktop is needed. You may download and install before obtaining credentials. |
| 2. [Download](INSTALL_GUIDE.md#step-2-download) | Clone `telegram-bot-setup-public` on Linux. |
| 3. [Install dependencies](INSTALL_GUIDE.md#step-3-install) | Run `./tg-install` in the project directory. In an interactive terminal, choose the display language before installation. Installation does not operate Telegram. |
| 4. [Fill in private settings](INSTALL_GUIDE.md#step-4-config) | Set `TG_API_ID`, `TG_API_HASH`, `TG_PHONE`, your bot display name, a unique username, and route `PERSONAL` in `.env`. Display names may repeat. Protect the file; an existing Chat ID is not needed. |
| 5. [Initialize](INSTALL_GUIDE.md#step-5-setup) | Run `./tg-setup` and enter the required OTP/2FA through hidden terminal prompts. If BotFather explicitly rejects the username, interactive setup offers checked suggestions for your approval, a custom name, or cancellation. It never changes the name without approval. Setup then creates or resumes the bot, starts the conversation, and sends the initial test notification. |
| 6. [Check completion](INSTALL_GUIDE.md#step-6-check) | Confirm `completed`. The program saves the Token as `TG_CUSTOM_PERSONAL_TOKEN` and your Chat ID as `TG_CUSTOM_PERSONAL_CHAT_ID` in `.env`, without displaying the Token. The adjacent route file holds key mappings only. Do not put a Bot Token in `TG_API_HASH`; normal creation does not require `TG_SETUP_BOT_TOKEN`. Follow recovery instructions after interruptions or unknown results. |
| 7. [Send your own notification](INSTALL_GUIDE.md#step-7-notify) | Run `./tg-message 'My first notification' PERSONAL NONE`. This sends another message after the initialization test. |

Official credential instructions: [Obtaining api_id](https://core.telegram.org/api/obtaining_api_id).

## Tools and entry points

| Entry point | Purpose |
| --- | --- |
| `tg-install` / `tg-setup` | Install dependencies; verify sign-in to your own Telegram account, create or resume a bot, register a route, and test notification delivery. |
| `tg_notify.py` / `tg-message` | Python text/image notifications; text notifications from the CLI. |
| `sys_notify.py` | System notifications, plain text by default. |
| `tg` / `tg_cli.py` | Account status, dialogs, history, recent messages, media downloads, and new bot updates. |
| `tg-receive` / `tg_receiver.py` | Save images/PDFs from allowlisted private-chat users, optionally save additional JPEG copies, and emit generic file events. |
| `provision_telegram_bot.py` | Account login, BotFather bot creation, and sending text using a user session. |
| `rotate_telegram_bot_tokens.py` | BotFather Token rotation, identity checks, and backups. |

`tg-send` and `tgsend` are now **text** aliases for `tg-message`; they do not provide the old `send <file>` interface. Download media with `tg download`; upload images using Python `send_photo()`. See [TG_USAGE.md, currently in Traditional Chinese](TG_USAGE.md) for all launchers and options.

## Notification settings

The built-in `DEFAULT` route reads `TG_BOT_TOKEN` and `TG_CHAT_ID` from private `.env`. Python `send_text()` / `send_photo()` and `tg-message` use `DEFAULT` when no route is specified. Missing Token or Chat ID stops delivery. `tg-setup` can create a custom route such as `PERSONAL`, saving credentials as `TG_CUSTOM_PERSONAL_TOKEN` and `TG_CUSTOM_PERSONAL_CHAT_ID`.

`send_text(text, bot_type="DEFAULT", parse_mode="HTML", *, resume=None)` retains positional arguments and successful `ok` / `result` responses. Default HTML mode escapes input as **literal text**, rather than interpreting arbitrary HTML templates. Use `None` for plain text in Python, or `NONE`, `TEXT`, or `PLAIN` in the CLI. Long text is split with a conservative UTF-16 budget, preserving non-BMP characters such as emoji and escaping each literal HTML segment. Short Markdown passes through unchanged; long Markdown or custom formatting that would require splitting is explicitly rejected. `send_photo(photo_path, caption="", bot_type="DEFAULT")` uploads an image and retains the first-1024-character caption rule.

## Delivery results and resuming

Each request permits at most three attempts. Explicit 400/401/403/409 rejections are not retried; 429 follows `retry_after`. All long-message parts share an inline wait budget of up to 30 seconds; exceeding it returns `retry_later`. Explicit 5xx rejections and pre-send connection timeouts use bounded backoff. Read timeouts, ambiguous connection outcomes, contradictory responses, non-JSON 5xx responses, and success responses without a valid positive integer `message_id` become `unknown` and stop automatic resending. API acceptance does not mean the recipient has read the message.

`delivery` records `status`, attempt counts, accepted and total parts, `message_ids`, and `resume`; long messages also include `results`. A resume fingerprint binds the bot type, **SHA-256 of the actual Token**, Chat ID, content, format, and split result. It can skip confirmed parts; a receipt containing `unknown_part` blocks automatic resuming. Receipts are neither authorization credentials nor a persistent outbox. Callers must retain receipts and handle waits and unknown outcomes when resuming across processes.

| Status | Meaning | `tg_notify.py` / `sys_notify.py` exit code |
| --- | --- | ---: |
| `success` | Accepted by the API | 0 |
| `failed` | Explicit failure | 1 |
| Configuration/argument error | Nothing sent | 2 |
| `partial` | Some parts accepted, followed by an explicit failure | 4 |
| `unknown` | Outcome cannot be determined | 5 |
| `retry_later` | Further handling must wait | 6 |

Notifications read only the two setting keys needed for the selected route. The default file is `.env`; explicitly override it with `TG_CONFIG_ENV_PATH`. File values take precedence over same-named process environment variables. The whole `.env` is not exported into the process environment. Successful responses remove known credentials; diagnostics redact known Tokens and common sensitive fields and do not log raw HTTP exceptions, request URLs, or payloads. Protect files and sessions and isolate processes appropriately.

## Accounts, bots, and state

`tg status`, `dialogs`, `history`, `recent`, and `download` use a Telethon user session to read conversations accessible to that account. Subcommands offer options including `--json`, `--peer`, `--limit`, `--per-dialog`, `--dialog-limit`, and `--bots-only`. `bot-updates --bot` uses the selected Bot Token and `getUpdates` to read **new** incoming updates only. It does not advance the local offset unless `--ack` is supplied. Do not compete with another consumer using the same Token. Bot API updates do not provide account history access.

BotFather tools provide `request-login-code`, `complete-login`, `create-bot`, and `send-message`. Creation accepts only new replies with message IDs after the current request; unexpected conversations require manual handling. Rotation uses `getMe` to verify that old and new Tokens identify the same bot. Normal output lists configuration keys, bot names, and updated file counts without displaying Tokens. Other consumers are updated only when explicitly supplied through `--consumer-file`.

Rotation preflights explicit sources, creates a separate private recovery directory for each run, backs up and verifies files, and journals progress before revocation. It saves and verifies a new Token before calling `getMe`, then updates files individually while recording their status. Partial failure stops processing other bots and prints `RECOVERY_DIR`; use protected records and BotFather for manual recovery. Do not assume an old Token still works. External revocation and multiple file updates are not an atomic transaction. See [rotation instructions, in Traditional Chinese](TG_USAGE.md#原有分段工具與輪換-token) and [SECURITY.md, in Traditional Chinese](SECURITY.md).

Account tools default to repository `.env`, with sessions, login state, update offsets, and Token rotation records under `~/.local/state/telegram-bot-setup`. `TG_CONFIG_STATE_DIR` overrides this state root, including `tg-cli-bot-updates.json` and the `token_rotation/` and `receiver/` subdirectories; tools retain their `--env-path`, `--session-path`, `--login-state-path`, and `--state-dir` overrides where supported. Existing users can copy the contents of repository `.state` to the new location, or set `TG_CONFIG_STATE_DIR` to the old directory. Never commit configuration, sessions, offsets, or Token rotation mappings. A signed-in account can read its latest Saved Messages entry with `tg history me --limit 1`.

Legacy account and provisioning tools tighten Session directories owned by the OS user running the command to 0700 and Session files, including SQLite sidecars, to 0600; unsafe paths or permission failures stop the operation. Use a dedicated Session directory. CLI diagnostics redact the current credentials. User-session sends require a message object with a positive integer ID; a missing receipt exits nonzero without `MESSAGE_SENT` or automatic resending. Configuration updates handle all duplicate keys consistently and retain atomic 0600 writes. Receiver download jobs stop on permanent 4xx rejections (except 429) or after 20 transient failures (about 70 minutes of backoff); HTTP rejection codes override conflicting JSON and existing queue databases remain compatible. See [receiving details](docs/RECEIVING.md).

## Receiving images and PDFs

After bot configuration, optionally run `./tg-receive` to receive images/PDFs from allowlisted private-chat users. Files default to project `received/`; override with `--destination`. Generic events let your own programs move, forward, or process saved files. On first interactive startup, choose whether to **also save JPEG copies** of images. Originals are always retained; PDFs are saved without conversion. Basic reception uses root-project dependencies; JPEG conversion requires the optional `images` dependencies. Integrate your own processing through Python event handlers or CLI JSON events. Private business processing is not included. See [the receiving guide, currently in Traditional Chinese](docs/RECEIVING.md) for configuration, allowlists, SQLite state, and the single-consumer restriction.

## Testing and preview scope

The 298 offline tests for 0.1.0 are historical results, not the validation count for 0.1.1. See [validation results, currently in Traditional Chinese](docs/VALIDATION.md) for the current revision, reproduction commands, and limits. Tests block real Telegram traffic. GitHub Actions provides tests and full-history Gitleaks scanning; consult Actions for actual runner results. Internal reports and site-specific settings are not included in public content.

Fixed URLs, licenses, and adoption boundaries for official APIs and five reference projects are in the [reference report](docs/REFERENCE_REPORT.md) and [third-party notices](THIRD_PARTY_NOTICES.md). See [CHANGELOG](CHANGELOG.md) for preview changes and [dependency documentation](docs/DEPENDENCIES.md) for Python, uv, direct/transitive packages, version sources, and updates. These supporting documents currently remain in Traditional Chinese.
