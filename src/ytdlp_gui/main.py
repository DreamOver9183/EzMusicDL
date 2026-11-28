# -*- coding: utf-8 -*-
"""
Package Entry Point & Native Win11 3-Stage Startup Environment Check Splash UI.
"""

import logging
import os
import re
import sys
import threading
from typing import Callable, Optional

from .core import binary_manager
from .gui.main_window import YTDLPGUIApp
from .gui.theme import apply_windows_titlebar
from .utils.logger import flush_logs, get_log_manager, log_startup_environment
from .utils.paths import get_logs_dir, get_resource_path

FONT_FAMILY = "Microsoft JhengHei UI"


def run_startup_bootstrap_ui() -> Optional[binary_manager.BootstrapReport]:
    """
    Show a clean native Windows splash window running:
    1. 檢查環境與引擎更新
    2. 下載與更新元件
    3. 二次檢查與驗證環境
    """
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("音樂下載工具 - 啟動檢查")
    root.geometry("520x250")
    root.resizable(False, False)
    root.configure(bg="#F3F3F3")

    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"520x250+{(sw - 520) // 2}+{(sh - 250) // 2}")
    apply_windows_titlebar(root, "light")

    try:
        ico_path = get_resource_path("assets/icon.ico")
        if ico_path.exists():
            root.iconbitmap(str(ico_path))
    except Exception:
        pass

    card = tk.Frame(
        root,
        bg="#FFFFFF",
        highlightbackground="#E2E2E2",
        highlightthickness=1,
    )
    card.pack(fill="both", expand=True, padx=16, pady=16)

    tk.Label(
        card,
        text="音樂下載工具",
        fg="#1A1A1A",
        bg="#FFFFFF",
        font=(FONT_FAMILY, 16, "bold"),
    ).pack(pady=(20, 6))

    stage_lbl = tk.Label(
        card,
        text="步驟 1/3：檢查環境與引擎更新",
        fg="#0F6B4A",
        bg="#FFFFFF",
        font=(FONT_FAMILY, 12, "bold"),
    )
    stage_lbl.pack(pady=(2, 4))

    detail_lbl = tk.Label(
        card,
        text="正在自動確認下載與轉檔元件狀態，請稍候...",
        fg="#525252",
        bg="#FFFFFF",
        font=(FONT_FAMILY, 10),
        wraplength=450,
        justify="center",
    )
    detail_lbl.pack(pady=(0, 14))

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(
        "FluentGreen.Horizontal.TProgressbar",
        troughcolor="#E2E2E2",
        background="#0F6B4A",
        bordercolor="#E2E2E2",
        lightcolor="#0F6B4A",
        darkcolor="#0F6B4A",
        thickness=10,
    )

    progress = ttk.Progressbar(
        card,
        mode="determinate",
        length=420,
        style="FluentGreen.Horizontal.TProgressbar",
    )
    progress.pack(pady=(0, 14))

    err_frame = tk.Frame(card, bg="#FFFFFF")
    result_holder: dict = {"report": None, "cancelled": False}

    def on_close():
        result_holder["cancelled"] = True
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    def _start_bootstrap():
        for w in err_frame.winfo_children():
            w.destroy()
        err_frame.pack_forget()
        progress["value"] = 4
        stage_lbl.config(text="步驟 1/3：檢查環境與引擎更新", fg="#0F6B4A")
        detail_lbl.config(text="正在檢查 yt-dlp、FFmpeg 與下載資料夾...", fg="#525252")

        def _on_progress(stage_num: int, stage_title: str, detail: str, pct: int):
            def _ui():
                if not root.winfo_exists():
                    return
                stage_lbl.config(text=f"步驟 {stage_num}/3：{stage_title}")
                detail_lbl.config(text=detail)
                progress["value"] = pct

            root.after(0, _ui)

        def _worker():
            report = binary_manager.run_environment_bootstrap(progress_callback=_on_progress)
            flush_logs()
            root.after(0, lambda: _on_complete(report))

        threading.Thread(target=_worker, daemon=True).start()

    def _open_logs():
        if os.name == "nt":
            os.startfile(str(get_logs_dir()))

    def _on_complete(report: binary_manager.BootstrapReport):
        if not root.winfo_exists():
            return
        result_holder["report"] = report
        if report.ok:
            progress["value"] = 100
            stage_lbl.config(text="環境檢查與二次驗證完成", fg="#0F6B4A")
            detail_lbl.config(
                text=f"yt-dlp {report.ytdlp_version} · FFmpeg 就緒 · 正在開啟主視窗",
                fg="#1A1A1A",
            )
            root.after(300, root.destroy)
        else:
            stage_lbl.config(text="啟動檢查未通過", fg="#B42318")
            detail_lbl.config(text=report.error_message, fg="#B42318")
            err_frame.pack(pady=(2, 10))
            tk.Button(
                err_frame,
                text="重試檢查",
                font=(FONT_FAMILY, 10, "bold"),
                bg="#0F6B4A",
                fg="#FFFFFF",
                relief="flat",
                padx=14,
                pady=6,
                command=_start_bootstrap,
            ).pack(side="left", padx=5)
            tk.Button(
                err_frame,
                text="開啟紀錄資料夾",
                font=(FONT_FAMILY, 10, "bold"),
                bg="#FFFFFF",
                fg="#1A1A1A",
                relief="solid",
                bd=1,
                padx=12,
                pady=6,
                command=_open_logs,
            ).pack(side="left", padx=5)
            tk.Button(
                err_frame,
                text="關閉",
                font=(FONT_FAMILY, 10),
                bg="#FFFFFF",
                fg="#1A1A1A",
                relief="solid",
                bd=1,
                padx=12,
                pady=6,
                command=on_close,
            ).pack(side="left", padx=5)

    _start_bootstrap()
    root.mainloop()

    if result_holder["cancelled"]:
        return None
    report = result_holder["report"]
    return report if (report and report.ok) else None


