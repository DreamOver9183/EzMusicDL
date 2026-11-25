# -*- coding: utf-8 -*-
"""
Settings & Diagnostics Dialog - Native Fluent sections without rainbow clutter or emojis.
"""

import logging
import os
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional

import customtkinter as ctk

from ytdlp_gui.core import binary_manager
from ytdlp_gui.gui.icons import get_icon
from ytdlp_gui.gui.theme import COLORS, RADIUS, apply_windows_titlebar, font
from ytdlp_gui.utils.logger import get_diagnostic_report
from ytdlp_gui.utils.paths import get_logs_dir


class HelpDialog(ctk.CTkToplevel):
    """Modal window for engine repair, save folder configuration, and diagnostics."""

    def __init__(
        self,
        parent,
        settings_manager,
        on_path_changed: Optional[Callable[[str], None]] = None,
        on_engine_repaired: Optional[Callable[[binary_manager.BootstrapReport], None]] = None,
    ):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.settings_manager = settings_manager
        self.on_path_changed = on_path_changed
        self.on_engine_repaired = on_engine_repaired

        self.title("設定與修復")
        self.geometry("600x580")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_canvas"])
        self.transient(parent)
        self.grab_set()

        theme_mode = self.settings_manager.get("theme_mode", "light")
        self.after(30, lambda: apply_windows_titlebar(self, theme_mode))

        self._setup_ui()
        self._refresh_status()

    def _setup_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=22, pady=18)

        # Header
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))
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

        # Section 1: Engine status & repair
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
        self.repair_btn.pack(fill="x", padx=16, pady=(0, 10))

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

        # Section 2: Save folder
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

        # Section 3: Diagnostics
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
            container,
            text="",
            font=font(14, bold=True),
            text_color=COLORS["accent"],
            anchor="w",
        )
        self.feedback_lbl.pack(fill="x", pady=(4, 0))

    def _refresh_status(self):
        st = binary_manager.get_engine_status()
        self.ytdlp_status_lbl.configure(text=f"yt-dlp：{st['ytdlp']}")
        self.ffmpeg_status_lbl.configure(text=f"FFmpeg：{st['ffmpeg']}")
        self.deno_status_lbl.configure(text=f"Deno：{st['deno']}")
        self.path_status_lbl.configure(text=self.settings_manager.get_output_directory())

    def _run_repair(self):
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
                    ),
                )

            report = binary_manager.run_environment_bootstrap(
                progress_callback=_cb, force_update=True, downloads_dir=out_dir
            )
            self.after(0, lambda: self._on_repair_done(report))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_repair_done(self, report: binary_manager.BootstrapReport):
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

    def _copy_logs(self):
        st = binary_manager.get_engine_status()
        extra = {
            "yt-dlp 版本": st["ytdlp"],
            "FFmpeg 狀態": st["ffmpeg"],
            "Deno 狀態": st["deno"],
            "音樂存檔位置": self.settings_manager.get_output_directory(),
        }
        report_text = get_diagnostic_report(extra_info=extra)
        self.clipboard_clear()
        self.clipboard_append(report_text)
        self.update()
        self.feedback_lbl.configure(text="已複製診斷紀錄至剪貼簿")

    def _open_logs_folder(self):
        if os.name == "nt":
            os.startfile(str(get_logs_dir()))

    def _change_folder(self):
        current = self.settings_manager.get_output_directory()
        chosen = filedialog.askdirectory(title="選擇音樂存檔資料夾", initialdir=current, parent=self)
        if chosen:
            self.settings_manager.set("output_directory", chosen)
            self.settings_manager.save_settings()
            self._refresh_status()
            self.feedback_lbl.configure(text=f"已變更存檔位置：{chosen}")
            if self.on_path_changed:
                self.on_path_changed(chosen)

    def _reset_folder(self):
        default_dir = self.settings_manager.reset_output_directory()
        self._refresh_status()
        self.feedback_lbl.configure(text=f"已恢復預設下載資料夾：{default_dir}")
        if self.on_path_changed:
            self.on_path_changed(default_dir)
