# EzMusicDL 介面風格改版計畫書：YT 暗黑工作台（Refined YT Studio Dark）

| 項目 | 內容 |
| :--- | :--- |
| **計畫書版本號** | `v1.3.0` |
| **適用專案版本基準** | `EasyMusicDL v2026.11.21` |
| **建立日期** | `2026-11-28` |
| **最後更新日期** | `2026-11-28` |
| **目前狀態** | `已核准，尚未開始實作里程碑` |

## Context

Windows 免安裝 YouTube 音樂下載器（Python 3.12、CustomTkinter、PyInstaller `--onedir`）。原計畫 v1.2.0 要改成深色工作台介面、支援多格式與播放清單，並先修正自我更新器。本版依程式碼與 F0 沙盒紀錄修正原計畫的錯誤與缺漏。本版已於 2026-11-28 經使用者核准，即本文件的 v1.3.0。原版保存在 `docs/archive/YT_STUDIO_DARK_REDESIGN_PLAN_v1.2.0.md`（含版面示意圖、目標檔案架構與原測試矩陣 T1–T5；與本版衝突時以本版為準）。

## 目標與產品決策

1. **單一深色設計**（使用者本次決定）：移除淺色模式、主題切換 UI 與 `theme_mode` 設定；舊 `settings.json` 的 `theme_mode` 忽略；固定 `ctk.set_appearance_mode("dark")`；啟動檢查視窗與 DWM 標題列一併改深色。系統原生 messagebox／filedialog 不處理。
2. 字級 `12–18px`（任何文字不小於 12px），點擊高度至少 38px，主要動作至少 44px。同步改寫 `.interface-design/system.md`（現行契約以高齡使用者為對象、主按鈕 46–50px；本次依使用者訪談決定放寬）。
3. 輸入：單曲網址、正式播放清單、關鍵字、批次多網址。含 `v=` 與 `list=RD…` 的混音電台預設當單曲，另附「改為展開播放清單」。
4. 格式：`MP3 320k`（預設）、`M4A`、`OPUS`，不提供 FLAC。**M4A／OPUS 保留原始音軌**（使用者本次決定），標籤不宣稱 160k；抓不到對應音軌才轉檔。「嵌入專輯封面」開關記住上次選擇。「我的音樂」掃描 `.mp3`／`.m4a`／`.opus`。
5. 四視圖：網址解析（左欄預覽與格式、右欄即時佇列）、下載佇列、我的音樂（點曲目才浮現底部列：系統播放器開啟、開啟所在資料夾、關閉；不內建播放器）、系統設定（內嵌頁，取代彈窗）。
6. 繁體中文文案，只保留必要技術名詞；零 Emoji。
7. 預設視窗 1200×760，最小 1020×660；底部 Cookie 燈號如實顯示。

## 執行方式：使用 `rgs-pr` skill（使用者指定）

**核准後以 `/rgs-pr` 執行本計畫。** Claude 規劃與審查；Gemini（Antigravity CLI）依規格在隔離 worktree 實作；sub-agent 跑驗證、更新文件、開 PR；每個 PR 經獨立的合併閘門審查後，**由使用者在 GitHub 手動合併**（不執行 `gh pr merge`）。流程細節以 `rgs-pr` 的 `SKILL.md` 與 `rgs-core/references/workflow.md`（閘門 G0–G8）為準。

1. **基準（在 `init` 之前確認）**：worktree 從 `origin/main` 建立，而目前 17 個修改檔不在上面。先經使用者**明確同意**（會推到公開 repo），開一個 `chore:` 基準 PR 由使用者合併。提交前看過完整 diff 並做機密掃描；不含 `.agents/`；`.interface-design/` 納入（F1 要改）；`docs/` 寫回本計畫（v1.3.0）後納入。使用者不同意或未合併前，不開任何里程碑。
2. **`init`**：`doctor.py --init --flow pr`；profile（quick＝`python -I -m compileall -q src main.py build.py`；verify＝quick 加 `python -m pytest tests -q`，M1 合併前只有 quick）、知識庫、權限規則請使用者確認；profile 與知識庫進版控前先問。
3. **`plan`**：以本計畫為來源寫 `docs/rgs/requirements.md`（R 編號與可驗證驗收條件）與 `docs/rgs/design.md`（已查證事實、決策、風險、里程碑、追溯矩陣、狀態總覽）。**G0：使用者另行核准這兩份後才能 `run`**；核准本計畫不等於通過 G0。
4. **里程碑（一個里程碑一個 PR）**：

| 里程碑 | 本計畫階段 | 分支 |
| :-- | :-- | :-- |
| M1 | P0 測試安全網 | `chore/m1-tests` |
| M2 | F0.1 更新器、死結與取消 | `fix/m2-updater` |
| M3 | F1 視覺地基 | `feat/m3-theme` |
| M4 | F2 後端 | `feat/m4-backend` |
| M5 | F3 主框架 | `feat/m5-shell` |
| M6 | F4＋F5 工作台與即時佇列 | `feat/m6-workbench` |
| M7 | F6 佇列頁 | `feat/m7-queue` |
| M8 | F7 我的音樂 | `feat/m8-library` |
| M9 | F8 設定頁與清理 | `feat/m9-settings` |

   `plan` 若認為 M4 太大、Gemini 無法在不執行程式下寫對，可再拆分，但每個 PR 合併後都要能啟動使用。
5. **每個 `run M<n>`**：規格列出完整「可修改的檔案」（含測試、`tools/ui_smoke.py`、要刪除的舊檔）與本計畫對應的設計規格、驗收條件；依序經 G1–G7。Gemini 不能執行建置或測試，pytest、`ui_smoke`、`network` 整合、沙盒打包、端對端由 Claude／finisher 執行，手動項目請使用者做。該里程碑的離線與沙盒驗收通過才把 PR 交給使用者合併；未驗證項目寫進 PR 內文。M2 的端對端驗收用任務 worktree 的複本打包，**通過後才請使用者合併**。
6. **相依與合併**：依表列順序；前一個 PR 未合併時用 `--stack-on`（PR 內文註明合併順序），同一時間只讓一個 Gemini 執行。使用者回報合併後執行 `merged <PR#>`（需要時先 `retarget` 子任務，再清理、沉澱知識、提交 ledger）。
7. **不變的限制**：刪除或修改公開 Release 須另外取得同意；正式版發佈不在本計畫範圍（之後走 `/rgs-pr release`）。