def make_progress_logger(logger: logging.Logger) -> Callable[[str, float], None]:
    """Throttle progress callbacks to log only upon stage transitions or crossing 10% steps."""
    last_stage: Optional[str] = None
    last_step: int = -1

    def _on_progress(msg: str, pct: float) -> None:
        nonlocal last_stage, last_step
        stage = re.sub(r"\d+", "", msg or "").strip()
        step = int(pct * 10)
        if stage != last_stage or step > last_step:
            last_stage = stage
            last_step = step
            logger.info("[SELF_UPDATE_TEST] 下載進度 %d%%: %s", int(pct * 100), msg)

    return _on_progress


def run_self_update_test() -> int:
    """Headless E2E hook (--self-update-test) to exercise portable self-update end-to-end."""
    from . import __version__
    from .core.settings_manager import SettingsManager
    from .core.update_checker import UpdateChecker

    get_log_manager()
    log_startup_environment({"RunMode": "self-update-test"})
    logger = logging.getLogger("ytdlp_gui.self_update_test")

    settings = SettingsManager()
    checker = UpdateChecker(settings)
    logger.info(
        "[SELF_UPDATE_TEST] 開始檢查更新 (version=%s, frozen=%s, app_root=%s, repo=%s)",
        __version__,
        checker.is_frozen(),
        checker.get_app_root(),
        checker.repo,
    )

    info = checker.check(force=True)
    logger.info(
        "[SELF_UPDATE_TEST] 檢查結果: status=%s | available=%s | current=%s | latest=%s | asset=%s | checksum=%s",
        info.get("status"),
        info.get("available"),
        info.get("current_version"),
        info.get("latest_version"),
        info.get("asset_name"),
        bool(info.get("checksum_url")),
    )

    if not info.get("available"):
        logger.info("[SELF_UPDATE_TEST] 無須更新或無可用更新 (status=%s)", info.get("status"))
        flush_logs()
        return 0

    _on_progress = make_progress_logger(logger)
    prepared = checker.download_update(info, progress_callback=_on_progress)
    if not prepared.get("ok"):
        logger.error("[SELF_UPDATE_TEST] 下載或驗證更新失敗: %s", prepared.get("error"))
        flush_logs()
        return 2

    if not checker.is_frozen():
        logger.info("[SELF_UPDATE_TEST] 非冷凍執行檔（原始碼模式），略過實際檔案替換")
        flush_logs()
        return 0

    applied = checker.apply_update(prepared)
    if not applied:
        logger.error("[SELF_UPDATE_TEST] 啟動背景更新程式失敗")
        flush_logs()
        return 3

    logger.info("[SELF_UPDATE_TEST] 更新背景程序已啟動，即將結束舊版程式以完成替換與重啟")
    flush_logs()
    return 0


def main():
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
        app = YTDLPGUIApp(bootstrap_report=report)
        app.run()
    except Exception as e:
        logging.error("啟動失敗: %s", e, exc_info=True)
        flush_logs()
        sys.exit(1)


if __name__ == "__main__":
    main()
