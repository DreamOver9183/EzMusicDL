# -*- coding: utf-8 -*-
"""
Human-readable Traditional Chinese translations of common yt-dlp errors.
"""

import re

ERROR_TRANSLATIONS = [
    (
        r"failed to decrypt with DPAPI",
        "無法讀取瀏覽器登入狀態，一般歌曲不需要登入也能下載；若為會員限定影片，請點右上角「協助與修復」查看說明。",
    ),
    (
        r"unable to download video data.*HTTP Error 403",
        "YouTube 暫時拒絕連線（403），請點右上角「協助與修復 → 一鍵修復引擎」更新後再試一次。",
    ),
    (
        r"Unable to download M3U8|Failed to download M3U8|m3u8.*(?:error|failed)",
        "無法讀取串流音訊，可能是地區限制或網路不穩，請稍後再試一次。",
    ),
    (
        r"Unable to download (?:fragment|segment).*HTTP Error 40[13]|Server returned 40[13]|403 Forbidden|HTTP Error 40[13]",
        "YouTube 拒絕存取（403），建議點右上角「協助與修復 → 一鍵修復引擎」更新引擎後再試。",
    ),
    (
        r"HTTP Error 404",
        "找不到這首歌（404），可能已被刪除或網址輸入錯誤。",
    ),
    (
        r"HTTP Error 429",
        "短時間內下載太多次，YouTube 請您稍等幾分鐘後再試一次。",
    ),
    (
        r"HTTP Error 5\d{2}",
        "YouTube 伺服器暫時忙碌，請稍等一會兒再試。",
    ),
    (
        r"Sign in to confirm|confirm your age|only available for registered users",
        "這首歌有年齡或登入限制，YouTube 要求先登入帳號才能讀取。",
    ),
    (
        r"video\s+(?:is\s+)?unavailable",
        "這首歌目前無法播放，可能已被原作者刪除或有地區限制。",
    ),
    (
        r"This video is private|private video",
        "這支影片已被原作者設為「私人影片」，無法下載。",
    ),
    (
        r"ffprobe.*not found|ffmpeg.*not found",
        "找不到音樂轉檔元件（FFmpeg），請點右上角「協助與修復 → 一鍵修復引擎」自動補齊。",
    ),
    (
        r"No video formats found|Unable to extract|failed to extract any player response",
        "無法解析這首歌的音訊格式，請點右上角「協助與修復 → 一鍵修復引擎」更新下載引擎後再試。",
    ),
    (
        r"requested format not available",
        "這首歌目前沒有可用的音訊格式，請試試搜尋列表中的其他版本。",
    ),
    (
        r"ConnectionError.*reset|Connection aborted|RemoteDisconnected",
        "網路連線中斷，請檢查 Wi-Fi 或網路線後再試一次。",
    ),
    (
        r"Timeout|timed out",
        "連線等候逾時，網路可能比較慢，請再試一次。",
    ),
    (
        r"Certificate verify failed",
        "電腦日期或時間不正確導致安全連線失敗，請檢查右下角系統時間。",
    ),
    (
        r"\[Errno \d+\]|Name or service not known|Temporary failure in name resolution|Network is unreachable|No route to host|getaddrinfo failed",
        "目前沒有網路連線，請確認電腦已連上 Wi-Fi 或網路線。",
    ),
]


def translate_error(error: Exception) -> str:
    """Convert common yt-dlp errors to plain Traditional Chinese messages."""
    error_str = str(error or "").strip()
    for pattern, message in ERROR_TRANSLATIONS:
        if re.search(pattern, error_str, re.IGNORECASE):
            return message
    if not error_str:
        return "下載失敗，請檢查網路後再試一次，或點右上角「協助與修復」複製查修紀錄。"
    if len(error_str) > 160:
        return f"下載時發生狀況：{error_str[:160]}..."
    return f"下載時發生狀況：{error_str}"
