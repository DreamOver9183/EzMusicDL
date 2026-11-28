# -*- coding: utf-8 -*-
"""
Logger & Troubleshooting Diagnostic Helpers
"""

from datetime import datetime
import logging
import logging.handlers
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlsplit

from .paths import (
    get_app_root,
    get_bin_dir,
    get_data_dir,
    get_default_downloads_dir,
    get_logs_dir,
)


class ColoredFormatter(logging.Formatter):
    """Colored console formatter."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
        "RESET": "\033[0m",
    }

    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            record = logging.makeLogRecord(record.__dict__)
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        return super().format(record)


class LogManager:
    """Manages portable UTF-8 application logging and latest.log."""

    def __init__(self, app_name: str = "yt-dlp-gui", log_dir: Optional[Path] = None):
        self.app_name = app_name
        self.log_dir = Path(log_dir) if log_dir else get_logs_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.latest_log_file = self.log_dir / "latest.log"
        self.app_log_file = self.log_dir / "app.log"
        self.error_log_file = self.log_dir / "error.log"
        self.download_log_file = self.log_dir / "downloads.log"

        self.setup_logging()

    def setup_logging(self):
        """Set up file and console logging handlers."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        for handler in list(root_logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
        root_logger.handlers.clear()

        if sys.stdout is not None:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(
                ColoredFormatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            root_logger.addHandler(console_handler)

        # Fresh single-session log for quick remote troubleshooting
        latest_handler = logging.FileHandler(
            self.latest_log_file, mode="w", encoding="utf-8"
        )
        latest_handler.setLevel(logging.INFO)
        latest_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(latest_handler)

        app_handler = logging.handlers.RotatingFileHandler(
            self.app_log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        app_handler.setLevel(logging.DEBUG)
        app_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(app_handler)

        error_handler = logging.handlers.RotatingFileHandler(
            self.error_log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s\n"
                "Exception: %(exc_info)s\n" + "-" * 80,
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(error_handler)

        download_logger = logging.getLogger("downloads")
        for handler in list(download_logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
        download_logger.handlers.clear()
        download_handler = logging.handlers.RotatingFileHandler(
            self.download_log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        download_handler.setLevel(logging.INFO)
        download_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        download_logger.addHandler(download_handler)
        download_logger.propagate = False

        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("yt_dlp").setLevel(logging.WARNING)

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)

    def get_download_logger(self) -> logging.Logger:
        return logging.getLogger("downloads")


_log_manager: Optional[LogManager] = None


def get_log_manager() -> LogManager:
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager()
    return _log_manager


def init_logging(app_name: str = "yt-dlp-gui", log_dir: Optional[Path] = None) -> LogManager:
    global _log_manager
    if _log_manager is not None and log_dir is None:
        return _log_manager
    _log_manager = LogManager(app_name, log_dir)
    return _log_manager


def get_logger(name: str) -> logging.Logger:
    return get_log_manager().get_logger(name)


def flush_logs():
    """Flush all file log handlers (root and downloads) to disk."""
    for target_logger in (logging.getLogger(), logging.getLogger("downloads")):
        for handler in list(target_logger.handlers):
            if isinstance(handler, logging.FileHandler):
                try:
                    handler.flush()
                except Exception:
                    pass


def log_download_event(event_type: str, url: str, details: str = ""):
    """Log a download-specific event."""
    download_logger = get_log_manager().get_download_logger()
    message = f"[{event_type}] {url}"
    if details:
        message += f" - {details}"
    download_logger.info(message)


def _sanitize_proxy_url(raw_url: str) -> str:
    """Return scheme://host:port without embedding credentials."""
    try:
        parsed = urlsplit(raw_url.strip())
        if not parsed.hostname:
            return "(已設定，格式非標準 URL)"
        host = parsed.hostname
        port = f":{parsed.port}" if parsed.port else ""
        scheme = f"{parsed.scheme}://" if parsed.scheme else ""
        return f"{scheme}{host}{port}"
    except Exception:
        return "(已設定)"


def get_proxy_summary() -> str:
    """Describe proxy environment variables without exposing any credentials."""
    found: List[str] = []
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        val = os.environ.get(key, "").strip()
        if val:
            found.append(f"{key}={_sanitize_proxy_url(val)}")
    return ", ".join(found) if found else "無"


def _get_os_summary() -> str:
    base = platform.platform()
    if platform.system() == "Windows":
        try:
            ver = sys.getwindowsversion()
            return f"{base} (build {ver.build}, arch={platform.machine()})"
        except Exception:
            pass
    return f"{base} (arch={platform.machine()})"


def _get_disk_free_str(path: Path) -> str:
    try:
        target = path if path.exists() else path.parent
        usage = shutil.disk_usage(target)
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        return f"{free_gb:.2f} GB 可用 / 共 {total_gb:.2f} GB"
    except Exception as e:
        return f"無法取得 ({e})"


def _get_cookie_diag_summary() -> Dict[str, object]:
    """Safely inspect cookies.txt presence and browser profile availability (never reads cookie contents)."""
    try:
        from ytdlp_gui.core.cookie_manager import CookieManager
        from ytdlp_gui.core.settings_manager import SettingsManager

        settings = SettingsManager()
        cm = CookieManager(settings)
        return cm.get_diagnostic_summary()
    except Exception as e:
        return {"error": str(e)}


def log_startup_environment(extra_info: Optional[Dict[str, str]] = None) -> None:
    """Write structured startup environment diagnostics to app/latest logs once."""
    startup_logger = logging.getLogger("ytdlp_gui.startup")
    try:
        from ytdlp_gui import __version__
    except Exception:
        __version__ = "unknown"

    app_root = get_app_root()
    bin_dir = get_bin_dir()
    data_dir = get_data_dir()
    logs_dir = get_logs_dir()
    downloads_dir = get_default_downloads_dir()
    mode = "免安裝執行檔" if getattr(sys, "frozen", False) else "Python 原始碼"

    startup_logger.info("=== EasyMusicDL 啟動環境摘要 ===")
    startup_logger.info("版本: %s | 執行模式: %s | Python: %s", __version__, mode, platform.python_version())
    startup_logger.info("作業系統: %s", _get_os_summary())
    startup_logger.info("程式位置: %s", app_root)
    startup_logger.info("目錄配置: bin=%s | data=%s | logs=%s", bin_dir, data_dir, logs_dir)
    startup_logger.info("預設下載資料夾: %s (%s)", downloads_dir, _get_disk_free_str(downloads_dir))
    startup_logger.info("環境變數 Proxy: %s", get_proxy_summary())

    cookie_summary = _get_cookie_diag_summary()
    if "error" in cookie_summary:
        startup_logger.info("Cookie 環境檢查失敗: %s", cookie_summary["error"])
    else:
        files = cookie_summary.get("cookies_files") or []
        files_desc = (
            ", ".join(f"{f['path']} ({f['size']} bytes)" for f in files)
            if files
            else "無"
        )
        browsers = cookie_summary.get("browsers") or {}
        browsers_desc = ", ".join(f"{k}={'有' if v else '無'}" for k, v in browsers.items())
        startup_logger.info(
            "Cookie 環境: cookies_enabled=%s | cookies.txt=%s | 本機瀏覽器=[%s]",
            cookie_summary.get("cookies_enabled"),
            files_desc,
            browsers_desc,
        )

    if extra_info:
        for k, v in extra_info.items():
            startup_logger.info("%s: %s", k, v)
    flush_logs()


def _append_log_tail(lines: List[str], header: str, path: Path, tail_count: int) -> None:
    if not path.exists():
        return
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        lines.append("")
        lines.append(header)
        lines.append(f"(無法讀取 {path.name}: {e})")
        return
    if not content:
        return
    lines.append("")
    lines.append(header)
    lines.extend(content[-tail_count:])


def get_diagnostic_report(extra_info: Optional[Dict[str, str]] = None) -> str:
    """Build a comprehensive plain-text diagnostic report for support troubleshooting."""
    flush_logs()
    try:
        from ytdlp_gui import __version__
    except Exception:
        __version__ = "unknown"

    logs_dir = get_logs_dir()
    lines = [
        "=== EasyMusicDL 音樂下載工具 診斷紀錄 ===",
        f"產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"程式版本: {__version__}",
        f"執行模式: {'免安裝執行檔' if getattr(sys, 'frozen', False) else 'Python 原始碼'}",
        f"Python 版本: {platform.python_version()}",
        f"作業系統: {_get_os_summary()}",
        f"程式位置: {get_app_root()}",
        f"環境變數 Proxy: {get_proxy_summary()}",
    ]
    if extra_info:
        for k, v in extra_info.items():
            lines.append(f"{k}: {v}")

    latest_path = logs_dir / "latest.log"
    lines.append("")
    lines.append("--- 最近操作紀錄 (logs/latest.log 末 150 行) ---")
    if latest_path.exists():
        try:
            content = latest_path.read_text(encoding="utf-8", errors="replace").splitlines()
            lines.extend(content[-150:])
        except Exception as e:
            lines.append(f"(無法讀取 latest.log: {e})")
    else:
        lines.append("(尚無 latest.log)")

    _append_log_tail(
        lines,
        "--- 錯誤紀錄摘要 (logs/error.log 末 30 行) ---",
        logs_dir / "error.log",
        30,
    )
    _append_log_tail(
        lines,
        "--- 下載紀錄摘要 (logs/downloads.log 末 15 行) ---",
        logs_dir / "downloads.log",
        15,
    )
    _append_log_tail(
        lines,
        "--- 應用程式更新紀錄 (logs/updater.log 末 40 行) ---",
        logs_dir / "updater.log",
        40,
    )

    return "\n".join(lines)