## 現況事實（已查證）

- 基準是**未提交的工作區**：HEAD `7577138` 之上有 17 個修改檔（+2462/-240）；HEAD 的 `update_checker.py` 只有 34 行 stub。repo 沒有任何測試檔。已安裝 pytest。
- F0 的 `updater.log`：下載、SHA-256、替換成功，並已刪除備份；重啟時回報 `Access is denied`，進入 catch 回滾，**把剛裝好的新版刪掉**。沙盒 live 目錄現在沒有 `EasyMusicDL.exe` 與 `_internal`（`bin/`、`data/`、`logs/`、`cookies.txt` 仍在）。原文件寫「檔案替換通過」並不代表更新成功。
- Python 在 17:39:03 回報已啟動 updater，`updater.log` 首行是 17:40:36。推測自動啟動沒有執行、之後是手動執行（未證實）。「`DETACHED_PROCESS` 造成」是假設；Windows 文件指出它與 `CREATE_NO_WINDOW` 併用時後者被忽略。
- 進度日誌 612 行。
- 測試 Release `v2026.11.28` 目前**公開、非 prerelease、是 Latest**，由未提交程式碼打包，內含會刪掉安裝的舊更新器。遠端 tag 指向 `7577138`，tag 觸發的 CI 在 release job 失敗（舊 workflow），未覆蓋資產。`release.ps1` 用當天日期當 tag。
- **既有死結**：`stop_all_downloads()` 持有非重入的 `queue_lock`，再經 `_cancel_download()` → `get_download_item()` 取同一把鎖。下載中關閉視窗、或在 GUI 按更新（`_exit_for_update`）會卡死；updater 等父行程 30 秒後放棄。`--self-update-test` 不經過這條路。
- 取消只改狀態，不終止 yt-dlp／FFmpeg；worker 之後仍可能改回完成或失敗。
- `add_download()` 強制 `audio_format="mp3"`；沒有標題時同步抓資訊（最多 4 次、各 30 秒）。
- `_DEST_RE` 之後只收 `.mp3`；來源已是目標格式時可能沒有 `[ExtractAudio] Destination`。
- `max_concurrent_downloads` 只在建構時讀取；`clear_completed_downloads_simple()` 連失敗項一起刪且不存檔；超過 24 小時（依 `created_at`）的失敗項載入時被清掉；`load_queue()` 在建構時就開始下載，早於 UI 註冊回呼；進度回呼只能逐 id 註冊。
- 純播放清單網址解析時沒用 `--flat-playlist`（30 秒逾時）；下載用的 `--no-playlist` 擋不住純 `list=` 網址整份下載。
- updater 腳本回滾缺陷：項目在 `Copy-Item` 成功後才記入 `copiedItems`，複製到一半失敗時殘缺目的資料夾留著，`Move-Item` 會把備份搬**進**它裡面；回滾錯誤被忽略仍記「Rollback completed」；腳本開頭直接刪除既有 `.update_backup`。
- `build.py` 的 `clean_build()` 會刪整個 `dist/`，包括必須保留的 `dist/EasyMusicDL.rar`。
- 五個舊元件不在 `hiddenimports`；`format_detector.py` 只被 `download_options.py` 匯入。
- `icons.py` 把顏色當 (light, dark) tuple 解包；現有色票鍵名（`accent`、`danger`…）與新 token 不同。
- 對比：白字配 `#FF4545` 為 3.39:1；`#6B7280` 在 `#18181C` 上 3.66、在 `#222228` 上 3.27，都低於 4.5:1。

## 設計規格

### 色彩（單一深色）
- 底色：`bg_canvas #0F0F11`、`bg_chrome #141417`、`bg_surface #18181C`、`bg_elevated #222228`、`bg_input #121215`、`bg_control_hover #2C2C34`、`thumb_bg #222228`。
- 邊框：`border_hairline #2A2A32`、`border_input #363642`。
- 文字：`text_primary #F4F4F6`、`text_secondary #9CA3AF`、`text_muted #969CA8`（為達對比調整）、`accent_text #FFFFFF`、`danger_text #FF8A8A`（所有錯誤**文字**用它）。
- 品牌：實心主按鈕底 `brand_fill #E03131`（白字 4.51:1），懸浮 `#C92A2A`；`brand_accent #FF4545` 只用於 3px 指示條、圖示、細框；`brand_subtle #2B1719`。
- 狀態：downloading `#38BDF8`、converting `#F59E0B`、success `#10B981`、danger `#EF4444`（僅燈號、圖示、框線，不當文字色）、neutral `#6B7280`（僅燈號）、`danger_bg #331A1A`、`danger_border #6E2B2A`。danger 與品牌紅幾乎同色，所以錯誤一律同時有圖示與文字。
- 合法文字配對（對比測試範圍，其他組合不得使用）：primary／secondary／muted／danger_text／downloading／converting／success × canvas、chrome、surface、elevated、input、control_hover；primary、danger_text × danger_bg；primary × brand_subtle；accent_text × brand_fill 與其懸浮色。

圓角：卡片 12、按鈕／輸入框 8、膠囊 14；1px 邊框。字體 `Microsoft JhengHei UI`；`mono_font()` 優先 `Cascadia Mono`、退回 `Consolas`，用於片長、位元率、百分比、速率、大小、錯誤碼、版本，固定寬度靠右。圖示沿用 Segoe Fluent Icons，補佇列、批次、封面、清除、外部開啟、篩選與語意色。

### 版面
側欄 168px（含佇列／音樂徽章）、頂部解析列約 68px（Enter、Ctrl+A/V、解析、批次匯入）、更新橫幅（可關閉）、底部狀態列（yt-dlp、FFmpeg、Cookie、版本）。解析頁兩欄權重 38:62，最小寬 300／460px（不用原圖的 36%/50%、400/580px）。1200×760 邏輯像素下，預覽、格式、送出按鈕與至少 3 張任務卡免捲動；候選清單與佇列內部捲動；空間不足時左欄可捲動。起始與最小視窗尺寸不得超過螢幕工作區（150% 縮放的 1080p 高度不足 760）。剪貼簿偵測到新 YouTube 連結時，在輸入列內浮現「一鍵貼上並解析」；沿用現行行為（只在 `<FocusIn>` 讀取、讀取例外忽略、記住已提示與已略過的網址），另加超過 2048 字元直接略過。

