# 從零建立自己的私人通知 Bot

[English](INSTALL_GUIDE.md) | **正體中文**

先選擇符合目前資料的路徑。程式可以在沒有 API_ID／API_HASH 時先完成下載與安裝；已有 Bot Token，也可以直接使用通知功能。由程式代為建立 Bot 的路徑，需要準備帳號 API 資料並完成必要本人授權。

申請 API 資料可用手機瀏覽器完成；下載、安裝及執行本專案則在 Linux 終端進行。無須 Telegram Desktop，也沒有強制設定精靈。

**CLI 語言：**互動執行 `./tg-install` 時先選 `1. 正體中文` 或 `2. English`；首次直接按 Enter 預設英文，之後以已儲存語言為 Enter 預設。命令可用 `--language zh-TW`／`--language en` 單次覆寫，也可設定 `TG_LANGUAGE`。成功安裝才保存所選介面語言，後續工具沿用。程式自有的 help、提示、錯誤、通知前綴與收件提示提供中英對照，訊息分別放在 `languages/en.ini` 與 `languages/zh_TW.ini`；第三方輸出與使用者訊息原文不翻譯。設定模板註解及程式說明已補中英對照，部分進階文件仍為正體中文。參數、設定鍵、JSON 欄位與狀態碼維持原樣。訊息檔維護詳見[語言說明](docs/LANGUAGES.md)。

