# -*- coding: utf-8 -*-
"""
Baseline tests for Traditional Chinese error translations and classifications:
1. Parametrized mapping from raw error strings to expected error codes (>= 38 cases).
2. Priority rules: age restriction and bot check take precedence over login required.
3. Empty/None errors map to EMPTY_ERROR, unknown errors to UNKNOWN_ERROR.
4. Raw excerpt truncation behavior.
5. is_local_cookie_error classification.
6. Validation that all rules have non-empty text and no obsolete wording.
"""

import pytest

from ytdlp_gui.utils.error_translations import (
    ERROR_RULES,
    analyze_error,
    is_local_cookie_error,
)

ERROR_CASES = [
    # 1. YT_BOT_CHECK (with unicode and ascii apostrophes)
    ("Sign in to confirm you’re not a bot", "YT_BOT_CHECK"),
    ("Sign in to confirm you're not a bot", "YT_BOT_CHECK"),
    ("confirm you're not a bot", "YT_BOT_CHECK"),
    ("ERROR: playerCaptchaViewModel found in response", "YT_BOT_CHECK"),
    ("requiring a captcha challenge to proceed", "YT_BOT_CHECK"),
    # 2. YT_AGE_RESTRICTED
    ("Sign in to confirm your age", "YT_AGE_RESTRICTED"),
    ("confirm your age", "YT_AGE_RESTRICTED"),
    ("This video is age-restricted", "YT_AGE_RESTRICTED"),
    ("age_verification_required", "YT_AGE_RESTRICTED"),
    # 3. YT_MEMBERS_ONLY
    ("Join this channel to get access to perks", "YT_MEMBERS_ONLY"),
    ("This video contains members-only content", "YT_MEMBERS_ONLY"),
    ("This video requires payment or YouTube Premium to watch", "YT_MEMBERS_ONLY"),
    # 4. YT_PRIVATE
    ("This video is private", "YT_PRIVATE"),
    ("Private video", "YT_PRIVATE"),
    # 5. YT_LOGIN_REQUIRED
    ("Sign in to confirm you have access to this video", "YT_LOGIN_REQUIRED"),
    ("This content is only available for registered users", "YT_LOGIN_REQUIRED"),
    ("Sign in if you've been granted access", "YT_LOGIN_REQUIRED"),
    ("Use --cookies-from-browser or --cookies for authentication", "YT_LOGIN_REQUIRED"),
    # 6. COOKIE_DB_LOCKED
    ("Could not copy Chrome cookie database", "COOKIE_DB_LOCKED"),
    ("sqlite3.OperationalError: database is locked", "COOKIE_DB_LOCKED"),
    ("PermissionError: [Errno 13] Permission denied: Cookies", "COOKIE_DB_LOCKED"),
    # 7. COOKIE_DPAPI
    ("failed to decrypt with DPAPI", "COOKIE_DPAPI"),
    ("Could not find app_bound_encrypted_key", "COOKIE_DPAPI"),
    ("Windows DPAPI error during cookie decryption", "COOKIE_DPAPI"),
    # 8. COOKIE_DB_NOT_FOUND
    ("could not find firefox cookies database", "COOKIE_DB_NOT_FOUND"),
    ("FileNotFoundError: [Errno 2] No such file or directory: '.../cookies.sqlite'", "COOKIE_DB_NOT_FOUND"),
    # 9. COOKIE_INVALID
    ("Your cookies are no longer valid", "COOKIE_INVALID"),
    ("The provided YouTube account cookies are no longer valid", "COOKIE_INVALID"),
    # 10. YT_RATE_LIMIT
    ("HTTP Error 429: Too Many Requests", "YT_RATE_LIMIT"),
    ("This content isn't available, try again later", "YT_RATE_LIMIT"),
    # 11. YT_REMOVED
    ("This video has been removed by the uploader", "YT_REMOVED"),
    ("The account associated with this video has been terminated", "YT_REMOVED"),
    ("HTTP Error 404: Not Found", "YT_REMOVED"),
    # 12. YT_GEO_BLOCKED
    ("The uploader has not made this video available in your country", "YT_GEO_BLOCKED"),
    ("This video is geo-restricted", "YT_GEO_BLOCKED"),
    # 13. YT_PREMIERE_OR_LIVE
    ("Premieres in 3 hours", "YT_PREMIERE_OR_LIVE"),
    ("This live event will begin in 10 minutes", "YT_PREMIERE_OR_LIVE"),
    # 14. YT_DRM
    ("This video is DRM protected and cannot be downloaded", "YT_DRM"),
    # 15. YT_UNAVAILABLE
    ("video is unavailable", "YT_UNAVAILABLE"),
    ("This video is not available", "YT_UNAVAILABLE"),
    # 16. YT_HTTP_403
    ("unable to download video data: HTTP Error 403: Forbidden", "YT_HTTP_403"),
    ("HTTP Error 403", "YT_HTTP_403"),
    # 17. YT_EXTRACT_FAIL
    ("No video formats found", "YT_EXTRACT_FAIL"),
    ("Signature solving failed: could not extract n sig", "YT_EXTRACT_FAIL"),
    # 18. YT_FORMAT_UNAVAILABLE
    ("ERROR: requested format not available", "YT_FORMAT_UNAVAILABLE"),
    # 19. YT_HLS_FAIL
    ("Unable to download M3U8 playlist", "YT_HLS_FAIL"),
    # 20. JS_RUNTIME_MISSING
    ("No supported JavaScript runtime could be found", "JS_RUNTIME_MISSING"),
    ("deno binary not found", "JS_RUNTIME_MISSING"),
    # 21. FFMPEG_MISSING
    ("ffmpeg not found on path", "FFMPEG_MISSING"),
    ("ffprobe was not found", "FFMPEG_MISSING"),
    # 22. FFMPEG_CONVERT_FAIL
    ("ffmpeg exited with code 1", "FFMPEG_CONVERT_FAIL"),
    ("Audio conversion failed", "FFMPEG_CONVERT_FAIL"),
    # 23. YTDLP_MISSING
    ("FileNotFoundError: yt-dlp.exe", "YTDLP_MISSING"),
    ("'yt-dlp' is not recognized as an internal command", "YTDLP_MISSING"),
    # 24. YT_SERVER_5XX
    ("HTTP Error 503: Service Unavailable", "YT_SERVER_5XX"),
    ("502 Bad Gateway", "YT_SERVER_5XX"),
    # 25. UNSUPPORTED_URL
    ("Unsupported URL: https://invalid-domain.com", "UNSUPPORTED_URL"),
    ("Incomplete YouTube ID provided", "UNSUPPORTED_URL"),
    # 26. DISK_FULL
    ("[Errno 28] No space left on device", "DISK_FULL"),
    # 27. DISK_PERMISSION
    ("Permission denied: output.mp3", "DISK_PERMISSION"),
    ("WinError 5 Access is denied", "DISK_PERMISSION"),
    # 28. FILENAME_TOO_LONG
    ("[Errno 36] File name too long", "FILENAME_TOO_LONG"),
    ("WinError 206 The filename or extension is too long", "FILENAME_TOO_LONG"),
    # 29. NET_SSL
    ("SSLError: Certificate verify failed", "NET_SSL"),
    # 30. NET_PROXY
    ("ProxyError: Unable to connect to proxy", "NET_PROXY"),
    # 31. NET_TIMEOUT
    ("ConnectTimeout: connection timed out", "NET_TIMEOUT"),
    ("連線逾時", "NET_TIMEOUT"),
    # 32. NET_RESET
    ("ConnectionResetError: Connection reset by peer", "NET_RESET"),
    ("Connection aborted", "NET_RESET"),
    # 33. NET_OFFLINE
    ("[Errno 11001] getaddrinfo failed", "NET_OFFLINE"),
    ("Network is unreachable", "NET_OFFLINE"),
    # Special cases: empty string, None, unknown
    ("", "EMPTY_ERROR"),
    (None, "EMPTY_ERROR"),
    ("   ", "EMPTY_ERROR"),
    ("some completely arbitrary unrecognized error string", "UNKNOWN_ERROR"),
]


