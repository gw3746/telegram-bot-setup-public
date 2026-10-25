# 0.1.1 公測修正版驗證與重跑方式

## Unreleased：審查修正離線驗收

2026-10-24，七項審查問題修正後，本機 Python 3.12.3 的完整離線測試 **449 passed、0 failed／error／skipped**，包含新增 74 項回歸、既有 56 項雙語介面與 32 項語言包驗收；中英各 249 個訊息鍵。新增回歸覆蓋 Session 與附屬檔權限、例外去敏、訊息回執、重複設定鍵、收件永久拒絕與 20 次上限、矛盾 HTTP／JSON 及合成未註冊路由。原 HEAD 加入同一批新回歸為 60 failed／14 passed；原有 375 項先前全過，不能單靠它們判定這些問題已受保護。

Current offline acceptance: **449 passed, zero failures/errors/skips**, with 74 added regression cases and 249 message IDs per language. Tests run in a network namespace with Telegram traffic blocked and synthetic credentials only. This round does not repeat fresh-container, remote CI, or live Telegram acceptance. The following 375-test results describe the earlier 0.1.1 validation.

本輪未使用真實設定、Session 或 Telegram；未重跑全新容器或遠端 CI。Session 目錄收緊規則與未取得有效訊息回執時的停止行為見[安全說明](../SECURITY.md)及[進階用法](../TG_USAGE.md)，收件 DB 相容與拒絕／重試規則見[收件指南](RECEIVING.md)。

## 0.1.1 先前離線驗收（歷史結果）

本版公開範圍僅涵蓋通用通知、帳號工具及收件，應用專用流程、路由、捷徑與部署不納入；保留通用內建 `DEFAULT`（`TG_BOT_TOKEN`／`TG_CHAT_ID`）、setup 自訂路由、一般 Bot API 圖片發送及通用帳號工具，新增獨立的通用圖片／PDF 收件與事件介面。最終離線測試數 **375** 項通過（含 56 項雙語介面與 32 項語言包驗收），0 失敗／錯誤／略過；下方 298 項是 0.1.0 舊版結果，不能算作本版完成驗收。全新 Debian 13／Python 3.12.13／uv 0.11.8 容器重跑同樣全通過；另驗證基礎安裝在沒有 Pillow 時仍能保存 PDF、Python sqlite3 可用、JPG 選配套件在啟動 launcher 後保留。新增 username 衝突案例涵蓋採用建議、自填、取消、非互動、查核故障、名稱競爭與保存失敗。之前以既有已登入 Session 真實唯讀查核「已占用」與「當下可用」兩種 username 回應，原設定與 Session 檔案雜湊未變；沒有建立新 Bot 或改動 BotFather 對話。本輪雙語修改未操作真實 Telegram，尚未以真實 Telegram 驗收完整新建 Bot 的互動改名流程或通用收件。

語言包驗收確認 245 個固定訊息鍵對應兩份 INI、490 段文字逐字保留；並驗證檔案重排與改文案、按選定語言載入及快取、空白／換行／百分號、壞格式／重複鍵、缺失訊息與清楚的 CLI 診斷。雙語驗收涵蓋八個入口的中英 help、245 組完整訊息與插值對照、實際終端選單、成功後保存並沿用、語言優先序、取消、無效輸入及 0600／symlink 保護；另驗證合成 OTP／2FA、username 建議、圖片模式提示與通知前綴。使用者訊息、第三方回覆與機器欄位保持原文。詳見[語言說明](LANGUAGES.md)。

Previous 0.1.1 offline acceptance: **375 tests passed**, including **56 bilingual UI cases** and **32 language-pack cases**. Fresh Linux checks covered installation and both languages. Telegram calls were blocked; simulated sign-in verification was not live OTP/2FA acceptance.

## 0.1.0 歷史驗收

2026-10-24，0.1.0 舊版在 Linux／Python 3.12.3 本機跑得 **298 passed、0 failed、0 errors、0 skipped**（8.57 秒）；另在獨立 Debian 13／Python 3.12.13 容器跑得相同 298 項結果（9.174 秒）。兩次均未使用真實 Telegram 憑證或驗收 OTP／2FA；舊版含本版移除的私人應用，其測試數與功能範圍不得作為 0.1.1 的結果。

## 本機重跑

在專案根目錄執行：

```bash
uv sync --frozen --python 3.12
uv venv .test-venv --python 3.12
uv pip install --python .test-venv/bin/python -r requirements-test.txt
uv run --no-project --python .test-venv/bin/python python -m pytest -q tests
```

測試直接依賴有固定版本，傳遞依賴未完整鎖定；安裝需網路或可用快取。根目錄 conftest 阻擋 requests、urllib、socket 的真實連線，Telegram、BotFather、帳號登入驗證、故障回應與等待使用合成替身。安裝案例使用假 uv 或受控快取，不與真實帳號操作混在一起。

## CI 與秘密掃描

`.github/workflows/ci.yml` 包含離線測試與 Gitleaks job；新獨立倉庫的秘密掃描使用 `--all --full-history -m`，涵蓋取得的全部 refs、各自完整歷史與 merge 差異。Actions 以完整 commit SHA 固定，權限為 contents: read，不向測試提供 Telegram 憑證。掃描器下載有固定版本及官方 SHA256 驗證，輸出去敏，不採基線忽略或排除整個測試目錄。

本機執行與 workflow 語法檢查不等同 GitHub runner 已執行；新倉庫的 CI 狀態以實際 Actions 記錄為準。公開前仍需核對全部擬公開 refs 及歷史，不只掃目前檔案。

工具固定來源：

- checkout：[actions/checkout 固定 commit](https://github.com/actions/checkout/tree/3d3c42e5aac5ba805825da76410c181273ba90b1)。
- uv 安裝：[astral-sh/setup-uv 固定 commit](https://github.com/astral-sh/setup-uv/tree/07a047e608db84b3d8c06cd9a7c7dcc9c355c18e)，工具版本固定 0.11.8；[官方 CI 說明](https://docs.astral.sh/uv/guides/integration/github/)。
- 秘密掃描：[Gitleaks 8.30.1](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1)。
- workflow 本機語法檢查：[Actionlint 1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12)。

可自行使用 [Gitleaks](https://github.com/gitleaks/gitleaks) 掃描：

```bash
gitleaks git --log-opts="--all --full-history -m" --ignore-gitleaks-allow --redact=100 --no-banner .
```

沒有命中不是安全保證；秘密掃描無法取代使用者自己的憑證管理、權限隔離及安全回報。

## 範圍與限制

驗收涵蓋 API 接受與必要回執判斷，不表示使用者已讀。setup 完成後重跑不重建或重送，unknown 不盲目重試；外部 Token 輪換後的 setup journal 不會自動銜接。缺少有效 retry_after 時保持人工處理。

長文字優先避開空白段界，但原文頭尾或找不到安全切點的特殊連續空白仍受 Telegram 正規化影響。長 Markdown／自訂格式不保證任意安全拆分。

正式服務、實際 OTP／2FA 初次登入、真實 429／unknown，以及通用收件的真實 Bot 訊息與單一 consumer 行為，需另在使用者自己的環境驗收。內部執行報告、主機資訊與私人測試紀錄不納入發行內容。
