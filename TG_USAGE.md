# Telegram 進階命令對照

CLI language: installation offers `1. 正體中文` / `2. English`; tools follow the saved choice. Override one command with `--language zh-TW` or `--language en`. / 安裝可選中英，工具沿用已存偏好，亦可單次覆寫；詳見[語言說明](docs/LANGUAGES.md)。

新使用者先依 [README 快速開始](README.zh-TW.md#快速開始) 選擇路徑；由程式自動建 Bot 見 [My Personal Notice 完整 Example](INSTALL_GUIDE.md#example-personal-bot)，沒有 API_ID／API_HASH 但已有 Bot Token 則見 [純 Bot 通知 Example](INSTALL_GUIDE.md#existing-bot-only)。本頁供安裝及配置後查進階命令，以下命令在倉庫根目錄執行。範例只有合成文字與 placeholder；真正送出、登入、建 Bot、輪換 Token 會連線 Telegram。以 `.env.example` 建立私有 `.env`，只填入需要的鍵，勿提交 Token、Chat ID、電話或 Session。完整功能及結果狀態見 [README](README.md)。

```bash
uv sync --frozen --project .
./tg-message --help
./tg --help
```

## 文字通知與圖片

通用內建路由為 `DEFAULT`，從 `TG_BOT_TOKEN`、`TG_CHAT_ID` 取值；setup 也可註冊 `PERSONAL` 等符合命名規則的自訂路由。文字、圖片、Python 通知 API 及 `bot-updates --bot` 均可使用。

`./tg-message`、`./tg-send`、`./tgsend` 等價，皆呼叫 `tg_notify.py` 送**文字**。未指定路由時使用 `DEFAULT`；第三個位置參數 `NONE`、`TEXT`、`PLAIN` 代表純文字，預設 `HTML` 將輸入標籤當字面文字跳脫。`sys_notify.py` 預設純文字。Python `send_text()`／`send_photo()` 也預設 `DEFAULT`，另可使用已註冊的自訂路由；設定鍵見 [README 通知設定](README.zh-TW.md#通知設定)。

下方 `DEFAULT` 命令使用事先填入的 Bot Token 與 Chat ID；`./tg-setup` 只建立指定的新路由（入門範例為 `PERSONAL`），不會自動配置 `DEFAULT`。使用 `PERSONAL` 前須先完成 setup。

```bash
./tg-message '測試訊息'
./tg-send '另一則通知' DEFAULT NONE
./tgsend '我的通知' PERSONAL NONE
uv run --project . python sys_notify.py --help
```

舊版 `tgsend send <檔案> --to-id ...` 已不支援。下載聊天室媒體使用 `./tg download`；上傳圖片由 Python API `tg_notify.send_photo(photo_path, caption, bot_type)` 提供，沒有傳檔 CLI。長文補送須保留 `delivery.resume` 並處理 `unknown`，它不是持久 outbox。

## 帳號查詢與媒體下載

`./tg` 使用本地 Telethon user session，預設讀本倉庫 `.env` 與 `~/.local/state/telegram-bot-setup/botfather_user`。全域 `--env-path`、`--session-path` 放在子命令之前；`TG_CONFIG_STATE_DIR` 可更換預設狀態資料夾。舊版使用者可把本倉庫 `.state` 的內容複製到 `~/.local/state/telegram-bot-setup`，或設定 `TG_CONFIG_STATE_DIR` 指回舊目錄。

帳號及 provision 入口會把本人擁有的 Session 父目錄收緊為 0700，Session 與 SQLite 附屬檔為 0600；不安全路徑或無法保護權限時拒絕操作。請使用專用 Session 目錄。CLI 錯誤經共用去敏，避免 Token、API hash、電話與密碼洩漏。

```bash
./tg status
./tg dialogs --limit 20 --json
./tg dialogs --bots-only --limit 100
./tg history @example_bot --limit 20 --json
./tg recent --limit 20 --dialog-limit 30 --per-dialog 5
./tg recent --peer @example_bot --peer @example_chat --limit 20 --json
./tg download @example_chat 12345 --output-dir ./downloads
./tg --env-path ./private.env --session-path ./private-session status
```

`history` 讀單一 peer；`recent` 未指定 `--peer` 時從聊天室彙整，重複 `--peer` 時只讀指定對話。peer 可為名稱或數字 ID。`dialogs --bots-only` 只列 Bot。`download` 用指定 peer 的**訊息 ID**下載媒體，不用 Bot API `file_id` 當訊息 ID；預設目的地為使用者 `Downloads/telegram`。`status` 與 `download` 固定輸出 JSON；`dialogs`、`history`、`recent` 可加 `--json`。

| 捷徑 | 作用 |
| --- | --- |
| `./tgbots` | `tg dialogs --bots-only --limit 100` |

`./tgbots` 把額外參數傳給 `tg`，例如 `./tgbots --json`。若要讀取其他指定對話，可直接使用上方的 `./tg recent --peer` 或 `./tg history`。

## Bot 新收件

`bot-updates` 以指定路由 Token 呼叫 Bot API `getUpdates`，只讀該 Bot 的**新**訊息，不能讀 user session 的全部聊天室歷史。預設不推進本地 offset；確認已處理後才加 `--ack`，它會更新 `~/.local/state/telegram-bot-setup/tg-cli-bot-updates.json`（可由 `TG_CONFIG_STATE_DIR` 更換根目錄）。同一 Token 若有現用收件 consumer，不要同時使用此命令競爭更新。

```bash
./tg bot-updates --bot PERSONAL --limit 20
./tg bot-updates --bot PERSONAL --limit 20 --ack
```

輸出圖片可能含 `file_id`，與 `tg download` 使用的 user session 訊息 ID 不同。

## 圖片與 PDF 收件

`./tg-receive` 依 `--allowed-user` 白名單收取私人聊天的圖片及 PDF；未指定位置時自動存入專案內 `received/`，可用 `--destination` 覆寫，`--bot` 可選內建 `DEFAULT` 或已建立的 `PERSONAL`。保留原檔；`--image-mode jpeg` 會另外儲存 JPG，須先安裝 `uv sync --frozen --extra images`。首次互動詢問、非互動預設、SQLite 狀態、事件輸出及單一 consumer 限制見[收件指南](docs/RECEIVING.md)。單純查 CLI 可用 `./tg-receive --help`；`--once` 仍會實際輪詢 Bot，不要用現用 Bot 與其他 consumer 競爭 offset。

## 初始化參數對照

完整七步與設定範例見 [README 快速開始](README.zh-TW.md#快速開始)及[My Personal Notice 完整 Example](INSTALL_GUIDE.md#example-personal-bot)。可先填檔後安裝，或先安裝後填檔。`./tg-install` 僅安裝相依；`./tg-setup` 串接必要授權、建立／恢復 Bot、身份核對、取得本人 Chat ID、新路由保存、啟動對話與首次通知。OTP／2FA 隱藏輸入，不放 argv。

| setup 參數 | 用途 |
| --- | --- |
| `--env-path`、`--state-dir` | 私有設定及專用狀態目錄。 |
| `--bot-name`、`--bot-username`、`--route` | 覆寫顯示名稱、唯一 username、路由等非秘密設定。顯示名可重複；username 不可與其他 Bot 重複。 |
| `--non-interactive` | 有效 Session 可直接使用；未授權立即退出。username 明確被拒時不等待輸入，也不自動採用建議，回報 `username_selection_required` 及安全的 `suggested_username`（若查得）。 |
| `--check` | 只讀本機紀錄，不連線、不建 Bot 或通知。 |
| `--confirm-started` | 手機向本次 Bot 傳 `/start` 後確認接續。 |
| `--test-again` | 明確另發測試，接受可能重複；不繞過已知限流期限。 |

未完成非零退出；已完成重跑只核對身份與路由。恢復時保留原設定、Session 與 journal，詳見安裝指引。

互動 setup 只在 BotFather 明確拒絕 username 已占用或不可用時，才查核並提供候選，讓你採用、另填名稱或取消；查核不保留名稱，最後仍以 BotFather 建立成功為準。採用後會寫入私有 `.env`；若原命令用 `--bot-username` 覆寫，重跑須改成已接受的名稱或省略該參數。服務錯誤、限流或建立結果不明仍依[恢復指引](INSTALL_GUIDE.md#recovery)處理，不當成重名自動再建。

## 原有分段工具與輪換 Token

`provision_telegram_bot.py` 保留原有分段管理功能，預設讀本倉庫 `.env`，Session 與登入狀態放在 `~/.local/state/telegram-bot-setup`；`TG_CONFIG_STATE_DIR` 可覆寫此目錄。全域 `--env-path`、`--session-path`、`--login-state-path` 放在子命令之前。首次登入請使用 setup 的隱藏輸入；舊 `complete-login` 介面仍保留，但本指南不提供把驗證碼放入命令列的範例。下列舊 `create-bot` 只建立 Bot／保存 Token，不等於完整初始化，也不會自動註冊新路由。

```bash
uv run --project . python provision_telegram_bot.py --help
uv run --project . python provision_telegram_bot.py create-bot \
  --display-name 'Example Bot' --username example_notice_bot \
  --token-env-key TG_EXAMPLE_TOKEN --chat-id-env-key TG_EXAMPLE_CHAT_ID \
  --chat-id-source-key TG_CHAT_ID
uv run --project . python provision_telegram_bot.py send-message \
  --peer @example_notice_bot --text '/start'
```

建 Bot 只採用本次送出指令後 message ID 更新的 BotFather 新回覆，擷取 Token 寫回指定設定鍵；來源 Chat ID 鍵存在時才複製。對話衝突或異常需人工處理。`send-message` 經 user session 傳送並讀近期回覆，與 Bot 通知路由不同。

設定寫回會一致處理同名鍵（含鍵旁空白），維持原子替換與 0600；重新載入即取得新值。`send-message` 僅在回傳訊息物件含有效正整數 ID 時輸出 `MESSAGE_SENT` 並回零；缺回執屬結果不明，非零退出且不自動重送，近期舊回覆不能充當本次回執。

`rotate_telegram_bot_tokens.py` 用 `getMe` 比對新舊 Bot 身份（`getMe` 回傳的是 Bot User，無須訊息 ID）；一般輸出不顯示 Token。預檢會讀取明確來源，其他 consumer 僅處理明確指定的 `--consumer-file`。`--dry-run` 查身份但不呼叫 BotFather 輪換；正式輪換會使舊 Token 失效。`--only` 可重複指定設定鍵。

正式執行先在 `~/.local/state/telegram-bot-setup/token_rotation`（可由 `TG_CONFIG_STATE_DIR` 更換根目錄）建立唯一私有 run 目錄、按來源完整路徑識別備份並讀回核對，然後在 journal 記錄 `revoking` 才呼叫 BotFather。取得新 Token 後，先以 0600 原子保存至 journal 並讀回，再用 `getMe` 核對身份；其後逐檔記錄 `updating` 及 `completed`／`unchanged`。備份 manifest 含來源與 SHA-256；同一來源只處理一次，同秒執行也有不同 run 目錄。來源或其目錄若為 symlink 會拒絕；來源原權限為 0400 不會被擴大，較寬權限會收緊至最多 0600。安全寫入使用排他建立的隨機 0600 暫存檔，先同步檔案，再替換目標並同步父目錄。狀態／run 目錄為 0700；journal、manifest、對照與備份為 0600。

進入撤銷階段後任一部分失敗會停止後續 Bot；一般失敗會嘗試標記 `needs_manual_recovery`，並以非零結束碼輸出 `RECOVERY_DIR`。若 journal 本身保存或同步失敗，也會停止且不覆寫既有 journal，紀錄可能只到 `revoking`，無法保證寫入恢復標記。請限制存取該目錄，核對 journal、manifest、備份與各來源實際狀態，再透過 BotFather 人工恢復；不要把含 Token 的檔案內容貼到終端紀錄或支援對話。舊 Token 可能已失效，備份不能當成自動回滾；現無自動恢復命令。外部撤銷與多檔更新並非原子交易，也沒有跨 run 鎖或對惡意並行重新命名的完整目錄 fd 保證。`getMe` 的網路、HTTP、JSON、API 失敗使用固定安全分類；CLI 錯誤不印 traceback、請求 URL 或 Token。憑證外洩與回報方式見 [SECURITY.md](SECURITY.md)。

```bash
uv run --project . python rotate_telegram_bot_tokens.py --dry-run
uv run --project . python rotate_telegram_bot_tokens.py --only TG_BOT_TOKEN \
  --consumer-file ./private-consumer.env
```

## Saved Messages

已登入的帳號可用 `./tg history me --limit 1` 讀取 Saved Messages 最後一筆。舊 `tgsend` 初始化或傳檔語法不適用。

官方及外部來源完整 URL 見 [參考報告](docs/REFERENCE_REPORT.md) 與 [第三方來源](THIRD_PARTY_NOTICES.md)；離線驗證及未測範圍見 [驗證說明](docs/VALIDATION.md)。
