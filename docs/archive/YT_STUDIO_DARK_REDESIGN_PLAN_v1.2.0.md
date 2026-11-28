# EzMusicDL 介面風格改版計畫書：YT 暗黑工作台（Refined YT Studio Dark）

| 項目 | 內容 |
| :--- | :--- |
| **計畫書版本號** | `v1.2.0` |
| **適用專案版本基準** | `EasyMusicDL v2026.11.21` |
| **建立日期** | `2026-11-28` |
| **最後更新日期** | `2026-11-28` |
| **目前狀態** | `待審閱（尚未實作 UI 改版；F0 實測發現 3 項更新器缺陷，已納入 F0.1 修正計畫）` |

> **聲明**：本文件為設計與實作規劃書，在取得使用者明確同意前，**不會實作任何 YT 暗黑工作台介面改版程式碼**。`F0` 沙盒端對端實測已完成初輪驗證，發現的 3 項自我更新器實務缺陷已記錄於 **`F0.1`** 與 **`T3-4`/`T3-5`**，待確認後修正並複測。

---

## 一、訪談確認之產品與設計決策總覽

| 決策維度 | 確認方案 |
| :--- | :--- |
| **1. 主題與密度定位** | **深色優先**（預設 YT 暗黑工作台，系統設定中保留淺色模式切換開關）；平衡清晰字體（`13–18px`）與舒適操作高度（`38–44px`），兼顧高資訊密度與易讀性。 |
| **2. 全局輸入與解析範圍** | 同時支援 **單曲網址**、**正式播放清單（`list=PL...` 等）**、**關鍵字搜尋** 與 **批次匯入多筆網址**。含 `v=` 與 `list=RD...` 的混音電台連結預設當單曲解析（另提供「改為展開播放清單」選用動作）。 |
| **3. 音訊格式與封面嵌入** | 提供 **3 種原生態音訊格式**：`MP3 320k`、`M4A`、`OPUS 160k`（不提供有損轉無損之 FLAC）；新增「**嵌入專輯封面**（`--embed-thumbnail`）」開關並記憶上次選擇；「我的音樂」同步掃描 `.mp3`、`.m4a`、`.opus`。 |
| **4. 四大視圖分工** | 左側窄版導覽列整合 **網址解析**（首屏雙欄 Bento：左欄預覽＋格式、右欄即時精簡佇列）、**下載佇列**（全寬詳細清單＋篩選／重試／錯誤詳情展開／一鍵清除）、**我的音樂**、**系統設定**（嵌入式完整頁面，取代原彈窗）。 |
| **5. 「我的音樂」按需控制列** | **簡化版按需展開資訊列**：僅在「我的音樂」點擊曲目時於底部動態浮現，提供曲目資訊、「以系統預設播放器開啟」與「開啟所在資料夾」，不在程式內建音訊解碼引擎。 |
| **6. 文案語系風格** | **純繁體中文主文案**，僅保留必要技術專有名詞（`MP3 320k`、`M4A`、`OPUS 160k`、`yt-dlp`、`FFmpeg`、`Cookie`）。 |
| **7. 視窗規格與 Cookie 狀態** | 預設視窗 **`1200×760`**（最小 **`1020×660`**）；底部狀態列 Cookie 燈號實事求是顯示「`Cookie: 匿名免登入`／`Cookie: cookies.txt 已載入`／`Cookie: 需登入或更新`（觸發認證異常時亮警示橘紅，點擊跳轉系統設定）」。 |

---

## 二、視覺系統設計規範（Design Tokens）

實作時將同步更新 `src/ytdlp_gui/gui/theme.py` 與 `.interface-design/system.md`。

### 2.1 色彩系統（Dark 預設 / Light 備選）

