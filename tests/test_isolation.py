# -*- coding: utf-8 -*-
"""
Tests verifying offline test isolation boundaries:
1. File paths are isolated to the temporary fake app root.
2. SettingsManager uses the isolated paths.
3. Network operations and yt-dlp wrapper functions trigger OfflineViolation.
"""

from pathlib import Path
import socket
import pytest

from ytdlp_gui.core import ytdlp_wrapper
from ytdlp_gui.core.settings_manager import SettingsManager
from ytdlp_gui.utils import paths


def test_paths_isolated_to_app_root(app_root: Path):
    """Verify that get_app_root, get_data_dir, get_logs_dir, and get_bin_dir point inside app_root."""
    assert paths.get_app_root() == app_root
    assert paths.get_data_dir().is_relative_to(app_root)
    assert paths.get_logs_dir().is_relative_to(app_root)
    assert paths.get_bin_dir().is_relative_to(app_root)


def test_settings_manager_isolation(app_root: Path, tmp_path: Path):
    """Verify that SettingsManager uses isolated directories and defaults output to tmp_path."""
    sm = SettingsManager()
    assert sm.settings_dir.is_relative_to(app_root)

    output_dir = Path(sm.get("output_directory"))
    assert output_dir.is_relative_to(tmp_path)
    assert Path(sm.get_output_directory()).is_relative_to(tmp_path)


def test_offline_guard_blocks_wrapper_functions(offline_violation):
    """Verify that ytdlp_wrapper functions are blocked by default in offline tests."""
    with pytest.raises(offline_violation):
        ytdlp_wrapper.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    with pytest.raises(offline_violation):
        ytdlp_wrapper.download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "dummy_output.mp3",
            "bestaudio/best",
        )

    with pytest.raises(offline_violation):
        ytdlp_wrapper.search_youtube("never gonna give you up")


def test_offline_guard_blocks_socket_connections(offline_violation):
    """Verify that socket network calls are blocked by default in offline tests."""
    with pytest.raises(offline_violation):
        socket.create_connection(("127.0.0.1", 80))

    with pytest.raises(offline_violation):
        socket.getaddrinfo("localhost", 80)

    s = socket.socket()
    try:
        with pytest.raises(offline_violation):
            s.connect(("127.0.0.1", 80))
        with pytest.raises(offline_violation):
            s.connect_ex(("127.0.0.1", 80))
    finally:
        s.close()
