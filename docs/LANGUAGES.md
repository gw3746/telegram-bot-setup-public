# CLI languages / 命令列介面語言

**English** | **正體中文說明如下**

The project's own CLI help, prompts, errors, notification prefixes, and receiving prompts are available in English (`en`) and Traditional Chinese (`zh-TW`). Their separate message files are `languages/en.ini` and `languages/zh_TW.ini`; source annotations and `.env.example` comments also have English/Traditional Chinese counterparts. Third-party output from uv or Telegram and text supplied by users remain as received. JSON field names, machine-readable status codes, CLI options, and configuration keys are not translated.

本專案自有的 CLI 說明、提示、錯誤、通知前綴與收件提示提供英文 `en` 和正體中文 `zh-TW`。獨立訊息檔為 `languages/en.ini` 與 `languages/zh_TW.ini`；程式說明與 `.env.example` 註解亦提供中英對照。uv／Telegram 等第三方輸出及使用者提供的文字維持原文；JSON 欄位、機器狀態碼、CLI 參數與設定鍵不翻譯。

## Choose a language / 選擇語言

| Priority | Source | Effect / 說明 |
| --- | --- | --- |
| 1 | `--language zh-TW` or `--language en` | Overrides this invocation. `./tg-install --language ...` saves that choice only when installation succeeds; other tools do not change the saved preference.／覆寫本次語言；只有安裝成功才會由 `tg-install` 保存。 |
| 2 | `TG_LANGUAGE=zh-TW` or `TG_LANGUAGE=en` | Selects the language when no CLI override is given.／未指定 CLI 語言時生效。 |
| 3 | Project `.tg-language` | Preference saved by a successful install.／成功安裝後保存的偏好。 |
| 4 | English (`en`) | Default when nothing above selects a language.／都未指定時的預設。 |

For an interactive `./tg-install` without a CLI or environment language, the installer shows `1. 正體中文` and `2. English` before installing. Press Enter to accept the saved preference; on a first install, Enter chooses `2. English`. This menu is a language choice only: it does not log in to Telegram, create a bot, or send a message. A non-interactive install and `--help` do not show the menu; with no selected or saved preference, they use English.

互動執行 `./tg-install` 且未指定 CLI／環境語言時，安裝前先顯示 `1. 正體中文`、`2. English`。按 Enter 採用已儲存偏好；首次安裝則預設 `2. English`。語言選單只選介面語言，不登入 Telegram、不建立 Bot，也不傳送訊息。非互動安裝與 `--help` 不顯示選單；沒有指定或已存偏好時使用英文。

## Save or override / 保存或單次覆寫

```bash
./tg-install --language en
./tg-install --language zh-TW
TG_LANGUAGE=zh-TW ./tg-setup
./tg-message --language en 'My first notification' PERSONAL NONE
```

Run `./tg-install --language en` or `./tg-install --language zh-TW` again to change the long-term preference. The installer writes the project-root `.tg-language` with file mode `0600` only after installation succeeds. Git ignores that file. It contains only the UI language preference, not credentials. Passing `--language` to another tool affects that invocation only. A failed installation leaves the saved preference unchanged.

再次執行 `./tg-install --language en` 或 `./tg-install --language zh-TW` 可切換長期偏好。安裝成功後才會以 `0600` 權限寫入專案根目錄的 `.tg-language`，此檔由 Git 忽略，只記介面語言、不含憑證。其他工具的 `--language` 僅影響當次執行；安裝失敗不更動已存偏好。

Bot username conflict approval remains a Terminal interaction in the selected language; it is not sent through Telegram. Display language does not alter setup decisions, credentials, routes, or message content supplied by the user.

Bot username 衝突確認仍在所選語言的 Terminal 中進行，不透過 Telegram 發送。介面語言不改變 setup 決策、憑證、路由或使用者提供的訊息內容。

## Maintain message files / 維護訊息檔

Each UTF-8 file has a `[messages]` section. Message keys are fixed, case-sensitive lowercase `snake_case` identifiers; the program looks them up by key, not by line number or displayed text. Each value is a JSON double-quoted string within the INI file, so escapes such as `\n`, quotes, backslashes, and trailing spaces survive. The file itself is not JSON. Literal `%` and `%s` are not INI interpolation. Variables use named fields such as `{p0}` and `{p1}`; matching keys in both files must keep the same fields and value types. Tests check keys and placeholders.

每份 UTF-8 檔使用 `[messages]` 區段。訊息鍵名固定為區分大小寫的小寫 `snake_case`；程式依鍵名查找，不依行號或顯示文字。每個值是 INI 檔中的 JSON 雙引號字串，可保留 `\n`、引號、反斜線與行尾空白；整份檔案不是 JSON。字面 `%`、`%s` 不做 INI 插值。變數使用 `{p0}`、`{p1}` 等具名欄位；兩份檔案的對應鍵須保留相同欄位與值型別，測試會檢查鍵名與預留欄位。

For example, `setup_username_suggestion` is `"Suggestion: @{p0} (just checked as available; not reserved)."` in `en.ini` and `"建議：@{p0}（剛才查核可用，尚未保留）。"` in `zh_TW.ini`. Both use the same `{p0}` field.

例如，`setup_username_suggestion` 在 `en.ini` 與 `zh_TW.ini` 都使用相同的 `{p0}` 欄位；上方兩段文字已對照實際檔案。

You may reorder entries and edit display wording without compilation; restart the CLI to load edits. Add a new message key to both files. To add a language, create its file, register it in the controlled language list, and supply the same keys and placeholder fields. The CLI loads only the selected language file and caches it; switching languages loads the other file. The language-choice menu and errors before a language is known or when its file cannot be read use fixed bilingual bootstrap text. Duplicate keys and malformed values, or missing keys when requested, stop with a fixed bilingual error that does not echo the bad value. Do not change machine-readable JSON codes or text supplied by users.

可調整項目順序與顯示文案，無須編譯；重新啟動 CLI 才會載入修改。新增訊息鍵須兩份檔案齊備。新增語言須建立檔案、登錄受控語言清單，並提供相同鍵名與預留欄位。CLI 只載入當前選定語言的檔案並快取；切換語言才載入另一份。語言尚未確定時的選單與錯誤，以及語言檔無法讀取時的錯誤，使用不依賴語言檔的固定雙語文字。重複鍵、格式損壞或查詢到缺失的訊息鍵時，會以固定雙語錯誤停止，且不回顯損壞的值。不得改動機器可讀的 JSON 代碼或使用者原始訊息。

See the [English installation guide](../INSTALL_GUIDE.md) or [正體中文安裝指南](../INSTALL_GUIDE.zh-TW.md) for the full setup flow.