| Token | YT 暗黑工作台（預設 Dark） | 亮色對照（Light） | 用途 |
| :--- | :--- | :--- | :--- |
| `bg_canvas` | `#0F0F11` | `#F4F4F6` | 視窗底層畫布 & Windows 11 DWM 標題列 |
| `bg_chrome` | `#141417` | `#EBEBEF` | 左側導覽列、頂部解析條底板、底部狀態列 |
| `bg_surface` | `#18181C` | `#FFFFFF` | 主要 Bento 功能卡片 |
| `bg_elevated` | `#222228` | `#F0F0F4` | 任務列、次要按鈕、懸浮互動態 |
| `bg_input` | `#121215` | `#FAFAFC` | 網址／搜尋輸入框、批次匯入文字區 |
| `border_hairline` | `#2A2A32` | `#DCDCE4` | `1px` 極細卡片與區域邊框（捨棄厚重陰影） |
| `border_input` | `#363642` | `#C6C6D2` | 輸入框與次要按鈕邊框 |
| `text_primary` | `#F4F4F6` | `#18181C` | 標題、曲名、主文案 |
| `text_secondary` | `#9CA3AF` | `#52525E` | 頻道名、說明文字、次要標籤 |
| `text_muted` | `#6B7280` | `#767686` | 輔助代碼、空狀態提示、分隔字元 |
| `brand_accent` | `#FF4545` | `#E03131` | **克制主強調色**：僅集中於「解析」、「加入下載佇列」與側欄當前頁 `3px` 指示條 |
| `brand_hover` | `#E53939` | `#C92A2A` | 主強調按鈕懸浮態 |
| `brand_subtle` | `#2B1719` | `#FDECEC` | 選中膠囊／側欄啟用底色 |
| `status_downloading` | `#38BDF8` | `#0284C7` | 下載進行中 `4px` 進度條與狀態膠囊（電光青） |
| `status_converting` | `#F59E0B` | `#D97706` | FFmpeg 轉檔／寫入封面中（琥珀黃） |
| `status_success` | `#10B981` | `#059669` | 任務完成、引擎就緒綠燈（翡翠綠） |
| `status_danger` | `#EF4444` | `#DC2626` | 異常狀態、Cookie 失效警示（警示橘紅） |
| `status_neutral` | `#6B7280` | `#71717A` | 等待中、匿名免登入中性燈號 |

### 2.2 圓角、間距與雙軌字體

- **圓角與邊界**：Bento 卡片 `12px`；按鈕／輸入框 `8px`；狀態與格式膠囊 `14px`；統一 `1px` 極細邊框。
- **雙軌字體（Dual-Track Typography）**：
  - **內容資訊（`font()`）**：`Microsoft JhengHei UI`（頁面標題 `18px Bold`、卡片標題 `15–16px Bold`、按鈕與內文 `14px`、輔助資訊 `12–13px`）。
  - **技術數據（`mono_font()`）**：優先偵測 Windows 系統 `Cascadia Mono`，退回 `Consolas`；專門用於片長（`43:47`）、位元率（`320k`）、百分比（`64.2%`）、傳輸速率（`4.8 MB/s`）、檔案大小（`12.4 MB`）、錯誤代碼與版本號，搭配靠右對齊，確保多列佇列即時更新時數字不跳動。
- **圖示系統**：沿用 `src/ytdlp_gui/gui/icons.py` 的 Windows `Segoe Fluent Icons`（2× Pillow 渲染，零 Emoji），補齊工作台所需圖示（佇列、批次匯入、封面圖片、清除、外部開啟、篩選）與語意色變體（`brand`、`cyan`、`amber`、`emerald`、`danger`、`muted`）。

---

## 三、版面架構與首屏空間預算（1200×760 零捲動工作台）

