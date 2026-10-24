# 相依套件與安裝重現

本文件按目前版控中的 [根專案 manifest](../pyproject.toml)、[根專案鎖檔](../uv.lock) 與[測試需求](../requirements-test.txt)整理。表內版本只代表各自文件記錄的環境；根專案與測試虛擬環境分開安裝。

## 工具與版本範圍

- 執行環境為 Linux，安裝需 `python3`、uv 與 Bash；從遠端取得專案時另需 Git 和該 repository 的存取權。Gitleaks 與 Actionlint 用於開發檢查，不是 Telegram 執行相依。操作入口見[安裝指南](../INSTALL_GUIDE.md)。
- 根專案 manifest 允許 Python `>=3.11`。安裝指南與 CI 使用 Python 3.12；[CI](../.github/workflows/ci.yml)另選用 uv `0.11.8`，uv 的本身版本未在 Python manifest 鎖定。
- 下列命令在 repository 根目錄執行。首次安裝依賴套件可能需要網路；`--frozen` 使用版控鎖檔，不會替測試需求產生完整鎖檔。

「已鎖定」指 lock 檔為這次依鎖安裝選定的確切版本，並非套件永遠只能用這一版。[根專案 manifest](../pyproject.toml) 以 `==` 指定直接依賴，[根專案 lock](../uv.lock)另記錄其傳遞依賴的確切版本；[測試需求](../requirements-test.txt)也以 `==` 指定直接版本，但未鎖住全部測試傳遞依賴。需要升級時可調整版本要求、更新 lock 並重新測試；`uv sync --frozen` 本身不會自行更新 lock。

## 根專案執行依賴

[根專案 manifest](../pyproject.toml) 直接固定 `requests==2.34.2` 和 `telethon==1.45.0`；可選 `images` extra 另固定 `Pillow==12.3.0` 與 `pillow-heif==1.8.0`。[根專案鎖檔](../uv.lock)記錄兩種安裝範圍的套件：

`requests` 用於 Bot API 的 HTTP 請求；`telethon` 用於本人帳號授權、歷史讀取與 BotFather 操作。

| 套件 | 鎖定版本 | 類別 |
| --- | --- | --- |
| requests | 2.34.2 | 直接依賴 |
| telethon | 1.45.0 | 直接依賴 |
| certifi | 2026.7.22 | 傳遞依賴 |
| charset-normalizer | 3.5.2 | 傳遞依賴 |
| idna | 3.20 | 傳遞依賴 |
| urllib3 | 2.8.0 | 傳遞依賴 |
| pyaes | 1.6.1 | 傳遞依賴 |
| rsa | 4.9.1 | 傳遞依賴 |
| pyasn1 | 0.6.4 | 傳遞依賴 |
| Pillow | 12.3.0 | `images` extra 直接依賴 |
| pillow-heif | 1.8.0 | `images` extra 直接依賴，使用 Pillow |

鎖檔另有本地專案項 `tg-config==0.1.1`；它不是額外的第三方套件。安裝根專案：

```bash
uv sync --frozen --python 3.12
```

一般使用者亦可照[安裝指南](../INSTALL_GUIDE.md#step-3-install)執行 `./tg-install`；此 launcher 使用專案鎖檔安裝相依，不進行 Telegram 初始化。

通用 `tg-receive` 的 `original` 模式只保存原圖片與 PDF，用上方根專案相依即可。若需保留原圖並另存 JPG，先安裝 `images` extra：

```bash
uv sync --frozen --extra images
```

Pillow 處理圖片轉換，pillow-heif 補 HEIF／HEIC 支援；兩者不由一般根專案安裝自動加入。收件 offset 使用 Python 標準庫 `sqlite3`，會在狀態目錄建立 SQLite 檔案，無須另裝 SQLite 伺服器、`sqlite3` CLI 或 pip 的 `sqlite3` 套件。若精簡 Python 缺少此標準庫支援，收件程式會在啟動前提示；參見[收件指南](RECEIVING.md)。

## 根目錄測試需求及界線

[測試需求](../requirements-test.txt)直接固定五個套件：`requests==2.34.2`、`telethon==1.45.0`、`pytest==9.1.1`、`Pillow==12.3.0`、`pillow-heif==1.8.0`。它不是完整測試鎖檔；經 `uv pip install -r` 解析出的測試傳遞依賴版本可能隨套件索引及安裝時間改變。

全新測試 runner 先用根專案鎖檔預備相依，再建立獨立測試環境，與[CI 安裝順序](../.github/workflows/ci.yml)一致：

```bash
uv sync --frozen --python 3.12
uv venv .test-venv --python 3.12
uv pip install --python .test-venv/bin/python -r requirements-test.txt
uv run --no-project --python .test-venv/bin/python python -m pytest -q tests
```

第一行預備根專案鎖檔的套件；部分舊版 help 測試會透過 uv 同步根專案環境，若全新 runner 未先備好套件快取，離線檢查可能因缺相依而失敗。這個安裝順序不能解讀為測試傳遞依賴也已完整鎖定。
