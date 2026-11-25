# -*- coding: utf-8 -*-
"""
Native Windows 11 Fluent Design Tokens, Fonts, and DWM Titlebar Integration.
"""

import ctypes
import platform
from typing import Tuple, Union

import customtkinter as ctk

FONT_FAMILY = "Microsoft JhengHei UI"

ColorToken = Union[str, Tuple[str, str]]

COLORS = {
    "bg_canvas": ("#F3F3F3", "#202020"),
    "bg_surface": ("#FFFFFF", "#2B2B2B"),
    "bg_surface_subtle": ("#F8F8F8", "#262626"),
    "bg_input": ("#FAFAFA", "#1C1C1C"),
    "bg_control": ("#FFFFFF", "#323232"),
    "bg_control_hover": ("#EFEFEF", "#3C3C3C"),
    "border_hairline": ("#E2E2E2", "#383838"),
    "border_input": ("#C8C8C8", "#4A4A4A"),
    "text_primary": ("#1A1A1A", "#F3F3F3"),
    "text_secondary": ("#525252", "#B8B8B8"),
    "accent": ("#0F6B4A", "#2EA87A"),
    "accent_hover": ("#0B553B", "#249168"),
    "accent_subtle": ("#E6F4EE", "#1B3B2F"),
    "accent_border": ("#9FD4BE", "#2C6E56"),
    "accent_text": "#FFFFFF",
    "danger": ("#B42318", "#F87171"),
    "danger_bg": ("#FEF3F2", "#381B1A"),
    "danger_border": ("#F5C2C0", "#6E2B2A"),
    "thumb_bg": ("#EAEAEA", "#353535"),
}

RADIUS = {
    "control": 6,
    "panel": 8,
}


def font(size: int = 16, bold: bool = False) -> ctk.CTkFont:
    """Create a Microsoft JhengHei UI font with consistent sizing."""
    return ctk.CTkFont(
        family=FONT_FAMILY,
        size=size,
        weight="bold" if bold else "normal",
    )


def _hex_to_colorref(hex_color: str) -> int:
    """Convert #RRGGBB string to Windows COLORREF (0x00BBGGRR)."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_windows_titlebar(window, mode: str) -> None:
    """Synchronize native Windows 11 titlebar dark/light mode and caption color."""
    if platform.system() != "Windows":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        if not hwnd:
            return

        dwmapi = ctypes.windll.dwmapi
        is_dark = 1 if mode == "dark" else 0

        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        val_dark = ctypes.c_int(is_dark)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val_dark), ctypes.sizeof(val_dark))

        # DWMWA_CAPTION_COLOR = 35, DWMWA_TEXT_COLOR = 36 (Windows 11 22000+)
        caption_hex = "#202020" if is_dark else "#F3F3F3"
        text_hex = "#F3F3F3" if is_dark else "#1A1A1A"

        val_cap = ctypes.c_int(_hex_to_colorref(caption_hex))
        val_txt = ctypes.c_int(_hex_to_colorref(text_hex))
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(val_cap), ctypes.sizeof(val_cap))
        dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(val_txt), ctypes.sizeof(val_txt))
    except Exception:
        pass