```text
+---------------------------------------------------------------------------------------------------+
| [Sidebar 168px] | [Top Global Parser Bar — Height ~68px, #141417]                                 |
|  #141417        | [貼上 YouTube 單曲／播放清單網址，或輸入歌名搜尋...] [一鍵貼上並解析*] [解析] [批次匯入] |
|                 +---------------------------------------------------------------------------------+
|  EzMusicDL      | [Update Banner（僅偵測到應用程式新版本時浮現，可關閉）]                                |
|                 +----------------------------------------+----------------------------------------+
| | 網址解析       | [Left Bento — ~36% / 400px, #18181C]   | [Right Bento — ~50% / 580px, #18181C]  |
|   下載佇列 (3)   |  +----------------------------------+  |  即時下載佇列             [進行中 1 · 共 3] |
|   我的音樂 (12)  |  |        16:9 圓角影片縮圖           |  |  +------------------------------------+  |
|   系統設定       |  |                         [43:47]  |  |  | [縮圖] 曲名         MP3 320k  64.2%  |  |
|                 |  +----------------------------------+  |  | 頻道 · 4.8 MB/s            [下載中]  |  |
|                 |  影片標題（最多兩行）                    |  |  | ============---------- (4px 青色)  |  |
|                 |  頻道名稱 · 狀態資訊                     |  |  +------------------------------------+  |
|                 |  ------------------------------------  |  | [縮圖] 曲名         OPUS 160k 94.0%  |  |
|                 |  輸出格式：[MP3 320k][M4A][OPUS 160k]   |  |  | 頻道 · 寫入封面    [FFmpeg 轉檔中]  |  |
|                 |  [切換] 嵌入專輯封面                     |  |  | ====================-- (4px 琥珀)  |  |
|                 |  [      加入下載佇列 (#FF4545)      ]   |  |  +------------------------------------+  |
|                 |                                        |  | [縮圖] 曲名         M4A       100%   |  |
|                 |  (若為關鍵字搜尋或正式播放清單，此區      |  |  | 頻道 · 8.2 MB          [開啟資料夾]  |  |
|                 |   下方展開可勾選候選曲目清單)             |  |  +------------------------------------+  |
+-----------------+----------------------------------------+----------------------------------------+
| ● yt-dlp 就緒   ● FFmpeg 就緒   ● Cookie: 匿名免登入（點按設定）                       v2026.11.21 |
+---------------------------------------------------------------------------------------------------+
```

> `*` **零佔位剪貼簿微互動**：視窗取得焦點且剪貼簿偵測到新 YouTube 連結時，於輸入框右側動態浮現「一鍵貼上並解析」膠囊提示鈕，不再佔用整列橫幅高度，確保首屏在零捲動下完整呈現工作區。

### 3.1 四大視圖詳細規格

1. **網址解析（Workbench / Parser — 首屏預設）**
   - **頂部全局解析列**：單行高辨識度輸入框（支援 Enter 解析、Ctrl+A/V、剪貼簿浮現快捷鈕）＋珊瑚紅 `#FF4545` 主按鈕「**解析**」＋次要按鈕「**批次匯入**」（開啟多行網址貼上彈窗，過濾有效網址後一次加入佇列）。
   - **左欄 Bento — 影片預覽與格式面板（寬度權重 38%）**：
     - **16:9 影音預覽卡**：固定 16:9 圓角縮圖（右下角半透明深色標籤顯示等寬片長），下方顯示粗體標題與頻道名稱。
     - **播放清單／搜尋候選區**：輸入關鍵字或貼上正式播放清單（`list=PL...`）時，於左欄下方呈現緊湊可捲動候選曲目（單擊載入上方預覽、勾選多筆後按鈕文字動態變為「加入已選 X 首至佇列」）；混音電台（含 `v=` 與 `list=RD...`）預設當單曲解析，另附小型連結「改為展開播放清單」。
     - **快速格式膠囊與送出**：`MP3 320k`（預設）、`M4A`、`OPUS 160k` 三顆膠囊切換鈕＋「嵌入專輯封面」開關＋全寬珊瑚紅「加入下載佇列」按鈕。
     - **解析失敗卡片**：直接串接 `src/ytdlp_gui/utils/error_translations.py` 的 `analyze_error()`，呈現錯誤標題、原因與建議、錯誤代碼與「前往設定複製診斷紀錄」捷徑。
   - **右欄 Bento — 即時多工下載與轉檔佇列（寬度權重 62%，視覺主角）**：
     - 右上角顯示等寬計數徽章（`進行中 X · 共 Y`）＋「查看完整佇列 →」捷徑。
     - 橫向緊湊任務卡：微型縮圖（`64×36`）、曲名、格式徽章、等寬百分比與速率（`MB/s`）、`4px` 細線進度條，以及右側狀態膠囊（`等待中` / `下載中` / `FFmpeg 轉檔中` / `寫入封面中`）。
     - 任務完成後，右側狀態膠囊直接轉為「**開啟資料夾**」快捷按鈕（`explorer /select,` 定位檔案）；失敗時顯示簡短錯誤標題與「重試」按鈕。

