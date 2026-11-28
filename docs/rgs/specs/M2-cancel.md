# M2：停止、取消與退出

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-2 |
| 相依 | M1（已合併） |
| 分支 | `fix/m2-cancel` |

## 目標

下載中關閉視窗或按應用程式更新時：程式不卡死、yt-dlp 與 FFmpeg 整個行程樹被結束、已取消的工作不會改回完成或失敗，也不會再啟動任何新行程。

## 可修改的檔案

- `src/ytdlp_gui/core/process_tracker.py`（新檔）：子行程追蹤、取消與退出
- `src/ytdlp_gui/core/ytdlp_wrapper.py`：三個啟動 yt-dlp 的位置改走追蹤器
- `src/ytdlp_gui/core/download_manager.py`：死結、取消競態、退出順序、佇列存檔
- `src/ytdlp_gui/gui/components/music_search_view.py`：退出中不再回寫 UI
- `build.py`：只在 `hiddenimports` 清單加入 `"ytdlp_gui.core.process_tracker"`
- `tests/conftest.py`：加入追蹤器的隔離 fixture
- `tests/test_process_tracker.py`（新檔）
- `tests/test_download_cancel.py`（新檔）

## 目前的缺陷（先讀程式確認）

1. **死結**：`download_manager.py` 的 `stop_all_downloads()` 持有 `queue_lock`（`threading.Lock`，不可重入）時呼叫 `_cancel_download()`，後者呼叫 `get_download_item()` 再取同一把鎖。
2. **停止後又開始下一筆**：被取消的 worker 收尾時呼叫 `_process_queue()`，會啟動下一個 PENDING。
3. **持鎖呼叫回呼**：`_process_queue()` 持鎖呼叫 `_start_download()`，後者呼叫 `_notify_progress_change()`。
4. **取消無效**：`_cancel_download()` 只改狀態，不終止子行程。worker 之後會把狀態改成 FAILED 或 COMPLETED，還可能因錯誤字串含重試關鍵字而換瀏覽器重試；`_on_subprocess_progress()` 與 `ytdlp_wrapper.download()` 的失敗回呼也會覆寫狀態。
5. **佇列存檔**：多個執行緒可能同時寫 `download_queue.json`；直接覆寫目標檔，程式在寫入中結束會留下半個檔案。

## 設計

### `core/process_tracker.py`

- `class ProcessCancelled(Exception)`。
- `class ProcessTracker`，內部用一把自己的 `threading.Lock`：
  - 屬性 `shutting_down: bool`（唯讀 property）。
  - `spawn(cmd, *, group: str, cancel_event: Optional[threading.Event] = None, **popen_kwargs) -> subprocess.Popen`：**在同一次持鎖中**完成「檢查 `shutting_down` 與 `cancel_event` → `subprocess.Popen` → 登記（行程、group、cancel_event）」。任一檢查不通過就丟 `ProcessCancelled`，不啟動行程。
  - `release(proc)`：移除登記。可重複呼叫。
  - `cancel(cancel_event)`：持鎖時 `cancel_event.set()` 並複製用這個 event 登記的行程；**放開鎖後**逐一終止。
  - `terminate_group(group)`：同樣先在鎖內複製，鎖外終止。（M8 切換查詢時使用，本里程碑只需實作與測試。）
  - `shutdown()`：持鎖設 `shutting_down = True`、複製全部行程並對其 event 呼叫 `set()`；鎖外終止。可重複呼叫。之後的 `spawn` 一律丟 `ProcessCancelled`。
  - `was_terminated(proc) -> bool`：這個行程是否被追蹤器終止（供呼叫端分辨取消與一般失敗）。在 `release` 之後仍要能查詢。
- `kill_process_tree(proc)`：
  - `proc.poll()` 已有值就直接返回。
  - Windows：`subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)`。
  - 非 Windows，或 taskkill 回傳非 0、丟例外、逾時：退回 `proc.kill()`（忽略 `OSError`）。
  - 最後 `proc.wait(timeout=2)`，忽略逾時。行程已結束一律視為成功；本函式不丟例外。
- 模組層級單例 `tracker = ProcessTracker()`。**其他模組一律在呼叫當下用 `process_tracker.tracker` 取用**（`from . import process_tracker`），不可 `from ... import tracker`，測試才能替換。

### `core/ytdlp_wrapper.py`

- `search_youtube`（group `"parse"`）與 `extract_info`（group `"info"`）：把 `subprocess.run` 改成 `tracker.spawn(...)` 加 `proc.communicate(timeout=timeout)`，`finally` 中 `release`。保留原本的 `stdout/stderr=PIPE`、`text=True`、`encoding="utf-8"`、`errors="replace"`、`creationflags`、`env`。
  - 逾時：先 `kill_process_tree(proc)`，再 `proc.communicate()` 收尾（避免管線卡住），其後沿用現有的逾時處理與訊息。
  - `ProcessCancelled` 或 `was_terminated(proc)`：記一行 info，`_set_last_error("已取消")`，回傳原本失敗時的型別（`[]` 或 `None`）。這個分支要放在一般 `except Exception` 之前。
  - 回傳值、日誌格式、診斷欄位的既有行為不變。
