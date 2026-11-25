# -*- coding: utf-8 -*-
"""Portable path helpers and Windows Downloads directory resolution."""

import os
import sys
import uuid
import ctypes
from pathlib import Path


_FOLDERID_DOWNLOADS = "{374DE290-123F-4565-9164-39C4925E467B}"


def get_app_root() -> Path:
    """Return the portable root directory beside the executable or repo root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def get_resource_path(relative_path: str) -> Path:
    """Resolve bundled read-only assets in both frozen and source runs."""
    rel = Path(relative_path)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass_candidate = Path(sys._MEIPASS) / rel
        if meipass_candidate.exists():
            return meipass_candidate

    root = get_app_root()
    for base in (root, root / "src"):
        candidate = base / rel
        if candidate.exists():
            return candidate
    return root / rel


def get_bin_dir() -> Path:
    """Return portable bin directory (<app_root>/bin) for yt-dlp, ffmpeg, deno."""
    bin_dir = get_app_root() / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    return bin_dir


def get_data_dir() -> Path:
    """Return portable data directory (<app_root>/data) for settings and history."""
    data_dir = get_app_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_logs_dir() -> Path:
    """Return portable logs directory (<app_root>/logs)."""
    logs_dir = get_app_root() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_default_downloads_dir() -> Path:
    """Return the system default Downloads folder (Windows KnownFolder with fallback)."""
    downloads_path = None
    if os.name == "nt":
        try:
            class _GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            uid = uuid.UUID(_FOLDERID_DOWNLOADS)
            guid = _GUID(
                uid.time_low,
                uid.time_mid,
                uid.time_hi_version,
                (ctypes.c_ubyte * 8)(*uid.bytes[8:]),
            )
            path_ptr = ctypes.c_wchar_p()
            hr = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(path_ptr)
            )
            if hr == 0 and path_ptr.value:
                downloads_path = Path(path_ptr.value)
            if path_ptr:
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
        except Exception:
            downloads_path = None

    if downloads_path is None:
        downloads_path = Path.home() / "Downloads"

    try:
        downloads_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        fallback = Path.home() / "Downloads"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    return downloads_path


def is_dir_writable(path: Path) -> bool:
    """Verify a directory exists and accepts file writes."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_check.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False
