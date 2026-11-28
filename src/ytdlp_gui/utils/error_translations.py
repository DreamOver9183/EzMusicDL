# -*- coding: utf-8 -*-
"""
Structured, human-readable Traditional Chinese error analysis and translation
for yt-dlp, YouTube, browser cookies, FFmpeg/Deno engines, network, filesystem,
and application updates.
"""

from dataclasses import dataclass
import re
from typing import List, Pattern, Tuple, Union


@dataclass(frozen=True)
class TranslatedError:
    """Structured error diagnosis with Traditional Chinese user guidance."""

    code: str
    category: str  # youtube | cookie | engine | network | filesystem | update | unknown
    title: str
    detail: str
    suggestion: str
    raw_excerpt: str = ""

    def full_message(self) -> str:
        """Return combined detail and next-step suggestion."""
        parts = [p.strip() for p in (self.detail, self.suggestion) if p and p.strip()]
        return " ".join(parts)


@dataclass(frozen=True)
class _ErrorRule:
    code: str
    category: str
    pattern: str
    title: str
    detail: str
    suggestion: str
    compiled: Pattern[str]


def _rule(
    code: str,
    category: str,
    pattern: str,
    title: str,
    detail: str,
    suggestion: str,
) -> _ErrorRule:
    return _ErrorRule(
        code=code,
        category=category,
        pattern=pattern,
        title=title,
        detail=detail,
        suggestion=suggestion,
        compiled=re.compile(pattern, re.IGNORECASE),
    )


