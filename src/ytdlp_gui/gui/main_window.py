# -*- coding: utf-8 -*-
"""
Main GUI window - Native Windows 11 Fluent Utility for Pure MP3 Music Downloading.
"""

import sys
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from ytdlp_gui import __version__
from ytdlp_gui.core import binary_manager
from ytdlp_gui.core.download_manager import DownloadManager
from ytdlp_gui.core.settings_manager import SettingsManager
from ytdlp_gui.core.update_checker import UpdateChecker
from ytdlp_gui.gui.components.help_dialog import HelpDialog
from ytdlp_gui.gui.components.music_search_view import MusicSearchView
from ytdlp_gui.gui.components.my_music_view import MyMusicView
from ytdlp_gui.gui.icons import get_icon
from ytdlp_gui.gui.theme import COLORS, RADIUS, apply_windows_titlebar, font
from ytdlp_gui.utils.logger import flush_logs, get_logger, init_logging
from ytdlp_gui.utils.notifications import init_notifications
from ytdlp_gui.utils.paths import get_resource_path


class YTDLPGUIApp:
    """Main pure-MP3 downloader window."""

    def __init__(self, bootstrap_report: Optional[binary_manager.BootstrapReport] = None):
        init_logging()
        self.logger = get_logger(__name__)
        self.bootstrap_report = bootstrap_report

        self.settings_manager = SettingsManager()
        theme_mode = self.settings_manager.get("theme_mode", "light")
        if theme_mode not in ("light", "dark"):
            theme_mode = "light"
        ctk.set_appearance_mode(theme_mode)

        self.download_manager = DownloadManager(self.settings_manager)
        self.update_checker = UpdateChecker(self.settings_manager)
        self._latest_update_info: Optional[dict] = None
        self._update_banner_dismissed = False

        self.root = ctk.CTk()
        self.root.title("音樂下載工具")
        self.root.geometry("1040x740")
        self.root.minsize(880, 620)
        self.root.configure(fg_color=COLORS["bg_canvas"])
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self._setup_ui(theme_mode)
        self.root.bind("<FocusIn>", self._on_window_focus)
        self.root.after(50, lambda: apply_windows_titlebar(self.root, theme_mode))
        self.root.after(200, self._set_window_icon)
        self.root.after(1500, self._start_background_update_check)

        self.notification_manager = init_notifications(self.root)
        self.notification_manager.enable_notifications(
            self.settings_manager.get("notification_enabled", True)
        )

    def _setup_ui(self, theme_mode: str):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

        # Top toolbar
        nav_bar = ctk.CTkFrame(
            self.root,
            fg_color=COLORS["bg_surface"],
            corner_radius=0,
        )
        nav_bar.grid(row=0, column=0, sticky="ew")
        nav_bar.grid_columnconfigure(1, weight=1)

        tabs_left = ctk.CTkFrame(nav_bar, fg_color="transparent")
        tabs_left.grid(row=0, column=0, padx=20, pady=12, sticky="w")

        self.tab_search_btn = ctk.CTkButton(
            tabs_left,
            text="搜尋下載",
            image=get_icon("search", size=18, variant="accent"),
            compound="left",
            width=148,
            height=44,
            font=font(16, bold=True),
            corner_radius=RADIUS["control"],
            command=lambda: self._switch_tab("search"),
        )
        self.tab_search_btn.pack(side="left", padx=(0, 8))

        self.tab_library_btn = ctk.CTkButton(
            tabs_left,
            text="已下載音樂 (0)",
            image=get_icon("music", size=18, variant="muted"),
            compound="left",
            width=184,
            height=44,
            font=font(16, bold=True),
            corner_radius=RADIUS["control"],
            command=lambda: self._switch_tab("library"),
        )
        self.tab_library_btn.pack(side="left")

        right_controls = ctk.CTkFrame(nav_bar, fg_color="transparent")
        right_controls.grid(row=0, column=2, padx=20, pady=12, sticky="e")

        initial_theme_label = "深色" if theme_mode == "dark" else "淺色"
        self.theme_var = ctk.StringVar(value=initial_theme_label)
        self.theme_selector = ctk.CTkSegmentedButton(
            right_controls,
            values=["淺色", "深色"],
            variable=self.theme_var,
            height=40,
            font=font(15, bold=True),
            fg_color=COLORS["bg_canvas"],
            selected_color=COLORS["accent_subtle"],
            selected_hover_color=COLORS["accent_subtle"],
            unselected_color=COLORS["bg_canvas"],
            unselected_hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            corner_radius=RADIUS["control"],
            command=self._on_theme_selected,
        )
        self.theme_selector.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            right_controls,
            text="設定與修復",
            image=get_icon("settings", size=17, variant="default"),
            compound="left",
            width=136,
            height=40,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._open_help_dialog,
        ).pack(side="left")

        # 1px top hairline divider
        ctk.CTkFrame(
            self.root,
            height=1,
            fg_color=COLORS["border_hairline"],
            corner_radius=0,
        ).grid(row=1, column=0, sticky="ew")

        # Main workspace
        self.content_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.content_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=16)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=1)

        # App update notification banner (hidden until a newer release is detected)
        self.update_banner = ctk.CTkFrame(
            self.content_frame,
            fg_color=COLORS["accent_subtle"],
            border_width=1,
            border_color=COLORS["accent_border"],
            corner_radius=RADIUS["panel"],
        )
        self.update_banner.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.update_banner,
            text="",
            image=get_icon("info", size=18, variant="accent"),
        ).grid(row=0, column=0, padx=(16, 10), pady=12)

        self.update_banner_lbl = ctk.CTkLabel(
            self.update_banner,
            text="",
            font=font(16, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        self.update_banner_lbl.grid(row=0, column=1, pady=12, sticky="w")

        update_banner_btns = ctk.CTkFrame(self.update_banner, fg_color="transparent")
        update_banner_btns.grid(row=0, column=2, padx=14, pady=10, sticky="e")

        ctk.CTkButton(
            update_banner_btns,
            text="前往更新",
            height=38,
            width=108,
            font=font(15, bold=True),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            corner_radius=RADIUS["control"],
            command=self._open_help_for_update,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            update_banner_btns,
            text="稍後提醒",
            height=38,
            width=92,
            font=font(15),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._dismiss_update_banner,
        ).pack(side="left")

        self.library_view = MyMusicView(
            self.content_frame,
            settings_manager=self.settings_manager,
            on_count_changed=self._update_library_badge,
        )

        self.search_view = MusicSearchView(
            self.content_frame,
            download_manager=self.download_manager,
            settings_manager=self.settings_manager,
            on_download_completed=self.library_view.refresh_list,
            on_open_folder=self.library_view.open_downloads_folder,
        )

        # 1px bottom hairline divider
        ctk.CTkFrame(
            self.root,
            height=1,
            fg_color=COLORS["border_hairline"],
            corner_radius=0,
        ).grid(row=3, column=0, sticky="ew")

        # Bottom status bar
        status_bar = ctk.CTkFrame(
            self.root,
            fg_color=COLORS["bg_surface"],
            corner_radius=0,
            height=38,
        )
        status_bar.grid(row=4, column=0, sticky="ew")
        status_bar.grid_columnconfigure(0, weight=1)

        self.status_left_lbl = ctk.CTkLabel(
            status_bar,
            text=f" {self._build_engine_status_text()}",
            image=get_icon("check", size=14, variant="accent"),
            compound="left",
            font=font(13),
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.status_left_lbl.grid(row=0, column=0, padx=20, pady=8, sticky="w")

        self.status_right_lbl = ctk.CTkLabel(
            status_bar,
            text=f"存檔位置：{self.settings_manager.get_output_directory()}  （MP3）",
            font=font(13),
            text_color=COLORS["text_secondary"],
            anchor="e",
        )
        self.status_right_lbl.grid(row=0, column=1, padx=20, pady=8, sticky="e")

        self._switch_tab("search")

    def _build_engine_status_text(self) -> str:
        if self.bootstrap_report and self.bootstrap_report.ok:
            return f"v{__version__} · 引擎驗證通過 · yt-dlp {self.bootstrap_report.ytdlp_version}"
        st = binary_manager.get_engine_status()
        return f"v{__version__} · 引擎就緒 · yt-dlp {st['ytdlp']}"

    def _switch_tab(self, tab: str):
        self.logger.info("[UI] 切換分頁: %s", tab)
        if tab == "search":
            self.library_view.grid_remove()
            self.search_view.grid(row=1, column=0, sticky="nsew")
            self.tab_search_btn.configure(
                fg_color=COLORS["accent_subtle"],
                hover_color=COLORS["accent_subtle"],
                text_color=COLORS["text_primary"],
                border_width=1,
                border_color=COLORS["accent_border"],
                image=get_icon("search", size=18, variant="accent"),
            )
            self.tab_library_btn.configure(
                fg_color="transparent",
                hover_color=COLORS["bg_control_hover"],
                text_color=COLORS["text_secondary"],
                border_width=0,
                image=get_icon("music", size=18, variant="muted"),
            )
        else:
            self.search_view.grid_remove()
            self.library_view.refresh_list()
            self.library_view.grid(row=1, column=0, sticky="nsew")
            self.tab_library_btn.configure(
                fg_color=COLORS["accent_subtle"],
                hover_color=COLORS["accent_subtle"],
                text_color=COLORS["text_primary"],
                border_width=1,
                border_color=COLORS["accent_border"],
                image=get_icon("music", size=18, variant="accent"),
            )
            self.tab_search_btn.configure(
                fg_color="transparent",
                hover_color=COLORS["bg_control_hover"],
                text_color=COLORS["text_secondary"],
                border_width=0,
                image=get_icon("search", size=18, variant="muted"),
            )

    def _update_library_badge(self, count: int):
        try:
            self.tab_library_btn.configure(text=f"已下載音樂 ({count})")
        except Exception:
            pass

    def _on_window_focus(self, event=None):
        if event and event.widget is self.root:
            self.search_view.check_clipboard()

    def _on_theme_selected(self, value: str):
        mode = "dark" if value == "深色" else "light"
        self.logger.info("[UI] 切換主題模式: %s", mode)
        self.settings_manager.set("theme_mode", mode)
        self.settings_manager.save_settings()
        ctk.set_appearance_mode(mode)
        apply_windows_titlebar(self.root, mode)

    def _open_help_dialog(self):
        self.logger.info("[UI] 開啟設定與修復視窗")
        HelpDialog(
            self.root,
            settings_manager=self.settings_manager,
            on_path_changed=self._on_save_path_changed,
            on_engine_repaired=self._on_engine_repaired,
            update_checker=self.update_checker,
            initial_update_info=self._latest_update_info,
            download_manager=self.download_manager,
            on_app_exit_for_update=self._exit_for_update,
            on_update_checked=self._on_manual_update_checked,
        )

    def _start_background_update_check(self):
        import threading

        def _worker():
            info = self.update_checker.check(force=False)
            try:
                self.root.after(0, lambda: self._on_background_update_checked(info))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_background_update_checked(self, info: Optional[dict]):
        if not info:
            return
        self._latest_update_info = info
        if info.get("available") and not self._update_banner_dismissed:
            latest = info.get("latest_version", "")
            self.update_banner_lbl.configure(
                text=f"發現應用程式新版本 v{latest}（目前 v{__version__}），可立即更新"
            )
            self.update_banner.grid(row=0, column=0, sticky="ew", pady=(0, 12))

    def _on_manual_update_checked(self, info: Optional[dict]):
        if not info:
            return
        self._latest_update_info = info
        if info.get("available") and not self._update_banner_dismissed:
            latest = info.get("latest_version", "")
            self.update_banner_lbl.configure(
                text=f"發現應用程式新版本 v{latest}（目前 v{__version__}），可立即更新"
            )
            self.update_banner.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        elif not info.get("available"):
            self.update_banner.grid_remove()

    def _dismiss_update_banner(self):
        self._update_banner_dismissed = True
        self.update_banner.grid_remove()

    def _open_help_for_update(self):
        self._open_help_dialog()

    def _exit_for_update(self):
        self.logger.info("[UPDATE] 結束主程式以套用免安裝版更新")
        try:
            self.download_manager.stop_all_downloads()
            self.settings_manager.save_settings()
        except Exception as e:
            self.logger.warning("[UPDATE] 結束前儲存設定發生警告: %s", e)
        flush_logs()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def _on_save_path_changed(self, new_path: str):
        self.status_right_lbl.configure(text=f"存檔位置：{new_path}  （MP3）")
        self.library_view.refresh_list()

    def _on_engine_repaired(self, report: binary_manager.BootstrapReport):
        self.bootstrap_report = report
        self.status_left_lbl.configure(text=f" {self._build_engine_status_text()}")

    def _set_window_icon(self):
        ico_path = get_resource_path("assets/icon.ico")
        if not ico_path.exists():
            return
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            win_large = user32.LoadImageW(None, str(ico_path), 1, 48, 48, 0x10)
            win_small = user32.LoadImageW(None, str(ico_path), 1, 16, 16, 0x10)
            if win_large:
                user32.SendMessageW(hwnd, 0x0080, 1, win_large)
            if win_small:
                user32.SendMessageW(hwnd, 0x0080, 0, win_small)
        except Exception:
            pass

    def on_closing(self):
        try:
            active_downloads = len(
                [item for item in self.download_manager.get_queue() if item.status.value == "downloading"]
            )
            if active_downloads > 0:
                confirm = messagebox.askyesno(
                    "仍有歌曲正在下載",
                    f"目前還有 {active_downloads} 首歌曲正在下載中。\n確定要停止下載並關閉視窗嗎？",
                    parent=self.root,
                )
                if not confirm:
                    return
            self.download_manager.stop_all_downloads()
            self.settings_manager.save_settings()
            self.root.destroy()
        except Exception as e:
            self.logger.error("關閉視窗時發生錯誤: %s", e)
            self.root.destroy()

    def run(self):
        flush_logs()
        self.logger.info("進入主畫面 mainloop")
        self.root.mainloop()
