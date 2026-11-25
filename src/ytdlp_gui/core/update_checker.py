# -*- coding: utf-8 -*-
"""
Update Checker - Upstream self-overwrite disabled for custom elderly edition.
Engine updates (yt-dlp/FFmpeg/Deno) are managed safely by binary_manager.
"""

import logging
from typing import Dict, Optional

from ytdlp_gui import __version__


class UpdateChecker:
    """No-op app self-updater to prevent overwriting custom UI with upstream build."""

    def __init__(self, settings_manager=None):
        self.logger = logging.getLogger(__name__)
        self._settings = settings_manager

    def is_frozen(self) -> bool:
        return False

    def check(self) -> Optional[Dict]:
        return {
            "available": False,
            "current_version": __version__,
            "disabled": True,
        }

    def download_update(self, *args, **kwargs) -> Optional[str]:
        return None

    def apply_update(self, *args, **kwargs) -> None:
        return None
