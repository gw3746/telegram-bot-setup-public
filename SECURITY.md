# 安全回報與憑證保護

公測階段維護最新 `0.1.x` 版本；修正以最新版本為準，不承諾回補舊版本。

## 私下回報漏洞

請優先使用本專案 GitHub Security 頁面的 **Report a vulnerability** 私人回報入口：[建立安全回報](https://github.com/gw3746/telegram-bot-setup-public/security/advisories/new)。此入口需由維護者啟用；若看不到，請先在 Issue 只提出「需要私密安全回報管道」，不貼漏洞細節，待維護者提供私密管道後再提交。不要在公開 Issue、PR、log 或截圖中貼出 Token、API hash、電話、Session 或含秘密的 journal。

回報可提供受影響版本、必要前置、合成資料的重現步驟、預期與實際行為；移除個人與憑證資料。維護者會依影響與可重現性處理，未設定保證回覆時限。

## 發現憑證外洩

Bot Token 視同密碼。若外洩，先透過官方 BotFather 撤銷／重發，再同步明確使用它的設定與 consumer；刪檔或改成 private 不能讓舊 Token 失效。Session 外洩時請用 Telegram 官方登入裝置管理處理對應授權。

輪換部分失敗時依工具輸出的 `RECOVERY_DIR` 及受保護 journal 人工核對；舊 Token 可能已失效，不把設定備份當作可用的自動回滾。不要自動重試結果不明的建立、撤銷或通知。

## 開發與部署

設定保留在 `.env` 或明確指定的私有檔案，0600 或更窄；Session、登入狀態、Bot 更新 offset、Token 輪換紀錄及收件狀態預設保存在 `~/.local/state/telegram-bot-setup`，可由 `TG_CONFIG_STATE_DIR` 覆寫根目錄，各工具的個別路徑參數仍優先。Session／狀態目錄 0700。舊版使用者可把 repo 內 `.state` 的內容複製到新位置，或設定 `TG_CONFIG_STATE_DIR` 指回舊目錄；遷移及備份副本同樣須保護憑證。不要提交這些檔案或把秘密放進命令列。自動測試使用合成資料，根目錄 conftest 阻擋真實 requests／urllib／socket；CI 不需要 Telegram 憑證。

舊帳號 CLI 與 provision 在建立及使用 Session 前後，會把本人擁有的 Session 父目錄收緊至 0700，Session 與 SQLite 附屬檔收緊至 0600；不安全的連結、非本人檔案或無法收緊權限時拒絕操作。請使用專用狀態目錄，避免把 Session 指向共用目錄。錯誤診斷沿用共用去敏，遮蔽當次 Token、API hash、電話與密碼；不要以去敏取代秘密管理。

本專案包含 Gitleaks 掃描；沒有命中不代表可保證不存在秘密或安全缺陷。發布前仍需檢查實際 Git refs、完整歷史、封裝內容及配置。內部運作報告與現場設定不屬公開候選版內容。

私人回報功能與 SECURITY.md 是不同設定，公開後由維護者核對啟用；流程見 [GitHub 官方說明](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately)。
