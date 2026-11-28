# M3：自我更新器

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-3 |
| 相依 | M2（已合併） |
| 分支 | `fix/m3-updater` |

## 目標

自我更新在**任何**失敗下都不留下壞掉的安裝：更新腳本確定啟動後主程式才退出；替換失敗可完整回滾；重啟失敗絕不刪除已安裝好的新版。

## 可修改的檔案

- `src/ytdlp_gui/core/update_checker.py`：更新腳本產生器與 `apply_update()`
- `src/ytdlp_gui/core/process_tracker.py`：`taskkill` 使用 System32 完整路徑
- `src/ytdlp_gui/main.py`：`--self-update-test` 進度日誌節流
- `src/ytdlp_gui/gui/components/help_dialog.py`：套用更新改在背景執行緒
- `tests/test_updater_script.py`（新檔）：真實執行產生的 PowerShell 腳本
- `tests/test_update_apply.py`（新檔）：握手、重入、日誌節流、完整路徑

## 目前的缺陷（先讀 `update_checker.py` 確認）

1. **實測過的嚴重缺陷**：重啟（`Start-Process`）寫在回滾用的 `try` 裡，且重啟前已刪除備份。重啟回報 `Access is denied` → 回滾把剛裝好的新版全部刪掉 → 安裝消失。
2. 項目在 `Copy-Item` **成功後**才記入清單；複製到一半失敗時殘缺的目的資料夾留著，回滾的 `Move-Item` 會把備份搬**進**它裡面。
3. 回滾錯誤以 `SilentlyContinue` 忽略，仍記「Rollback completed」。
4. 腳本開頭直接刪除既有 `.update_backup`，上次失敗留下的唯一備份可能被毀。
5. `apply_update()` 在 `Popen` 後立刻回傳 True，腳本沒啟動時主程式照樣退出。啟動旗標同時用了 `DETACHED_PROCESS` 與 `CREATE_NO_WINDOW`（兩者併用時後者被忽略）；推測這是腳本沒有執行的原因，尚未證實。
6. 失敗 Popup 逾時值為 0（永遠等待）。
7. `--self-update-test` 每個下載區塊都寫一行進度（實測 612 行）。

## 設計

### 1. `apply_update()`

- 啟動旗標：`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`（**移除** `DETACHED_PROCESS`）；`stdin`、`stdout`、`stderr` 皆 `subprocess.DEVNULL`；`close_fds=True`；保留 `env=self._clean_env()`。
- `powershell.exe` 用完整路徑 `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`（檔案不存在時退回 `"powershell.exe"`）。保留 `-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File`。腳本維持以 `utf-8-sig` 寫出。
- **握手**：標記檔 `updater.started` 一律位於 `staging_dir`（在系統暫存目錄，與腳本同處，不依賴程式目錄可寫）。啟動前先刪除同路徑的舊標記。啟動後每 0.1 秒檢查：
  - 標記出現 → 成功。
  - 子行程已結束但沒有標記，或超過逾時（類別屬性 `HANDSHAKE_TIMEOUT_S = 10.0`，測試可調小）→ 用 `process_tracker.kill_process_tree(proc)` 終止，記錄原因，回傳 False（主程式不退出）。
  - `Popen` 本身丟例外 → 記錄並回傳 False。
- **更新腳本不可登記到 `process_tracker.tracker`**（否則主程式退出時會把它終止）。只使用 `kill_process_tree` 這個函式。
- **防重入**：實例上的 `threading.Lock`，非阻塞取得；取不到就回傳 False 且不啟動任何行程。失敗時釋放鎖；成功時保持持有（程式即將退出），之後的呼叫回傳 False。
- 既有的前置條件（`prepared` 有效、Windows、frozen）維持；前置條件不符時不可卡住鎖。

### 2. `build_windows_updater_script(...)`