- 縮圖（預覽、候選、佇列卡）共用一個非同步載入器：固定 3 個 worker、8 秒逾時、記憶體快取；離線、逾時、非圖片時靜默保留 `thumb_bg` 佔位；寫回前確認元件仍存在且其目前要的網址未變。
- 左欄：16:9 縮圖＋片長、標題（最多兩行）、頻道、候選清單（單擊預覽、多選後按鈕變「加入已選 X 首至佇列」）、格式膠囊、封面開關、主按鈕；解析失敗用 `analyze_error()` 顯示標題、原因、建議、代碼、前往設定複製診斷。
- 即時佇列卡：64×36 縮圖、曲名、格式、百分比、速率、4px 進度條、狀態（等待／下載／轉檔／寫入封面）；等待中與進行中的卡片有「取消」（呼叫 `remove_download()`：終止並移出佇列）；完成可開啟資料夾，失敗顯示短標題與重試；顯示「進行中 X · 共 Y」與完整佇列連結。
- 佇列頁：全部／進行中／已完成／失敗（附數量）；重試全部失敗、清除已完成、清除失敗；失敗列預設展開代碼與建議，可單筆重試／移除；等待中與進行中列可單筆取消（同即時佇列卡）；完成列有路徑、大小、開啟資料夾。
- 我的音樂：依修改時間排序、搜尋（對全部檔案）、格式徽章；最多畫 100 列並註明；徽章顯示總數。
- 設定五卡：下載偏好（同時下載 1/2/3、預設格式、封面）、應用程式更新、引擎狀態與修復、存檔位置、Cookie 與診斷。

### 後端
- `classify_youtube_input()`：先去頭尾空白，空字串不送出；缺協定的 YouTube 網域（`youtu.be/…`、`youtube.com/…`、`www.`／`m.`／`music.`）補 `https://`。「影片 ID」指 `v=`、`youtu.be/<id>`、`shorts/<id>`、`live/<id>`、`embed/<id>`。依序判定：非網址 → `keyword`；有影片 ID 且 `list=RD…` → `radio_url`；其他帶 `list=` → `playlist_url`（含 `watch?v=…&list=PL…`）；其餘網址（含 music 網域單曲、非播放清單網址，以及非 YouTube 網址；單筆輸入沿用現行行為交給 yt-dlp，不支援時顯示 `UNSUPPORTED_URL`）→ `single_url`。
- `extract_playlist_entries(url, max_entries=50)`：`--flat-playlist --dump-single-json --playlist-end 51`；超過 50 提示「僅顯示前 50 首」；略過私人／已刪除條目。
- 批次匯入：只收 YouTube 網域；一次最多 50 筆有效網址，超過時提示且多的不入列。空行忽略；重複者計入「重複」；非網址、非 YouTube、超出上限分別提示。去重、顯示無效數。凡含影片 ID 的網址（包括帶 `list=` 者）一律當單曲入列（下載帶 `--no-playlist`）；只有**沒有**影片 ID 的播放清單網址不入列，提示單獨貼上展開。
- 格式參數（`-f`／其他）：
  - mp3_320：`bestaudio/best`；`--extract-audio --audio-format mp3 --audio-quality 320K`
  - m4a：`bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/best`；`--extract-audio --audio-format m4a --audio-quality 0`
  - opus：`bestaudio[acodec=opus]/bestaudio/best`；`--extract-audio --audio-format opus`
  - 開封面：`--embed-thumbnail --convert-thumbnails jpg`；三種格式都要實測（含 OPUS）。執行期若失敗發生在封面抓取／轉換／嵌入，同一策略不帶封面參數重試一次，成功則標為完成，把「封面未嵌入」寫入 `status_note`，顯示在佇列卡與佇列頁完成列。下載中間檔一律寫到任務專屬暫存夾（下載夾內以任務 id 命名的隱藏子資料夾，`--paths temp:<夾>`；`-o` 須改成相對檔名並用 `--paths home:<下載夾>`，否則 `--paths` 無效）。清理規則：成功或 `remove_download()` → 刪整個暫存夾；封面重試前、下載失敗、停止但保留項目 → 刪除 `.part`／`.ytdl` 以外的檔案，保留它們供續傳。任何讓項目離開佇列的路徑（`remove_download()`、清除失敗、清除已完成、`load_queue()` 丟棄已取消或逾 24 小時的失敗項）都走同一個移除函式，依該項目的 `output_path` 與 id 刪整個暫存夾；清除失敗因此也要有存檔、通知的後端方法。不掃描刪除「無主」暫存夾（另一份免安裝程式可能共用同一下載夾），也不依檔名猜測刪除下載夾裡的其他檔案。若 F2 實測 OPUS 根本無法嵌入封面，停下來問使用者（停用 OPUS 封面開關或另找工具），不自行決定。
- 最終路徑：每次嘗試用獨立暫存檔 `--print-to-file after_move:filepath <tmp>` 以 UTF-8 讀回並去除換行，`finally` 刪除暫存檔；`_DEST_RE` 擴充三種副檔名作備援。進度階段分 `converting` 與 `embedding_cover`。
- `DownloadItem` 加 `uploader`、`thumbnail`、`duration_str`、`audio_format`、`audio_quality_label`、`embed_thumbnail`、`status_note`（預設空字串），全部有預設值；舊佇列項依 `format_info` 維持原行為（MP3 品質 0，標籤「MP3」）。
- `add_download()` 接受格式與封面，不再強制 mp3。`add_batch_downloads()` 不阻塞 UI：背景固定 2 個 worker 取得資訊，取得前以網址當標題；寫回前確認項目仍存在且未取消；取資訊失敗只保留網址標題，成敗由下載本身決定（下載成功後以檔名補標題）。
- 取消（在 F0.1 實作）：`ytdlp_wrapper.download()` 交出行程 handle；取消時終止整個行程樹（`taskkill /T /F /PID`）；已取消的 worker 不得覆寫狀態、不得換瀏覽器重試。取消旗標檢查與 handle 註冊在同一把鎖內完成（已取消則新行程立即終止）。`taskkill` 帶 `CREATE_NO_WINDOW` 與逾時，失敗或逾時退回 `proc.kill()`，行程已結束視為成功。解析、搜尋、清單展開、取資訊的 yt-dlp 行程也納入同一追蹤，在換查詢（只終止舊解析）、關閉視窗、更新退出時終止。`.part` 的保留與清理依下方「任務暫存夾」規則。
- `retry_download()` 只接受失敗項，清除錯誤與進度並重設 `created_at`；`remove_download()` 對進行中項目先取消；新增只刪完成項的方法（存檔、通知）；新增 `set_max_concurrent()`（立即生效，調低不中斷進行中項目）。
- 新增全域監聽介面；所有回呼在 `queue_lock` 之外呼叫；UI 經 `root.after` 轉主執行緒，原地更新元件、每秒最多重繪 4 次；UI 註冊後主動讀一次佇列。
- Cookie 燈號：有 `cookies.txt` 顯示「已載入」否則「匿名免登入」；最終失敗碼屬於 `YT_BOT_CHECK`、`YT_LOGIN_REQUIRED`、`YT_AGE_RESTRICTED`、`COOKIE_INVALID` 時顯示「需登入或更新」（點擊到設定），下一次下載成功或 `cookies.txt` 變更後復原。本機瀏覽器 `COOKIE_*` 讀取錯誤不蓋掉原始錯誤。燈號狀態由後端保存，UI 初始化時直接查詢；視窗 `<FocusIn>` 與進入設定頁時比對 `cookies.txt` 的 mtime／大小；檔案空白或讀不到顯示「需登入或更新」。佇列自動續傳改由明確的 `start()` 觸發，UI 註冊監聽後才呼叫。
- 設定新增 `default_audio_format="mp3_320"`、`embed_thumbnail=True`。

