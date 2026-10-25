# 公開來源參考報告

本報告保留先前固定來源閱讀紀錄，列出五個公開專案的指定原始碼及授權檔。下列 commit SHA 與 URL 是該紀錄的定位；本次文件整理沒有重新連線核對遠端內容。專案自有程式沿用作者既有程式再修改；五個公開專案僅為設計參考，未複製原函式，也未新增為執行相依。授權摘要見[第三方來源與授權紀錄](../THIRD_PARTY_NOTICES.md)。

## Apprise

Chris Caron 與 contributors；固定 commit `80526d601c6f144f21d5ea1eaf0d57e1ddc6c879`；先前紀錄的 `LICENSE` 為 BSD-2-Clause。

| 原 repo 相對路徑 | 固定來源 |
| --- | --- |
| `apprise/plugins/telegram.py` | https://github.com/caronc/apprise/blob/80526d601c6f144f21d5ea1eaf0d57e1ddc6c879/apprise/plugins/telegram.py |
| `apprise/plugins/base.py` | https://github.com/caronc/apprise/blob/80526d601c6f144f21d5ea1eaf0d57e1ddc6c879/apprise/plugins/base.py |
| `LICENSE` | https://github.com/caronc/apprise/blob/80526d601c6f144f21d5ea1eaf0d57e1ddc6c879/LICENSE |

參考通知期間追蹤已接受目的地與片段，以及可設定 overflow；本專案的回執及補送仍不是持久 outbox。相簿合併、媒體降級、跨服務備援與 Apprise 的 URL 設定流程未整合。

## telegram-send

Rahiel Kasim 與 contributors；固定 commit `f5466fc2b8b8b9aaa55dd28fb80b6ae138b578d8`。`LICENSE.txt` 是 GPLv3 原文；`telegram_send/telegram_send.py` 第 5–8 行檔頭標示 GPL-3.0-or-later；`telegram_send/utils.py` 沒有獨立授權檔頭，不能把另一檔的宣告視為它自己的檔頭。

| 原 repo 相對路徑 | 固定來源 |
| --- | --- |
| `telegram_send/utils.py` | https://github.com/rahiel/telegram-send/blob/f5466fc2b8b8b9aaa55dd28fb80b6ae138b578d8/telegram_send/utils.py |
| `telegram_send/telegram_send.py` | https://github.com/rahiel/telegram-send/blob/f5466fc2b8b8b9aaa55dd28fb80b6ae138b578d8/telegram_send/telegram_send.py |
| `LICENSE.txt` | https://github.com/rahiel/telegram-send/blob/f5466fc2b8b8b9aaa55dd28fb80b6ae138b578d8/LICENSE.txt |

參考長文應自動處理的需求及原版 Python 字元切片的界線；本專案以作者既有 UTF-16 拆段為基礎修正，沒有複製 `split_message` 原函式。長 Markdown 不作不安全的自動拆段。

## python-telegram-bot

python-telegram-bot contributors；固定 commit `9a38d8f516fd14c56ef51dc21817d8fbe44c267c`。先前紀錄中，`pyproject.toml` 宣告 LGPL-3.0-only，`_aioratelimiter.py` 檔頭為 LGPL-3.0-or-later，`examples/echobot.py` 為 CC0；`LICENSE.dual` 開頭有 GPLv3／LGPLv3 選擇通知，另保留 `LICENSE`、`LICENSE.lesser` 原文定位。這些檔案層宣告不合併成單一授權說法。

| 原 repo 相對路徑 | 固定來源 |
| --- | --- |
| `src/telegram/ext/_aioratelimiter.py` | https://github.com/python-telegram-bot/python-telegram-bot/blob/9a38d8f516fd14c56ef51dc21817d8fbe44c267c/src/telegram/ext/_aioratelimiter.py |
| `pyproject.toml` | https://github.com/python-telegram-bot/python-telegram-bot/blob/9a38d8f516fd14c56ef51dc21817d8fbe44c267c/pyproject.toml |
| `LICENSE` | https://github.com/python-telegram-bot/python-telegram-bot/blob/9a38d8f516fd14c56ef51dc21817d8fbe44c267c/LICENSE |
| `LICENSE.lesser` | https://github.com/python-telegram-bot/python-telegram-bot/blob/9a38d8f516fd14c56ef51dc21817d8fbe44c267c/LICENSE.lesser |
| `examples/echobot.py` | https://github.com/python-telegram-bot/python-telegram-bot/blob/9a38d8f516fd14c56ef51dc21817d8fbe44c267c/examples/echobot.py |
| `LICENSE.dual` | https://github.com/python-telegram-bot/python-telegram-bot/blob/9a38d8f516fd14c56ef51dc21817d8fbe44c267c/LICENSE.dual |

