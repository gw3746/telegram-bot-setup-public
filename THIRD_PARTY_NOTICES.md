# 第三方來源與授權紀錄

本專案 `telegram-bot-setup-public` 的自有程式碼採 [MIT](LICENSE)；專案網址為 https://github.com/gw3746/telegram-bot-setup-public，發布狀態以 GitHub 頁面為準。它沿用作者自有的通知、帳號、Bot 與圖片處理程式，再作整合與修改；這些功能並非本輪從零重寫。五個下列公開專案用於閱讀及設計參考，沒有複製其原函式，也沒有安裝它們作為新增執行相依。Requests 是既有相依。各專案固定 commit、原始碼及授權檔的完整 URL、檔案層差異和採用界線見 [來源參考報告](docs/REFERENCE_REPORT.md)。

| 公開來源與署名 | 先前來源紀錄中的授權資訊 | 本專案採用界線 |
| --- | --- | --- |
| [Apprise](docs/REFERENCE_REPORT.md#apprise)，Chris Caron 與 contributors | BSD-2-Clause | 通知回執與 overflow 設計參考。 |
| [telegram-send](docs/REFERENCE_REPORT.md#telegram-send)，Rahiel Kasim 與 contributors | `LICENSE.txt` 是 GPLv3 原文；`telegram_send/telegram_send.py` 檔頭標示 GPL-3.0-or-later；`utils.py` 無獨立授權檔頭。 | 長文處理需求參考；未複製 `split_message`。 |
| [python-telegram-bot](docs/REFERENCE_REPORT.md#python-telegram-bot)，contributors | `pyproject.toml` 標示 LGPL-3.0-only；`_aioratelimiter.py` 檔頭為 LGPL-3.0-or-later；`examples/echobot.py` 為 CC0；`LICENSE.dual` 有 GPLv3／LGPLv3 選擇通知。 | 限流及 `RetryAfter` 設計參考；未整合其排程器。 |
| [aiogram](docs/REFERENCE_REPORT.md#aiogram)，contributors；其 LICENSE 署名 Alex Root Junior | MIT | 錯誤分類設計參考；未整合框架功能。 |
| [TelegramBotCreator-SDK](docs/REFERENCE_REPORT.md#telegrambotcreator-sdk)，gitReply | MIT | 只比較 Bot 名稱、username、頭像等介面；SDK 建立程式未採用。 |

授權欄按先前固定來源閱讀紀錄記載，保留各檔宣告差異；未重新核對遠端版本，也不據此主張 GPL／LGPL 與本專案整體相容。若日後實際複製或修改第三方原碼，應依所採用的檔案及版本另行處理其著作權、授權與 notices。