# Ordered strictly from most specific to most general so narrow diagnostics win.
ERROR_RULES: List[_ErrorRule] = [
    _rule(
        code="YT_BOT_CHECK",
        category="youtube",
        pattern=(
            r"Sign in to confirm you['’]re not a bot|confirm you['’]re not a bot"
            r"|not a bot|playerCaptchaViewModel|requiring a captcha challenge"
        ),
        title="YouTube 觸發防機器人驗證",
        detail="YouTube 將目前連線環境判定為自動化流量而暫時擋下（這通常是網路風控，不一定代表影片有年齡限制）。",
        suggestion="常見於使用 VPN、公司/學校/公共 Wi-Fi、電信共用 IPv6 或短時間頻繁操作；建議先關閉 VPN 或切換網路後再試，必要時可點右上角「設定與修復 → 複製診斷紀錄」協助排查。",
    ),
    _rule(
        code="YT_AGE_RESTRICTED",
        category="youtube",
        pattern=(
            r"Sign in to confirm your age|confirm your age|This video is age-restricted"
            r"|age_verification_required|age_check_required|inappropriate for some users"
        ),
        title="影片受 18 歲年齡限制",
        detail="這支影片被 YouTube 標記為成人／年齡限制內容，匿名連線無法取得音訊串流。",
        suggestion="YouTube 要求使用已完成年齡驗證的帳號 Cookie（如放置 cookies.txt 或以 Firefox 登入）才能讀取。",
    ),
    _rule(
        code="YT_MEMBERS_ONLY",
        category="youtube",
        pattern=(
            r"Join this channel to get access|members-only content"
            r"|available to this channel's members|requires payment|rent or buy|YouTube Premium"
        ),
        title="頻道會員或付費限定內容",
        detail="這支影片僅限頻道付費會員、YouTube Premium 或已購買的帳號觀看，無法公開下載。",
        suggestion="請改搜尋其他公開版本；若您本身具備會員資格，需透過有效登入 Cookie 才能讀取。",
    ),
    _rule(
        code="YT_PRIVATE",
        category="youtube",
        pattern=r"This video is private|Private video",
        title="影片已設為私人",
        detail="這支影片已被上傳者設為「私人影片」，未經授權無法讀取或下載。",
        suggestion="請確認連結是否正確，或改搜尋其他公開上傳的版本。",
    ),
    _rule(
        code="YT_LOGIN_REQUIRED",
        category="youtube",
        pattern=(
            r"Sign in to confirm|only available for registered users|LOGIN_REQUIRED"
            r"|Sign in if you've been granted access|Use --cookies-from-browser or --cookies"
        ),
        title="YouTube 要求登入驗證",
        detail="YouTube 要求登入帳號後才能讀取這支影片的串流資訊。",
        suggestion="若為公開歌曲但仍出現此訊息，可能是目前 IP 被暫時限制或引擎過舊，請先點右上角「設定與修復 → 檢查並更新下載引擎」，或切換網路後重試。",
    ),
    _rule(
        code="COOKIE_DB_LOCKED",
        category="cookie",
        pattern=r"Could not copy .* cookie database|database is locked|PermissionError.*Cookies",
        title="瀏覽器 Cookie 資料庫被鎖定",
        detail="瀏覽器目前正在執行並鎖定 Cookie 檔案，導致程式無法讀取瀏覽器登入狀態。",
        suggestion="若要讓程式讀取瀏覽器登入狀態，請先完全關閉瀏覽器視窗後再重試；一般公開歌曲無需登入即可下載。",
    ),
    _rule(
        code="COOKIE_DPAPI",
        category="cookie",
        pattern=r"failed to decrypt with DPAPI|app_bound_encrypted_key|\bDPAPI\b",
        title="無法解密瀏覽器 Cookie（Windows DPAPI）",
        detail="新版 Chrome／Edge 在 Windows 啟用了應用程式綁定加密，外部工具無法直接解密本機 Cookie。",
        suggestion="一般公開歌曲不需登入即可下載；若確定需要登入才能下載的影片，請改用 Firefox 登入或匯出 cookies.txt，詳情可點右上角「設定與修復 → 複製診斷紀錄」排查。",
    ),
    _rule(
        code="COOKIE_DB_NOT_FOUND",
        category="cookie",
        pattern=r"could not find .* cookies database|No such file or directory.*cookies",
        title="找不到瀏覽器 Cookie 檔案",
        detail="偵測到瀏覽器資料夾，但找不到對應的 Cookie 資料庫檔案。",
        suggestion="一般公開歌曲不需登入即可下載；若需登入狀態，請確認已開啟過該瀏覽器並登入 YouTube。",
    ),
    _rule(
        code="COOKIE_INVALID",
        category="cookie",
        pattern=r"cookies are no longer valid|provided YouTube account cookies are no longer valid",
        title="YouTube 登入 Cookie 已失效",
        detail="目前使用的 YouTube Cookie 已過期或遭到登出，無法通過帳號驗證。",
        suggestion="請重新在瀏覽器登入 YouTube 並更新 cookies.txt，或移除舊的 cookies.txt 後重試。",
    ),
    _rule(
        code="YT_RATE_LIMIT",
        category="youtube",
        pattern=(
            r"HTTP Error 429|Too Many Requests|This content isn't available, try again later"
            r"|rate-limited|All player responses are invalid.*blocked"
        ),
        title="請求過於頻繁（YouTube 限流 429）",
        detail="短時間內搜尋或下載次數過多，YouTube 已暫時限制目前連線的讀取權限。",
        suggestion="請稍候數分鐘至一小時後再試，或更換網路連線（關閉 VPN）再重新下載。",
    ),
    _rule(
        code="YT_REMOVED",
        category="youtube",
        pattern=(
            r"This video has been removed|copyright claim"
            r"|account associated with this video.*terminated|Video has been deleted|HTTP Error 404"
        ),
        title="影片已被移除或不存在（404）",
        detail="這支影片可能已被原作者刪除、因版權申訴下架、帳號遭停權或網址有誤。",
        suggestion="請檢查網址是否完整正確，或在搜尋欄改以歌名搜尋其他版本。",
    ),
    _rule(
        code="YT_GEO_BLOCKED",
        category="youtube",
        pattern=(
            r"not made this video available in your country|not available in your country"
            r"|geo.?restricted|blocked it in your country"
        ),
        title="影片受地區版權限制",
        detail="上傳者限制了這支影片的觀看國家／地區，您目前的網路地區無法播放或下載。",
        suggestion="請在搜尋欄搜尋其他地區可播放的版本，或確認是否因 VPN 連線至受限國家所致。",
    ),
    _rule(
        code="YT_PREMIERE_OR_LIVE",
        category="youtube",
        pattern=r"Premieres in|This live event will begin|live stream is offline|will begin in",
        title="首播或直播尚未開始",
        detail="這支影片目前為預定首播或尚未開始／已離線的直播活動，尚無完整音訊檔。",
        suggestion="請等首播或直播結束、YouTube 轉檔完成後再進行下載。",
    ),
    _rule(
        code="YT_DRM",
        category="youtube",
        pattern=r"DRM protected|This video is DRM|licenseInfos",
        title="影片受 DRM 數位版權保護",
        detail="此內容採用 DRM 加密串流保護，依技術與版權規範無法解密或轉存為 MP3。",
        suggestion="請改搜尋同一首歌曲的非加密公開版本。",
    ),
    _rule(
        code="YT_UNAVAILABLE",
        category="youtube",
        pattern=r"video\s+(?:is\s+)?unavailable|This video is not available",
        title="影片目前無法播放",
        detail="YouTube 回報這支影片目前無法使用，可能已被刪除、設為不公開或受地區限制。",
        suggestion="請嘗試在瀏覽器確認該連結是否可正常播放，或改搜尋其他版本。",
    ),
    _rule(
        code="YT_HTTP_403",
        category="youtube",
        pattern=(
            r"unable to download video data.*HTTP Error 40[13]"
            r"|Unable to download (?:fragment|segment).*HTTP Error 40[13]"
            r"|Server returned 40[13]|403 Forbidden|HTTP Error 40[13]"
        ),
        title="YouTube 拒絕存取串流（HTTP 403/401）",
        detail="YouTube 拒絕了此次串流下載請求，常見原因為下載引擎過舊、簽章變更或網路 IP 遭擋。",
        suggestion="請點右上角「設定與修復 → 檢查並更新下載引擎」更新 yt-dlp 後重試；若仍發生請檢查網路或 VPN。",
    ),
    _rule(
        code="YT_EXTRACT_FAIL",
        category="youtube",
        pattern=(
            r"The page needs to be reloaded|SABR|Only images are available"
            r"|No video formats found|Unable to extract|failed to extract any player response"
            r"|Signature solving failed|n challenge solving failed"
        ),
        title="無法解析影片音訊格式",
        detail="YouTube 網頁結構或播放器驗證已變更，或 JS 挑戰解析失敗，導致找不到可用音訊串流。",
        suggestion="請點右上角「設定與修復 → 檢查並更新下載引擎」確保 yt-dlp 與 Deno 為最新狀態後再試。",
    ),
    _rule(
        code="YT_FORMAT_UNAVAILABLE",
        category="youtube",
        pattern=r"requested format(?: is)? not available",
        title="找不到可用的音訊格式",
        detail="這支影片目前沒有提供符合條件的可下載音訊串流。",
        suggestion="請先點右上角「設定與修復 → 檢查並更新下載引擎」，或改選搜尋列表中的其他版本。",
    ),
    _rule(
        code="YT_HLS_FAIL",
        category="youtube",
        pattern=r"Unable to download M3U8|Failed to download M3U8|m3u8.*(?:error|failed)|fragment.*not found",
        title="串流分段下載失敗（M3U8）",
        detail="下載 HLS 串流音訊分段時失敗，可能因網路不穩、串流連結過期或地區封鎖所致。",
        suggestion="請確認網路穩定後再試一次，必要時可先更新下載引擎。",
    ),
    _rule(
        code="JS_RUNTIME_MISSING",
        category="engine",
        pattern=r"No supported JavaScript runtime|deno.*not found|JS challenge",
        title="缺少 JS 解析輔助元件（Deno）",
        detail="找不到可用的 JavaScript 執行環境（Deno），部分 YouTube 影片簽章將無法解開。",
        suggestion="請點右上角「設定與修復 → 檢查並更新下載引擎」，系統會自動補齊 Deno 元件。",
    ),
    _rule(
        code="FFMPEG_MISSING",
        category="engine",
        pattern=r"ffprobe.*not found|ffmpeg.*not found|avconv.*not found|Postprocessing: ffprobe",
        title="缺少音訊轉檔元件（FFmpeg）",
        detail="找不到 FFmpeg 或 FFprobe 執行檔，無法將下載的音訊轉存為 MP3。",
        suggestion="請點右上角「設定與修復 → 檢查並更新下載引擎」自動下載並驗證 FFmpeg。",
    ),
    _rule(
        code="FFMPEG_CONVERT_FAIL",
        category="engine",
        pattern=r"Postprocessing:|ffmpeg exited with code|Error converting|Audio conversion failed|mutagen",
        title="MP3 轉檔或標籤寫入失敗",
        detail="音訊已下載但 FFmpeg 轉檔或寫入歌曲資訊時發生錯誤（可能為檔案受損或空間不足）。",
        suggestion="請確認磁碟空間足夠且存檔資料夾可寫入，或點右上角「設定與修復 → 複製診斷紀錄」查看詳細輸出。",
    ),
    _rule(
        code="YTDLP_MISSING",
        category="engine",
        pattern=r"FileNotFoundError.*yt-dlp|WinError 2.*yt-dlp|'yt-dlp' is not recognized",
        title="找不到下載引擎（yt-dlp）",
        detail="系統找不到 yt-dlp.exe 執行檔，可能被防毒軟體誤刪或尚未完成下載。",
        suggestion="請點右上角「設定與修復 → 檢查並更新下載引擎」重新下載並驗證引擎。",
    ),
    _rule(
        code="YT_SERVER_5XX",
        category="youtube",
        pattern=r"HTTP Error 5\d{2}|502 Bad Gateway|503 Service Unavailable|504 Gateway",
        title="YouTube 伺服器暫時異常（5xx）",
        detail="YouTube 伺服器端回傳暫時性錯誤，並非本機程式問題。",
        suggestion="請稍候數十秒至幾分鐘後再重新嘗試。",
    ),
    _rule(
        code="UNSUPPORTED_URL",
        category="youtube",
        pattern=r"Unsupported URL|is not a valid URL|Incomplete YouTube ID|Truncated YouTube ID",
        title="網址格式不正確或不支援",
        detail="輸入的網址不完整、影片 ID 遭截斷，或不屬於支援的影音連結格式。",
        suggestion="請確認已完整複製 YouTube 網址，或直接輸入歌名／歌手進行搜尋。",
    ),
    _rule(
        code="DISK_FULL",
        category="filesystem",
        pattern=r"No space left on device|\[Errno 28\]|disk full",
        title="磁碟儲存空間不足",
        detail="存檔磁碟機已沒有足夠的剩餘空間，無法繼續下載或轉換 MP3。",
        suggestion="請清理磁碟空間，或點右上角「設定與修復 → 變更資料夾」改存至其他磁碟機。",
    ),
    _rule(
        code="DISK_PERMISSION",
        category="filesystem",
        pattern=r"Permission denied|\[Errno 13\]|Access is denied|WinError 5|WinError 32",
        title="資料夾或檔案存取遭拒絕",
        detail="無法寫入目標資料夾或檔案正被其他程式（例如音樂播放器、防毒軟體）佔用中。",
        suggestion="請關閉正在播放該檔案的程式後重試，或至「設定與修復 → 變更資料夾」選擇其他可寫入資料夾。",
    ),
    _rule(
        code="FILENAME_TOO_LONG",
        category="filesystem",
        pattern=r"File name too long|\[Errno 36\]|WinError 206|MAX_PATH",
        title="檔案路徑過長",
        detail="存檔資料夾路徑加上歌曲標題超過 Windows 路徑長度上限。",
        suggestion="請點右上角「設定與修復 → 變更資料夾」改存至較淺層的路徑（例如 D:\\Music）。",
    ),
    _rule(
        code="NET_SSL",
        category="network",
        pattern=r"Certificate verify failed|SSLError|\bSSL:|\bTLS\b",
        title="安全連線（SSL/TLS）驗證失敗",
        detail="建立 HTTPS 安全連線時失敗，常見原因為電腦系統日期時間不正確，或公司網路憑證攔截。",
        suggestion="請檢查 Windows 右下角系統日期與時間是否準確，並確認防毒／公司代理未攔截連線。",
    ),
    _rule(
        code="NET_PROXY",
        category="network",
        pattern=r"ProxyError|Unable to connect to proxy|SOCKS",
        title="Proxy 代理伺服器連線失敗",
        detail="程式嘗試透過系統設定的 Proxy 連線但無法連上代理伺服器。",
        suggestion="請檢查 Windows 網路代理設定或關閉異常的 VPN／代理軟體後再試。",
    ),
    _rule(
        code="NET_TIMEOUT",
        category="network",
        pattern=r"Timeout|timed out|ReadTimeout|ConnectTimeout|連線逾時|搜尋逾時",
        title="網路連線等候逾時",
        detail="與 YouTube 伺服器連線或等候回應時間過長而自動中止。",
        suggestion="目前網路速度可能不穩或受阻，請檢查 Wi-Fi／網路線連線後再試一次。",
    ),
    _rule(
        code="NET_RESET",
        category="network",
        pattern=r"ConnectionError.*reset|Connection aborted|RemoteDisconnected|ConnectionResetError|BrokenPipe|IncompleteRead",
        title="網路連線意外中斷",
        detail="下載過程中與伺服器的連線被中斷或重設。",
        suggestion="請確認網路連線穩定（避免在訊號微弱時下載長曲目）後再試一次。",
    ),
    _rule(
        code="NET_OFFLINE",
        category="network",
        pattern=(
            r"\[Errno 11001\]|\[Errno \d+\]|Name or service not known"
            r"|Temporary failure in name resolution|Network is unreachable"
            r"|No route to host|getaddrinfo failed|Failed to resolve"
        ),
        title="無法連線或 DNS 解析失敗",
        detail="電腦目前可能未連上網際網路，或無法解析 YouTube 網域名稱（常見於 DNS 異常或 IPv6 無連線）。",
        suggestion="請確認電腦已連上網路並可開啟網頁後再試一次。",
    ),
]