2. **下載佇列（Queue — 全寬詳細管理視圖）**
   - 頂部狀態篩選膠囊：`全部`、`進行中`、`已完成`、`失敗`（附筆數），右側提供「重試全部失敗」、「清除已完成」、「清除失敗」。
   - 全寬任務列：失敗任務預設展開顯示 `error_code`、完整繁中說明與操作建議（含單筆「重試」與「移除」）；完成任務顯示存檔路徑、檔案大小與「開啟資料夾」。

3. **我的音樂（My Music — 多格式本地庫＋按需展開資訊列）**
   - 掃描存檔資料夾內 `.mp3`、`.m4a`、`.opus`（依修改時間新到舊），提供即時搜尋過濾與格式徽章（`MP3` / `M4A` / `OPUS`）。
   - **按需展開控制列（On-Demand Bar）**：預設隱藏；點擊曲目後於底部動態浮現，顯示曲名、格式、檔案大小（等寬）、修改時間，並提供「**以系統預設播放器開啟**」、「**開啟所在資料夾**」與關閉鈕。

4. **系統設定（Settings — 嵌入式完整 Bento 頁面）**
   - 取代原本的彈窗 `src/ytdlp_gui/gui/components/help_dialog.py`，分為 5 張 Bento 卡片：
     1. **外觀與下載偏好**：深色／淺色主題切換（同步 DWM 標題列）、同時下載上限（`1 / 2 / 3`）、預設音訊格式與封面嵌入開關。
     2. **應用程式版本與更新（免安裝版）**：完整串接 `src/ytdlp_gui/core/update_checker.py`（檢查更新、進度條、SHA-256 驗證與安全重啟）。
     3. **下載引擎狀態與修復**：`yt-dlp`、`FFmpeg`、`Deno` 燈號、版本與三階段修復更新。
     4. **音樂存檔位置**：變更資料夾／恢復系統預設 Downloads。
     5. **Cookie 與問題診斷紀錄**：顯示 Cookie 模式（匿名／`cookies.txt` 路徑與大小／本機瀏覽器狀態）、「複製診斷紀錄」與「開啟紀錄資料夾」。

---

## 四、後端與核心模組配套升級

1. **`src/ytdlp_gui/core/ytdlp_wrapper.py`**：
   - 新增 `classify_youtube_input(query)` 區分 `keyword` / `single_url` / `radio_url` / `playlist_url`。
   - 新增 `extract_playlist_entries(url, max_entries=50)`（`--flat-playlist --dump-single-json`，快速載入播放清單曲目供勾選）。
   - 擴充 `download()` 的 `_DEST_RE` 同時偵測 `.mp3` / `.m4a` / `.opus` 最終存檔路徑，並細分 `converting`（`[ExtractAudio]`）與 `embedding_cover`（`[EmbedThumbnail]`）進度階段。
2. **`src/ytdlp_gui/core/download_manager.py`**：
   - `DownloadItem` 新增 `uploader`、`thumbnail`、`duration_str`、`audio_format`、`audio_quality_label`、`embed_thumbnail`（向後相容既有 `download_queue.json`）。
   - `_prepare_ydl_options()` 支援三種格式與封面嵌入：
     - `MP3 320k`：`--extract-audio --audio-format mp3 --audio-quality 320K`
     - `M4A`：`--extract-audio --audio-format m4a --audio-quality 0`
     - `OPUS 160k`：`--extract-audio --audio-format opus --audio-quality 160K`
     - `embed_thumbnail=True`：加入 `--embed-thumbnail`（MP3／M4A 搭配 `--convert-thumbnails jpg` 確保相容性）。
   - 新增 `retry_download(download_id)`、`remove_download(download_id)`、`add_batch_downloads(...)`，並將認證／Cookie 類錯誤狀態即時同步給底部狀態列。
