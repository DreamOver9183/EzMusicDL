# -*- coding: utf-8 -*-
"""
Notifications - Restrained Win11 Fluent toast notifications (Zero Emoji).
"""

import logging
from enum import Enum
from tkinter import messagebox

import customtkinter as ctk

from ytdlp_gui.gui.icons import get_icon
from ytdlp_gui.gui.theme import COLORS, RADIUS, font
from ytdlp_gui.utils.error_translations import translate_error


class NotificationType(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationManager:
    """Manages application notifications."""

    def __init__(self, parent_window=None):
        self.logger = logging.getLogger(__name__)
        self.parent_window = parent_window
        self.notifications_enabled = True
        self.toast_notifications = []

    def set_parent_window(self, parent_window):
        self.parent_window = parent_window

    def enable_notifications(self, enabled: bool):
        self.notifications_enabled = enabled

    def show_success(self, title: str, message: str, show_toast: bool = True):
        self._show_notification(NotificationType.SUCCESS, title, message, show_toast)

    def show_error(self, title: str, message: str, show_toast: bool = True, show_dialog: bool = False):
        self._show_notification(NotificationType.ERROR, title, message, show_toast)
        if show_dialog and self.parent_window:
            messagebox.showerror(title, message, parent=self.parent_window)

    def _show_notification(self, notification_type: NotificationType, title: str, message: str, show_toast: bool):
        if not self.notifications_enabled:
            return

        log_message = f"{title}: {message}"
        if notification_type == NotificationType.ERROR:
            self.logger.error(log_message)
        elif notification_type == NotificationType.WARNING:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

        if show_toast and self.parent_window:
            self.parent_window.after(0, lambda: self._show_toast(notification_type, title, message))

    def _show_toast(self, notification_type: NotificationType, title: str, message: str):
        try:
            toast = ToastNotification(self.parent_window, notification_type, title, message)
            self.toast_notifications.append(toast)

            def cleanup():
                if toast in self.toast_notifications:
                    self.toast_notifications.remove(toast)

            toast.on_close = cleanup
        except Exception as e:
            self.logger.error("顯示通知視窗失敗: %s", e)


class ToastNotification(ctk.CTkToplevel):
    """Restrained Win11 surface toast notification."""

    def __init__(self, parent, notification_type: NotificationType, title: str, message: str):
        super().__init__(parent)
        self.notification_type = notification_type
        self.on_close = None
        self.setup_window()
        self.setup_ui(title, message)
        self.after(4500, self.close_notification)

    def setup_window(self):
        self.title("")
        self.geometry("400x104")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        x = max(20, screen_width - 424)
        self.geometry(f"400x104+{x}+24")
        self.attributes("-topmost", True)

    def setup_ui(self, title: str, message: str):
        is_error = self.notification_type in (NotificationType.ERROR, NotificationType.WARNING)
        bg_color = COLORS["danger_bg"] if is_error else COLORS["bg_surface"]
        border_color = COLORS["danger_border"] if is_error else COLORS["border_hairline"]
        icon_name = "warning" if is_error else ("check" if self.notification_type == NotificationType.SUCCESS else "info")
        icon_variant = "danger" if is_error else ("accent" if self.notification_type == NotificationType.SUCCESS else "muted")

        main_frame = ctk.CTkFrame(
            self,
            fg_color=bg_color,
            border_width=1,
            border_color=border_color,
            corner_radius=RADIUS["panel"],
        )
        main_frame.pack(fill="both", expand=True)

        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=16, pady=14)
        content_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            content_frame,
            text="",
            image=get_icon(icon_name, size=20, variant=icon_variant),
        ).grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="n")

        ctk.CTkLabel(
            content_frame,
            text=title,
            font=font(15, bold=True),
            text_color=COLORS["danger"] if is_error else COLORS["text_primary"],
            anchor="w",
        ).grid(row=0, column=1, sticky="ew")

        ctk.CTkLabel(
            content_frame,
            text=message,
            font=font(14),
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
            wraplength=280,
        ).grid(row=1, column=1, sticky="ew", pady=(2, 0))

        ctk.CTkButton(
            content_frame,
            text="",
            image=get_icon("close", size=14, variant="muted"),
            width=28,
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_control_hover"],
            corner_radius=RADIUS["control"],
            command=self.close_notification,
        ).grid(row=0, column=2, sticky="ne")

        main_frame.bind("<Button-1>", lambda e: self.close_notification())

    def close_notification(self):
        try:
            if self.on_close:
                self.on_close()
            if self.winfo_exists():
                self.destroy()
        except Exception:
            pass


class ErrorHandler:
    """Centralized Traditional Chinese error handler."""

    def __init__(self, notification_manager: NotificationManager):
        self.logger = logging.getLogger(__name__)
        self.notification_manager = notification_manager

    def handle_download_error(self, error: Exception, url: str = "", show_user: bool = True):
        user_msg = translate_error(error)
        self.logger.error("下載失敗 (%s): %s", url, error)
        if show_user:
            self.notification_manager.show_error("下載未完成", user_msg, show_toast=True)

    def handle_unexpected_error(self, error: Exception, context: str = ""):
        user_msg = "發生未預期的狀況，請再試一次，或點右上角「設定與修復」複製診斷紀錄。"
        self.logger.error("未預期錯誤 (%s): %s", context, error, exc_info=True)
        self.notification_manager.show_error("系統提醒", user_msg, show_toast=True, show_dialog=True)


_notification_manager = None
_error_handler = None


def get_notification_manager() -> NotificationManager:
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager


def get_error_handler() -> ErrorHandler:
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler(get_notification_manager())
    return _error_handler


def init_notifications(parent_window):
    notification_manager = get_notification_manager()
    notification_manager.set_parent_window(parent_window)
    return notification_manager
