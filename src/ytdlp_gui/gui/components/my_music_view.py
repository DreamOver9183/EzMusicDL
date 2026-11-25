# -*- coding: utf-8 -*-
"""
My Music View - Restrained Win11 Fluent file list (Zero Emoji).
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from ytdlp_gui.core import ytdlp_wrapper
from ytdlp_gui.gui.icons import get_icon
from ytdlp_gui.gui.theme import COLORS, RADIUS, font


class MyMusicView(ctk.CTkFrame):
    """Shows MP3 files in the Downloads folder with Play and Show in Folder actions."""

    def __init__(self, parent, settings_manager, on_count_changed: Optional[Callable[[int], None]] = None):
        super().__init__(parent, fg_color="transparent")
        self.logger = logging.getLogger(__name__)
        self.settings_manager = settings_manager
        self.on_count_changed = on_count_changed
        self._setup_ui()
        self.refresh_list()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header_bar = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_surface"],
            border_width=1,
            border_color=COLORS["border_hairline"],
            corner_radius=RADIUS["panel"],
        )
        header_bar.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header_bar.grid_columnconfigure(0, weight=1)

        path_info = ctk.CTkFrame(header_bar, fg_color="transparent")
        path_info.grid(row=0, column=0, padx=18, pady=14, sticky="w")

        ctk.CTkLabel(
            path_info,
            text="存檔資料夾",
            font=font(17, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).pack(anchor="w")

        self.path_label = ctk.CTkLabel(
            path_info,
            text="",
            font=font(14),
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.path_label.pack(anchor="w", pady=(2, 0))

        btns_col = ctk.CTkFrame(header_bar, fg_color="transparent")
        btns_col.grid(row=0, column=1, padx=18, pady=14, sticky="e")

        ctk.CTkButton(
            btns_col,
            text="開啟資料夾",
            image=get_icon("folder_open", size=17, variant="default"),
            compound="left",
            width=136,
            height=44,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self.open_downloads_folder,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btns_col,
            text="重新整理",
            image=get_icon("refresh", size=17, variant="default"),
            compound="left",
            width=120,
            height=44,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self.refresh_list,
        ).pack(side="left")

        self.list_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.list_scroll.grid(row=1, column=0, sticky="nsew")
        self.list_scroll.grid_columnconfigure(0, weight=1)

    def refresh_list(self) -> int:
        out_dir = Path(self.settings_manager.get_output_directory())
        self.path_label.configure(text=str(out_dir))

        for child in self.list_scroll.winfo_children():
            child.destroy()

        mp3_files = []
        try:
            if out_dir.exists():
                mp3_files = sorted(
                    [p for p in out_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp3"],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
        except Exception as e:
            self.logger.warning("掃描 MP3 檔案失敗: %s", e)

        if self.on_count_changed:
            self.on_count_changed(len(mp3_files))

        if not mp3_files:
            empty_box = ctk.CTkFrame(self.list_scroll, fg_color="transparent")
            empty_box.grid(row=0, column=0, sticky="ew", pady=48)
            ctk.CTkLabel(
                empty_box,
                text="",
                image=get_icon("folder", size=38, variant="muted"),
            ).pack(pady=(0, 12))
            ctk.CTkLabel(
                empty_box,
                text="目前尚無已下載的 MP3 檔案",
                font=font(18, bold=True),
                text_color=COLORS["text_primary"],
            ).pack()
            ctk.CTkLabel(
                empty_box,
                text="請切換至「搜尋下載」分頁搜尋並下載歌曲",
                font=font(15),
                text_color=COLORS["text_secondary"],
            ).pack(pady=(6, 0))
            return 0

        for idx, file_path in enumerate(mp3_files[:100]):
            self._create_file_row(idx, file_path)
        return len(mp3_files)

    def _create_file_row(self, row_idx: int, file_path: Path):
        row = ctk.CTkFrame(
            self.list_scroll,
            fg_color=COLORS["bg_surface"],
            border_width=1,
            border_color=COLORS["border_hairline"],
            corner_radius=RADIUS["panel"],
        )
        row.grid(row=row_idx, column=0, sticky="ew", pady=(0, 8))
        row.grid_columnconfigure(1, weight=1)

        try:
            st = file_path.stat()
            size_str = ytdlp_wrapper.format_bytes(st.st_size)
            date_str = datetime.fromtimestamp(st.st_mtime).strftime("%Y/%m/%d %H:%M")
        except Exception:
            size_str = ""
            date_str = ""

        ctk.CTkLabel(
            row,
            text="",
            image=get_icon("music", size=22, variant="muted"),
        ).grid(row=0, column=0, padx=(18, 12), pady=14)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=0, column=1, pady=12, sticky="ew")

        ctk.CTkLabel(
            info,
            text=file_path.stem,
            font=font(17, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
            wraplength=540,
            justify="left",
        ).pack(anchor="w")

        ctk.CTkLabel(
            info,
            text=f"{size_str}  ·  {date_str}",
            font=font(14),
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=2, padx=16, pady=12, sticky="e")

        ctk.CTkButton(
            actions,
            text="播放",
            image=get_icon("play", size=16, variant="on_accent"),
            compound="left",
            width=108,
            height=44,
            font=font(16, bold=True),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            corner_radius=RADIUS["control"],
            command=lambda p=file_path: self._play_file(p),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            actions,
            text="顯示位置",
            image=get_icon("folder", size=16, variant="default"),
            compound="left",
            width=122,
            height=44,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=lambda p=file_path: self._reveal_file(p),
        ).pack(side="left")

    def open_downloads_folder(self):
        out_dir = self.settings_manager.get_output_directory()
        try:
            if os.name == "nt":
                os.startfile(out_dir)
        except Exception as e:
            self.logger.error("無法開啟資料夾: %s", e)

    def _play_file(self, file_path: Path):
        try:
            if os.name == "nt":
                os.startfile(str(file_path))
        except Exception as e:
            self.logger.error("播放失敗: %s", e)

    def _reveal_file(self, file_path: Path):
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(file_path)])
        except Exception as e:
            self.logger.error("開啟檔案位置失敗: %s", e)
