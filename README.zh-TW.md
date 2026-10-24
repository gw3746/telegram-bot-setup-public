# telegram-bot-setup-public — 自動建立並設定 Telegram Bot

[English](README.md) | **正體中文**

目前為 0.1.1 公開預覽，請以 main 的功能與驗證說明為準。

README 與安裝指南均有英文及正體中文版本。程式自有的 CLI 說明、提示、錯誤、通知前綴與收件提示可切換英文或正體中文，訊息分別放在 `languages/en.ini` 與 `languages/zh_TW.ini`；互動安裝先選 `1. 正體中文` 或 `2. English`，首次預設英文。單次可用 `--language zh-TW`／`--language en` 覆寫，亦可設定 `TG_LANGUAGE`；其他工具預設沿用成功安裝後儲存的語言。設定模板註解與程式說明亦有中英對照，部分進階文件仍為正體中文；命令、參數、設定鍵、JSON 欄位與狀態碼不翻譯。詳細優先序、保存方式與訊息檔維護見[語言說明](docs/LANGUAGES.md)。

準備好 Telegram `API_ID` 與 `API_HASH`，依安裝指南填妥設定並完成必要本人授權，即可自動建立私人通知 Bot、保存憑證、取得 Chat ID、設定路由並完成首次通知驗證。無需 Telegram Desktop。

本專案提供 Bot API 通知、Telethon 帳號工具及 BotFather 建立／輪換。自有程式採 [MIT](LICENSE)，外部設計參考及依賴保留各自授權，見 [第三方來源](THIRD_PARTY_NOTICES.md)。支援與驗證範圍見 [測試說明](docs/VALIDATION.md)；安全回報見 [SECURITY.md](SECURITY.md)。