## 實作步驟與驗收（依序；每階段結束要能啟動使用、`python -m pytest tests -q` 通過，經 `rgs-pr` 審查開 PR，由使用者合併）

### P0 基準與安全網
先依「執行方式」完成基準 PR、`init`、`plan` 與 G0，再執行 `run M1`。記錄 `dist/EasyMusicDL.rar` 的 SHA-256。建 `tests/`：以 fixture 把 app root／data／logs 指到暫存目錄並 mock yt-dlp，禁止寫入 repo、禁止自動下載。先為錯誤翻譯（至少 38 個錯誤字串案例）、Logger 隱私、UpdateChecker 寫基線測試。**打包一律在 `%TEMP%` 的原始碼複本內執行，絕不在 repo 根目錄跑 `build.py`。**
在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 註冊 `network` marker 並設 `addopts = '-m "not network"'`，讓預設指令只跑離線測試（命令列 `-m network` 會覆蓋）。yt-dlp mock 與禁止下載的 fixture 只套用在非 `network` 測試；`network` 測試用真實 `bin/yt-dlp.exe`、`bin/ffmpeg.exe`、`bin/ffprobe.exe` 與外網，仍使用暫存 app root（以參數指向 repo 的 `bin/`）與暫存下載夾。
P0 同時放一個最小的 `network` marker 測試（只驗 marker 與 fixture 邊界）。
驗收：基準提交已在 `origin/main`；pytest 通過且輸出顯示該 network 測試被 deselected；`python -m pytest tests -q -m network` 顯示該最小測試 1 passed（不需外網）；`git status` 不出現測試產物。

### F0.1 更新器、死結與取消修正
1. 修死結：鎖內只複製 id 清單，鎖外取消；依「後端」節實作行程樹終止（避免更新或關閉後留下 yt-dlp／FFmpeg 孤兒行程）。回歸測試：有進行中項目時呼叫 `stop_all_downloads()`，在執行緒中 3 秒內返回，假子行程樹已結束，worker 不覆寫狀態。
2. 啟動：`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`，`stdin/stdout/stderr=DEVNULL`、`close_fds=True`。握手：腳本一開始寫 `updater.started` 標記；`apply_update()` 最多等 10 秒，沒看到就終止子行程、回傳 False，主程式不退出。`updater.started` 一律寫在 `%TEMP%` 的更新暫存目錄（與腳本同處），不依賴程式目錄可寫；`updater.log` 寫不進程式目錄的 `logs/` 時改寫到 `%TEMP%`，任何日誌寫入失敗都不中斷腳本。啟動前先刪同路徑舊標記；`apply_update()` 防重入（進行中再呼叫回傳 False，UI 停用更新按鈕）。保留現有的 `utf-8-sig` 寫檔與 `-NoProfile -ExecutionPolicy Bypass`。
3. 腳本分三段：
   - A 備份替換。先做不改動安裝內容的前置檢查（寫日誌與握手標記除外），依序：(1) 等父行程結束，逾時就記錄並提示「請關閉程式後重試」後退出；(2) 已有非空 `.update_backup` 而主程式或 `_internal` 任一缺失時，中止並提示手動復原；(3) 確認程式目錄可寫。全部通過後才清除舊 `.update_backup` 並開始備份替換。檔案被鎖（例如開著第二個程式視窗）搬移失敗時回滾並提示關閉所有視窗；複製**前**先記錄項目；回滾時先刪目的地並確認消失，再搬回備份；任何一步失敗就保留備份、記「ROLLBACK INCOMPLETE」、提示路徑。回滾僅限 A、B 段，進入 C 段後絕不回滾。
   - B 確認：目的 exe 的 SHA-256 與 payload 相同；不同則依 A 回滾。
   - C 重啟：獨立 try/catch，`Start-Process -PassThru`，最多 5 次、遞增等待。行程存活 10 秒才刪備份與暫存；否則**保留新版與備份**，提示「已更新完成，請手動開啟」。分開記錄「啟動被拒」（例外，重試）與「啟動後 10 秒內結束」（記 ExitCode，不再重啟，提示附 `.update_backup` 路徑與手動復原步驟）。重啟邏輯寫成獨立 PS 函式，測試可覆寫以模擬暫時性 `Access is denied`。
   - 所有 Popup 15 秒自動關閉。