- `download(...)` 新增最後一個參數 `cancel_event: Optional[threading.Event] = None`，用 group `"download"` 啟動，`finally` 中 `release`。
  - 被取消（`ProcessCancelled`、`was_terminated(proc)` 或 `cancel_event.is_set()`）時：**不呼叫** `progress_callback`（不送 completed、failed、error），`_set_last_error("")`，回傳非 0 的整數。
  - stdout 讀取迴圈中，若已取消就不要再呼叫 `progress_callback`。
  - 其他行為不變。
- `extract_info_flat`、`is_playlist`、`get_playlist_info` 不需改簽章。

### `core/download_manager.py`

- 每個進行中的下載有一個 `threading.Event`（例如 `self._cancel_events[download_id]`），啟動 worker 前建立，傳給 `ytdlp_wrapper.download(..., cancel_event=event)`。
- `active_downloads`、`_cancel_events` 的讀寫都在 `queue_lock` 內；**持鎖時不可呼叫任何會再取 `queue_lock` 的方法、任何回呼、`tracker` 的方法、或存檔**。
- `_process_queue()`：在鎖內挑出要啟動的項目、設定狀態、建立 thread 與 event 並登記；**鎖外**才 `thread.start()` 與送通知。`tracker.shutting_down` 或本管理器正在退出時直接返回。並發上限的現有行為不變。
- `_cancel_download(download_id)`：鎖內找出項目與 event、把狀態設為 CANCELLED（只有 PENDING 或 DOWNLOADING 的項目才改）、`stage="cancelled"`；鎖外呼叫 `tracker.cancel(event)`，再送通知。保留這個方法名稱。
- `stop_all_downloads()`（關閉視窗與更新退出共用，`main_window.py` 已呼叫它，不需修改）依序：
  1. 設定退出旗標（之後不再啟動新下載）。
  2. 鎖內把所有進行中項目標為 CANCELLED 並設定其 event；PENDING 項目**保持 PENDING**（下次啟動續傳，維持現行行為）。
  3. 呼叫 `tracker.shutdown()`（同時終止下載、解析、取資訊的行程）。
  4. 存檔一次。
  - 必須在 3 秒內返回。**不要** `join` worker 執行緒（worker 可能正在等主執行緒處理 Tk 呼叫）。
- 退出中不送任何 UI 回呼：`_notify_progress_change` 與 `_notify_queue_change` 在退出旗標設定後直接返回。
- `_download_worker`：
  - 每次嘗試瀏覽器策略**之前**與 `ytdlp_wrapper.download` 返回或丟例外**之後**，都檢查 event；已取消就跳出，**不改** status／stage／error 欄位（即使 `exit_code == 0` 也維持 CANCELLED），不換瀏覽器重試，不呼叫 `error_handler`、`notification_manager`，不記 FAILED 或 COMPLETED 事件。
  - 清理（移出 `active_downloads` 與 `_cancel_events`）放在 `finally`，任何例外都要執行。
  - 退出中：清理後直接返回，不寫歷史、不存檔、不呼叫 `_process_queue()`。
  - 單筆取消（非退出）：清理後照常存檔、送通知、呼叫 `_process_queue()` 讓下一筆開始。
- `_on_subprocess_progress`：項目狀態是 CANCELLED 時直接返回。
- `_get_video_info`：`tracker.shutting_down` 時停止嘗試下一個瀏覽器。
- `save_queue()`：用一把專屬的 `threading.Lock` 讓存檔序列化（取鎖順序固定為「存檔鎖 → queue_lock」，快照要在存檔鎖內取得）；`_write_json_with_timeout` 改成寫到同目錄的暫存檔（檔名含唯一值）再用 `os.replace` 換掉目標檔，失敗時刪除暫存檔。檔案格式不變。
- 維持現行行為：載入佇列時丟棄 CANCELLED、把 DOWNLOADING 改回 PENDING；建構時自動開始下載（M6 才改）。

### `gui/components/music_search_view.py`

- `_search_worker` 與下載加入流程中的背景執行緒：若 `process_tracker.tracker.shutting_down`，直接返回，不呼叫 `self.after(...)`。不改其他介面行為。

### `tests/conftest.py`

新增 autouse fixture：每個測試用 `monkeypatch.setattr(process_tracker, "tracker", ProcessTracker())` 換上新的追蹤器，測試結束後呼叫它的 `shutdown()`（清掉殘留的測試行程）。名稱用 `process_tracker_instance`，回傳該追蹤器。既有 fixture 不動。

## 實作要點

