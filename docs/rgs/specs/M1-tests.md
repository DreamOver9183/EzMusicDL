# M1：測試安全網

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-1 |
| 相依 | 無 |
| 分支 | `chore/m1-tests` |

## 目標

為 repo 建立第一套 pytest 測試：預設只跑離線測試、完全不碰使用者資料與 repo 內的 `data/`、`logs/`，並為錯誤翻譯、日誌隱私、`UpdateChecker` 建立基線測試，供後續里程碑驗證沒有退化。本里程碑**不改任何產品程式碼**。

## 可修改的檔案

- `pyproject.toml`：加入 pytest 設定與開發相依
- `.gitignore`：只加一行例外，讓 `tests/` 下的測試檔不被既有的 `test_*` 規則忽略
- `tests/conftest.py`（新檔）：隔離與離線防護 fixture
- `tests/test_isolation.py`（新檔）：驗證離線測試的隔離邊界
- `tests/test_network_marker.py`（新檔）：最小的 `network` 測試
- `tests/test_error_translations.py`（新檔）：錯誤翻譯基線
- `tests/test_logger_privacy.py`（新檔）：日誌與診斷報告隱私
- `tests/test_update_checker.py`（新檔）：更新檢查與下載驗證基線

## 設計

### `pyproject.toml`

新增 `[tool.pytest.ini_options]`：`testpaths = ["tests"]`、`pythonpath = ["src"]`、`markers` 註冊 `network`（說明：需要真實外部工具或外網）、`addopts = '-m "not network"'`。命令列的 `-m network` 會覆蓋 `addopts`。在 `[project.optional-dependencies]` 的 `dev` 加 `"pytest>=7.0"`。版本號與其他欄位不動。

### `tests/conftest.py`

**A. 路徑隔離（autouse，離線與 network 測試都套用）**，以 `tmp_path / "app_root"` 為假的 app root：

1. `ytdlp_gui.utils.paths.get_app_root()` 在非 frozen 時回傳 `Path(__file__).resolve().parents[3]`。很多模組用 `from ... import` 綁定了路徑函式，逐一替換函式容易漏掉。請改用 `monkeypatch.setattr(paths, "__file__", str(fake_root / "src" / "ytdlp_gui" / "utils" / "paths.py"))`，`get_data_dir`、`get_logs_dir`、`get_bin_dir`、`get_app_root`（含別名匯入）就會一起指到假目錄。
2. `get_default_downloads_dir` 在 Windows 會回傳使用者真正的「下載」資料夾。它被多個模組用 `from ... import` 綁定，必須在 `ytdlp_gui.utils.paths` **以及每一個匯入了這個名字的模組**各自替換（請搜尋 `src/` 找出全部，至少有 `core/settings_manager.py` 與 `utils/logger.py`；`core/binary_manager.py` 也要檢查）。替換成回傳 `tmp_path / "downloads"`（要建立目錄）。
3. `CookieManager` 會檢查 `Path.cwd() / "cookies.txt"`：`monkeypatch.chdir` 到暫存目錄。
4. 用 `monkeypatch.delenv(..., raising=False)` 清掉 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 與小寫版本。
5. fixture 回傳假 app root 的 `Path`，名稱用 `app_root`。

**B. 離線防護（autouse，只在測試沒有 `network` marker 時套用**，用 `request.node.get_closest_marker("network")` 判斷）：

- 把 `ytdlp_gui.core.ytdlp_wrapper` 的 `extract_info`、`download`、`search_youtube` 換成丟出自訂例外 `OfflineViolation`（`RuntimeError` 子類別）的函式。
- 把 `socket.socket.connect`、`socket.socket.connect_ex`、`socket.create_connection`、`socket.getaddrinfo` 換成丟出 `OfflineViolation`。
- 不要全面封鎖 `subprocess`（之後的里程碑要在測試中真實執行 PowerShell）。
- 在模組層級先保存三個原始函式的參考，供 network 測試比對。測試檔需要取用這些參考與例外類別時，用 fixture 提供（例如 `original_wrapper_functions`、`offline_violation`），**不要** `import conftest` 或 `from tests...`。

**C.** fixture `real_bin_dir`：回傳 repo 根目錄下的 `bin`（由 `Path(__file__).resolve().parent.parent / "bin"` 算出）。這個資料夾不進版控，在乾淨的 checkout 可能不存在。

### `tests/test_isolation.py`（離線）

- `paths.get_app_root()` 等於 `app_root`；`get_data_dir()`、`get_logs_dir()` 位於其下。
- `SettingsManager()` 的 `settings_dir` 位於 `app_root` 之下，預設 `output_directory` 位於 `tmp_path` 之下。
- 呼叫三個 wrapper 函式與 `socket.create_connection` 都丟出 `OfflineViolation`。

### `tests/test_network_marker.py`

只有**一個**測試函式，加 `@pytest.mark.network`。它**不可以**連網，也不可以要求 `bin/` 內任何檔案存在（本里程碑只驗邊界）。斷言：三個 wrapper 函式仍是原始函式（沒有套離線防護）；app root 仍是假目錄；`real_bin_dir.name == "bin"` 且不在假 app root 之下。

## 實作要點