4. 退出順序（關閉視窗與 `_exit_for_update` 共用）：先設關閉旗標（之後不再啟動任何新行程）、丟棄未開始的背景工作，再終止進行中行程。之後加入的批次取資訊與縮圖 worker 一律用 daemon 執行緒加自有佇列並提供 `shutdown()`（不用退出時會等待排隊工作的 `ThreadPoolExecutor`），納入同一退出順序；F2 與 F4＋F5 各補測：50 筆待取資訊／延遲縮圖排隊時呼叫退出，3 秒內返回且不再開新行程。
5. `run_self_update_test()` 進度日誌每 10% 或階段變更才寫。
驗收（自動）：在含中文與單引號的暫存路徑真實執行產生的 PS 腳本，涵蓋：成功；A 段複製中途失敗後舊版逐檔雜湊一致；啟動前兩次失敗後成功；五次全失敗時新版與備份都在；`bin/`、`data/`、`logs/`、`cookies.txt` 不變；唯讀目錄被預先攔截（整個程式目錄含 `logs/` 都唯讀，仍能寫出標記並提示）；節流後下載進度日誌不超過 20 行；非空備份且主程式／`_internal` 缺失時中止；回滾失敗時記「ROLLBACK INCOMPLETE」並保留備份；父行程逾時與鎖檔；新版提早結束；繁中路徑與日誌不亂碼。另以 Python 單元測試驗：握手逾時（子行程終止、回傳 False）、舊標記殘留、重複呼叫。
驗收（端對端）：用修正後的程式碼打包**新的**「舊版」`v2026.11.21` 到新沙盒（更新腳本由舊版產生，所以原備份 exe 含舊缺陷、不能用來驗收；原備份保留不動），沿用現有公開 Release 資產、不重新上傳。執行 `EasyMusicDL.exe --self-update-test`，全程不介入：`updater.log` 在啟動後 10 秒內出現、替換完成、保留目錄不變、新版自動進主畫面（其 log 有「進入主畫面 mainloop」）；再用新版執行同一旗標，log 顯示 `status=up_to_date`（兩種情況 exit code 都是 0，必須看 log）。注意：現有資產內的新版仍含舊更新器，只能驗第一跳。GUI 路徑另用一份**獨立**的修正版 `v2026.11.21` 沙盒複本（不能沿用已被升級的目錄）手動驗一次：下載中按更新，確認視窗關閉、無殘留 yt-dlp／FFmpeg、更新完成。
沙盒前置：打包產物不含引擎與使用者資料，先複製 repo `bin/` 引擎進沙盒，並在 `bin/`、`data/`、`logs/` 各放一個標記檔、另放假內容 `cookies.txt`，記錄這四個檔的 SHA-256；更新後四者雜湊不變、四個引擎檔仍存在（新版啟動檢查可能自行更新引擎，所以引擎本身不比雜湊）。GUI 路徑的「無殘留」：更新後、啟動新下載前，`Get-Process yt-dlp,ffmpeg -ErrorAction SilentlyContinue` 篩 `Path` 位於沙盒者為零；「更新完成」：重啟後 log 的啟動摘要版本為 `2026.11.28` 且有「進入主畫面 mainloop」。
複測後：**經使用者明確同意**才執行 `gh release delete v2026.11.28 --cleanup-tag`；若不同意刪除，改標 prerelease。任何正式 Release 前必須先移除同名測試 tag。

### F1 視覺地基
`theme.py` 改單一深色並加 `mono_font()`；同一提交內調整 `icons.py`（含 `thumb_bg` 解包）；舊鍵名暫留為指向新色的別名（F8 移除）；移除主題切換與 `theme_mode`；啟動視窗、DWM、`HelpDialog` 改深色；改寫設計契約；加兩個新設定。
驗收：測試所有文字／底色組合對比 ≥4.5:1、所有 `COLORS[...]` 鍵存在、舊 settings 含 `theme_mode="light"` 仍啟動為深色、新設定可存讀；原有畫面可啟動。

### F2 後端
依「後端」節實作。
驗收：單元測試涵蓋四分類（含 `youtu.be?list=`、shorts、music、`watch?v=&list=PL`）、批次過濾、三格式×封面的完整參數、舊 `download_queue.json` 載入、重試／移除／清除／並發調整、取消後無殘留子行程且狀態不被覆寫、不可用瀏覽器被略過、本機 Cookie 失敗保留原始 `YT_BOT_CHECK`、診斷報告不含 `cookies.txt` 內容與 Proxy 帳密。另涵蓋：清單超過 50 首提示與略過私人／已刪除條目；封面失敗後不帶封面重試並註明、非封面錯誤不走此分支；`--print-to-file` 暫存檔在成功／失敗／取消後都刪除、非 ASCII 路徑讀回、讀不到時退回 `_DEST_RE`；批次背景最多 2 個 worker、移除／取消後不寫回、取資訊失敗仍可下載；Cookie 燈號狀態轉移（無檔、空白、不可讀、mtime 變更、認證失敗、成功復原）；監聽回呼時 `queue_lock` 未被持有；`start()` 前不自動下載、呼叫後才續傳；任務暫存夾依清理規則（成功、移除、清除失敗、載入時丟棄已取消與逾期失敗項都整夾刪除；封面重試前、失敗、`stop_all_downloads()` 停止但保留項目只留 `.part`／`.ytdl`；其他 id 的暫存夾不受影響）、`status_note` 有值且舊佇列缺此欄位可載入、下載夾內既有的同名圖片不被刪。
整合（`-m network`，不使用瀏覽器 Cookie）：`4rgSzQwe5DQ` 解析成功、`07FYdnEawAQ` 回 `YT_AGE_RESTRICTED`、一個超過 50 首的公開清單在 30 秒內回傳 50 筆並標示被截斷；實際下載 3 格式×封面開關共 6 個檔，回傳路徑存在，`bin/ffprobe.exe -of json -show_streams -show_format` 的 codec 依序為 mp3、aac、opus，開封面者有 `disposition.attached_pic=1` 的串流或（OPUS）`METADATA_BLOCK_PICTURE` 標籤，關封面者兩者皆無。M4A／OPUS「未重新編碼」的判定：先用相同 `-f`、不帶 `--extract-audio` 與封面參數，另下載一份參考音軌到獨立資料夾；參考檔與開／關封面的產出各跑 `bin/ffmpeg.exe -i <檔> -map 0:a -c copy -f md5 -`，雜湊相同。樣本影片候選 `jNQXAC9IVRw`，使用前以 `yt-dlp -F` 確認同時有 m4a 與 opus 音軌；清單網址於執行時挑選。所用樣本與結果記錄在 `tests/network_samples.json`。外部影片失效要記為「未驗證」並換樣本，不得算通過。