@pytest.mark.parametrize("error_input, expected_code", ERROR_CASES)
def test_analyze_error_codes(error_input, expected_code):
    """Verify that raw error strings match the correct diagnostic codes."""
    diag = analyze_error(error_input)
    assert diag.code == expected_code


def test_priority_age_restriction_over_login_required():
    """Verify that age restriction strings are not preempted by generic login required."""
    text = "Sign in to confirm your age"
    diag = analyze_error(text)
    assert diag.code == "YT_AGE_RESTRICTED"
    assert diag.code != "YT_LOGIN_REQUIRED"


def test_priority_bot_check_over_login_required():
    """Verify that bot check strings are not preempted by generic login required."""
    text = "Sign in to confirm you're not a bot"
    diag = analyze_error(text)
    assert diag.code == "YT_BOT_CHECK"
    assert diag.code != "YT_LOGIN_REQUIRED"


def test_clean_excerpt_truncation():
    """Verify that error messages exceeding the 220 character limit are properly truncated."""
    long_error = "x " * 150  # 300 characters
    diag = analyze_error(long_error)
    single_line = " ".join(long_error.split())
    expected = single_line[:220] + "..."
    assert diag.raw_excerpt == expected


def test_is_local_cookie_error():
    """Verify that is_local_cookie_error is True for local cookie issues and False otherwise."""
    # Local cookie errors
    assert is_local_cookie_error("Could not copy Chrome cookie database")
    assert is_local_cookie_error("failed to decrypt with DPAPI")
    assert is_local_cookie_error("could not find chrome cookies database")

    # False for YT_BOT_CHECK
    assert not is_local_cookie_error("Sign in to confirm you're not a bot")
    assert not is_local_cookie_error("Sign in to confirm you’re not a bot")

    # False for other error categories
    assert not is_local_cookie_error("HTTP Error 404")
    assert not is_local_cookie_error("")
    assert not is_local_cookie_error(None)


def test_error_rules_content_and_no_assist_fix():
    """Verify that every defined rule has non-empty fields and does not contain obsolete wording."""
    for rule in ERROR_RULES:
        assert rule.code and rule.code.strip()
        assert rule.category and rule.category.strip()
        assert rule.title and rule.title.strip()
        assert rule.detail and rule.detail.strip()
        assert rule.suggestion and rule.suggestion.strip()

        assert "協助與修復" not in rule.title
        assert "協助與修復" not in rule.detail
        assert "協助與修復" not in rule.suggestion
