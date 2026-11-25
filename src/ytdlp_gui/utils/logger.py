# -*- coding: utf-8 -*-
"""
Logger & Troubleshooting Diagnostic Helpers
"""

import logging
import logging.handlers
import platform
import sys
from pathlib import Path
from typing import Dict, Optional

from .paths import get_app_root, get_logs_dir


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
    """Flush all file log handlers to disk."""
    for handler in logging.getLogger().handlers:
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


def get_diagnostic_report(extra_info: Optional[Dict[str, str]] = None) -> str:
    """Build a plain-text diagnostic report for copying to family/support."""
    flush_logs()
    try:
        from ytdlp_gui import __version__
    except Exception:
        __version__ = "unknown"

    lines = [
        "=== 輕鬆聽音樂下載器 查修紀錄 ===",
        f"程式版本: {__version__}",
        f"執行模式: {'免安裝執行檔' if getattr(sys, 'frozen', False) else 'Python 原始碼'}",
        f"作業系統: {platform.platform()}",
        f"程式位置: {get_app_root()}",
    ]
    if extra_info:
        for k, v in extra_info.items():
            lines.append(f"{k}: {v}")

    lines.append("")
    lines.append("--- 最近操作紀錄 (logs/latest.log 末 60 行) ---")
    latest_path = get_logs_dir() / "latest.log"
    if latest_path.exists():
        try:
            content = latest_path.read_text(encoding="utf-8", errors="replace").splitlines()
            lines.extend(content[-60:])
        except Exception as e:
            lines.append(f"(無法讀取 latest.log: {e})")
    else:
        lines.append("(尚無 latest.log)")

    return "\n".join(lines)