| 目前有什麼 | 可以先做什麼 |
| --- | --- |
| 尚未申請本人 API | 可先[下載專案](INSTALL_GUIDE.zh-TW.md#step-2-download)、[安裝相依](INSTALL_GUIDE.zh-TW.md#step-3-install)，之後再到 `.env` 填 API 資料；此時不能用 user session 讀歷史或由程式自動建 Bot。 |
| 已有 Bot Token 與 Chat ID，沒有本人 API | 可依[既有 Bot 通知 Example](INSTALL_GUIDE.zh-TW.md#existing-bot-only)，在 `telegram-bot-setup-public/.env` 填 `TG_BOT_TOKEN` 與 `TG_CHAT_ID`，直接用 Bot API 的 `DEFAULT` 通知；這條路徑不會自動建 Bot。 |
| 要由程式自動建 Bot | 走下方七步，在 [`telegram-bot-setup-public/.env`](INSTALL_GUIDE.zh-TW.md#step-4-config) 填本人 `TG_API_ID`／`TG_API_HASH`，並完成必要本人授權。 |

## 使用情境：依任務分開建立 Bot

可以依不同任務建立各自的 Bot，為每個 Bot 設定獨立 Token 與通知路由。Linux 端的工作完成後，由執行該工作的程式選擇對應路由，將結果送到負責該任務的 Bot。同一位使用者可在 Telegram 分別查看各個 Bot 的對話，避免不同工作的訊息混在同一個 Bot。

| 任務 | Bot 分工範例 | 使用方式 |
| --- | --- | --- |
| 排程與背景工作 | 任務通知 Bot | 工作完成或失敗時，由 Linux 程式透過對應 Bot 傳送結果。 |
| 不同業務或專案 | 每項任務各自的 Bot | 按用途分開通知，各 Bot 使用自己的 Token；可通知同一位使用者。 |
| PDF 列印 | 文件列印 Bot | 使用者將 PDF 傳給專用 Bot，收件程式保存檔案，再交由自己的後端與印表機執行列印。 |
| 圖片辨識與留存 | 圖片 OCR Bot | 使用者將圖片傳給專用 Bot，收件後交由自己的後端執行 OCR，保存圖片與辨識結果，供查詢或後續流程使用。 |

PDF 處理與圖片 OCR 是可自行串接的一般應用情境。公開專案提供 Bot 建立、通知、圖片／PDF 收件保存與通用檔案事件；處理工具、OCR 引擎、辨識結果入庫及後續業務流程，需由使用者自己的後端接上。串接方式見[收件指南](docs/RECEIVING.md)。

## 快速開始

以下七步是在 Linux **由程式自動建立**一個私人通知 Bot；完整填寫與畫面範例見 [My Personal Notice 完整 Example](INSTALL_GUIDE.zh-TW.md#example-personal-bot)。每一步的操作細節都在 [完整安裝指南](INSTALL_GUIDE.zh-TW.md)。

| 步驟 | 要做什麼 |
| --- | --- |
| 1. [申請本人 API](INSTALL_GUIDE.zh-TW.md#step-1-api) | 先有已註冊的 Telegram 帳號；用**手機或電腦瀏覽器**進入 [my.telegram.org/apps](https://my.telegram.org/apps) 的 **API development tools**。同一次申請取得 `API_ID` 與 `API_HASH`，無須 Telegram Desktop；網頁登入碼會傳到 Telegram App。可先做第 2、3 步，再回來申請與填寫。 |
| 2. [下載專案](INSTALL_GUIDE.zh-TW.md#step-2-download) | 在 Linux 取得本專案 `telegram-bot-setup-public`。 |
| 3. [安裝相依](INSTALL_GUIDE.zh-TW.md#step-3-install) | 在專案目錄執行 `./tg-install`；互動終端會先選介面語言，安裝本身不操作 Telegram。 |
| 4. [填入私有設定](INSTALL_GUIDE.zh-TW.md#step-4-config) | 在 `telegram-bot-setup-public/.env` 填 `TG_API_ID`、`TG_API_HASH`、`TG_PHONE`、自訂 Bot 顯示名 `My Personal Notice`、唯一 username（範例：`my_personal_notice_bot`）及路由 `PERSONAL`；顯示名可重複，此檔須受保護，不需既有 Chat ID。 |
| 5. [完成初始化](INSTALL_GUIDE.zh-TW.md#step-5-setup) | 執行 `./tg-setup`；依提示完成必要的本人 OTP／2FA 隱藏輸入。若 BotFather 明確拒絕 username 已占用或不可用，互動模式會提供已查核的建議，讓你確認採用、自行改名或取消；不會擅自換名。之後建立或恢復 Bot、啟動對話及發首次測試通知。 |
| 6. [確認完成](INSTALL_GUIDE.zh-TW.md#step-6-check) | 依指引確認狀態為 `completed`；新 Bot Token 由程式寫入 `telegram-bot-setup-public/.env` 的 `TG_CUSTOM_PERSONAL_TOKEN`，本人 Chat ID 寫入 `TG_CUSTOM_PERSONAL_CHAT_ID`，畫面不顯示 Token；相鄰的路由對照檔只存鍵名對應。不要將 Token 回填成 `TG_API_HASH`，正常建 Bot 也不用填 `TG_SETUP_BOT_TOKEN`。中斷或結果不明時依安裝指南恢復。 |
| 7. [送出第一則自訂通知](INSTALL_GUIDE.zh-TW.md#step-7-notify) | 初始化已發一則測試通知；現在執行 `./tg-message '我的第一則通知' PERSONAL NONE`，另發一則自訂通知。 |

官方 API 申請流程見 [Telegram 申請說明](https://core.telegram.org/api/obtaining_api_id)。

## 進階功能與入口

| 入口 | 實際用途 |
| --- | --- |
| `tg-install`／`tg-setup` | 安裝相依；明確初始化本人帳號、建立或恢復私人通知 Bot、註冊路由並測試通知。 |
| `tg_notify.py`（Python）／`tg-message`（文字 CLI） | Python 提供文字與圖片通知；CLI 提供文字通知。 |
| `sys_notify.py` | 系統通知，預設純文字。 |
| `tg`、`tg_cli.py` | 帳號狀態、對話、歷史、近期訊息、媒體下載及 Bot 新收件。 |
| `tg-receive`／`tg_receiver.py` | 依私人聊天白名單保存圖片、PDF，選擇是否另存 JPG，並輸出通用檔案事件。 |
| `provision_telegram_bot.py` | 帳號登入、BotFather 建 Bot、用 user session 傳文字。 |
| `rotate_telegram_bot_tokens.py` | BotFather Token 輪換、身份核對與備份。 |

`tg-send`、`tgsend` 現為 `tg-message` 的**文字**別名，沒有舊版 `send <檔案>` 介面；媒體下載使用 `tg download`，上傳圖片使用 Python `send_photo()`。全部 launcher 與操作參數見 [TG_USAGE.md](TG_USAGE.md)。

## 通知設定

通用內建路由為 `DEFAULT`，從私有 `.env` 讀取 `TG_BOT_TOKEN` 與 `TG_CHAT_ID`。Python `send_text()`／`send_photo()` 和 `tg-message` 未指定路由時都使用 `DEFAULT`；缺少 Token 或 Chat ID 時停止。`tg-setup` 另可建立符合命名規則的自訂路由，例如上方的 `PERSONAL`，其 Token 與 Chat ID 由程式寫入 `TG_CUSTOM_PERSONAL_TOKEN`、`TG_CUSTOM_PERSONAL_CHAT_ID`。

`send_text(text, bot_type="DEFAULT", parse_mode="HTML", *, resume=None)` 保留位置參數與成功回應 `ok`／`result`。預設 HTML 把輸入當**字面文字跳脫**，不解讀任意 HTML 模板；純文字可用 `None`，CLI 用 `NONE`、`TEXT` 或 `PLAIN`。長文以保守 UTF-16 預算分段，保留 emoji 等非 BMP 字元，不拆 Unicode 字元；字面 HTML 每段再跳脫。短 Markdown 原樣傳送，需拆段的長 Markdown 或自訂格式明確拒絕。`send_photo(photo_path, caption="", bot_type="DEFAULT")` 上傳圖片，caption 沿用前 1024 字元規則。

## 傳送結果與補送

每次請求最多三次嘗試。明確 400／401／403／409 拒絕不重試；429 遵守 `retry_after`。長文全部片段共用最多 30 秒的行內等待預算，超出回 `retry_later`。明確 5xx 拒絕與送出前連線逾時有界退避；讀取逾時、連線結果不明、矛盾回應、非 JSON 5xx 及無有效正整數 `message_id` 的成功回應標為 `unknown`，停止自動重送。API 接受不等於使用者已讀。

`delivery` 記載 `status`、嘗試次數、已接受片段、總片段、`message_ids` 與 `resume`；長文另有 `results`。`resume` 指紋綁定 Bot 類型、**實際 Token 的 SHA-256**、Chat ID、內容、格式及分段結果，可略過已確認片段；含 `unknown_part` 的回執會停止自動補送。回執既非授權憑證，也非持久 outbox。跨程序補送時，呼叫端須自行保留回執、處理等待與不明結果。

| 狀態 | 意義 | `tg_notify.py`／`sys_notify.py` 結束碼 |
| --- | --- | ---: |
| `success` | API 接受 | 0 |
| `failed` | 明確失敗 | 1 |
| 設定／參數錯誤 | 尚未送出 | 2 |
| `partial` | 部分片段已接受、後續明確失敗 | 4 |
| `unknown` | 結果無法判定 | 5 |
| `retry_later` | 須待後續處理 | 6 |

通知每次只讀當次路由兩個設定鍵；預設 `.env`，可用 `TG_CONFIG_ENV_PATH` 顯式覆寫，檔案鍵優先於同名程序環境變數。不將整份 `.env` 匯出至程序環境。成功回應去除已知憑證，錯誤診斷遮蔽已知 Token 與常見敏感欄位，也不記錄原始 HTTP 例外、請求 URL 或 payload。這並不取代檔案權限及程序隔離；部署者仍須保護設定與 Session。

## 帳號、Bot 與狀態

`tg status`、`dialogs`、`history`、`recent`、`download` 用 Telethon user session 讀取該帳號有權存取的對話；提供 `--json`、`--peer`、`--limit`、`--per-dialog`、`--dialog-limit`、`--bots-only` 等各子命令參數。`bot-updates --bot` 使用指定 Bot Token 的 `getUpdates`，只讀該 Bot 的**新**收件；預設不推進本地 offset，`--ack` 才更新。不可與現用同 Token consumer 競爭，亦不能將 Bot API 視為帳號歷史讀取工具。

BotFather 工具提供 `request-login-code`、`complete-login`、`create-bot`、`send-message`；建 Bot 只接受本次請求後 message ID 更新的新回覆，對話異常仍需人工處理。輪換工具用 `getMe` 核對新舊 Token 的 Bot 身份；一般輸出只列設定鍵、Bot 名稱與更新檔數，不顯示 Token。其他 consumer 只在明確提供 `--consumer-file` 時處理。

輪換先預檢明確來源，為每次執行建立獨立私有目錄，備份並讀回核對，再於撤銷前記錄 journal。取得新 Token 後先安全保存並讀回，完成 `getMe` 身份核對才逐檔更新；每檔狀態留在 journal。若部分失敗，工具停止處理其他 Bot 並輸出 `RECOVERY_DIR`，須參照受保護紀錄及 BotFather 人工恢復，不能假設舊 Token 仍有效。外部撤銷與多檔更新不構成原子交易；詳見 [輪換操作](TG_USAGE.md#原有分段工具與輪換-token) 及 [安全回報與憑證保護](SECURITY.md)。

主帳號工具預設設定為本倉庫 `.env`，Session、登入狀態、Bot 更新 offset 與 Token 輪換紀錄在 `~/.local/state/telegram-bot-setup`。`TG_CONFIG_STATE_DIR` 可覆寫此狀態根目錄，包含 `tg-cli-bot-updates.json` 與 `token_rotation/`、`receiver/` 子目錄；各工具仍可依介面使用 `--env-path`、`--session-path`、`--login-state-path`、`--state-dir` 覆寫。舊版使用者可把本倉庫 `.state` 的內容複製到新位置，或設定 `TG_CONFIG_STATE_DIR` 指回舊目錄。設定、Session、offset 及 Token 輪換對照均不可提交。已登入帳號可用 `tg history me --limit 1` 讀 Saved Messages 最後一筆。

舊帳號及 provision 入口將本人 Session 目錄收緊至 0700、Session 與 SQLite 附屬檔至 0600，不安全路徑或權限失敗會停止操作；請使用專用目錄。CLI 診斷遮蔽當次憑證。user-session 發送須有含正整數 ID 的訊息物件，缺回執非零退出、不印 `MESSAGE_SENT` 且不自動重送；設定更新一致處理全部同名鍵並維持原子 0600 寫入。收件下載遇永久 4xx 拒絕（429 除外）或累計 20 次暫時失敗（約 70 分鐘退避）即停止，HTTP 拒絕優先於矛盾 JSON，既有 queue DB 可繼續用；詳見[收件指南](docs/RECEIVING.md)。

## 圖片與 PDF 收件

完成 Bot 設定後，可選用 `./tg-receive` 收取白名單使用者在私人聊天傳來的圖片與 PDF，預設自動存入專案內 `received/` 並產生通用事件，可用 `--destination` 改位置。也可由自己的程式指定收件位置，或在存檔後接事件搬移、轉送與處理。首次在互動終端啟動時可選擇是否將圖片**另存 JPG**；原檔始終保留，PDF 僅保存。一般收檔只需根專案相依，JPG 轉換需安裝可選 `images` 相依。後續個人處理可接 Python 事件 handler 或 CLI JSON 事件；本專案不內建私人業務處理。設定、白名單、SQLite 狀態與單一 Bot consumer 限制見[收件指南](docs/RECEIVING.md)。

## 測試與公測範圍

0.1.0 的 298 項離線測試是舊版歷史結果；0.1.1 公測修正版的驗收結果見 [驗證說明](docs/VALIDATION.md)。測試禁止真實 Telegram 流量；GitHub Actions 的測試及完整歷史 Gitleaks 掃描已提供，雲端執行狀態以 Actions 頁面為準。內部執行報告及現場設定不包含在公開內容。

官方 API 與五個外部專案的固定來源 URL、授權及採用界線見 [參考報告](docs/REFERENCE_REPORT.md) 與 [第三方來源](THIRD_PARTY_NOTICES.md)。公測變更見 [CHANGELOG](CHANGELOG.md)。

Python、uv、直接與傳遞相依套件、版本來源及更新方式見 [相依套件清單](docs/DEPENDENCIES.md)。
