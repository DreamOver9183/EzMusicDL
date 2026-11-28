# EasyMusicDL 知識庫

> Claude、Gemini 與 sub-agent 共用的專案規範。每段工作完成後只補「新的架構決策、新慣例、踩到的坑」，不要寫進度或流水帳。不要寫本機絕對路徑或 commit hash。

## 文件指引

| 想知道 | 看哪裡 |
| :-- | :-- |
| 改版計畫（設計規格、各階段驗收） | `docs/YT_STUDIO_DARK_REDESIGN_PLAN.md` |
| 需求與設計、進度 | `docs/rgs/requirements.md`、`docs/rgs/design.md` |
| 介面設計契約 | `.interface-design/system.md` |
| 怎麼建置與測試 | 本檔「常用指令」 |

## 環境

| 項目 | 值 |
| :-- | :-- |
| 語言／框架 | Python（`pyproject.toml` 要求 3.9 以上，CI 用 3.12）、CustomTkinter、Pillow、requests、packaging |
| 目標平台 | Windows 10／11 免安裝版 |
| 建置工具 | PyInstaller `--onedir`，由 `build.py` 驅動 |
| 外部引擎 | `bin/` 下的 yt-dlp、FFmpeg、FFprobe、Deno，執行時下載，不進版控 |

## 架構規範

- `src/ytdlp_gui/core/` 放下載、設定、更新等邏輯；`gui/` 放畫面；`utils/` 放路徑、日誌、錯誤翻譯、通知。
- `core/` 不新增對 `gui/` 的直接依賴。現況是 `download_manager.py` 透過 `utils/notifications.py` 間接依賴 GUI。
- 所有可寫路徑都經由 `utils/paths.py`。免安裝版的根目錄是執行檔所在資料夾；從原始碼執行時是 repo 根目錄。
- 色票放 `gui/theme.py`，圖示放 `gui/icons.py`，錯誤分類與說明放 `utils/error_translations.py`。
- 版本號單一來源是 `src/ytdlp_gui/__init__.py`；`pyproject.toml` 要一致。
- yt-dlp 一律經由 `core/process_tracker.py` 啟動（呼叫當下用 `process_tracker.tracker`，不可 `from ... import tracker`），離開函式前結束仍在執行的行程再解除登記。更新用的 PowerShell 腳本**不可**納入追蹤。
- 關閉視窗與更新退出共用 `stop_all_downloads()`：之後不啟動任何新行程、不送 UI 回呼、不 `join` worker 執行緒。
- 背景下載的狀態轉換（完成、失敗、進度）在同一個 `queue_lock` 區塊內檢查取消並寫入。
- 使用者可見文字一律繁體中文，只保留必要技術名詞，不使用 Emoji。

## 機密規則（不可違反）

- `cookies.txt`（以及任何 `*cookies*.txt`）可能含 YouTube 登入資訊；`data/`、`logs/` 含使用者設定、紀錄與本機路徑。任何 agent 都不得讀取、列印、複製或 commit 這些檔案。
- 診斷紀錄不得輸出 cookie 內容或 Proxy 帳號密碼。
- 測試需要的假 cookie 或假帳密在暫存目錄於執行時產生。

## 常用指令

| 目的 | 指令 |
| :-- | :-- |
| 快速檢查 | `python -I -m compileall -q src main.py build.py` |
| 完整驗證 | 快速檢查，加上 `python -m pytest tests -q` |
| `network` 測試 | `python -m pytest tests -q -m network`（需要真實工具或外網的測試才標 `network`；預設不執行） |
| 安裝測試工具 | `pip install pytest`（列在 `pyproject.toml` 的 `dev` 相依） |
| 從原始碼啟動 | `python main.py`（會連網檢查引擎，並在 repo 根目錄寫入 `data/`、`logs/`） |
| 打包 | `python build.py --zip`，**只在 repo 以外的原始碼複本執行**（見踩坑紀錄） |

## 慣例

