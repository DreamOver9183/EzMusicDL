# -*- coding: utf-8 -*-
"""
Settings, Diagnostics & Portable Self-Update Dialog - Native Fluent sections.
"""

import logging
import os
from pathlib import Path
import threading
from tkinter import filedialog, messagebox
from typing import Callable, Dict, Optional
import webbrowser

import customtkinter as ctk

from ytdlp_gui import __version__
from ytdlp_gui.core import binary_manager
from ytdlp_gui.core.cookie_manager import CookieManager
from ytdlp_gui.core.update_checker import UpdateChecker
from ytdlp_gui.gui.icons import get_icon
from ytdlp_gui.gui.theme import COLORS, RADIUS, apply_windows_titlebar, font
from ytdlp_gui.utils.logger import get_diagnostic_report
from ytdlp_gui.utils.paths import get_logs_dir


class HelpDialog(ctk.CTkToplevel):
    """Modal window for portable app updates, engine repair, save folder, and diagnostics."""

    def __init__(
        self,
        parent,
        settings_manager,
        on_path_changed: Optional[Callable[[str], None]] = None,
        on_engine_repaired: Optional[Callable[[binary_manager.BootstrapReport], None]] = None,
        update_checker: Optional[UpdateChecker] = None,
        initial_update_info: Optional[Dict] = None,
        download_manager=None,
        on_app_exit_for_update: Optional[Callable[[], None]] = None,
        on_update_checked: Optional[Callable[[Dict], None]] = None,
    ):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.settings_manager = settings_manager
        self.on_path_changed = on_path_changed
        self.on_engine_repaired = on_engine_repaired
        self.update_checker = update_checker or UpdateChecker(settings_manager)
        self._update_info: Optional[Dict] = initial_update_info
        self.download_manager = download_manager
        self.on_app_exit_for_update = on_app_exit_for_update
        self.on_update_checked = on_update_checked
        self._checking_app_update = False
        self._applying_app_update = False

        self.title("設定與修復")
        self.geometry("620x660")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_canvas"])
        self.transient(parent)
        self.grab_set()

        theme_mode = self.settings_manager.get("theme_mode", "light")
        self.after(30, lambda: apply_windows_titlebar(self, theme_mode))

        self._setup_ui()
        self._refresh_status()
        if self._update_info:
            self._apply_update_info_to_ui(self._update_info)

    def _setup_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=(16, 12))
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        # Fixed header
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            header,
            text="設定與修復",
            font=font(20, bold=True),
            text_color=COLORS["text_primary"],
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="關閉",
            width=80,
            height=38,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self.destroy,
        ).pack(side="right")

        # Scrollable sections container (prevents clipping on high-DPI displays)
        container = ctk.CTkScrollableFrame(outer, fg_color="transparent", corner_radius=0)
        container.grid(row=1, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)

        # Section 1: Portable Application Updates
        app_sec = ctk.CTkFrame(
            container,
            fg_color=COLORS["bg_surface"],
            border_width=1,
            border_color=COLORS["border_hairline"],
            corner_radius=RADIUS["panel"],
        )
        app_sec.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            app_sec,
            text="應用程式版本與更新（免安裝版）",
            font=font(16, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 6))

        mode_label = "免安裝執行檔" if self.update_checker.is_frozen() else "Python 原始碼模式"
        self.app_version_lbl = ctk.CTkLabel(
            app_sec,
            text=f"目前版本：v{__version__}（{mode_label}）",
            font=font(14),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        self.app_version_lbl.pack(fill="x", padx=16, pady=2)

        self.app_update_status_lbl = ctk.CTkLabel(
            app_sec,
            text="點擊「檢查應用程式更新」確認是否有新版可用。",
            font=font(14),
            text_color=COLORS["text_secondary"],
            wraplength=520,
            anchor="w",
            justify="left",
        )
        self.app_update_status_lbl.pack(fill="x", padx=16, pady=(2, 10))

        row_app_btns = ctk.CTkFrame(app_sec, fg_color="transparent")
        row_app_btns.pack(fill="x", padx=16, pady=(0, 10))
        row_app_btns.grid_columnconfigure((0, 1), weight=1)

        self.check_app_update_btn = ctk.CTkButton(
            row_app_btns,
            text="檢查應用程式更新",
            image=get_icon("refresh", size=16, variant="default"),
            compound="left",
            height=42,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._check_app_update,
        )
        self.check_app_update_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.apply_app_update_btn = ctk.CTkButton(
            row_app_btns,
            text="下載並更新",
            image=get_icon("download", size=16, variant="on_accent"),
            compound="left",
            height=42,
            font=font(15, bold=True),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            corner_radius=RADIUS["control"],
            state="disabled",
            command=self._apply_or_open_app_update,
        )
        self.apply_app_update_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.app_update_progress = ctk.CTkProgressBar(
            app_sec,
            height=8,
            progress_color=COLORS["accent"],
            fg_color=COLORS["border_hairline"],
        )
        self.app_update_progress.set(0)

        self.app_update_msg_lbl = ctk.CTkLabel(
            app_sec,
            text="",
            font=font(13),
            text_color=COLORS["text_secondary"],
            wraplength=520,
            anchor="w",
            justify="left",
        )

        # Section 2: Engine status & repair
        engine_sec = ctk.CTkFrame(
            container,
            fg_color=COLORS["bg_surface"],
            border_width=1,
            border_color=COLORS["border_hairline"],
            corner_radius=RADIUS["panel"],
        )
        engine_sec.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            engine_sec,
            text="下載引擎狀態",
            font=font(16, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 6))

        self.ytdlp_status_lbl = ctk.CTkLabel(
            engine_sec,
            text="yt-dlp：檢查中",
            font=font(14),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        self.ytdlp_status_lbl.pack(fill="x", padx=16, pady=2)

        self.ffmpeg_status_lbl = ctk.CTkLabel(
            engine_sec,
            text="FFmpeg：檢查中",
            font=font(14),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        self.ffmpeg_status_lbl.pack(fill="x", padx=16, pady=2)

        self.deno_status_lbl = ctk.CTkLabel(
            engine_sec,
            text="Deno：檢查中",
            font=font(14),
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.deno_status_lbl.pack(fill="x", padx=16, pady=(2, 12))

        self.repair_btn = ctk.CTkButton(
            engine_sec,
            text="檢查並更新下載引擎",
            image=get_icon("repair", size=17, variant="on_accent"),
            compound="left",
            height=46,
            font=font(16, bold=True),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            corner_radius=RADIUS["control"],
            command=self._run_repair,
        )
        self.repair_btn.pack(fill="x", padx=16, pady=(0, 12))

        self.repair_progress = ctk.CTkProgressBar(
            engine_sec,
            height=8,
            progress_color=COLORS["accent"],
            fg_color=COLORS["border_hairline"],
        )
        self.repair_progress.set(0)

        self.repair_msg_lbl = ctk.CTkLabel(
            engine_sec,
            text="",
            font=font(14),
            text_color=COLORS["text_secondary"],
            wraplength=520,
            anchor="w",
            justify="left",
        )

        # Section 3: Save folder
        folder_sec = ctk.CTkFrame(
            container,
            fg_color=COLORS["bg_surface"],
            border_width=1,
            border_color=COLORS["border_hairline"],
            corner_radius=RADIUS["panel"],
        )
        folder_sec.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            folder_sec,
            text="音樂存檔位置",
            font=font(16, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 4))

        self.path_status_lbl = ctk.CTkLabel(
            folder_sec,
            text="",
            font=font(14),
            text_color=COLORS["text_secondary"],
            anchor="w",
            wraplength=520,
            justify="left",
        )
        self.path_status_lbl.pack(fill="x", padx=16, pady=(0, 10))

        row_folder = ctk.CTkFrame(folder_sec, fg_color="transparent")
        row_folder.pack(fill="x", padx=16, pady=(0, 14))
        row_folder.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            row_folder,
            text="變更資料夾",
            image=get_icon("folder", size=16, variant="default"),
            compound="left",
            height=42,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._change_folder,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            row_folder,
            text="恢復預設下載資料夾",
            height=42,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._reset_folder,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # Section 4: Diagnostics
        diag_sec = ctk.CTkFrame(
            container,
            fg_color=COLORS["bg_surface"],
            border_width=1,
            border_color=COLORS["border_hairline"],
            corner_radius=RADIUS["panel"],
        )
        diag_sec.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            diag_sec,
            text="問題診斷紀錄",
            font=font(16, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 8))

        row_diag = ctk.CTkFrame(diag_sec, fg_color="transparent")
        row_diag.pack(fill="x", padx=16, pady=(0, 14))
        row_diag.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            row_diag,
            text="複製診斷紀錄",
            image=get_icon("copy", size=16, variant="default"),
            compound="left",
            height=42,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._copy_logs,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            row_diag,
            text="開啟紀錄資料夾",
            image=get_icon("folder_open", size=16, variant="default"),
            compound="left",
            height=42,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._open_logs_folder,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.feedback_lbl = ctk.CTkLabel(
            outer,
            text="",
            font=font(14, bold=True),
            text_color=COLORS["accent"],
            anchor="w",
        )
        self.feedback_lbl.grid(row=2, column=0, sticky="ew", pady=(6, 0))

    def _refresh_status(self):
        st = binary_manager.get_engine_status()
        self.ytdlp_status_lbl.configure(text=f"yt-dlp：{st['ytdlp']}")
        self.ffmpeg_status_lbl.configure(text=f"FFmpeg：{st['ffmpeg']}")
        self.deno_status_lbl.configure(text=f"Deno：{st['deno']}")
        self.path_status_lbl.configure(text=self.settings_manager.get_output_directory())

    # ---------------- App Self-Update ----------------

    def _check_app_update(self):
        if self._checking_app_update or self._applying_app_update:
            return
        self._checking_app_update = True
        self.logger.info("[UPDATE] 使用者手動檢查應用程式更新")
        self.check_app_update_btn.configure(state="disabled", text="檢查中...")
        self.apply_app_update_btn.configure(state="disabled")
        self.app_update_status_lbl.configure(
            text="正在連線 GitHub 檢查最新版本，請稍候...",
            text_color=COLORS["text_secondary"],
        )

        def _worker():
            info = self.update_checker.check(force=True)
            self.after(0, lambda: self._on_check_app_update_done(info))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_check_app_update_done(self, info: Dict):
        self._checking_app_update = False
        if not self.winfo_exists():
            return
        self.check_app_update_btn.configure(state="normal", text="檢查應用程式更新")
        self._update_info = info
        self._apply_update_info_to_ui(info)
        if self.on_update_checked:
            self.on_update_checked(info)

    def _apply_update_info_to_ui(self, info: Dict):
        status = info.get("status", "")
        msg = info.get("message") or ""
        if info.get("available"):
            if self.update_checker.is_frozen():
                self.app_update_status_lbl.configure(text=msg, text_color=COLORS["accent"])
                self.apply_app_update_btn.configure(text="下載並更新", state="normal")
            else:
                self.app_update_status_lbl.configure(
                    text=f"{msg}（目前為原始碼模式，請至發佈頁面下載免安裝版）",
                    text_color=COLORS["accent"],
                )
                self.apply_app_update_btn.configure(text="開啟發佈頁面", state="normal")
        elif status == "no_asset" and info.get("release_url"):
            self.app_update_status_lbl.configure(text=msg, text_color=COLORS["danger"])
            self.apply_app_update_btn.configure(text="開啟發佈頁面", state="normal")
        elif status == "error":
            self.app_update_status_lbl.configure(text=msg, text_color=COLORS["danger"])
            self.apply_app_update_btn.configure(text="下載並更新", state="disabled")
        else:
            self.app_update_status_lbl.configure(
                text=msg or f"目前已是最新版本（v{__version__}）。",
                text_color=COLORS["text_secondary"],
            )
            self.apply_app_update_btn.configure(text="下載並更新", state="disabled")

    def _apply_or_open_app_update(self):
        info = self._update_info or {}
        if not info.get("available") or not self.update_checker.is_frozen():
            release_url = info.get("release_url") or self.update_checker.releases_page_url
            self.logger.info("[UPDATE] 開啟發佈頁面: %s", release_url)
            webbrowser.open(release_url)
            return

        if self._applying_app_update:
            return

        active_count = 0
        if self.download_manager is not None:
            try:
                active_count = len(
                    [
                        item
                        for item in self.download_manager.get_queue()
                        if item.status.value == "downloading"
                    ]
                )
            except Exception:
                active_count = 0

        latest_ver = info.get("latest_version", "")
        warn_active = (
            f"\n\n注意：目前還有 {active_count} 首歌曲正在下載中，更新時將會先中止下載。"
            if active_count > 0
            else ""
        )
        confirmed = messagebox.askyesno(
            "確認更新應用程式",
            f"即將下載並更新至 v{latest_ver}（目前版本 v{__version__}）。\n\n"
            "更新過程會完整保留您的引擎（bin）、設定與紀錄（data / logs）、"
            "cookies.txt 與已下載的音樂檔案，並在替換完成後自動重新啟動程式。"
            f"{warn_active}\n\n確定要立即更新嗎？",
            parent=self,
        )
        if not confirmed:
            return

        self._applying_app_update = True
        self.logger.info("[UPDATE] 使用者確認執行應用程式更新 -> v%s", latest_ver)
        self.check_app_update_btn.configure(state="disabled")
        self.apply_app_update_btn.configure(state="disabled", text="更新中...")
        self.app_update_progress.pack(fill="x", padx=16, pady=(0, 6))
        self.app_update_progress.set(0.05)
        self.app_update_msg_lbl.configure(
            text="正在下載並驗證應用程式更新檔...",
            text_color=COLORS["text_secondary"],
        )
        self.app_update_msg_lbl.pack(fill="x", padx=16, pady=(0, 12))

        def _progress(msg: str, pct: float):
            self.after(
                0,
                lambda: (
                    self.app_update_progress.set(max(0.05, min(1.0, pct))),
                    self.app_update_msg_lbl.configure(text=msg),
                )
                if self.winfo_exists()
                else None,
            )

        def _worker():
            prepared = self.update_checker.download_update(info, progress_callback=_progress)
            self.after(0, lambda: self._on_download_app_update_done(prepared))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_download_app_update_done(self, prepared: Dict):
        if not self.winfo_exists():
            return
        if not prepared.get("ok"):
            self._applying_app_update = False
            self.check_app_update_btn.configure(state="normal")
            self.apply_app_update_btn.configure(state="normal", text="下載並更新")
            self.app_update_msg_lbl.configure(
                text=prepared.get("error") or "下載或驗證更新檔失敗。",
                text_color=COLORS["danger"],
            )
            return

        self.app_update_msg_lbl.configure(
            text="正在啟動背景更新程序...",
            text_color=COLORS["accent"],
        )

        def _apply_worker():
            try:
                applied = self.update_checker.apply_update(prepared)
            except Exception as e:
                self.logger.error("[UPDATE] 背景套用更新發生例外: %s", e, exc_info=True)
                applied = False

            def _on_apply_done():
                if applied:
                    if self.on_app_exit_for_update:
                        self.on_app_exit_for_update()
                    elif self.winfo_exists():
                        self.destroy()
                else:
                    if self.winfo_exists():
                        self._applying_app_update = False
                        self.check_app_update_btn.configure(state="normal")
                        self.apply_app_update_btn.configure(state="normal", text="下載並更新")
                        self.app_update_msg_lbl.configure(
                            text="無法啟動免安裝更新背景程序，請查看診斷紀錄。",
                            text_color=COLORS["danger"],
                        )

            try:
                self.master.after(0, _on_apply_done)
            except Exception:
                if self.winfo_exists():
                    try:
                        self.after(0, _on_apply_done)
                    except Exception:
                        pass

        threading.Thread(target=_apply_worker, daemon=True).start()

    # ---------------- Engine Repair ----------------

    def _run_repair(self):
        self.logger.info("[UI_HELP] 使用者啟動一鍵修復/更新下載引擎")
        self.repair_btn.configure(state="disabled", text="正在檢查並更新...")
        self.repair_progress.pack(fill="x", padx=16, pady=(0, 6))
        self.repair_progress.set(0.05)
        self.repair_msg_lbl.configure(
            text="正在執行環境檢查、更新與二次驗證...",
            text_color=COLORS["text_secondary"],
        )
        self.repair_msg_lbl.pack(fill="x", padx=16, pady=(0, 12))

        def _worker():
            out_dir = Path(self.settings_manager.get_output_directory())

            def _cb(stage_num, stage_title, detail, pct):
                self.after(
                    0,
                    lambda: (
                        self.repair_progress.set(max(0.05, pct / 100.0)),
                        self.repair_msg_lbl.configure(text=f"步驟 {stage_num}/3 · {stage_title}：{detail}"),
                    )
                    if self.winfo_exists()
                    else None,
                )

            report = binary_manager.run_environment_bootstrap(
                progress_callback=_cb, force_update=True, downloads_dir=out_dir
            )
            self.after(0, lambda: self._on_repair_done(report))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_repair_done(self, report: binary_manager.BootstrapReport):
        if not self.winfo_exists():
            return
        self.repair_btn.configure(state="normal", text="檢查並更新下載引擎")
        self._refresh_status()
        if report.ok:
            self.repair_msg_lbl.configure(
                text=f"檢查與更新完成，yt-dlp 目前版本：{report.ytdlp_version}",
                text_color=COLORS["accent"],
            )
        else:
            self.repair_msg_lbl.configure(
                text=report.error_message,
                text_color=COLORS["danger"],
            )
        if self.on_engine_repaired:
            self.on_engine_repaired(report)

    # ---------------- Diagnostics & Folder ----------------

    def _copy_logs(self):
        st = binary_manager.get_engine_status()
        cookie_summary = CookieManager(self.settings_manager).get_diagnostic_summary()
        files = cookie_summary.get("cookies_files") or []
        cookies_desc = (
            ", ".join(f"{f['path']} ({f['size']} bytes)" for f in files)
            if files
            else "無"
        )
        browsers = cookie_summary.get("browsers") or {}
        browsers_desc = ", ".join(f"{k}={'有' if v else '無'}" for k, v in browsers.items())
        update_status = (
            (self._update_info or {}).get("status")
            or ("尚未檢查" if not self._update_info else "unknown")
        )

        extra = {
            "應用程式版本": f"v{__version__}",
            "更新檢查狀態": f"{update_status} (repo={self.update_checker.repo})",
            "yt-dlp 版本": st["ytdlp"],
            "FFmpeg 狀態": st["ffmpeg"],
            "Deno 狀態": st["deno"],
            "Cookie 設定": f"enabled={cookie_summary.get('cookies_enabled')} | cookies.txt={cookies_desc} | 瀏覽器=[{browsers_desc}]",
            "音樂存檔位置": self.settings_manager.get_output_directory(),
        }
        self.logger.info("[DIAG] 使用者已複製診斷紀錄")
        report_text = get_diagnostic_report(extra_info=extra)
        self.clipboard_clear()
        self.clipboard_append(report_text)
        self.update()
        self.feedback_lbl.configure(text="已複製診斷紀錄至剪貼簿")

    def _open_logs_folder(self):
        self.logger.info("[UI_HELP] 開啟紀錄資料夾")
        if os.name == "nt":
            os.startfile(str(get_logs_dir()))

    def _change_folder(self):
        current = self.settings_manager.get_output_directory()
        chosen = filedialog.askdirectory(title="選擇音樂存檔資料夾", initialdir=current, parent=self)
        if chosen:
            self.logger.info("[UI_HELP] 變更存檔位置: %s -> %s", current, chosen)
            self.settings_manager.set("output_directory", chosen)
            self.settings_manager.save_settings()
            self._refresh_status()
            self.feedback_lbl.configure(text=f"已變更存檔位置：{chosen}")
            if self.on_path_changed:
                self.on_path_changed(chosen)

    def _reset_folder(self):
        default_dir = self.settings_manager.reset_output_directory()
        self.logger.info("[UI_HELP] 恢復預設下載資料夾: %s", default_dir)
        self._refresh_status()
        self.feedback_lbl.configure(text=f"已恢復預設下載資料夾：{default_dir}")
        if self.on_path_changed:
            self.on_path_changed(default_dir)
