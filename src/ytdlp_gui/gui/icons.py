# -*- coding: utf-8 -*-
"""
Monochrome Windows Segoe Fluent Icons renderer for CustomTkinter.
Renders 2x supersampled glyphs via Pillow into CTkImage (light/dark pairs).
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from .theme import COLORS

GLYPHS = {
    "search": "\uE721",
    "music": "\uE8D6",
    "folder": "\uE8B7",
    "folder_open": "\uE838",
    "download": "\uE896",
    "play": "\uE768",
    "paste": "\uE77F",
    "settings": "\uE713",
    "refresh": "\uE72C",
    "copy": "\uE8C8",
    "sun": "\uE706",
    "moon": "\uE708",
    "check": "\uE73E",
    "warning": "\uE7BA",
    "link": "\uE71B",
    "close": "\uE711",
    "repair": "\uE90F",
    "info": "\uE946",
}

_VARIANT_COLORS: Dict[str, Tuple[str, str]] = {
    "default": COLORS["text_primary"],
    "muted": COLORS["text_secondary"],
    "on_accent": (COLORS["accent_text"], COLORS["accent_text"]),
    "accent": COLORS["accent"],
    "danger": COLORS["danger"],
}

_ICON_CACHE: Dict[Tuple[str, int, str], ctk.CTkImage] = {}
_THUMB_CACHE: Dict[Tuple[int, int], ctk.CTkImage] = {}
_FONT_PATH: Optional[Path] = None
_FONT_SEARCHED = False


def _find_icon_font() -> Optional[Path]:
    global _FONT_PATH, _FONT_SEARCHED
    if _FONT_SEARCHED:
        return _FONT_PATH
    _FONT_SEARCHED = True
    for candidate in (
        Path(r"C:\Windows\Fonts\SegoeIcons.ttf"),
        Path(r"C:\Windows\Fonts\segmdl2.ttf"),
    ):
        if candidate.exists():
            _FONT_PATH = candidate
            break
    return _FONT_PATH


def _render_fallback_glyph(name: str, size: int, hex_color: str) -> Image.Image:
    """Minimal geometric vector fallback if Windows icon font is unavailable."""
    scale = 2
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(4, s // 6)
    lw = max(2, s // 10)
    if name == "play":
        draw.polygon([(pad, pad), (s - pad, s // 2), (pad, s - pad)], fill=hex_color)
    elif name == "check":
        draw.line([(pad, s // 2), (s * 2 // 5, s - pad), (s - pad, pad)], fill=hex_color, width=lw)
    else:
        draw.ellipse((pad, pad, s - pad, s - pad), outline=hex_color, width=lw)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _render_glyph_image(name: str, size: int, hex_color: str) -> Image.Image:
    font_path = _find_icon_font()
    glyph = GLYPHS.get(name)
    if not font_path or not glyph:
        return _render_fallback_glyph(name, size, hex_color)

    scale = 2
    canvas_sz = size * scale
    font_px = max(12, int(canvas_sz * 0.85))
    try:
        pil_font = ImageFont.truetype(str(font_path), font_px)
    except Exception:
        return _render_fallback_glyph(name, size, hex_color)

    img = Image.new("RGBA", (canvas_sz, canvas_sz), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), glyph, font=pil_font)
    gw = bbox[2] - bbox[0]
    gh = bbox[3] - bbox[1]
    x = (canvas_sz - gw) / 2 - bbox[0]
    y = (canvas_sz - gh) / 2 - bbox[1]
    draw.text((x, y), glyph, font=pil_font, fill=hex_color)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def get_icon(name: str, size: int = 18, variant: str = "default") -> ctk.CTkImage:
    """Return a cached light/dark monochrome CTkImage for the named Fluent icon."""
    key = (name, size, variant)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    light_hex, dark_hex = _VARIANT_COLORS.get(variant, COLORS["text_primary"])
    light_img = _render_glyph_image(name, size, light_hex)
    dark_img = _render_glyph_image(name, size, dark_hex)
    ctk_img = ctk.CTkImage(light_image=light_img, dark_image=dark_img, size=(size, size))
    _ICON_CACHE[key] = ctk_img
    return ctk_img


def get_placeholder_thumb(width: int = 120, height: int = 68) -> ctk.CTkImage:
    """Return a restrained neutral placeholder thumbnail with centered music glyph."""
    key = (width, height)
    if key in _THUMB_CACHE:
        return _THUMB_CACHE[key]

    def _make(bg_hex: str, fg_hex: str) -> Image.Image:
        img = Image.new("RGBA", (width * 2, height * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((0, 0, width * 2 - 1, height * 2 - 1), radius=12, fill=bg_hex)
        glyph_img = _render_glyph_image("music", 48, fg_hex)
        gx = (width * 2 - 48) // 2
        gy = (height * 2 - 48) // 2
        img.paste(glyph_img, (gx, gy), glyph_img)
        return img.resize((width, height), Image.Resampling.LANCZOS)

    light_bg, dark_bg = COLORS["thumb_bg"]
    ctk_img = ctk.CTkImage(
        light_image=_make(light_bg, "#6B6B6B"),
        dark_image=_make(dark_bg, "#A3A3A3"),
        size=(width, height),
    )
    _THUMB_CACHE[key] = ctk_img
    return ctk_img
