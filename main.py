#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
輕鬆聽音樂下載器 (EasyMusicDL) - Portable Entry Point
"""

import logging
import os
import sys
import threading
from pathlib import Path

STARTUP_COMPLETE = False
STARTUP_TIMEOUT_S = 20


def setup_paths():
    """Configure module search path and prepend portable bin/ to PATH."""
    if getattr(sys, "frozen", False):
        app_path = Path(sys.executable).resolve().parent
    else:
        app_path = Path(__file__).resolve().parent

    src_path = app_path / "src"
    if src_path.exists() and str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    elif str(app_path) not in sys.path:
        sys.path.insert(0, str(app_path))

    bin_path = app_path / "bin"
    if bin_path.exists():
        os.environ["PATH"] = str(bin_path) + os.pathsep + os.environ.get("PATH", "")


setup_paths()

try:
    from ytdlp_gui.gui.main_window import YTDLPGUIApp
    from ytdlp_gui.main import run_self_update_test, run_startup_bootstrap_ui
    from ytdlp_gui.utils.logger import flush_logs, get_log_manager, log_startup_environment
    from ytdlp_gui.utils.paths import get_logs_dir
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)


def watchdog():
    """Show a Traditional Chinese system dialog if GUI initialization hangs."""
    if STARTUP_COMPLETE:
        return
    log_dir = get_logs_dir()
    message = (
        f"程式啟動超過 {STARTUP_TIMEOUT_S} 秒仍未出現主視窗。\n\n"
        "可能是防毒軟體正在掃描或資料夾存取受阻。\n\n"
        f"查修紀錄位置：{log_dir}\n\n"
        "您可以先從工作管理員結束程式後再試一次。"
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            message,
            "輕鬆聽音樂下載器 - 啟動異常提醒",
            0x10 | 0x1000,
        )
    except Exception:
        pass


def main():
    """Start the application with automatic 3-stage environment check -> download -> verify."""
    if "--self-update-test" in sys.argv:
        sys.exit(run_self_update_test())
    try:
        get_log_manager()
        log_startup_environment()
        report = run_startup_bootstrap_ui()
        if not report or not report.ok:
            logging.warning("啟動環境檢查未通過或被使用者取消，結束程式")
            flush_logs()
            sys.exit(1)

        global STARTUP_COMPLETE
        timer = threading.Timer(STARTUP_TIMEOUT_S, watchdog)
        timer.daemon = True
        timer.start()

        app = YTDLPGUIApp(bootstrap_report=report)
        STARTUP_COMPLETE = True
        flush_logs()
        app.run()
    except Exception as e:
        logging.error("應用程式啟動失敗: %s", e, exc_info=True)
        flush_logs()
        sys.exit(1)


if __name__ == "__main__":
    main()
