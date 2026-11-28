<h1>
  <img src="assets/logo.png?v=2" width="32" height="32" style="vertical-align: text-bottom; margin-right: 8px;" />
  <sup>EasyMusicDL</sup>
</h1>

輸入歌名或貼上 YouTube 連結，一鍵下載成 MP3。介面簡潔、字體清楚，不需要任何設定，引擎會自動更新。

## 功能

- 以歌名搜尋，或直接貼上 YouTube 連結
- 一鍵下載純 MP3，存到 Windows「下載」資料夾（可在設定中更改）
- 「已下載音樂」頁面：列出已下載的歌曲，可直接播放或在資料夾中顯示
- 下載佇列重新啟動後仍會保留
- 自動下載並更新 yt-dlp、ffmpeg，程式本身也會自動檢查更新
- 「設定與修復」：更改存檔位置、修復下載引擎、複製診斷紀錄
- 支援淺色／深色模式

## 技術

- Python 3.9+
- CustomTkinter
- yt-dlp
- Pillow
- PyInstaller

## 安裝

1. 從 [Releases](../../releases) 下載最新的 `.exe`，僅支援 Windows 10/11
2. 執行。程式沒有簽章，SmartScreen 可能會跳出提示：點「其他資訊」，再點「仍要執行」
3. 第一次啟動會自動下載 yt-dlp 與 ffmpeg，請稍候

### 從原始碼執行

```bash
git clone https://github.com/DreamOver9183/EzMusicDL.git
cd EzMusicDL
pip install -r requirements.txt
python main.py
```

打包成 exe：`pip install pyinstaller`，然後執行 `python build.py`。

### 執行測試

```bash
pip install pytest
python -m pytest tests -q
```

預設執行 155 個離線測試（含在暫存目錄實際執行更新用 PowerShell 腳本的情境，約需一分鐘）。需要外部工具或外網的測試標記為 `network`，以 `python -m pytest tests -q -m network` 另外執行。

## 使用方式

1. 開啟程式，在「搜尋下載」頁輸入歌名，或貼上 YouTube 連結
2. 從結果中選擇歌曲，按下載
3. 在「已下載音樂」頁播放，或開啟檔案所在的資料夾

- 若下載失敗或引擎異常，到右上角「設定與修復」執行修復
- 部分地區的 YouTube 可能需要使用 VPN

## 致謝

本專案衍生自 [vokrob/yt-dlp-gui](https://github.com/vokrob/yt-dlp-gui)，並以 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 作為下載核心。授權條款見 [LICENSE](LICENSE)。