# Legacy tuple list kept for backward compatibility.
ERROR_TRANSLATIONS: List[Tuple[str, str]] = [
    (rule.pattern, f"{rule.detail} {rule.suggestion}".strip())
    for rule in ERROR_RULES
]

_LOCAL_COOKIE_ERROR_CODES = frozenset(
    {"COOKIE_DB_LOCKED", "COOKIE_DPAPI", "COOKIE_DB_NOT_FOUND"}
)


def _clean_excerpt(error_str: str, limit: int = 220) -> str:
    single_line = " ".join((error_str or "").split())
    if len(single_line) > limit:
        return single_line[:limit] + "..."
    return single_line


def analyze_error(error: Union[Exception, str, None]) -> TranslatedError:
    """Analyze a raw yt-dlp/system error and return structured diagnosis details."""
    error_str = str(error or "").strip()
    excerpt = _clean_excerpt(error_str)

    if not error_str:
        return TranslatedError(
            code="EMPTY_ERROR",
            category="unknown",
            title="下載失敗",
            detail="作業未完成，但引擎未回傳具體錯誤訊息。",
            suggestion="請檢查網路連線後再試一次，或點右上角「設定與修復 → 複製診斷紀錄」協助排查。",
            raw_excerpt="",
        )

    for rule in ERROR_RULES:
        if rule.compiled.search(error_str):
            return TranslatedError(
                code=rule.code,
                category=rule.category,
                title=rule.title,
                detail=rule.detail,
                suggestion=rule.suggestion,
                raw_excerpt=excerpt,
            )

    return TranslatedError(
        code="UNKNOWN_ERROR",
        category="unknown",
        title="發生未分類錯誤",
        detail=f"執行時發生狀況：{excerpt}",
        suggestion="可點右上角「設定與修復 → 檢查並更新下載引擎」或「複製診斷紀錄」協助排查。",
        raw_excerpt=excerpt,
    )


def is_local_cookie_error(error: Union[Exception, str, None]) -> bool:
    """Return True when the error comes from local browser cookie access/decryption."""
    return analyze_error(error).code in _LOCAL_COOKIE_ERROR_CODES


def translate_error(error: Union[Exception, str, None]) -> str:
    """Convert common yt-dlp/system errors to detailed Traditional Chinese messages."""
    return analyze_error(error).full_message()


def translate_error_short(error: Union[Exception, str, None]) -> str:
    """Convert common yt-dlp/system errors to a concise Traditional Chinese title."""
    return analyze_error(error).title