### F3 主框架
`sidebar_nav.py`、`status_bar.py`、改 `main_window.py`。過渡期：解析頁掛舊 `MusicSearchView`、我的音樂掛舊 view、設定頁放開啟 `HelpDialog` 的按鈕、佇列頁佔位。含更新橫幅與視窗尺寸限制。
同時建立 `tools/ui_smoke.py` 骨架（F4–F8 各階段補該頁檢查）。
驗收：`python tools/ui_smoke.py` exit 0；更新橫幅（假更新資訊）顯示後可關閉；燈號點擊切到設定頁。舊功能手動清單：關鍵字搜尋出現結果、按下載後完成並出現在我的音樂、播放與顯示位置可用、從設定頁開啟 `HelpDialog` 可複製診斷與更換資料夾。

### F4＋F5 解析工作台左側與即時佇列（`parser_workbench_view.py`，同一次交付）
左右兩欄都完成後才移除 `MusicSearchView` 掛載（中途提交保留舊畫面），確保下載一直看得到進度；佇列卡拆成可重用元件供 F6。
驗收（自動，用假的解析器與下載管理器）：單曲→預覽 1 筆且按鈕「加入下載佇列」；混音→單曲預覽並有「改為展開播放清單」，點了呼叫清單展開；清單與關鍵字→候選列表，勾 X 首後按鈕為「加入已選 X 首至佇列」，單擊換預覽；批次→只有有效網址入列且各計數正確；解析失敗卡含 `analyze_error()` 的標題、原因、建議、代碼與設定捷徑。解析假函式延遲 3 秒期間，每 100ms 的 `after` 計時器間隔不超過 500ms；先後發兩次查詢、舊的後回來時畫面維持新結果；進度更新前後任務卡 widget id 相同、1 秒灌 50 次事件時重繪不超過 4 次；百分比與速率用 `mono_font()`、固定寬度靠右。進行中卡片按「取消」呼叫 `remove_download()` 一次且卡片消失（F6 對佇列頁做同樣檢查）。帶 `status_note="封面未嵌入"` 的完成項在即時佇列卡顯示該文字、空字串時不顯示（F6 對佇列頁完成列做同樣檢查）。無效與延遲的縮圖網址保留佔位且不拋例外；快速切換預覽、移除卡片後，晚到的縮圖不覆蓋新預覽、不寫入已銷毀元件。手動：完成項「開啟資料夾」在檔案總管選取該檔。

### F6 佇列頁（`queue_view.py`）／F7 我的音樂（改 `my_music_view.py`）
驗收：篩選計數、重試、清除與首屏佇列同步；混合三種副檔名的暫存資料夾掃描、排序、搜尋、超過 100 檔提示、底部列顯示／關閉、檔案已不存在時不當掉；`.opus` 無關聯播放器（`os.startfile` 的 `OSError`）時顯示提示並提供開啟資料夾；存檔資料夾不存在或無權限時顯示空狀態與原因；掃描在背景執行緒；大寫副檔名可掃到。

### F8 設定頁與清理（`settings_view.py`）
對照 `HelpDialog` 清單逐項搬移：手動檢查更新、下載中更新確認、進度、原始碼模式開發佈頁、三階段引擎修復、換／重設資料夾並同步清單與狀態列、複製診斷（含 Cookie 摘要）、開紀錄資料夾。另加兩個防護：有下載或解析進行中時，引擎修復先詢問並全部停止（避免 `bin/` 檔案鎖定）；換資料夾先用 `is_dir_writable()` 檢查，失敗則保留原設定並提示，已入列項目維持原輸出路徑。兩者都要有測試。刪除 `help_dialog`、`music_search_view`、`download_options`、`download_queue`、`progress_display`、`simple_url_input`、`video_preview`、`format_detector` 與舊色鍵別名；更新 `build.py` `hiddenimports`；`clean_build()` 改為只刪 `build/`、`dist/EasyMusicDL/` 與本版本的 zip／sha256，保留 `dist/` 其他檔案（暫存目錄測試驗證；修好並通過測試前仍只在複本打包）。更新過時文案：通知、錯誤建議中的「設定與修復」、僅 MP3 的描述、`build.py` 產生的使用說明、README、`pyproject.toml` 描述。
驗收：清單逐項通過，其中偵測到新版、下載中更新確認、更新進度、下載失敗、原始碼模式用假的 `UpdateChecker`（回傳固定資料、`apply_update` 只記錄呼叫）驗證，不依賴任何遠端 Release；舊模組名搜尋零引用；`python -m compileall -q src main.py build.py` 與全模組匯入通過；在沙盒複本跑 `python build.py --zip`，zip 不含 `bin/` 引擎、`data/`、`logs/`、`cookies.txt`，打包版能啟動並開啟四頁。

## 最終驗證（proof）
- `python -m pytest tests -q`（離線），另跑 `python -m pytest tests -q -m network`（回報 skip 與原因）。
- `python -I -m compileall -q src main.py build.py`
- `python tools/ui_smoke.py`（F3 起建立；需已登入的 Windows 互動桌面；暫存 app root、略過 bootstrap、假資料；失敗時列出元件並非零退出）。1200×760 與 1020×660 逐頁檢查各頁具名主要元件（解析：解析列、預覽、格式膠囊、主按鈕、佇列卡；佇列：篩選列、清單、批次按鈕；我的音樂：搜尋、清單、底部列；設定：五張卡；全域：側欄、狀態列）已顯示、邊界在視窗內（捲動區內項目以捲動區為界）、文字需求寬度不超過元件寬度。另檢查：走訪所有可見元件，字型大小介於 12–18px、按鈕／輸入框／膠囊高度 ≥38、主要動作按鈕 ≥44（皆為邏輯像素）；1200×760 放 3 筆假佇列資料時，預覽、格式、主按鈕與 3 張卡不需捲動即完整可見。
- 視窗尺寸夾限寫成純函式，單元測試給工作區 1280×672 與 1920×1040，確認初始與最小尺寸不超過工作區。
- `python -m pytest tests/test_source_rules.py -q`（F8 啟用全部規則）：掃 `src/**/*.py`、`main.py`、`build.py`、`README.md`、`pyproject.toml`、`tools/`：(a) 無 U+1F000–U+1FAFF、U+2600–U+27BF 字元；(b) 無「設定與修復」「協助與修復」「純 MP3」「下載 MP3」「已存成 MP3」「轉換 MP3」，並人工複查 README、使用說明、`pyproject.toml` 描述是否仍只講 MP3；(c) 對 `src`、`main.py`、`build.py` 檢查無舊模組的匯入路徑或 hiddenimport（比對 `components.<舊名>`、相對匯入與 `format_detector`；不比對單字 `download_queue`，因它也是屬性與佇列檔名）；(d) 無 `theme_mode` 與主題切換元件。
- F8 全模組匯入：`tests/test_imports.py` 以 `pkgutil.walk_packages` 匯入 `ytdlp_gui` 下全部模組。
- 手動（附截圖）：Windows 縮放 100／125／150% 無截斷與重疊；啟動檢查視窗、主視窗與 DWM 標題列皆為深色、沒有主題切換；剪貼簿浮現、底部列、燈號跳轉；繁體中文文案。
- `Get-FileHash dist\EasyMusicDL.rar` 與 P0 相同；`git status` 沒有非預期檔案。

