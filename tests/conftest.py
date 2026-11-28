# -*- coding: utf-8 -*-
"""
Pytest configuration and isolation fixtures for EasyMusicDL.
Provides path isolation, offline guard against network/yt-dlp execution,
and boundary verification fixtures.
"""

from pathlib import Path
import socket
import sys
import types

import pytest

from ytdlp_gui.core import ytdlp_wrapper


class OfflineViolation(RuntimeError):
    """Raised when an unmocked network or yt-dlp operation is attempted in offline tests."""


# Preserve original references at module import time for verification in network tests
_ORIGINAL_EXTRACT_INFO = ytdlp_wrapper.extract_info
_ORIGINAL_DOWNLOAD = ytdlp_wrapper.download
_ORIGINAL_SEARCH_YOUTUBE = ytdlp_wrapper.search_youtube


@pytest.fixture
def original_wrapper_functions() -> types.SimpleNamespace:
    """Fixture providing original references to ytdlp_wrapper functions."""
    return types.SimpleNamespace(
        extract_info=_ORIGINAL_EXTRACT_INFO,
        download=_ORIGINAL_DOWNLOAD,
        search_youtube=_ORIGINAL_SEARCH_YOUTUBE,
    )


@pytest.fixture
def offline_violation():
    """Fixture providing the OfflineViolation exception class."""
    return OfflineViolation


@pytest.fixture
def real_bin_dir() -> Path:
    """Return the real repository root bin directory (<repo_root>/bin)."""
    return Path(__file__).resolve().parent.parent / "bin"


@pytest.fixture(autouse=True)
def app_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Autouse fixture that isolates application paths to a temporary root directory.
    Applied to both offline and network tests.
    """
    fake_root = (tmp_path / "app_root").resolve()
    fake_root.mkdir(parents=True, exist_ok=True)

    fake_downloads = (tmp_path / "downloads").resolve()
    fake_downloads.mkdir(parents=True, exist_ok=True)

    # 1. Isolate paths module via monkeypatching __file__
    fake_paths_file = fake_root / "src" / "ytdlp_gui" / "utils" / "paths.py"
    fake_paths_file.parent.mkdir(parents=True, exist_ok=True)
    fake_paths_file.touch()

    import ytdlp_gui.utils.paths as paths_mod
    monkeypatch.setattr(paths_mod, "__file__", str(fake_paths_file))
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    # 2. Isolate get_default_downloads_dir across all modules that import it
    downloads_getter = lambda: fake_downloads
    monkeypatch.setattr(paths_mod, "get_default_downloads_dir", downloads_getter)

    import ytdlp_gui.core.settings_manager as sm_mod
    monkeypatch.setattr(sm_mod, "get_default_downloads_dir", downloads_getter)

    import ytdlp_gui.utils.logger as logger_mod
    monkeypatch.setattr(logger_mod, "get_default_downloads_dir", downloads_getter)

    import ytdlp_gui.core.binary_manager as bm_mod
    monkeypatch.setattr(bm_mod, "get_default_downloads_dir", downloads_getter)

    # 3. Change working directory to tmp_path so CookieManager does not see repo cookies.txt
    monkeypatch.chdir(tmp_path)

    # 4. Clear proxy environment variables
    for var in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.delenv(var, raising=False)

    return fake_root


@pytest.fixture(autouse=True)
def offline_guard(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """
    Autouse fixture that blocks socket network calls and yt-dlp wrapper functions
    in offline tests (tests without the 'network' marker).
    """
    if request.node.get_closest_marker("network"):
        return

    def _violation(*args, **kwargs):
        raise OfflineViolation("Network call or yt-dlp execution attempted in offline test")

    # yt-dlp wrapper functions
    monkeypatch.setattr(ytdlp_wrapper, "extract_info", _violation)
    monkeypatch.setattr(ytdlp_wrapper, "download", _violation)
    monkeypatch.setattr(ytdlp_wrapper, "search_youtube", _violation)

    # socket calls
    monkeypatch.setattr(socket.socket, "connect", _violation)
    monkeypatch.setattr(socket.socket, "connect_ex", _violation)
    monkeypatch.setattr(socket, "create_connection", _violation)
    monkeypatch.setattr(socket, "getaddrinfo", _violation)


@pytest.fixture(autouse=True)
def process_tracker_instance(monkeypatch: pytest.MonkeyPatch):
    """
    Autouse fixture providing an isolated ProcessTracker for each test.
    Shuts down and cleans up any remaining child processes after the test.
    """
    from ytdlp_gui.core import process_tracker
    from ytdlp_gui.core.process_tracker import ProcessTracker

    tracker_instance = ProcessTracker()
    monkeypatch.setattr(process_tracker, "tracker", tracker_instance)
    yield tracker_instance
    tracker_instance.shutdown()
