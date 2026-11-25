# -*- coding: utf-8 -*-
"""
Portable Settings Manager - stores settings in <app_root>/data/settings.json
and defaults output_directory to the system Downloads folder.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict

from ytdlp_gui.utils.paths import get_data_dir, get_default_downloads_dir


def _write_json_with_timeout(path: Path, data: Dict[str, Any], timeout: float = 3.0) -> bool:
    """Write JSON to disk in a worker thread with a hard timeout."""
    result = [False]

    def _do_write():
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            result[0] = True
        except Exception:
            pass

    thread = threading.Thread(target=_do_write, daemon=True)
    thread.start()
    thread.join(timeout)
    return result[0]


class SettingsManager:
    """Portable settings manager."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.settings_dir = self._get_settings_directory()
        self.settings_file = self.settings_dir / "settings.json"
        self.DEFAULT_SETTINGS = {
            "output_directory": str(get_default_downloads_dir()),
            "max_concurrent_downloads": 2,
            "theme_mode": "light",
            "proxy_enabled": False,
            "proxy_url": "",
            "cookies_enabled": True,
            "cookies_browser": "chrome",
            "cookies_fallback_browsers": ["firefox", "edge", "chrome"],
            "notification_enabled": True,
        }
        self.settings = self.DEFAULT_SETTINGS.copy()

        self.settings_dir.mkdir(parents=True, exist_ok=True)
        self.load_settings()

    def _get_settings_directory(self) -> Path:
        """Store portable settings inside <app_root>/data."""
        return get_data_dir()

    def load_settings(self):
        """Load settings from file."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    saved_settings = json.load(f)
                self.settings.update(saved_settings)
                self.logger.info("已載入設定檔: %s", self.settings_file)
            else:
                self.logger.info("找不到設定檔，使用預設設定（存檔於 Downloads 資料夾）")
                self.save_settings()
        except Exception as e:
            self.logger.error("讀取設定檔失敗: %s", e)

    def save_settings(self):
        """Save current settings to file."""
        try:
            if not _write_json_with_timeout(self.settings_file, self.settings):
                self.logger.warning("設定檔寫入逾時，已略過")
                return
            self.logger.info("設定已儲存")
        except Exception as e:
            self.logger.error("儲存設定檔失敗: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        self.settings[key] = value

    def get_output_directory(self) -> str:
        """Return output directory; create or fall back to system Downloads."""
        output_dir = self.get("output_directory") or str(get_default_downloads_dir())
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            return str(Path(output_dir))
        except Exception as e:
            self.logger.warning("自訂下載路徑無法使用 (%s)，退回系統 Downloads: %s", output_dir, e)
            fallback = str(get_default_downloads_dir())
            self.set("output_directory", fallback)
            return fallback

    def reset_output_directory(self) -> str:
        """Reset output directory back to system default Downloads."""
        default_dir = str(get_default_downloads_dir())
        self.set("output_directory", default_dir)
        self.save_settings()
        return default_dir

    def get_network_settings(self) -> Dict[str, Any]:
        return {
            "proxy_enabled": self.get("proxy_enabled"),
            "proxy_url": self.get("proxy_url"),
            "cookies_enabled": self.get("cookies_enabled"),
            "cookies_browser": self.get("cookies_browser"),
            "cookies_fallback_browsers": self.get("cookies_fallback_browsers"),
        }