保留現有位置參數與 `relaunch`；新增關鍵字參數（皆有預設值）：`parent_wait_seconds=30`、`popup_seconds=15`、`alive_seconds=10`、`relaunch_delays=(2, 4, 6, 8)`（5 次嘗試之間的 4 段等待）、`fallback_log_path=None`（None 時腳本用 `Join-Path ([System.IO.Path]::GetTempPath()) 'EasyMusicDL_updater.log'`）。`relaunch=False` 時跳過 C 段重啟，視為成功並清理。

**腳本結構（必須遵守，測試靠它覆寫函式）**：先是參數賦值，接著所有 `function` 定義，然後**獨立一行 `# --- main ---`**，之後是主流程。主流程中對外部有副作用或需要模擬失敗的動作一律透過函式呼叫：

| 函式 | 職責 |
| :-- | :-- |
| `Write-UpdaterLog([string]$msg)` | 寫入 `$logPath`；失敗改寫 `$fallbackLogPath`；兩者都失敗也**不可丟例外** |
| `Show-UpdaterPopup([string]$text, [string]$title, [int]$icon)` | `WScript.Shell` Popup，逾時秒數 `$popupSeconds`；包在 try/catch。**所有**提示都經由它 |
| `Test-AppDirWritable([string]$dir)` | 建立並刪除唯一名稱的探測檔，回傳 bool |
| `Move-ItemAtomic([string]$src, [string]$dst)` | 用 `[System.IO.Directory]::Move` 或 `[System.IO.File]::Move`（同一磁碟的改名；目的地已存在會丟例外，**不會把來源搬進目的資料夾**），最多重試 5 次、間隔 500ms |
| `Copy-UpdateItem([string]$src, [string]$dst)` | `Copy-Item -LiteralPath ... -Recurse -Force` |
| `Remove-ItemVerified([string]$path)` | 刪除（含重試），刪完仍存在就丟例外 |
| `Invoke-LaunchProcess([string]$exe, [string]$workDir)` | 只做 `Start-Process -FilePath ... -WorkingDirectory ... -PassThru` 並回傳行程物件 |
| `Start-UpdatedApp(...)` | C 段的重試與存活判斷，內部呼叫 `Invoke-LaunchProcess` |

**主流程**

0. 一開始就建立握手標記 `Join-Path $stagingDir 'updater.started'`（寫入失敗也不可中止），接著寫開始日誌。握手標記與日誌之外，A 段前置檢查通過前**不得改動安裝內容**。

**A 段前置檢查（依序）**
1. 等父行程結束（最多 `$parentWaitSeconds`）。逾時：記錄、提示「請關閉程式後重試」、`exit 1`。
2. 若 `.update_backup` 存在且非空，而且（`$appRoot\<exeName>` 不存在，**或** 備份內有 `_internal` 但 `$appRoot\_internal` 不存在）：不刪除任何東西，記錄、提示備份路徑與「請手動復原」、`exit 1`。
3. `Test-AppDirWritable $appRoot` 為假：記錄、提示、`exit 1`。
全部通過才刪除舊 `.update_backup` 並建立新的空資料夾。

**A 段替換**：對 payload 中每個不在 `$preserved` 的項目：
- **任何改動之前**先把紀錄 `{ Name; HadOriginal }` 加入清單。
- 若原始項目存在：`Move-ItemAtomic` 到備份。
- `Copy-UpdateItem` 到目的地。

**回滾（只用於 A、B 段）**，依清單逆序，逐筆各自 try/catch：
- `HadOriginal` 為真：
  - **只有當備份中確實存在該項目時**，才刪除目的地（`Remove-ItemVerified`）並用 `Move-ItemAtomic` 把備份搬回。
  - **備份中不存在代表原始項目從未被搬走：絕對不可刪除或改動目的地。**（這是最重要的一條。）
- `HadOriginal` 為假：目的地存在就 `Remove-ItemVerified`。
- 任一筆失敗：繼續處理其他筆；最後記 `ROLLBACK INCOMPLETE`（附失敗項目），**保留 `.update_backup`**，提示備份完整路徑。全部成功才記 `Rollback completed.`。
- 提示中包含日誌路徑；檔案被占用時提示「請關閉所有程式視窗後重試」。然後 `exit 1`。

