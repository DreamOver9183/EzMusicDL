# -*- coding: utf-8 -*-
"""
Tests verifying privacy protection in logger and diagnostic reports:
1. Proxy URLs are sanitized to strip usernames and passwords.
2. Startup environment logs and diagnostic reports never leak cookie contents, proxy usernames, or passwords.
3. Diagnostic reports aggregate log tail excerpts and drop earlier entries when exceeding line limits.
"""

import logging
from pathlib import Path
import uuid
import pytest

from ytdlp_gui.utils import paths
from ytdlp_gui.utils.logger import (
    _sanitize_proxy_url,
    get_diagnostic_report,
    log_startup_environment,
)


def test_sanitize_proxy_url():
    """Verify proxy URL sanitization strips credentials across various URL formats."""
    user = f"user_{uuid.uuid4().hex[:8]}"
    password = f"pass_{uuid.uuid4().hex[:8]}"
    host = "proxy.example.invalid"

    # With credentials
    raw_url = f"http://{user}:{password}@{host}:8080"
    sanitized = _sanitize_proxy_url(raw_url)
    assert user not in sanitized
    assert password not in sanitized
    assert sanitized == f"http://{host}:8080"

    # Without credentials
    no_cred_url = f"http://{host}:3128"
    assert _sanitize_proxy_url(no_cred_url) == f"http://{host}:3128"

    no_port_url = f"https://{host}"
    assert _sanitize_proxy_url(no_port_url) == f"https://{host}"

    # Non-standard format
    assert _sanitize_proxy_url("not_a_valid_url") == "(已設定，格式非標準 URL)"
    assert _sanitize_proxy_url("http://:8080") == "(已設定，格式非標準 URL)"


def test_startup_environment_and_diagnostic_report_privacy(
    app_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """Verify that startup logs and diagnostic reports never reveal cookie secrets or proxy credentials."""
    cookie_secret = f"secret_cookie_token_{uuid.uuid4().hex}"
    proxy_user = f"puser_{uuid.uuid4().hex[:8]}"
    proxy_pass = f"ppass_{uuid.uuid4().hex[:8]}"
    proxy_host = "proxy.example.invalid"
    proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:8080"

    # Write fake cookies in app_root / data / cookies.txt
    cookie_file = app_root / "data" / "cookies.txt"
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    cookie_file.write_text(
        f"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\t{cookie_secret}\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HTTP_PROXY", proxy_url)

    # 1. log_startup_environment with caplog on ytdlp_gui.startup
    with caplog.at_level(logging.INFO, logger="ytdlp_gui.startup"):
        log_startup_environment()

    startup_logs = caplog.text
    assert cookie_secret not in startup_logs
    assert proxy_user not in startup_logs
    assert proxy_pass not in startup_logs
    assert proxy_host in startup_logs
    assert str(cookie_file) in startup_logs

    # 2. get_diagnostic_report
    report = get_diagnostic_report()
    assert cookie_secret not in report
    assert proxy_user not in report
    assert proxy_pass not in report
    assert proxy_host in report


def test_diagnostic_report_log_tails(app_root: Path):
    """Verify that diagnostic report includes tail excerpts from logs and truncates earliest latest.log lines."""
    logs_dir = paths.get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)

    marker_error = f"error_marker_{uuid.uuid4().hex}"
    marker_downloads = f"download_marker_{uuid.uuid4().hex}"
    marker_updater = f"updater_marker_{uuid.uuid4().hex}"

    (logs_dir / "error.log").write_text(f"Line 1\n{marker_error}\n", encoding="utf-8")
    (logs_dir / "downloads.log").write_text(f"Line 1\n{marker_downloads}\n", encoding="utf-8")
    (logs_dir / "updater.log").write_text(f"Line 1\n{marker_updater}\n", encoding="utf-8")

    # latest.log tail limit is 150 lines
    earliest_line = f"earliest_marker_{uuid.uuid4().hex}"
    latest_tail_marker = f"latest_tail_marker_{uuid.uuid4().hex}"

    lines = [earliest_line] + [f"dummy log entry {i}" for i in range(1, 199)] + [latest_tail_marker]
    assert len(lines) == 200
    (logs_dir / "latest.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = get_diagnostic_report()

    assert marker_error in report
    assert marker_downloads in report
    assert marker_updater in report
    assert latest_tail_marker in report
    assert earliest_line not in report