| 目前情況 | 要走哪條路 |
| --- | --- |
| 還沒有 API 資料，先裝程式 | 先做 [Step 2 下載](#step-2-download)、[Step 3 安裝](#step-3-install)，可先建立 [Step 4 的 `.env`](#step-4-config)；之後取得 API 再回填，不必重新安裝。此時尚未自動建立 Bot。 |
| 要讓程式自動建立 Bot | 依下方七步 Example，API 資料及必要授權備妥後執行 setup。 |
| 已有 Bot Token，或願意自行在 BotFather 建 Bot | 使用 [Example B：純 Bot 通知](#existing-bot-only)，不必申請 API_ID／API_HASH。 |

API_ID／API_HASH 是本人帳號的 API 資料；Bot Token 是特定 Bot 的憑證，兩者不互相代替。

<a id="example-personal-bot"></a>

## 完整 Example A：讓程式建立我的私人通知 Bot

以下從沒有專案環境、設定檔、Session、Token 或 Chat ID 開始，採「先安裝，再填設定」順序。全程使用同一個例子：

| 項目 | 本文示例 |
| --- | --- |
| Bot 顯示名稱 | `My Personal Notice`，可自行指定，可與其他 Bot 重複 |
| Bot username | `my_personal_notice_bot`，須改成未被占用的唯一名稱 |
| 通知路由 | `PERSONAL` |
| 通知目的地 | 你自己的私人聊天，由程式取得 |

下面分清「在瀏覽器操作」「在 Linux 終端執行」「填入設定檔」及「終端輸出示意」。請只執行標明為命令的區塊，設定與輸出示意不要貼到終端執行。

<a id="step-1-api"></a>

### Step 1：到官方網頁，一次取得 API_ID 與 API_HASH

先自行使用官方 Telegram App 註冊帳號，再依 [Telegram 官方申請說明](https://core.telegram.org/api/obtaining_api_id) 操作：

1. 用手機或電腦瀏覽器開啟 [https://my.telegram.org/apps](https://my.telegram.org/apps)。
2. 輸入本人 Telegram 帳號的國際格式電話；到 Telegram App 查收登入碼，再回到瀏覽器登入。這個官方網頁登入碼不是以 SMS 傳送。
3. 進入 **API development tools**，填表建立應用程式。
4. **API_ID 與 API_HASH 會在同一處、同一次申請流程中一起取得，不需要分開申請。**保留這兩項資料，稍後填入自己的 `.env`。

這是官方網頁的申請流程，手機即可完成，無須電腦或 Telegram Desktop。官方網頁登入與稍後本專案的 Session 授權是不同步驟；取得 API 資料後，首次執行仍可能需要登入碼及 2FA。

還沒申請時，可以先完成 Step 2、Step 3 的下載與安裝，再回來申請。自動建 Bot 的 Step 5 仍會檢查 API 資料及授權，不會借用別人的帳號憑證。

<a id="step-2-download"></a>

### Step 2：下載專案，進入專案目錄

在有 Git 的 Linux 終端執行：

```bash
git clone https://github.com/gw3746/telegram-bot-setup-public.git
cd telegram-bot-setup-public
```

這是公測版的獨立 repository URL；上述 `cd` 進入剛下載的專案目錄。GitHub 下載與 Telegram API 申請是不同流程，Telegram 的 API 資料不作為 GitHub 登入憑證。

後續所有終端命令都在這個 `telegram-bot-setup-public` 目錄內執行。已下載此專案的人可直接進入原目錄，保留既有 `.env` 與狀態資料。

<a id="step-3-install"></a>

### Step 3：安裝專案相依

Linux 需先有 `python3` 及 uv。可先在終端確認：

```bash
python3 --version
uv --version
```

找不到 uv 時，依 [uv 官方安裝文件](https://docs.astral.sh/uv/getting-started/installation/) 完成使用者範圍安裝，讓終端可以執行 `uv`，再繼續。

在專案目錄執行安裝命令：

```bash
./tg-install
```

互動終端先顯示 `1. 正體中文`、`2. English`，首次按 Enter 選英文，之後按 Enter 選已保存語言；也可執行 `./tg-install --language zh-TW` 或 `./tg-install --language en` 指定。非互動安裝及 `./tg-install --help` 不顯示選單。安裝使用現有 `uv.lock` 與 Python 3.12，在本專案 `.venv` 建立環境；不需要全域 pip 或 sudo。此時沒有 `.env`、Session 或 Chat ID 也可安裝。

**終端輸出示意，不是命令：**

```text
安裝完成，Bot 尚未初始化；請依 INSTALL_GUIDE.zh-TW.md 填檔後執行 ./tg-setup。
```

這是選正體中文時的輸出示意，表示相依已安裝，接著填設定；選英文會顯示相同意思的英文訊息。只有安裝成功才保存語言偏好。安裝本身不登入 Telegram、不建立 Bot、不發通知。未安裝相依時，`./tg-install --help` 與 `./tg-setup --help` 仍可使用。

<a id="step-4-config"></a>

### Step 4：建立私有設定檔，填入最小資料

**資料填在你下載的專案根目錄 `telegram-bot-setup-public/.env`。**`.env` 是以點開頭的隱藏檔，請用文字編輯器開啟；`.env.example` 是空白模板，不是執行時讀取的設定檔。

新下載且尚無 `.env` 的副本，在終端執行：

```bash
umask 077
cp -n .env.example .env
chmod 600 .env
```

複製使用不覆蓋既有檔案的方式。若已有 `.env`，略過複製，直接用文字編輯器修改原檔；設定應是本人的一般檔案，不使用 symlink。

打開 `.env`，先填完最上方首次初始化區。**下面是設定檔內容示例，不是終端命令；尖括號文字必須換成你自己的資料：**

```dotenv
TG_API_ID=<YOUR_API_ID>
TG_API_HASH=<YOUR_API_HASH>
TG_PHONE=<YOUR_PHONE_WITH_COUNTRY_CODE>
TG_SETUP_BOT_NAME=My Personal Notice
TG_SETUP_BOT_USERNAME=my_personal_notice_bot
TG_SETUP_ROUTE=PERSONAL
```

| 欄位 | 你要填什麼 |
| --- | --- |
| `TG_API_ID` | Step 1 取得的數字 API_ID，填寫時移除尖括號。 |
| `TG_API_HASH` | Step 1 同時取得的 32 位十六進位 API_HASH。 |
| `TG_PHONE` | 本人 Telegram 電話，含國碼；只有有效 Session 已存在時可不填。 |
| `TG_SETUP_BOT_NAME` | 自訂顯示名稱，1–64 字元、不含換行，可與其他 Bot 重複。示例為 `My Personal Notice`。也可用 `--bot-name` 覆寫。 |
| `TG_SETUP_BOT_USERNAME` | 唯一公開 username：5–32 字元、英文字母開頭，限英文／數字／底線，以 `bot` 結尾；也可用 `--bot-username` 覆寫。 |
| `TG_SETUP_ROUTE` | 本例使用 `PERSONAL`；這是程式內選用新 Bot 的路由名稱。 |

占位文字不是可用憑證，尚未替換時程式會提示缺項或格式不符。`my_personal_notice_bot` 也只是統一示例，請自行換成可建立的 username，後面以程式實際顯示的名稱為準。

若尚未取得 API 資料，先保留 `TG_API_ID`、`TG_API_HASH` 為空白；取得後再填回**這同一份 `.env`**，才進行 Step 5。只有安裝完成或設定檔已建立，不會顯示 Bot 初始化完成。

`TG_2STEP_PASSWORD` 建議留空，需要時由終端隱藏輸入；`TG_SETUP_BOT_TOKEN` 正常建立時留空，只供人工核對既有 Bot 後恢復。通用內建 `DEFAULT` 的 `TG_BOT_TOKEN`／`TG_CHAT_ID` 可留空；建立 `PERSONAL` 時不需自己填 Token 或取得 Chat ID。

設定檔是 UTF-8 的 `KEY=value` 資料，不支援 shell 變數展開；不要 `source` 或 `eval`。API hash、Token、電話、登入碼及 2FA 密碼都不要放進命令列或 shell history。

<a id="step-5-setup"></a>

### Step 5：執行初始化，完成必要本人授權

填好並保存 `.env` 後，在終端執行：

```bash
./tg-setup
```

這個命令會實際連線 Telegram。Session 尚未授權時，程式傳送登入碼並在終端隱藏提示輸入；服務要求 2FA 才再提示密碼。請依 Telegram 當次登入流程取得驗證碼，不要把舊碼寫進 `.env`。

**可能出現的終端提示示意，不是命令，也不用照抄：**

```text
Telegram 登入碼（隱藏輸入）：
Telegram 兩步驗證密碼（隱藏輸入）：
```

有效 Session 會直接重用，沒有啟用或沒有被要求 2FA 時不會出現密碼提示。固定設定已填好就不重問，OTP 不持久保存。

授權具備後，程式會建立 Bot、先私有保存 Token、用 getMe 核對身份、取得你的私人 Chat ID、保存 `PERSONAL` 路由、以 user session 傳 `/start`，再由 Bot API 發一次初始化測試通知。Bot 沒有回覆 `/start` 的程式也可完成，因為這裡核對的是送出與通知回執。

若 [BotFather](https://core.telegram.org/bots/features#botfather) **明確拒絕 username 已占用或不可用**，互動 setup 才會查核最多五個候選，讓你選擇採用已查核建議、另填自己想要的 username，或輸入 `q` 取消。回答不採用建議後也可另填名稱；手填名稱會先做本機格式驗證，再向 Telegram 查核。只有你同意且查核成功後，程式才將新 `TG_SETUP_BOT_USERNAME` 寫回 `.env` 與 journal，然後重試建立。查核依 [Telegram `bots.checkUsername`](https://core.telegram.org/method/bots.checkUsername)；查核不保留 username，最後仍以 BotFather 建立成功為準。若候選在建立前被搶先使用，互動模式會再次詢問；不會未經確認自行換名。

**下方是選正體中文時、合成 username 的互動示意，不含 Token；選英文時會顯示同義英文，實際提示與候選依當次回覆為準：**

```text
BotFather 明確拒絕 my_personal_notice_bot：username 已占用。
查核後建議：my_personal_notice_a1b2c3_bot（此時未保留名稱）
採用建議請輸入 y；可另輸入自己的 username，或輸入 q 取消：
```

選定並成功建立後，CLI 會顯示最後採用的 username。若原命令用了 `--bot-username` 覆寫，之後重跑須改用接受後的名稱或省略該覆寫，以免舊參數再次覆蓋 `.env`。`--non-interactive` 不會等待輸入，也不會自動採用；username 明確被拒時回報 `username_selection_required`，可附安全的 `suggested_username`（有查核成功候選時），請修改 `.env` 或 `--bot-username` 後重跑。查核服務錯誤或限流不代表候選可用；其他拒絕（例如 Bot 數量上限）也不是重名。建立結果不明或連線中斷仍維持 `creation_pending` 人工恢復，不會因猜測重名而重新建立。

<a id="step-6-check"></a>

### Step 6：確認初始化完成

**成功輸出示意；下面的名稱與數字是假資料，不是命令：**

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

以你實際輸出的 Bot username 與數字為準。`status=completed` 代表身份、路由、啟動對話及首次通知目的地／正整數訊息 ID 都已核對；Token 保存成功單獨不代表全部完成。

回到 Telegram，打開程式實際建立的 Bot 對話，確認看到初始化測試通知。API 接受表示已取得傳送回執，不代表使用者已讀。

**程式幫你建立的 Bot Token 已自動保存，不需自己複製回填：**

| 存放位置（預設專案根目錄） | 欄位／內容 | 誰填寫 |
| --- | --- | --- |
| `telegram-bot-setup-public/.env` | `TG_API_ID`、`TG_API_HASH` | 你填入官方網頁取得的帳號 API 資料。 |
| `telegram-bot-setup-public/.env` | `TG_CUSTOM_PERSONAL_TOKEN` | 程式自動寫入新 Bot Token；這就是 `PERSONAL` Bot 的 Token key。 |
| `telegram-bot-setup-public/.env` | `TG_CUSTOM_PERSONAL_CHAT_ID` | 程式自動寫入你的私人通知目的地。 |
| `telegram-bot-setup-public/.env.routes.json` | `PERSONAL` 與上述兩個鍵名的對應 | 程式自動建立，這份檔案不存 Token 值。 |

若路由改成其他名稱，欄位跟著使用 `TG_CUSTOM_<路由名>_TOKEN`／`TG_CUSTOM_<路由名>_CHAT_ID`。若用 `--env-path` 指定其他設定檔，則寫在那一份檔案及相鄰的 `.routes.json`。

終端只顯示安全的狀態及身份，不列 Token。需要交給自己的其他程式使用時，從私有 `.env` 的對應欄位取用，勿提交或貼到對話中。`TG_SETUP_BOT_TOKEN` 是人工恢復欄位，不是正常新建 Bot 的日常保存欄位，也不要把 Bot Token 填成 `TG_API_HASH`。

<a id="step-7-notify"></a>

### Step 7：發送我的第一則自訂通知

在終端執行：

```bash
./tg-message '我的第一則通知' PERSONAL NONE
```

回到同一個 Bot 對話，確認「我的第一則通知」已出現。`PERSONAL` 就是 Step 4 的路由，`NONE` 表示純文字。

**正常完成本例會收到兩則通知：初始化自動發一則，這個命令另發一則。**再次執行這個通知命令會再送；請依需要操作。

日後只想查本機保存狀態，可執行：

```bash
./tg-setup --check
```

本機紀錄完整時會顯示 `status=recorded_complete`；它不連線，不能當成即時線上驗收。已完成後普通重跑 `./tg-setup` 會連線核對身份及路由，不重建 Bot、不重寫路由、不重送通知。明確加 `--test-again` 才會另發測試。

完成通知初始化後，若還想用同一 Bot 收取圖片與 PDF，可另依[收件指南](docs/RECEIVING.md)設定 `./tg-receive`；這不是上述七步的必做項。收件須指定正整數的私人聊天傳送者 `user_id` 白名單（本人私人聊天通常與 Chat ID 相同），並確保該 Bot 只有一個 `getUpdates` consumer。使用已設定的 `DEFAULT` 或已建的 `PERSONAL` Token 即可，不需為純 Bot 收件再申請帳號 API 資料。

## 另一種順序：先填設定，再安裝

同一份設定與初始化核心也支援先填檔。選擇順序即可，不需另一套精靈：

| 順序 | 操作 |
| --- | --- |
| 本文主 Example：先安裝 | [Step 1 申請](#step-1-api) → [Step 2 下載](#step-2-download) → [Step 3 安裝](#step-3-install) → [Step 4 填檔](#step-4-config) → [Step 5 初始化](#step-5-setup) → [Step 6 確認](#step-6-check) → [Step 7 通知](#step-7-notify) |
| 先填設定 | Step 1 → Step 2 → **Step 4 填檔** → **Step 3 安裝** → Step 5 → Step 6 → Step 7 |

安裝使用 `uv sync --frozen`；`./tg-install --offline` 只用本機快取，缺快取仍會失敗。工具、Python 或下載未就緒時會非零退出，處理原因後重跑安裝。

<a id="existing-bot-only"></a>

## Example B：已有 Bot Token，沒有帳號 API 資料也能通知

這條路徑使用 Bot API。**只需 Bot Token 與目的地 Chat ID，不需要 API_ID／API_HASH，也不需要 user Session。**若還沒有 Token，可自行在 Telegram 聯絡官方 [BotFather](https://t.me/BotFather)，用 `/newbot` 按提示建立；取得 Token 的官方說明見 [Bot Token 申請](https://core.telegram.org/bots/tutorial#obtain-your-bot-token)。這是使用者手動建立，不是本專案自動建 Bot。

1. 完成 Step 2、Step 3 的下載與安裝。
2. 按 Step 4 建立私有 `telegram-bot-setup-public/.env`，將 BotFather 給你的 Token 填入下面的 `TG_BOT_TOKEN`。其餘 API 欄位可留空；以下尖括號仍是待替換占位文字，不是命令或可用憑證。

```dotenv
TG_BOT_TOKEN=<YOUR_BOT_TOKEN>
TG_CHAT_ID=<YOUR_PRIVATE_CHAT_ID>
```

3. 用 Telegram 打開你自己的 Bot，按「開始」或傳 `/start`。
4. 若不知道自己的私人 Chat ID，先讓 `TG_CHAT_ID` 留空，在專案終端執行以下命令。這個查收件命令只需要 Token，不需要 API_ID／API_HASH 或先填 Chat ID。

```bash
./tg bot-updates --bot DEFAULT --limit 20
```

5. 在輸出中找到自己剛傳送的私人訊息，取它的 `chat_id`，填回**同一份 `.env` 的 `TG_CHAT_ID`**。使用實際輸出的數字，不要把 Bot ID 或訊息 ID 當成 Chat ID。若你已知道私人 Chat ID，可直接填寫並略過查收件。
6. 在專案終端發第一則通知：

```bash
./tg-message '我的第一則通知' DEFAULT NONE
```

這裡 `DEFAULT` 是通用內建路由，目的地就是你填入的私人 Chat ID。只查收沒有其他收件 consumer／webhook 使用的 Bot；已有 consumer 時請用已知 Chat ID，避免競爭 `getUpdates`。

此模式不執行 `./tg-setup`，不會產生自動初始化的 `completed` 紀錄；以通知回執及 Telegram 收到訊息確認可用。Bot Token 是你手動填的 `TG_BOT_TOKEN`；Example A 自動建立的 Token 則由程式填在 `TG_CUSTOM_PERSONAL_TOKEN`。需要 user session 的帳號歷史／媒體讀取，以及程式自動建 Bot，仍需帳號 API 資料。

<a id="recovery"></a>

## 遇到問題：依原進度恢復

恢復使用原設定路徑、狀態目錄、Bot 與路由，保留 journal。不要因結果不明就刪狀態並重新建 Bot。

| 問題／狀態 | 下一步 |
| --- | --- |
| 缺鍵、格式或權限錯誤 | 回 Step 4 修正列出的鍵；秘密檔案須 0600 或更窄，設定及祖先不使用 symlink。 |
| username 明確已用／不可用、`username_selection_required` | 互動 setup 可選查核後的建議、自行輸入合法名稱或取消；非互動模式改 `.env` 或 `--bot-username` 後重跑。若查核失敗或限流，先處理錯誤，不把候選當成已可用。 |
| 其他 `creation_rejected` | 核對 BotFather 的實際拒絕原因；Bot 數量上限等情況不當成重名。 |
| 登入碼錯誤、過期、取消或 2FA 失敗 | 核對本人帳號，在可隱藏輸入的終端重跑；授權前不會建 Bot。 |
| `creation_pending`／建立結果不明 | 到 BotFather 核對，把已建立的該 Bot Token 填入私有檔案 `TG_SETUP_BOT_TOKEN`，維持相符 username 再接續，不盲目再 `/newbot`。 |
| Token 已存，驗證或路由寫入失敗 | 同路徑重跑，從原 Bot 接續；身份衝突先人工核對，不 revoke、不再建 Bot。 |
| `start_pending`／`start_unknown` | 手機向本次 Bot 手動傳 `/start`，確認後執行 `./tg-setup --confirm-started`。 |
| `notification_pending`／`notification_unknown` | 通知可能已送達，先查看對話；接受可能重複後才明確執行 `./tg-setup --test-again`。 |
| `notification_retry_later` | 等待指定期限後重跑，`--test-again` 不繞過等待；沒有有效期限時保留停止並人工處理，不自行刪改 journal。 |
| `notification_failed` | 修正明確失敗原因後重跑，沿用原 Bot 重新測試。 |
| 完成但路由改動、紀錄損毀或帳號不符 | 先核對原帳號、路由及受保護備份，不把 Token 已存當作完成。 |

`--confirm-started` 不跳過身份、路由或通知核對。setup 帳號鎖涵蓋同一 OS 使用者的不同設定副本；請勿同時手動與其他 provision／輪換工具操作 BotFather。

## 進階設定與資料保存

setup 固定資料只讀指定設定檔。`--env-path` 優先於 `TG_CONFIG_ENV_PATH`，再來是 repository `.env`；`--state-dir` 優先於 `TG_CONFIG_STATE_DIR`，再來是 `~/.local/state/telegram-bot-setup`。舊版使用者可把 repository `.state` 的內容複製到新位置，或設定 `TG_CONFIG_STATE_DIR` 指回舊目錄。`--bot-name`、`--bot-username`、`--route` 可覆寫對應非秘密檔案值。有效 Session 可加 `--non-interactive`，未授權會立即退出、不發登入碼、不等 stdin；username 明確被拒也不進入互動選擇。未完成回非零，成功或本機完整紀錄回零。

使用別的設定檔時：

```bash
./tg-setup --env-path ./private.env --state-dir ./private-state
TG_CONFIG_ENV_PATH=./private.env ./tg-message '我的私人通知' PERSONAL NONE
./tg --env-path ./private.env bot-updates --bot PERSONAL
```

`DEFAULT` 是通用內建路由，讀取 `TG_BOT_TOKEN`／`TG_CHAT_ID`；setup 不自動配置，也不覆蓋。新路由名須大寫字母開頭，限大寫／數字／底線，最多 32 字元；新憑證保存於 `TG_CUSTOM_<路由>_TOKEN`／`TG_CUSTOM_<路由>_CHAT_ID`，私人 Chat ID 與 Bot ID 分開。

`.env` 保存憑證，相鄰 `<設定檔名>.routes.json` 保存路由與鍵名對應。Session 在 `<state-dir>/botfather_user.session`；含 Token 的 journal 在 `<state-dir>/setup/<設定絕對路徑 SHA256>/journal.json`。專用目錄 0700、秘密檔案 0600 或更窄，設定與路由鎖與設定相鄰。跨副本帳號鎖在 `${XDG_STATE_HOME:-~/.local/state}/tg-config-public/setup-account-locks/<user_id>.lock`。勿提交這些檔案；備份或搬移時要考慮原路徑綁定。

舊帳號／provision 入口亦把本人 Session 父目錄收緊為 0700，Session 與 SQLite 附屬檔為 0600；不安全路徑或權限失敗會拒絕操作，請使用專用目錄。CLI 錯誤經共用憑證去敏；user-session 發送須有正整數訊息 ID，缺有效回執即停止且不自動重送。舊設定寫回一致處理重複鍵，維持原子 0600 替換。收件下載遇永久 4xx（429 除外）或 20 次暫時失敗（約 70 分鐘退避）即停止，HTTP 錯誤優先於矛盾 JSON，既有收件 DB 可繼續用；詳見[收件指南](docs/RECEIVING.md)。

更多 Python／CLI、圖片、既有路由與輪換用法見 [進階操作對照](TG_USAGE.md)。`bot-updates` 不可與同 Token 的現用 consumer 競爭更新。

## 驗證與參考

0.1.0 的 298 項離線測試是舊版歷史結果；0.1.1 公測修正版的驗收結果、重跑方式及限制見 [驗證紀錄](docs/VALIDATION.md)。正式服務與重新真實 OTP／2FA 仍需在使用者自己的環境驗收。安全回報與憑證保護見 [SECURITY.md](SECURITY.md)。

完整來源及授權見 [參考報告](docs/REFERENCE_REPORT.md) 與 [第三方來源](THIRD_PARTY_NOTICES.md)。官方行為參考 [getMe](https://core.telegram.org/bots/api#getme)、[sendMessage](https://core.telegram.org/bots/api#sendmessage) 及 [Telethon 登入](https://docs.telethon.dev/en/stable/basic/signing-in.html)。