**B 段確認**（仍屬可回滾範圍）：目的 exe 存在，且其 SHA-256（`Get-FileHash`）與 payload 中的 exe 相同；payload 有 `_internal` 時目的地也要有。不符就丟例外走回滾。

**C 段重啟**：與上面**完全分開**的 `try/catch`，進入後**任何情況都不回滾、不刪除已安裝的檔案**。
- 最多 5 次呼叫 `Invoke-LaunchProcess`。**啟動被拒**（丟例外）：記錄例外，依 `$relaunchDelays` 等待後重試。
- 啟動成功後等 `$aliveSeconds` 秒（可輪詢 `HasExited`）：仍存活 → 刪除 `.update_backup` 與 `$stagingDir`（刪除失敗只記錄），記成功，`exit 0`。
- **啟動後在期限內結束**：記錄 `ExitCode`，**不再重啟**。
- 5 次都被拒，或提早結束：保留新版與 `.update_backup`，提示「已更新完成，請手動開啟 <exe>」，提早結束時另附備份路徑與手動復原步驟；`exit 2`。

`$preserved`、`_ps_quote`、路徑含單引號與中文的處理維持。所有提示用繁體中文。腳本必須相容 **Windows PowerShell 5.1**（不可用 `&&`、`??`、三元運算子）。

### 3. `process_tracker.py`

`kill_process_tree` 的 `taskkill` 改用 `%SystemRoot%\System32\taskkill.exe`（不存在時退回 `"taskkill"`）。其他行為不變。

### 4. `main.py`（`src/ytdlp_gui/main.py`）

`run_self_update_test()` 的下載進度日誌節流：只有跨過新的 10% 級距，或階段改變時才寫。「階段」以訊息去掉數字後的文字判斷。把節流邏輯做成可單獨測試的模組層級函式，例如 `make_progress_logger(logger) -> Callable[[str, float], None]`。其他行為不變。

### 5. `help_dialog.py`

`_on_download_app_update_done` 中的 `apply_update()` 最多阻塞 10 秒，改在背景 daemon 執行緒呼叫，期間按鈕保持停用並顯示「正在啟動背景更新程序...」。完成後回到主執行緒：
- 用父視窗排程（`self.master.after(...)`），因為使用者可能已關閉對話框。
- 成功：**無論對話框是否還存在**都要呼叫 `self.on_app_exit_for_update`（沒有這個回呼時才 `destroy` 對話框）。
- 失敗：對話框還存在時恢復按鈕並顯示「無法啟動免安裝更新背景程序，請查看診斷紀錄。」。

## 測試

### 安全規則（務必遵守，這些測試會執行真實的 PowerShell）

- `appRoot`、`stagingDir`、payload、日誌、`fallback_log_path` **一律在 `tmp_path` 之下**。組腳本的輔助函式要在執行前斷言這幾個路徑都在 `tmp_path` 內，否則拒絕執行。
- **每一個**執行的腳本都必須覆寫 `Show-UpdaterPopup`（改成把標題與內容寫到 `tmp_path` 的檔案），不得彈出任何視窗；同時傳 `popup_seconds=1` 當保險。
- **不可**呼叫真正的 `Start-Process`：每個 `relaunch=True` 的腳本都覆寫 `Invoke-LaunchProcess`（需要「存活的行程」時，覆寫版本可用 `[System.Diagnostics.Process]::Start` 搭配 `ProcessStartInfo`，`UseShellExecute=$false`、`CreateNoWindow=$true`，啟動 `sys.executable -c "import time; time.sleep(N)"`；結束時清掉它）。
- 覆寫方式：在產生的腳本中，把覆寫的函式定義插在 `# --- main ---` 那一行**之前**。插入前斷言該行恰好出現一次。
- `parent_pid` 用一個已經結束的行程 PID（先啟動 `sys.executable -c "pass"` 並 `wait()`）。測「父行程逾時」時才用存活中的假行程，並設 `parent_wait_seconds=2`。
- 以 `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File <script>` 執行，`subprocess.run(..., timeout=90, creationflags=CREATE_NO_WINDOW)`；腳本以 `utf-8-sig` 寫檔。日誌用 `utf-8-sig` 讀取。
- `alive_seconds`、`relaunch_delays` 用很小的值讓測試快速。
- 假安裝內容：exe 用任意位元組、`_internal/` 放數個檔案（含中文檔名）；`bin/`、`data/`、`logs/`、`cookies.txt` 各放標記檔（內容在執行時產生）。appRoot 路徑需含**中文、空格與單引號**。
- 「舊版完全一致」用整棵樹的相對路徑與 SHA-256 比對。