## 範圍外
正式版本發佈與版本號變更、程式內音訊播放、FLAC、`--no-check-certificate` 的安全性檢討（既有行為，另案）、更新中斷電的復原。

## 風險
- Defender 擋住時間可能超過 5 次重試：保留新版與備份並提示手動開啟。
- `DETACHED_PROCESS` 假設可能錯：握手避免主程式在 updater 沒啟動時退出；E2E 失敗就回頭查根因。
- CustomTkinter 大量任務卡效能與 DPI 排版：原地更新、節流、限制列數。
- yt-dlp 行為（`--print-to-file`、OPUS 封面）依版本而異：以整合測試確認；本機 repo `bin/` 版本為 2026.11.23。
- 公開測試 Release 在刪除前可能被舊客戶端更新到含缺陷版本：F0.1 排最前面，複測後立即處理。

## 假設清單
1. 「單一色彩設計」指只保留 YT 暗黑工作台深色。
2. 為達對比而調整主按鈕底色與 `text_muted`，不違背使用者的視覺方向。
3. 沒有使用者透過正式 Release 拿到含完整更新器的 `v2026.11.21`（GitHub 目前只列出測試 Release）。
4. `bin/yt-dlp.exe` 支援嵌入 OPUS 封面（待 F2 實測）。
5. 提交、刪除 Release 等動作在執行當下再取得同意。

## 審查摘要

以下的 v1–v8 是審查期間的草稿版次，不是本文件的版本號。

**v6 到 v8 是第 3 輪後的修訂，未經審查。** 最後一次受審的版本是 v5。「執行方式」一節依使用者要求撰寫（先指定 `rgs-main`，後改為 `rgs-pr`），分支、基準提交與合併做法隨之調整。

- 審查模型（替補清單：gemini-4-neon-high → gemini-4-hydrogen-xhigh → gemini-4-argon-high → gemini-3.8-flash-high → gpt-oss-120b-medium → claude-opus-5-5-high）：
  - logic：gemini-4-neon-high（agy 回報：Gemini 4 Neon (High)）
  - gaps：gemini-4-neon-high（agy 回報：Gemini 4 Neon (High)）
  - verifiability：gemini-4-neon-high（agy 回報：Gemini 4 Neon (High)）
  - 改用替補模型的原因：無
  - 非跨模型審查的角度：無
- 輪數：3 / 3
- 最終 verdict（針對 v5）：logic REVISE、gaps REVISE、verifiability REVISE
- 收斂方式：達到輪數上限
- 採納的 findings：36 條全部採納（logic 10、gaps 18、verifiability 8），其中 gaps 的 F5、F11、F17 只採納一部分。較重要者：
  - 更新器：握手與防重入、各種失敗分支、唯讀目錄時標記與日誌寫到 `%TEMP%`、前置檢查順序。
  - 取消與退出：行程樹終止提前到 F0.1、取消競態、解析行程追蹤、背景佇列的退出順序、介面上的取消按鈕。
  - 下載：批次併發上限、封面失敗降級、任務暫存夾與清理路徑、網址分類邊界、縮圖載入器。
  - 驗收：對比色票修正、`network` 測試與離線測試分開、主觀驗收改為可量測條件、proof 指令補齊。
- 駁回的 findings 與理由：沒有整條駁回。部分駁回如下：
  - gaps F5：現有程式已用 `utf-8-sig` 與 `-ExecutionPolicy Bypass`，只加保留要求與亂碼測試。
  - gaps F11：剪貼簿例外處理、`<FocusIn>` 觸發與去重現有程式已做到，只加長度上限。
  - gaps F17：不採納「掃描刪除無主暫存夾」的選用建議，因為另一份免安裝程式可能共用同一下載夾。
- 第 3 輪 6 條（已寫入 v6，未複審）：logic F10 與 gaps F17（清除路徑漏刪暫存夾）、gaps F16（唯讀目錄下的標記與日誌）、gaps F18（背景工作的退出順序）、verifiability F1（P0 要實際跑 network 測試）、verifiability F2（`status_note` 的介面驗收）。
- 流程偏差：第 1 輪在每個角度回覆後就修訂，所以三個角度分別審到 v1、v2、v3；第 2、3 輪各自以同一版本（v4、v5）審完三個角度才修訂。第 2 輪 gaps 第一次送出時，因我的處置欄位值寫錯回傳 `usage_error`（未送到模型），修正後重送。
- 剩餘風險與未覆蓋範圍：
  - 審查者只看到計畫本文，沒有讀程式碼或執行指令。「現況事實」由起草者讀程式碼與 F0 紀錄查得，沒有經過獨立覆核；死結與回滾缺陷是靜態閱讀結論，尚未以測試重現。
  - `yt-dlp` 的 OPUS 封面、`--print-to-file`、`--paths`，測試影片 `jNQXAC9IVRw` 的音軌，以及 CustomTkinter 在各 DPI 的排版，都要到實作時才能確認。
  - 第 2、3 輪新增的機制（任務暫存夾、縮圖載入器、退出順序）讓範圍比原計畫大。三輪都只用到清單中的第一個模型，所以只有一家模型的觀點。