- Commit：`type(scope): 摘要`（英文）；內文說明原因。
- 分支：`feat/…`、`fix/…`、`chore/…`。
- PR 由使用者在 GitHub 手動合併。
- 暗黑工作台改版期間：里程碑合併後，只含文件的更新（本檔、`docs/rgs/design.md`、`docs/rgs/reviews/`）直接提交到 `main`；其他變更一律走 PR。合併審查報告不貼 PR 留言。
- CI（`.github/workflows/build.yml`）只在推送 `v*` tag 時執行。`release.ps1` 會以當天日期建立 tag 並推送 `main`，未經使用者同意不得執行。
- 刪除或修改公開 Release 須另外取得使用者同意。
- 所有 `gh` 指令帶 `--repo DreamOver9183/EzMusicDL`；執行會呼叫 `gh` 的 `rgs` 腳本時設定環境變數 `GH_REPO=DreamOver9183/EzMusicDL`。不得對 `upstream`（原作者專案）做任何寫入。
- PR 要等合併閘門完成並通過後才請使用者合併。
- 測試：pytest，放在 `tests/`；不得寫入 repo 內的 `data/`、`logs/`，離線測試不得連網或啟動真實下載。
- `tests/conftest.py` 自動套用兩層保護：`app_root` 把程式目錄、下載夾與工作目錄導向暫存位置；離線防護封鎖 socket 與 `ytdlp_wrapper` 的網路呼叫（標 `network` 者除外）。離線防護不封鎖 `subprocess`。
- 新增匯入 `get_default_downloads_dir` 的模組時，要在 `app_root` fixture 補上替換，否則測試會指向使用者真正的下載夾。

## 踩坑紀錄

<!-- 依領域分組；每條寫「現象 → 原因 → 做法」。標「靜態閱讀」者尚未以測試重現。 -->

### 下載佇列

- 下載中停止全部任務會卡死 → `queue_lock` 不可重入，持鎖時又呼叫會取同一把鎖的方法 → 持鎖時只處理資料；回呼、追蹤器呼叫、存檔一律在鎖外。
- 取消後狀態又變回完成或失敗 → 檢查取消與寫入狀態之間沒有持鎖 → 在同一個鎖區塊內檢查並寫入。
- 取消後行程仍在執行 → 只改狀態或只 set event，沒有終止行程樹 → 結束整個行程樹（yt-dlp 會再啟動子行程與 FFmpeg）。
- 測試建立 `DownloadManager` 可能直接開始下載 → 建構時就載入佇列檔並處理待下載項目 → 測試先把資料目錄指到暫存位置並替換 yt-dlp 呼叫。

### 自我更新

- 新版已裝好，重啟失敗後程式整個消失（實測紀錄） → 重啟寫在回滾用的 `try` 裡，而且重啟前已刪除備份 → 重啟獨立處理，失敗不得回滾已裝好的新版。
- 複製到一半失敗時回滾可能把備份搬進殘缺資料夾（靜態閱讀） → 項目在複製成功後才記錄 → 複製前先記錄，還原前先刪除目的地。
- 修了更新器，用舊的打包檔測不出效果 → 更新腳本由執行中的舊版產生 → 驗收時要用修正後的程式重新打包「舊版」。
- 產生的 `.ps1` 含中文路徑與文字 → Windows PowerShell 5.1 需要 BOM 才會以 UTF-8 讀取 → 維持以 `utf-8-sig` 寫檔。

### 版控與測試

- 開 PR 失敗並回報分支沒有 commit，或審查腳本找不到剛開的 PR → 本機有 `upstream` remote，`gh` 未指定 repo 時操作原作者專案 → 依「慣例」指定本專案 repo。

- 新增的 `tests/test_*.py` 沒出現在 `git status`，提交時漏掉 → `.gitignore` 的 `test_*`（原意是忽略測試下載檔）一併忽略測試檔 → 已加 `!tests/**/test_*.py`；新增檔案後確認 git 看得到。
- 用類別屬性保存原始函式後，`is` 比對失敗 → 透過實例讀取類別屬性會變成 bound method → 用 `types.SimpleNamespace` 保存。
- 行程樹測試偶爾讀到空的 PID 檔 → 檔案一建立 `exists()` 就為真，內容可能還沒寫入 → 假腳本寫暫存檔後 `os.replace`，測試輪詢到內容是數字為止。
- 測試失敗後遺留睡眠行程 → 清理只 `kill()` 父行程 → 父行程還活著時用 `kill_process_tree()` 清整棵樹。
- 缺陷回來時整個測試程序卡住 → 在主執行緒呼叫可能死結的方法 → 放在 daemon 執行緒並設 `join` 逾時。
- 測試全過但防護沒被測到 → 另一道防護剛好遮住 → 把缺陷放回程式，確認有測試失敗。
- 「日誌不含機密」的測試可能在程式沒讀到假資料時也通過 → 只做否定斷言 → 同時斷言假檔案確實被偵測到。

### 打包與設定

- 打包會刪掉 `dist/` 內其他檔案 → `build.py` 的 `clean_build()` 刪除整個 `dist/` → 修正前只在原始碼複本打包。
- 改了設定預設值，既有使用者沒有變化 → 第一次啟動就把全部預設值寫進 `settings.json` → 需要改既有行為時要明確處理舊值。

### 介面

- 把色票改成單一字串後圖示出錯（靜態閱讀） → `gui/icons.py` 把顏色當淺／深色 tuple 解包 → `theme.py` 與 `icons.py` 在同一次變更中修改。