參考整體／群組限流、伺服器 `RetryAfter` 與有限重試；本專案最多三次嘗試及長文共用 30 秒行內等待預算是本地策略。上游 `max_retries` 預設為 0；未整合其整體排程器、ConversationHandler 或持久化機制。

## aiogram

aiogram contributors；`LICENSE` 署名 Alex Root Junior；固定 commit `c5ead5b9fa615ca45cd971ba35d53785597c07c6`；先前紀錄的 `LICENSE` 為 MIT。

| 原 repo 相對路徑 | 固定來源 |
| --- | --- |
| `aiogram/exceptions.py` | https://github.com/aiogram/aiogram/blob/c5ead5b9fa615ca45cd971ba35d53785597c07c6/aiogram/exceptions.py |
| `LICENSE` | https://github.com/aiogram/aiogram/blob/c5ead5b9fa615ca45cd971ba35d53785597c07c6/LICENSE |

參考限流、網路、授權、禁止、衝突、伺服器及遷移錯誤的分類；未整合 FSM、callback factory 或完整媒體群組。

## TelegramBotCreator-SDK

gitReply；固定 commit `5971807f73269f0b0aca0e30036bf3696a07a7c3`；先前紀錄的 `LICENSE` 為 MIT。

| 原 repo 相對路徑 | 固定來源 |
| --- | --- |
| `bot.py` | https://github.com/gitReply/TelegramBotCreator-SDK/blob/5971807f73269f0b0aca0e30036bf3696a07a7c3/bot.py |
| `LICENSE` | https://github.com/gitReply/TelegramBotCreator-SDK/blob/5971807f73269f0b0aca0e30036bf3696a07a7c3/LICENSE |

僅比較 Bot 名稱、username、頭像等介面完整性。SDK BotFather 建立程式未採用，描述及頭像一致化未列為已實作。

## 官方協定與既有工具

| 來源 | 本專案參考界線 |
| --- | --- |
| https://core.telegram.org/api/obtaining_api_id | 使用者以自己的 Telegram 帳號申請 API ID／hash 的前置流程。 |
| https://my.telegram.org/apps | 使用者以自己的 Telegram 帳號申請 API 資料的入口。 |
| https://docs.telethon.dev/en/stable/basic/signing-in.html | 使用者自己的 Telegram 帳號登入、登入碼、2FA 與 Session 重用；實作沿用 Telethon。 |
| https://core.telegram.org/bots/api#getme | Bot 身份核對。 |
| https://core.telegram.org/bots/api#responseparameters | `retry_after` 與 `migrate_to_chat_id` 的協定依據。 |
| https://core.telegram.org/bots/api#sendmessage | 文字通知及回傳訊息的協定依據。 |
| https://requests.readthedocs.io/en/latest/_modules/requests/models/ | Requests 例外可能含完整 URL；僅參考行為，未複製原始碼。Requests 是既有相依。 |
| https://docs.astral.sh/uv/getting-started/installation/ | 使用者自行安裝 uv 的官方入口。 |

上述公開連結與五個框架設計參考的紀錄，不代表本輪重做遠端查證或已完成整體授權相容性判斷。

## 通用圖片與 PDF 收件

本專案自有實作見 [tg_receiver.py](../tg_receiver.py)，收件入口見 [tg-receive](../tg-receive)。它提供通用圖片／PDF 收件、存檔、JPEG 處理及檔案完成事件，應用專用 handler 與部署不納入公開範圍。官方行為參考為 [getUpdates](https://core.telegram.org/bots/api#getupdates)、[getFile](https://core.telegram.org/bots/api#getfile)、[Python sqlite3](https://docs.python.org/3/library/sqlite3.html) 與 [Pillow Image](https://pillow.readthedocs.io/en/stable/reference/Image.html)。使用者介面與事件界線見 [收件指南](RECEIVING.md)。

## Bot username 衝突互動

自有實作見 [tg_setup.py](../tg_setup.py)：只在 BotFather 明確拒絕名稱時查核替代 username，確認後才保存與重試。名稱查核依官方 [bots.checkUsername](https://core.telegram.org/method/bots.checkUsername)，顯示名稱與 username 規則依 [BotFather 說明](https://core.telegram.org/bots/features#botfather)。查核只反映當下狀態、不保留名稱；不以嘗試建立 Bot 代替可用性查核。建立結果不明時沿用 journal 的人工恢復流程。