3. **`src/ytdlp_gui/core/settings_manager.py`**：
   - 預設 `theme_mode` 調整為 `"dark"`；新增 `default_audio_format: "mp3_320"` 與 `embed_thumbnail: True`。
4. **`build.py`**：
   - 同步更新 `hiddenimports` 對應新模組，並移除 `src/ytdlp_gui/gui/components/` 內已廢棄的上游舊元件（`download_options.py`、`download_queue.py`、`progress_display.py`、`simple_url_input.py`、`video_preview.py`）。

### 目標介面檔案架構

```text
src/ytdlp_gui/gui/
├── theme.py                        # 更新：YT Studio Dark / Light 雙主題色票、mono_font()、DWM #0F0F11
├── icons.py                        # 擴充：工作台圖示與語意色變體 (brand/cyan/amber/emerald/danger)
├── main_window.py                  # 重構：左側窄導覽列 + 更新橫幅 + 四大視圖 + 底部健康狀態列
└── components/
    ├── sidebar_nav.py              # 新增：左側窄導覽列（168px、3px 珊瑚紅指示條、佇列/音樂徽章）
    ├── status_bar.py               # 新增：底部系統健康狀態列（yt-dlp / FFmpeg / Cookie 燈號 + 版本）
    ├── parser_workbench_view.py    # 新增：頂部全局解析列 + 左欄預覽/格式/候選清單 + 右欄即時佇列 + 批次匯入彈窗
    ├── queue_view.py               # 新增：全寬下載佇列（狀態篩選、單筆重試、展開錯誤詳情、批次清理）
    ├── my_music_view.py            # 翻新：多格式掃描＋搜尋＋底部按需展開簡化控制列
    └── settings_view.py            # 新增：嵌入式系統設定頁（完整取代 HelpDialog 彈窗）
```

---

## 五、小階段目標實作規劃（F0 ~ F8）

