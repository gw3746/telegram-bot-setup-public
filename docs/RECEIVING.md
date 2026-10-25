# 圖片與 PDF 收件

`./tg-receive` 是通用 Bot 收件工具：只接收白名單使用者在**私人聊天**傳來的圖片與 PDF，保存原檔，並產生供後續程式使用的檔案事件。群組訊息不入列，也沒有稅務、列印、特定目的地或個人業務 handler。它與 [Python `send_photo()` 發圖片](../README.zh-TW.md#通知設定)是不同功能。

## 使用前準備

先按[安裝指南](../INSTALL_GUIDE.md)完成根專案安裝，並選定已有憑證的 `DEFAULT`，或透過七步 setup 建立 `PERSONAL`。純 Bot 收件只用 Bot Token，不需要帳號 `API_ID`／`API_HASH` 或 user Session。`--allowed-user` 必須填允許傳檔者的正整數 Telegram `user_id`，可重複指定；傳送者與 Bot 的一對一私人聊天中，該傳送者的 `user_id` 通常與該聊天的 Chat ID 相同，但請以實際訊息核對，不要填 Bot ID。未指定 `--destination` 時，目標固定為專案根目錄內的 `received/`，第一次有效啟動時自動建立，不受目前終端所在目錄影響；需要其他位置時才指定 `--destination`。範例的 `received/` 已由 Git 忽略；自訂目錄可放在倉庫外，或自行加入忽略清單，避免提交收到的私人檔案。

## 收到的檔案放在哪裡

| 使用方式 | 檔案位置與後續處理 |
| --- | --- |
| 不指定位置 | 自動建立專案內 `received/`，先把圖片及 PDF 存在這裡。 |
| 使用 `--destination` | 改變收件時的存檔目錄；絕對路徑可指向你選擇的其他位置。 |
| 用自己的程式串接 | 呼叫 `Receiver` 時以 `destination` 指定收件位置，或接收保存完成事件，再由自己的程式搬移、轉送或處理。 |

收件與後續處理是兩個步驟：事件的 `path` 是已保存原檔的位置。後續目的地與處理邏輯由自己的程式決定；需可靠確認處理成功時，使用下方 Python handler 介面並以 `event_id` 去重。

在專案根目錄，以實際 user ID 取代下方示例數字：

```bash
./tg-receive --bot PERSONAL --allowed-user 123456789
```

首次於互動終端啟動且未指定圖片模式時，會問「圖片要保留原檔並另存 JPG 嗎？[y/N]」。回答否或直接按 Enter，使用 `original`；回答是，使用 `jpeg`。選擇保存至狀態目錄的 `receiver.json`，下次沿用。可用 `--image-mode original` 或 `--image-mode jpeg` 明確指定並保存；`--non-interactive` 不詢問，無既有選擇時使用 `original`。預設狀態目錄是 `~/.local/state/telegram-bot-setup/receiver`；設定 `TG_CONFIG_STATE_DIR` 時使用其下的 `receiver/`，`--state-dir` 可再指定其他目錄；`--env-path` 可指定私有設定檔。舊版使用者可把專案 `.state` 的內容複製到新狀態根目錄，或設定 `TG_CONFIG_STATE_DIR` 指回舊 `.state`。

只需保留原檔與 PDF 時，根專案相依已足夠。選擇 `jpeg` 前，先在專案根目錄安裝可選圖片相依：

```bash
uv sync --frozen --extra images
```

`images` extra 固定 Pillow 12.3.0 與 pillow-heif 1.8.0；版本及鎖檔見[相依套件清單](DEPENDENCIES.md)。`jpeg` 模式仍保留圖片原檔，另外產生 `.converted.jpg`：透明背景轉白底，按 EXIF 方向旋正；動圖或多頁圖僅另存第一幀，原檔維持完整。轉換圖片上限 6,000 萬像素；若 JPG 轉換失敗，原檔仍交付，事件含 `conversion_error`。PDF 只保存，不轉 JPG；接收時須有 `%PDF-` 檔頭。單檔上限 20 MiB，實際下載也受 Telegram Bot API 的限制。以「照片」上傳時 Telegram 可能已壓縮；若要保留原始檔案位元組，請以「檔案」方式傳送。

## 狀態、事件與後續處理

收件 offset 和工作狀態存於狀態目錄的 `receiver.sqlite3`，由 Python 標準庫 `sqlite3` 自動建立；一般不用安裝 SQLite 伺服器、`sqlite3` 命令或 pip 套件。若精簡 Python 缺少 `sqlite3` 支援，程式會在啟動收件前明確提示；請補齊該 Python 的 SQLite 支援。`./tg-receive --help` 仍可查參數。

下載遇 400／401／403／404／409 等永久 4xx 拒絕（429 除外），工作標為 `rejected` 並停止重試。暫時性網路、API 或本機存檔錯誤最多嘗試 20 次（約 70 分鐘退避），含既有資料的 `attempts`；429 遵守伺服器等待時間，其餘採有上限退避，達上限亦標為 `rejected`。HTTP 拒絕狀態優先於矛盾 JSON 錯誤碼。既有 DB 的欄位與狀態值不變，可繼續讀取；被拒絕工作保留供人工核對，不會自動重新排程。

Download jobs stop with the existing `rejected` status on permanent 4xx responses (except 429), or after 20 transient failures (about 70 minutes of backoff), including persisted attempts. HTTP rejection codes take precedence over conflicting JSON. Rate limits retain the server delay; other retries use bounded backoff. Existing databases remain compatible and rejected jobs are retained for manual review.

每個已保存檔案的事件使用 `schema=tg.received_file.v1`，含 `event_id`（Bot ID 與 update ID 組成）、`kind`（`image`／`pdf`）、原檔 `path`、`sha256`、`chat_id`、`message_id`、`user_id` 及可為空的 `jpeg_path`。成功另存 JPG 時可含 `jpeg_sha256` 與圖片資訊；轉換失敗時含 `conversion_error`。加 `--json-events` 後，每個完成檔案輸出一行 JSON，供自己的後續程式讀取；互動詢問寫入標準錯誤，不混入 JSON 事件輸出。Python 也可用 `Receiver.dispatch_events(handler)` 接收事件；handler 成功返回後才標記完成。handler 失敗或程序中斷可能讓同一 `event_id` 再送，後續程式須用 `event_id` 去重。CLI 的完成標記只代表 JSON 已寫入標準輸出，不代表管線下游已完成處理；需要以業務成功作為確認時，使用 Python handler 介面。

```bash
./tg-receive --bot DEFAULT --allowed-user 123456789 --non-interactive --json-events
```

`--once` 只執行一輪收件，仍會實際呼叫 Bot API 並處理 offset；單純查看 CLI 用 `--help`。同一 Bot 只能有一個 `getUpdates` consumer，勿與現用輪詢器或 `tg bot-updates --ack` 競爭。若 Bot 已設 webhook，工具會拒絕啟動，不會自動刪除 webhook；請先選定單一收件方式。任何正式 Bot 的收件及轉換仍需在自己的環境驗收，本輪文件不代表已完成真實 Telegram 收件測試。

## 官方參考

- [Telegram getUpdates](https://core.telegram.org/bots/api#getupdates)、[getFile](https://core.telegram.org/bots/api#getfile)：收件 offset 與下載流程。
- [Python sqlite3](https://docs.python.org/3/library/sqlite3.html)：標準庫介面、免伺服器及精簡 Python 的可選模組說明。
- [Pillow Image](https://pillow.readthedocs.io/en/stable/reference/Image.html)：圖片解碼及 JPEG 輸出。