1. 你不能執行程式。寫每一個斷言前，先讀被測模組的實際實作，斷言**目前的行為**。如果你認為目前行為是錯的，不要改產品程式碼，也不要寫一定會失敗的測試；在回覆中說明。
2. `tests/test_error_translations.py`（被測：`utils/error_translations.py`）：
   - 用 `pytest.mark.parametrize` 提供**至少 38 組**「原始錯誤字串 → 預期 `code`」。規則依序比對，第一個符合者勝出，寫每一組前都要確認前面沒有別的規則先命中。
   - 必含：含 Unicode `’` 的 `Sign in to confirm you’re not a bot`（`YT_BOT_CHECK`）與 ASCII `'` 版本、年齡限制、Chrome cookie 資料庫被鎖、DPAPI、私人影片。盡量涵蓋每一個規則代碼。
   - 優先序：年齡限制字串不可被判成 `YT_LOGIN_REQUIRED`；機器人驗證字串不可被判成 `YT_LOGIN_REQUIRED`。
   - 空字串與 `None` → `EMPTY_ERROR`；不認得的字串 → `UNKNOWN_ERROR`；過長字串的 `raw_excerpt` 依 `_clean_excerpt` 截斷。
   - `is_local_cookie_error` 對本機 cookie 類為真、對 `YT_BOT_CHECK` 為假。
   - 每一條規則的 `title`、`detail`、`suggestion` 都非空，且不含「協助與修復」。
3. `tests/test_logger_privacy.py`（被測：`utils/logger.py`）：
   - 假的 cookie 內容、Proxy 帳號與密碼一律在執行時用 `uuid.uuid4().hex` 組出來，**不要寫成字面值**，Proxy URL 也在執行時組合，主機用 `proxy.example.invalid`。
   - 在 `app_root / "data" / "cookies.txt"` 寫入假內容，設定 `HTTP_PROXY`。
   - `get_diagnostic_report()` 的結果與 `log_startup_environment()` 的日誌（用 `caplog`，對 `ytdlp_gui.startup` 設 INFO）都不得含 cookie 內容、Proxy 帳號、密碼；Proxy 主機名稱應出現。
   - `_sanitize_proxy_url` 的帳密、無帳密、非標準格式案例。
   - 在假的 logs 目錄寫入 `latest.log`、`error.log`、`downloads.log`、`updater.log` 各自的標記行，確認診斷報告都包含；`latest.log` 超過尾段行數時，最早的行不出現（行數以實作為準）。
   - 不要呼叫 `get_log_manager()` 或 `init_logging()`（會改全域 root logger）。
4. `tests/test_update_checker.py`（被測：`core/update_checker.py`）：用 `monkeypatch` 替換 `ytdlp_gui.core.update_checker.requests.get`，回傳自製的假回應物件；不得連網。涵蓋：
   - `_parse_version`（含前綴 `v`、空字串、無效字串）。
   - `_find_asset`：zip 優先於 exe、略過 source zip、略過 `yt-dlp.exe` 之類、沒有可用資產。
   - `_find_checksum_asset`（同名 `.sha256` 優先、退回 `checksums.txt`、沒有）與 `_parse_expected_sha256`。
   - `_safe_extract_zip` 拒絕含 `../` 路徑的 zip（zip 在 `tmp_path` 內產生），目標目錄外沒有產生檔案。
   - `check()`：有新版（用很大的版本號，例如 `v9999.1.1`，含 checksum）、已是最新、有新版但沒有資產、404、403 且無快取、304 且有快取（快取內的 `current_version` 與 `repo` 要符合實作的條件）、`requests.ConnectionError`。
   - `download_update()` 在 SHA-256 不符時回傳 `ok` 為假，且暫存目錄被刪除（用 `monkeypatch` 讓 `tempfile.mkdtemp` 建在 `tmp_path` 下以便檢查）。
   - `apply_update()`：無效的 `prepared` 回傳 False；非 frozen 模式回傳 False。
   - **不要**測 `build_windows_updater_script` 或實際套用更新；那段已知有缺陷，M3 會重寫。

## 不要做

- 不要修改上面清單以外的檔案，包括任何 `src/` 下的產品程式碼、知識庫、README、建置設定、CI。
- 不要重新排版無關內容。
- 不要新增其他第三方相依（只用標準函式庫與 pytest）。
- 不要讀取或建立 repo 內的 `data/`、`logs/`、`cookies.txt`。

## 驗收條件

- [ ] `python -m pytest tests -q` 全部通過，輸出顯示 `1 deselected`，不連網。
- [ ] `python -m pytest tests -q -m network` 顯示 `1 passed`，不需要外網與 `bin/` 內的檔案。
- [ ] 錯誤翻譯參數化案例至少 38 組。
- [ ] 執行後 `git status` 沒有測試產物，repo 根目錄沒有被寫入 `data/`、`logs/`。

## 必要測試

| 測試檔 | 案例 | 對應驗收條件 |
| :-- | :-- | :-- |
| `tests/test_isolation.py` | 路徑隔離、離線防護 | 1、4 |
| `tests/test_network_marker.py` | marker 與 fixture 邊界 | 1、2 |
| `tests/test_error_translations.py` | 見實作要點 2 | 3 |
| `tests/test_logger_privacy.py` | 見實作要點 3 | 1 |
| `tests/test_update_checker.py` | 見實作要點 4 | 1 |

## 先前里程碑的教訓

1. 測試不得寫入 repo 內的 `data/`、`logs/`；建構 `DownloadManager` 前要隔離，否則可能開始真實下載（本里程碑不需要建構它）。
2. 假 cookie 與假帳密在執行時組出，避免 secret scan 命中。