| 階段 | 小階段名稱 | 核心目標與交付項目 | 涉及檔案 | 驗收條件（Definition of Done） |
| :--- | :--- | :--- | :--- | :--- |
| **F0** | **前置驗證：免安裝應用程式內更新實測** | 獨立於沙盒打包冷凍舊版 `v2026.11.21`（留存備份）與新版 `v2026.11.28` `.zip` + `.sha256`，發佈至 GitHub Release 實際測試 `--self-update-test` 全自動自我更新流程。 | `main.py`、`src/ytdlp_gui/main.py` | **已產出資源與初步驗證**：已於沙盒打包舊版備份（`%TEMP%\EasyMusicDL_update_e2e\backup_old_v2026.11.21`）與新版並發佈公開測試 Release（`https://github.com/DreamOver9183/EzMusicDL/releases/tag/v2026.11.28`）；下載 39.8MB `.zip`、SHA-256 驗證與檔案替換／資料保留通過，並抓出 3 項實測缺陷（納入 `F0.1`）。原 `dist/` 未被更動。 |
| **F0.1** | **修正 F0 實測發現之 3 項更新器缺陷並複測通過** | ① `apply_update()` 改用 `CREATE_NO_WINDOW \| CREATE_NEW_PROCESS_GROUP`（移除互斥之 `DETACHED_PROCESS`），並加上 `stdin/stdout/stderr=subprocess.DEVNULL`、`close_fds=True`；<br>② `build_windows_updater_script()` 拆分為獨立三階段：Phase A 備份與替換（失敗回滾）→ Phase B 確認新版就位後才清理 `.update_backup` 與暫存 → Phase C 獨立重試重啟 `try/catch`（最多 5 次等待 Windows Defender 放行，重啟失敗絕不刪除已安裝新版）；<br>③ `$ws.Popup` 改為有限秒數（15 秒）避免無限阻塞，且 `run_self_update_test()` 節流進度日誌（每 10% 或階段變更才寫入）。 | `src/ytdlp_gui/core/update_checker.py`、`src/ytdlp_gui/main.py` | 舊版冷凍 `EasyMusicDL.exe --self-update-test` 全程免人工介入一次跑完：自動寫出 `logs/updater.log`、完成檔案替換、保留 `bin/`/`data/`/`logs/`/`cookies.txt`、成功重啟新版 `v2026.11.28` 進入主畫面，且新版再次檢查回報 `up_to_date`。（測試完成後可用 `gh release delete v2026.11.28 --repo DreamOver9183/EzMusicDL --cleanup-tag -y` 清除測試 Release。） |
| **F1** | **視覺系統與設定偏好地基** | 建立 YT Studio Dark（預設）與 Light 雙主題色票、等寬字體 `mono_font()`、DWM `#0F0F11` 標題列、新增工作台 Fluent 圖示與語意變體，更新預設設定與設計契約。 | `theme.py`、`icons.py`、`settings_manager.py`、`.interface-design/system.md` | 新色票與 `mono_font()` 可正常渲染；`theme_mode` 預設 `"dark"`；`default_audio_format` 與 `embed_thumbnail` 可讀寫持久化。 |
| **F2** | **後端多格式轉檔、封面嵌入與清單解析** | 實作網址四分類、播放清單展開（`--flat-playlist`）、三種原生態格式（`MP3 320k`/`M4A`/`OPUS 160k`）、`--embed-thumbnail`、`embedding_cover` 進度階段、單筆重試／移除與認證異常通知 Hook。 | `ytdlp_wrapper.py`、`download_manager.py` | 通過 `T1-2`、`T1-3`、`T1-4` 與 `T2-1`、`T2-2` 測試；舊版 `download_queue.json` 無痛載入。 |
| **F3** | **主框架與 Chrome 導覽骨架** | 實作左側 168px 窄導覽列（`3px` 珊瑚紅指示條、佇列／音樂徽章）、底部系統健康狀態列（`yt-dlp` / `FFmpeg` / `Cookie` 燈號＋版本號）與 `1200×760` 主視窗骨架。 | `sidebar_nav.py`、`status_bar.py`、`main_window.py` | 四個分頁可無閃爍切換；狀態列燈號即時反應引擎／Cookie 狀態並可點擊跳轉設定；最小視窗 `1020×660` 無排版錯亂。 |
| **F4** | **工作台頂部全局輸入與左欄預覽格式面板** | 實作頂部全局解析列（剪貼簿零佔位浮現快捷鈕、珊瑚紅「解析」、批次匯入彈窗）與左欄 Bento（16:9 縮圖＋片長、候選清單勾選、混音單曲優先＋展開、三格式膠囊、封面開關、`TranslatedError` 卡片）。 | `parser_workbench_view.py` | 貼上單曲、混音、正式清單、關鍵字與多行批次均能正確解析／入列；解析失敗顯示結構化錯誤與錯誤代碼。 |
| **F5** | **工作台右欄即時多工佇列** | 實作右欄 Bento 即時任務卡（微型縮圖、格式徽章、等寬百分比與 `MB/s`、`4px` 語意進度條、轉檔／寫入封面琥珀態、完成轉「開啟資料夾」、失敗快速重試與總任務計數徽章）。 | `parser_workbench_view.py` | 首屏 `1200×760` 零捲動同時容納預覽面板與多筆佇列卡；等寬數字更新不跳動；完成後一鍵定位檔案。 |
| **F6** | **獨立「下載佇列」全寬管理視圖** | 實作全寬佇列管理頁：狀態篩選膠囊（全部／進行中／已完成／失敗）、失敗項目預設展開完整 `error_code` 與繁中建議、單筆重試／移除及批次清理操作。 | `queue_view.py` | 各篩選分頁計數與切換正確；失敗詳情完整對齊 `error_translations.py`；重試與清除即時同步首屏右欄。 |
| **F7** | **翻新「我的音樂」與按需展開資訊列** | 升級掃描 `.mp3`、`.m4a`、`.opus`、即時搜尋過濾與格式徽章；實作底部按需展開簡化控制列（僅點擊曲目時浮現：曲名／大小／時間＋預設播放器開啟＋開啟資料夾＋關閉）。 | `my_music_view.py` | 預設不顯示控制列；點擊任一曲目立即展開；三種副檔名皆可正常掃描、排序、搜尋與開啟。 |
| **F8** | **嵌入式「系統設定」頁、打包對齊與舊檔清理** | 實作嵌入式 5 卡 Bento 設定頁（外觀與下載偏好、免安裝自我更新、引擎狀態修復、存檔位置、Cookie 與診斷複製），同步更新 `build.py` `hiddenimports` 並清理廢棄舊元件。 | `settings_view.py`、`build.py`、移除廢棄舊元件 | 全數功能無損遷移自原 `HelpDialog`；`py_compile`、全套測試 `T1–T5` 與離屏 GUI 冒煙全數通過。 |