1. 你不能執行程式。逐一核對 import、函式簽章、鎖的取得順序；改完後在回覆中列出每一個「持有 `queue_lock`」的程式區塊，確認裡面沒有再取鎖或回呼。
2. 測試需要真實子行程時，用 `sys.executable -c "..."`；**不要**依賴 yt-dlp、FFmpeg 或網路。離線防護不封鎖 `subprocess`。
3. 行程樹測試：父腳本啟動一個長睡的子 Python，把子行程 PID 寫進 `tmp_path` 的檔案後長睡。等該檔案出現（有逾時上限的輪詢）再取消。確認行程是否存活要用不會誤殺的方式：Windows 上用 `ctypes` 的 `OpenProcess` 加 `GetExitCodeProcess`（`STILL_ACTIVE = 259`）寫一個小工具函式；**不要用 `os.kill(pid, 0)`**（在 Windows 會終止行程）。
4. 每個會等待的測試都要有逾時上限（`thread.join(timeout=...)` 後斷言 `not thread.is_alive()`），任何缺陷都應讓測試失敗而不是卡住整個測試程序。會卡死的呼叫一律放在 daemon 執行緒中。所有測試啟動的行程都要在 `finally` 結束。
5. 建構 `DownloadManager` 前，conftest 的 `app_root` 已隔離資料目錄。測試要在建構**之後、加入下載之前**替換 `ytdlp_wrapper.download`（離線防護預設會讓它丟例外）。`add_download` 傳 `video_title` 以免觸發取資訊。若歷史紀錄或通知模組需要隔離，用 `monkeypatch` 處理。
6. 要測真實的 `ytdlp_wrapper.download` 與 `search_youtube` 時，用 `original_wrapper_functions` fixture 取得原始函式，並替換追蹤器實例的 `spawn`：包一層把 `cmd` 換成 `[sys.executable, "-c", 腳本]` 後呼叫原本的 `spawn`。
7. 修改的檔案結尾不得有多餘空白行；不要重排無關程式碼，不要改換行格式。

## 不要做

- 不要修改清單以外的檔案（含 `main_window.py`、`update_checker.py`、`binary_manager.py`、知識庫、README）。
- 更新腳本（`update_checker.py` 啟動的 PowerShell）**絕不可**納入追蹤器，否則更新時會被自己終止。
- 不要新增 `remove_download`、`retry_download`、批次、新的 UI 按鈕或多格式（後面里程碑）。
- 不要改 `max_concurrent_downloads`、自動續傳、錯誤翻譯的現有行為。
- 不要新增第三方相依。

## 驗收條件

- [ ] 有進行中下載時，`stop_all_downloads()` 在 3 秒內返回（回歸死結）。
- [ ] 返回後，假子行程與其子行程都已結束；worker 結束後項目仍是 CANCELLED；佇列檔是合法 JSON。
- [ ] 退出開始後不再啟動任何新行程；原本的 PENDING 項目不會被啟動且仍是 PENDING。
- [ ] 取消後即使錯誤字串含重試關鍵字，也不換瀏覽器重試；即使退出碼為 0 也不改成 COMPLETED。
- [ ] 單筆取消後，下一個 PENDING 項目會開始。
- [ ] 進度回呼執行時 `queue_lock` 沒有被持有。
- [ ] `search_youtube`／`extract_info` 逾時或被取消時，行程樹被結束。
- [ ] 既有測試全部通過。

## 必要測試

| 測試檔 | 案例 | 對應驗收條件 |
| :-- | :-- | :-- |
| `tests/test_process_tracker.py` | 父子行程樹被結束；`shutdown` 後 `spawn` 丟 `ProcessCancelled` 且 `Popen` 沒被呼叫；event 已設定時同樣不啟動；`cancel` 只結束該 event 的行程；`terminate_group` 只結束該群組；taskkill 失敗（monkeypatch）時退回 `proc.kill()`；已結束的行程不丟例外；`shutdown` 可重複呼叫；真實 `search_youtube` 逾時（`timeout=1`）後行程樹結束且回傳 `[]` | 2、3、7 |
| `tests/test_download_cancel.py` | 死結回歸（3 秒）；真實 `ytdlp_wrapper.download` 取消後不送失敗回呼且行程樹結束；停止後狀態與佇列檔；PENDING 不啟動；403 錯誤字串不重試（假 download 呼叫次數為 1）；退出碼 0 仍為 CANCELLED；單筆取消後下一筆開始；回呼時鎖未持有；退出中不呼叫 UI 回呼；並發存檔後 JSON 合法且沒有殘留暫存檔 | 1–6 |

## 先前里程碑的教訓

1. 持有 `queue_lock` 時不可呼叫會再取鎖的方法或任何回呼。
2. 測試不得寫入 repo 內的 `data/`、`logs/`；建構 `DownloadManager` 前要隔離，否則可能開始真實下載。
3. 否定斷言要同時斷言前提成立（例如斷言「行程已結束」之前，先斷言它確實啟動過且當時存活），否則可能空過。
4. 保存函式參考供 `is` 比對時用 `types.SimpleNamespace`，不要用類別屬性。
5. 新增檔案後確認沒有被 `.gitignore` 忽略。
6. 修改的檔案結尾不得有空白行，局部編輯刪不掉時整檔覆寫。