### `tests/test_updater_script.py` 必要情境

| # | 情境 | 必要斷言 |
| --: | :-- | :-- |
| 1 | 成功（`relaunch=True`，假行程存活） | 新版內容就位；舊的多餘檔案不殘留於 `_internal`；備份與 staging 被刪；保留項目雜湊不變；握手標記曾建立（可在覆寫的啟動函式中檢查並寫檔記錄）；exit 0 |
| 2 | 成功（`relaunch=False`） | 同上的安裝結果 |
| 3 | A 段複製到一半失敗（覆寫 `Copy-UpdateItem`：先在目的地建立部分內容再 `throw`） | 舊版整棵樹逐檔一致；目的地沒有巢狀的 `_internal\_internal`；日誌有 `Rollback completed.` |
| 4 | **備份搬移失敗**（測試程序以獨佔方式持有安裝中的某個檔案，讓搬移失敗；至少涵蓋被鎖的是**第一個**以及**較後面**的項目） | 舊版整棵樹逐檔一致，**被鎖的原始項目沒有被刪除或改動**；非零退出；有提示 |
| 5 | 回滾本身失敗（讓複製丟例外，並覆寫 `Move-ItemAtomic` 使「搬回」失敗） | 日誌有 `ROLLBACK INCOMPLETE`、沒有 `Rollback completed.`；`.update_backup` 內仍有原始檔案；提示含備份路徑 |
| 6 | B 段雜湊不符（覆寫 `Copy-UpdateItem` 讓複製出的 exe 內容不同） | 回滾後與舊版一致 |
| 7 | 重啟前兩次被拒、第三次成功 | 啟動呼叫次數 3；成功清理；exit 0 |
| 8 | **五次全部被拒（`Access is denied`）** | **新版完整仍在**；`.update_backup` 保留；呼叫次數 5；提示含「手動開啟」；exit 2；日誌沒有任何回滾字樣 |
| 9 | 啟動後立刻結束 | 只啟動 1 次；日誌含 ExitCode；新版與備份都在；提示含備份路徑；exit 2 |
| 10 | 非空備份且主程式缺失 | 備份內容不變、安裝不變、非零退出 |
| 11 | 非空備份且備份有 `_internal` 但安裝缺 `_internal` | 同上 |
| 12 | 非空備份但安裝完整（上次重啟失敗留下） | 更新照常成功 |
| 13 | 程式目錄不可寫（覆寫 `Test-AppDirWritable` 回傳 `$false`，且讓 `logPath` 寫不進去，例如它的父路徑是一個**檔案**） | 握手標記仍建立；日誌寫到 fallback；安裝與既有備份不變；有提示；非零退出 |
| 14 | `Test-AppDirWritable` 本身（不覆寫） | 正常目錄回傳真；不存在或是檔案的路徑回傳假；沒有遺留探測檔 |
| 15 | 父行程逾時 | 安裝不變；提示含「關閉程式」；非零退出 |
| 16 | 繁中與單引號路徑 | 日誌讀回的路徑與中文字沒有亂碼 |
| 17 | `single_exe` 型態（payload 只有 exe）且有舊備份殘留 | 能成功更新（不因沒有 `_internal` 誤判為需手動復原） |

