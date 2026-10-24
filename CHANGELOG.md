# 更新紀錄

## Unreleased

- Resolve sibling imports from each module's real directory before loading shared modules, supporting direct CLI execution, package imports, and imports through external symlinks without duplicate search-path entries.
- 載入共用模組前，先以各模組的實體目錄解析同目錄匯入，支援直接執行 CLI、套件匯入與外部 symlink 匯入，且不重複加入搜尋路徑。
- Move default Sessions, login state, bot update offsets, Token rotation records, and setup/receiver state to `~/.local/state/telegram-bot-setup`; retain `TG_CONFIG_STATE_DIR` and per-tool overrides.
- Session、登入狀態、Bot 更新 offset、Token 輪換紀錄及 setup／收件狀態預設改放 `~/.local/state/telegram-bot-setup`；保留 `TG_CONFIG_STATE_DIR` 及各工具的個別覆寫。
- Protect legacy account Sessions and SQLite sidecars with 0600 permissions; tighten owned Session directories to 0700 and reject unsafe paths. CLI diagnostics share credential redaction.
- 舊帳號入口強制 Session 與 SQLite 附屬檔 0600、本人 Session 目錄 0700；拒絕不安全路徑，CLI 共用憑證去敏。
- User-session sends require a valid positive integer message ID; missing receipts exit nonzero without automatic resending. Duplicate configuration keys are updated consistently through atomic private writes.
- user-session 發送須有有效正整數訊息 ID；缺回執非零退出且不自動重送。重複設定鍵一致更新，維持原子私有寫入。
- Receiver downloads stop on permanent HTTP/API rejections and after 20 transient failures (about 70 minutes of backoff). HTTP rejection codes take precedence over conflicting JSON; the existing queue schema remains compatible.
- 收件下載遇永久 HTTP／API 拒絕或累計 20 次暫時失敗（約 70 分鐘退避）即停止；HTTP 拒絕優先於矛盾 JSON，既有 queue schema 維持相容。
- Replace private application references and route examples with generic public descriptions and synthetic unregistered-route tests.
- 私人應用及路由名稱改為通用公開描述與合成未註冊路由測試。

## 0.1.1 — 修正版（2026-10-24，公開預覽）

- Separate language packs: `languages/en.ini` and `languages/zh_TW.ini` use 245 stable message IDs; entry order and display-wording changes no longer affect lookup.
- 獨立語言包：中英文各一份 INI，245 個固定語意鍵取代原文字串索引；調整行序及翻譯文字不影響程式對應。
- Bilingual CLI: interactive installation offers `1. 正體中文` and `2. English`, saves the successful installation's choice, and shares paired help, prompts, errors, and notification prefixes across tools. Use `--language zh-TW|en` for an invocation override; see [CLI languages](docs/LANGUAGES.md).
- 中英介面：互動安裝提供 `1. 正體中文`、`2. English`，成功後保存語言偏好；工具共用中英說明、提示、錯誤與通知前綴。亦可用 `--language zh-TW|en` 單次覆寫，程式說明及設定模板註解提供中英對照。
- 公開通知設定改為通用內建 `DEFAULT`（`TG_BOT_TOKEN`／`TG_CHAT_ID`）及 setup 註冊的自訂路由；保留通用文字、圖片、帳號查詢、近期訊息、歷史與媒體下載。
- 公開版僅保留通用通知、帳號工具與收件能力；應用專用流程、路由、捷徑及部署不納入。一般 Bot API 的 `send_photo()` 圖片發送仍可使用。
- 新增通用 `tg-receive` 圖片／PDF 收件：原檔保存、可選另存 JPG、私人聊天白名單及通用檔案事件；個人後續程式可接事件介面，公開版不含私人 handler。JPG 轉換相依置於可選 `images` extra。
- Bot 顯示名稱可自行指定；username 明確遭 BotFather 拒絕為已占用／不可用時，互動 setup 查核候選並請使用者採用、另填或取消。非互動模式回報待選擇狀態，不自動改名或把建立結果不明當作重名。
- 收件未指定目的地時，預設自動建立專案內 `received/`，再由使用者自行串接後續處理。
- 更新入門、命令與驗證文件，使公開能力和實際提供的功能一致。

## 0.1.0 — 公測版（2026-10-24）

- 本人授權後自動建立／恢復私人通知 Bot，保存 Token、Chat ID 與自訂路由。
- 無帳號 API 時可先安裝，已有 Bot Token 可使用純 Bot 通知 Example。
- 文字、長文分段、圖片、帳號查詢與媒體下載、Token 輪換及中斷保護。
- 初版自用應用的範圍於 0.1.1 重新收斂；請以新版功能及限制說明為準。
- 加入離線測試／完整歷史秘密掃描 workflow 與安全回報文件。
- 測試入口使用當前 Python 環境，支援 Python 安裝於 `/usr/local/bin` 的 Linux 容器。

公測仍不提供無人介入的初次帳號授權、跨 Token 輪換自動同步 setup journal 或任意長 Markdown 安全拆分。
