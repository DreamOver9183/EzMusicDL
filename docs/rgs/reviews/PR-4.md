# 審查裁決紀錄：PR #4「fix: make stop, cancel and exit terminate downloads safely (M2)」

## 第 1 輪審查（2026-11-28 23:24，`gemini-3.8-flash-high`，判定 PASS）

報告：`.rgs/runs/m2/review-1/review.md`

| # | 嚴重度 | 位置 | 問題 | 裁決 | 理由 |
| --: | :-- | :-- | :-- | :-- | :-- |
| 1 | 次要 | `src/ytdlp_gui/core/download_manager.py:713` | _write_json_with_timeout 逾時後背景執行緒缺乏取消旗標 | 延後到 M6 | 分析成立；需磁碟寫入停滯超過 3 秒且其後又存檔才會發生，改版前直接覆寫目標檔的風險更高，非退化。M6 會改寫佇列管理，屆時在逾時後設取消旗標，os.replace 前檢查。 |
| 2 | 次要 | `src/ytdlp_gui/core/download_manager.py:747` | 存檔失敗時統一記錄為逾時，日誌訊息精度不足 | 延後到 M6 | 與第 1 項同一段程式；M6 一併回傳實際失敗原因。 |
| 3 | 次要 | `src/ytdlp_gui/core/process_tracker.py:34` | Windows 下 taskkill 呼叫未指定完整路徑 | 延後到 M3 | 風險低（能在程式資料夾放置執行檔者也能直接替換主程式），非本里程碑引入的唯一案例。M3 處理更新腳本啟動時，一併讓 taskkill 與 powershell.exe 使用 System32 完整路徑。 |
| 4 | 次要 | `tests/test_process_tracker.py:89` | 測試清理以純整數 PID 執行 taskkill 存在理論上的 PID 重用風險 | 不採納 | 清理前先確認 PID 仍在執行，重用時間窗僅毫秒級；若照建議在正常路徑略過清理，測試中途失敗時較容易遺留行程。僅影響測試程式。 |

裁決只能填：採納、不採納、延後到 M<n>；不採納與延後都要寫理由。

結論：沒有 blocker／major，合併閘門通過。延後項目需寫進 M3、M6 的規格。

備註：使用者回報以真實下載完成「下載中關閉視窗」的手動驗收並通過後合併；Claude 沒有讀取沙盒的日誌，轉檔階段是否另行測試未回報。合併後 `main` 內容與審查版本相同。