另外檢查產生的腳本文字：有且僅有一行 `# --- main ---`；沒有 Popup 逾時 `0`；`relaunch=True` 時回滾程式碼在 C 段之前。

### `tests/test_update_apply.py`

用 `monkeypatch` 讓 `is_frozen()` 為真、`get_app_root()` 與日誌目錄指到 `tmp_path`、`subprocess.Popen`（`update_checker` 模組內使用的）換成假物件；**不得啟動真的 PowerShell**。

- 標記出現 → True，且呼叫參數不含 `DETACHED_PROCESS`、含 `CREATE_NO_WINDOW` 與 `CREATE_NEW_PROCESS_GROUP`、三個標準串流為 `DEVNULL`、`close_fds=True`、執行檔是 System32 完整路徑、含 `-NoProfile` 與 `Bypass`。
- 逾時 → False，假行程被終止。
- 子行程提早結束且無標記 → False，不必等滿逾時。
- 啟動前已有舊標記而新腳本沒有寫 → False（舊標記被刪除，不可誤判）。
- `Popen` 丟例外 → False，之後可再次呼叫。
- 重入：第一次進行中時第二次回傳 False 且沒有再呼叫 `Popen`；成功後再呼叫回傳 False；失敗後可重試。
- 寫出的腳本以 BOM 開頭。
- 進度節流：模擬 600 次 `0.05 → 1.0` 的下載回呼，寫出的日誌行數 ≤ 20；階段改變一定寫。
- `kill_process_tree` 呼叫的 `taskkill` 是 System32 完整路徑（monkeypatch `subprocess.run`，用假的行程物件，不要結束任何真實行程）。

## 實作要點

1. 你不能執行任何東西。PowerShell 部分請逐行核對 5.1 語法：`function` 參數、字串中的 `$` 跳脫、`return` 行為（函式中未捕捉的輸出會成為回傳值，需要時用 `| Out-Null`）、`$ErrorActionPreference='Stop'` 之下哪些呼叫會丟例外。
2. 既有的 `tests/test_update_checker.py::test_apply_update` 必須繼續通過。
3. 修改的檔案結尾剛好一個換行；不要重排無關程式碼。

## 不要做

- 不要修改清單以外的檔案（含知識庫、README、`build.py`、`main_window.py`、版本號）。
- 不要改更新檢查、下載、SHA-256 驗證、解壓縮的行為。
- 不要在任何測試中連網。
- 不要處理更新中途斷電的復原（範圍外）。

## 驗收條件

- [ ] 上表 17 個情境全部有測試且通過。
- [ ] `apply_update()` 的握手、重入與啟動參數測試通過。
- [ ] `--self-update-test` 進度日誌節流後不超過 20 行。
- [ ] 測試過程沒有彈出任何視窗，沒有寫入 `tmp_path` 以外的位置。
- [ ] 既有測試全部通過。

（端對端驗收：由 Claude 用本分支打包「舊版」後在沙盒執行，不屬於你的工作。）

## 先前里程碑的教訓

1. 回滾範圍不得包含重啟新版。
2. 否定斷言要同時斷言前提成立（例如斷言「沒有回滾」之前，先確認腳本確實跑到了該階段），否則可能空過。
3. 測試中可能卡住的呼叫要有逾時，讓缺陷造成失敗而不是卡住整個測試程序。
4. 行程間用檔案傳資料要先寫暫存檔再改名，讀取端輪詢到內容完整。
5. 子行程確定結束前不可放棄追蹤；測試清理要在父行程還活著時清整棵行程樹。
6. 保存函式參考供 `is` 比對時用 `types.SimpleNamespace`。
7. 新增檔案後確認沒有被 `.gitignore` 忽略。
8. 修改的檔案結尾不得有空白行或缺少結尾換行，局部編輯做不到時整檔覆寫。