- 原始紀錄：`%TEMP%\rgs-facet\fe163214-dbea-4511-b78b-7fbb1d8baf81\`
- 註：`APPROVED` 只表示審查者未發現問題，不代表計畫正確。本次最後一輪沒有任何角度可視為已核准目前版本。

# 附錄：跨模型計畫審查紀錄

## 逐輪審查結果
所有輪次、角度的模型皆為 gemini-4-neon-high（agy 回報：Gemini 4 Neon (High)），沒有改用替補。

| 輪次 | 受審版本 | logic | gaps | verifiability |
| :-- | :-- | :-- | :-- | :-- |
| 1 | v1／v2／v3 | REVISE（6） | REVISE（12） | REVISE（6） |
| 2 | v4 | REVISE（3） | REVISE（3） | APPROVED（0，之後因計畫修訂而作廢） |
| 3 | v5 | REVISE（1） | REVISE（3） | REVISE（2） |

### 各輪 coverage 與 limitations（摘錄）
- coverage：三個角度每輪都涵蓋計畫本文全部章節；第 2、3 輪並逐條覆核上一輪處置，審查者回報上一輪項目皆已解決。
- limitations（各輪一致）：只讀計畫本文，未讀 repo 程式碼、未執行指令，未實測 `bin/yt-dlp.exe` 與 YouTube 樣本；完整內容見原始紀錄各輪輸出。

## 逐輪處置表

| 輪 | 角度 | ID | 嚴重度 | 摘要 | 處置 | 理由／對應修改 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | logic | F1 | medium | 色票與對比驗收矛盾 | 採納 | 重算屬實；改 `text_muted`、增 `danger_text`、定義配對矩陣 |
| 1 | logic | F2 | medium | F8 時已無 Release 可驗更新 | 採納 | 改用假 `UpdateChecker` |
| 1 | logic | F3 | medium | 行程終止太晚 | 採納 | 提前到 F0.1；下載執行緒是 daemon，實際風險為孤兒子行程 |
| 1 | logic | F4 | low | 回滾範圍字面矛盾 | 採納 | 限 A、B 段 |
| 1 | logic | F5 | low | F4 後無佇列介面 | 採納 | F4＋F5 合併 |
| 1 | logic | F6 | low | 分類與批次過濾落差 | 採納 | 以影片 ID 定義 |
| 1 | gaps | F1 | high | 握手殘留與重入 | 採納 | 刪舊標記、防重入、測試 |
| 1 | gaps | F2 | high | 更新器異常復原 | 採納 | 補中止條件、提示、ExitCode、測試 |
| 1 | gaps | F3 | high | 取消競態與解析行程 | 採納 | 原子註冊、備援終止、統一追蹤 |
| 1 | gaps | F4 | high | 批次併發 | 採納 | 上限 50、2 worker、寫回檢查 |
| 1 | gaps | F5 | medium | PS1 編碼與執行原則 | 部分採納 | 現有程式已做到，加保留要求與測試 |
| 1 | gaps | F6 | medium | 網址分類邊界 | 採納 | trim、補協定、live／embed |
| 1 | gaps | F7 | medium | 封面失敗與路徑編碼 | 採納 | 降級重試、UTF-8；OPUS 不支援時問使用者 |
| 1 | gaps | F8 | medium | 我的音樂邊界 | 採納 | 補例外與背景掃描 |
| 1 | gaps | F9 | medium | 修復與換資料夾衝突 | 採納 | 先停任務、寫入預檢 |
| 1 | gaps | F10 | medium | Cookie 燈號與啟動競態 | 採納 | 後端狀態、`start()` |
| 1 | gaps | F11 | medium | 剪貼簿防護 | 部分採納 | 沿用既有行為，加 2048 字元上限 |
| 1 | gaps | F12 | low | `clean_build` 仍刪 `dist/` | 採納 | F8 修正並測試 |
| 1 | verifiability | F1 | high | 量化目標無檢查 | 採納 | `ui_smoke`、source rules |
| 1 | verifiability | F2 | high | 驗收主觀 | 採納 | 改可量測條件 |
| 1 | verifiability | F3 | high | 離線與聯網指令衝突 | 採納 | marker 與 addopts |
| 1 | verifiability | F4 | medium | F2 資料與比對不足 | 採納 | 樣本、ffprobe、單元測試清單 |
| 1 | verifiability | F5 | medium | proof 缺指令 | 採納 | 補指令與歸屬階段 |
| 1 | verifiability | F6 | low | E2E 沙盒前置 | 採納 | 標記檔雜湊、行程與版本判定 |
| 2 | logic | F7 | medium | `-k` 不保留原始 M4A | 採納 | 另下載參考音軌 |
| 2 | logic | F8 | low | P0 無法看到 deselected | 採納 | P0 加最小測試 |
| 2 | logic | F9 | low | 清備份早於等父行程 | 採納 | 前置檢查排序 |
| 2 | gaps | F13 | medium | 缺取消入口 | 採納 | 卡片與佇列頁加取消 |
| 2 | gaps | F14 | medium | 縮圖載入規則 | 採納 | 共用載入器 |
| 2 | gaps | F15 | low | 封面殘留檔與註記欄位 | 採納 | 任務暫存夾、`status_note`；起草者另修正清理規則的自相矛盾 |
| 3 | logic | F10 | medium | 清除路徑漏刪暫存夾 | 採納 | 統一移除函式（未複審） |
| 3 | gaps | F16 | medium | 唯讀目錄下標記與日誌 | 採納 | 改寫 `%TEMP%`（未複審） |
| 3 | gaps | F17 | medium | 同 logic F10 | 部分採納 | 不掃描刪無主暫存夾（未複審） |
| 3 | gaps | F18 | medium | 背景工作退出順序 | 採納 | 關閉旗標、daemon worker、測試（未複審） |
| 3 | verifiability | F1 | medium | P0 未實跑 network 測試 | 採納 | 加 `-m network` 驗收（未複審） |
| 3 | verifiability | F2 | low | `status_note` 無介面驗收 | 採納 | F4＋F5、F6 加驗收（未複審） |

## 版本變更紀錄（Changelog）

| 計畫書版本 | 日期 | 變更說明 |
| :--- | :--- | :--- |
| `v1.0.0` | `2026-11-28` | 初版定稿：產品與設計決策、雙主題色票、工作台架構、三格式與封面嵌入、嵌入式系統設定。 |
| `v1.1.0` | `2026-11-28` | 拆分 `F0`–`F8` 與測試矩陣 `T1`–`T5`，啟動 `F0` 實測。 |
| `v1.2.0` | `2026-11-28` | 記錄 `F0` 實測成果與 3 項更新器缺陷，新增 `F0.1`、`T3-4`、`T3-5`。 |
| `v1.3.0` | `2026-11-28` | 依程式碼與 `F0` 紀錄修正並經跨模型審查（3 輪）；改為單一深色設計、M4A／OPUS 保留原始音軌、以 `rgs-pr` 分 M1–M9 執行。 |