---

## 六、完整測試項目清單（Test Matrix）

| 編號 | 類別 | 測試項目 | 驗證方式與預期結果 |
| :--- | :--- | :--- | :--- |
| **T1-1** | 單元測試 | 錯誤翻譯規則與優先權 | 覆蓋 38+ 種錯誤字串（含 `Sign in to confirm you’re not a bot` Unicode `’`、年齡限制、Chrome 鎖定、DPAPI、私人影片等），確認分類精準且無舊「協助與修復」文案。 |
| **T1-2** | 單元測試 | YouTube 輸入分類與批次過濾 | 驗證 `classify_youtube_input()` 正確識別單曲、`v=&list=RD` 混音電台、`list=PL` 正式清單、關鍵字，並正確過濾多行批次貼上網址。 |
| **T1-3** | 單元測試 | 三格式與封面嵌入 CLI 組裝 | 驗證 `MP3 320k`、`M4A`、`OPUS 160k` 與 `embed_thumbnail` True/False 產生精確的 `yt-dlp` 参数，並檢驗 `_DEST_RE` 捕捉 `.mp3`/`.m4a`/`.opus`。 |
| **T1-4** | 單元測試 | 佇列重試與錯誤保留 | 驗證跳過未安裝瀏覽器、本機 Cookie 失敗不蓋掉原始 `YT_BOT_CHECK`、`retry_download()`／`remove_download()` 狀態轉移，及舊 `download_queue.json` 相容載入。 |
| **T1-5** | 單元測試 | `UpdateChecker` 安全與邊界 | 驗證 404/304/200/403 處理、`.zip` 優先選擇、SHA-256 不符拒絕、Zip Slip 拒絕、`updater.ps1` 中文路徑與失敗自動回滾。 |
| **T1-6** | 單元測試 | 日誌與診斷隱私 | 驗證啟動摘要與 `get_diagnostic_report()` 整合 4 份 log，且絕對不輸出 `cookies.txt` 內容與 Proxy 帳號密碼。 |
| **T2-1** | 整合測試 | 真實 `yt-dlp` 解析與年齡限制 | 實測 `4rgSzQwe5DQ` 成功解析、`07FYdnEawAQ` 判定 `YT_AGE_RESTRICTED`，並驗證真實播放清單 `--flat-playlist` 快速展開條目。 |
| **T2-2** | 整合測試 | 真實三格式下載與封面嵌入 | 針對短音訊／測試曲目實際驗證 `MP3 320k`、`M4A`、`OPUS 160k`＋封面嵌入產檔成功且可讀取大小。 |
| **T2-3** | 整合測試 | 我的音樂多格式掃描與篩選 | 建立混合 `.mp3`/`.m4a`/`.opus` 臨時資料夾，驗證掃描排序、關鍵字篩選與按需控制列資訊正確。 |
| **T2-4** | 整合測試 | `build.py` 打包與 `--zip` 排除 | 驗證動態讀取版本號，且 `create_portable_zip()` 排除 `bin/` 二進位與 `data/`/`logs/`/`cookies.txt`。 |
| **T3-1** | 端對端 | **免安裝應用程式內自我更新 E2E** | 舊版冷凍 `EasyMusicDL.exe`（`v2026.11.21`）連真實 GitHub Release `v2026.11.28` 下載、校驗、替換、保留 `bin/`/`data/`/`logs/`/`cookies.txt` 並成功重啟進入新版 `v2026.11.28` 主畫面。 |
| **T3-2** | 端對端 | 更新後不重複觸發驗證 | 新版 `v2026.11.28` 再次檢查更新確認回傳 `up_to_date`（exit 0，無重複更新）。 |
| **T3-3** | 端對端 | 唯讀目錄與失敗回滾驗證 | 驗證無寫入權限資料夾預先攔截，以及替換階段異常時 `.update_backup` 完整還原舊版。 |
| **T3-4** | 端對端 | 冷凍無主控台進程喚起更新腳本 | 驗證 `--noconsole` 冷凍 `EasyMusicDL.exe` 透過 `CREATE_NO_WINDOW \| CREATE_NEW_PROCESS_GROUP` + `DEVNULL` 啟動 `powershell.exe` 後，確實寫出 `logs/updater.log`（無 `DETACHED_PROCESS` 衝突）。 |
| **T3-5** | 端對端 | 重啟 `Access is denied` 保護與限時提示 | 模擬重啟階段遇防毒掃描短暫回傳 `Access is denied` 時，確認最多 5 次重試可恢復、重啟失敗時**絕不誤刪已安裝的新版檔案**，且提示視窗於 15 秒自動逾時不無限阻塞。 |
| **T4-1** | UI / 版面 | 首屏視窗與 DPI 響應測試 | 於 `1200×760` 與最小 `1020×660` 離屏實例化並切換四頁，驗證首屏零捲動、無按鈕截斷或文字重疊。 |
| **T4-2** | UI / 主題 | Dark 預設與 Light 切換測試 | 驗證啟動預設 YT Studio Dark（`#0F0F11`）、切換淺色即時重繪與 DWM 標題列同步。 |
| **T4-3** | UI / 互動 | 微互動與狀態燈號測試 | 驗證剪貼簿焦點浮現快捷鈕、「我的音樂」按需控制列顯隱、狀態列 `yt-dlp`/`FFmpeg`/`Cookie` 燈號與點擊跳轉設定。 |
| **T4-4** | UI / 規範 | 雙軌字體與文案／零 Emoji 檢核 | 確認技術數據使用 `mono_font()` 對齊、全介面為純繁體中文主文案＋必要技術名詞、零 Emoji。 |
| **T5-1** | 回歸檢查 | 全專案編譯與模組匯入 | 所有 `.py` 通過 `python -m py_compile` 與模組匯入檢查，無殘留廢棄引用。 |
| **T5-2** | 回歸檢查 | 既有診斷能力回歸 | 重跑錯誤翻譯／Logger／免安裝更新核心測試，確認 `F0` 與既有修復零退化。 |
| **T5-3** | 打包安全 | 工作區與現有 `dist/` 保護 | 驗證開發測試過程不動到既有的 `dist/EasyMusicDL.rar` 與無關設定檔。 |

---

## 七、版本變更紀錄（Changelog）

| 計畫書版本 | 日期 | 變更說明 |
| :--- | :--- | :--- |
| `v1.0.0` | `2026-11-28` | 初版定稿：完成 7 項產品與設計決策訪談對齊，定義 YT Studio Dark 雙主題色票、雙軌字體、1200×760 零捲動工作台架構、三格式（`MP3 320k`/`M4A`/`OPUS 160k`）與封面嵌入規格、嵌入式系統設定與四階段架構。 |
| `v1.1.0` | `2026-11-28` | 拆分為詳細小階段實作目標 **`F0` ~ `F8`**（含涉及檔案與 DoD 驗收條件），並新增完整測試項目矩陣 **`T1` ~ `T5`**；啟動 **`F0`** 沙盒打包與真實 GitHub Release 免安裝應用程式內更新端對端實測。 |
| `v1.2.0` | `2026-11-28` | 記錄 `F0` 實測成果（GitHub Release `v2026.11.28` 已發佈、舊版備份已留存）與發現的 3 項更新器實務缺陷，新增 **`F0.1`** 修正計畫及 **`T3-4`**、**`T3-5`** 驗收測試項目。 |
