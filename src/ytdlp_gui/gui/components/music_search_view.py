# -*- coding: utf-8 -*-
"""
Music Search & Pure MP3 Download View - Restrained Win11 Fluent Layout (Zero Emoji).
"""

import io
import logging
import os
import re
import threading
from typing import Callable, Dict, List, Optional

import customtkinter as ctk
import requests
from PIL import Image

from ytdlp_gui.core import ytdlp_wrapper
from ytdlp_gui.core.download_manager import DownloadStatus
from ytdlp_gui.gui.icons import get_icon, get_placeholder_thumb
from ytdlp_gui.gui.theme import COLORS, RADIUS, font
from ytdlp_gui.utils.error_translations import TranslatedError, analyze_error

_YT_URL_RE = re.compile(
    r"^https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/\S+",
    re.IGNORECASE,
)


class MusicSearchView(ctk.CTkFrame):
    """Search by song title or paste YouTube URL, with 1-click MP3 download."""

    def __init__(
        self,
        parent,
        download_manager,
        settings_manager,
        on_download_completed: Optional[Callable] = None,
        on_open_folder: Optional[Callable] = None,
    ):
        super().__init__(parent, fg_color="transparent")
        self.logger = logging.getLogger(__name__)
        self.download_manager = download_manager
        self.settings_manager = settings_manager
        self.on_download_completed = on_download_completed
        self.on_open_folder = on_open_folder

        self.results: List[dict] = []
        self.card_widgets: Dict[str, dict] = {}
        self.url_to_download_id: Dict[str, str] = {}
        self._thumb_cache: Dict[str, ctk.CTkImage] = {}
        self._placeholder_thumb = get_placeholder_thumb(120, 68)
        self._last_seen_clipboard = ""
        self._dismissed_clipboard_url = ""
        self._searching = False

        self._setup_ui()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # 0. Clipboard auto-detect bar (hidden until a YouTube URL is copied)
        self.clipboard_banner = ctk.CTkFrame(
            self,
            fg_color=COLORS["accent_subtle"],
            border_width=1,
            border_color=COLORS["accent_border"],
            corner_radius=RADIUS["panel"],
        )
        self.clipboard_banner.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.clipboard_banner,
            text="",
            image=get_icon("link", size=18, variant="accent"),
        ).grid(row=0, column=0, padx=(16, 10), pady=12)

        ctk.CTkLabel(
            self.clipboard_banner,
            text="偵測到剪貼簿中的 YouTube 網址，是否直接查看歌曲？",
            font=font(16, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).grid(row=0, column=1, pady=12, sticky="w")

        banner_btns = ctk.CTkFrame(self.clipboard_banner, fg_color="transparent")
        banner_btns.grid(row=0, column=2, padx=14, pady=10, sticky="e")

        ctk.CTkButton(
            banner_btns,
            text="查看歌曲",
            height=40,
            width=108,
            font=font(15, bold=True),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            corner_radius=RADIUS["control"],
            command=self._apply_clipboard_url,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            banner_btns,
            text="略過",
            height=40,
            width=72,
            font=font(15),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._dismiss_clipboard,
        ).pack(side="left")

        # 1. Flat Search Bar Surface
        search_bar = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_surface"],
            border_width=1,
            border_color=COLORS["border_hairline"],
            corner_radius=RADIUS["panel"],
        )
        search_bar.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        search_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            search_bar,
            text="搜尋歌名或貼上 YouTube 網址",
            font=font(17, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).grid(row=0, column=0, padx=18, pady=(14, 8), sticky="w")

        input_row = ctk.CTkFrame(search_bar, fg_color="transparent")
        input_row.grid(row=1, column=0, padx=18, pady=(0, 16), sticky="ew")
        input_row.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="輸入歌名、歌手，或貼上網址",
            height=50,
            font=font(17),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border_input"],
            border_width=1,
            text_color=COLORS["text_primary"],
            corner_radius=RADIUS["control"],
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self.perform_search())
        self.search_entry.bind("<KeyPress>", self._on_key_press)

        self.search_btn = ctk.CTkButton(
            input_row,
            text="搜尋",
            image=get_icon("search", size=18, variant="on_accent"),
            compound="left",
            width=126,
            height=50,
            font=font(17, bold=True),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            corner_radius=RADIUS["control"],
            command=self.perform_search,
        )
        self.search_btn.grid(row=0, column=1, padx=(0, 8))

        self.paste_btn = ctk.CTkButton(
            input_row,
            text="貼上網址",
            image=get_icon("paste", size=17, variant="default"),
            compound="left",
            width=128,
            height=50,
            font=font(16, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._paste_and_search,
        )
        self.paste_btn.grid(row=0, column=2)

        # 2. Results header + scrollable list
        results_wrap = ctk.CTkFrame(self, fg_color="transparent")
        results_wrap.grid(row=2, column=0, sticky="nsew")
        results_wrap.grid_columnconfigure(0, weight=1)
        results_wrap.grid_rowconfigure(1, weight=1)

        self.results_heading = ctk.CTkLabel(
            results_wrap,
            text="",
            font=font(15, bold=True),
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.results_heading.grid(row=0, column=0, pady=(0, 8), sticky="w")

        self.results_scroll = ctk.CTkScrollableFrame(
            results_wrap,
            fg_color="transparent",
            corner_radius=0,
        )
        self.results_scroll.grid(row=1, column=0, sticky="nsew")
        self.results_scroll.grid_columnconfigure(0, weight=1)

        self._show_empty_prompt()
        self.after(150, lambda: self.search_entry.focus())

    def _on_key_press(self, event):
        if not (event.state & 0x4):
            return None
        if event.keycode == 65:
            self.search_entry.select_range(0, "end")
            self.search_entry.icursor("end")
            return "break"
        if event.keycode == 86:
            self._paste_from_clipboard()
            return "break"
        return None

    def _paste_from_clipboard(self) -> str:
        try:
            content = self.clipboard_get().strip()
        except Exception:
            content = ""
        if content:
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, content)
        return content

    def _paste_and_search(self):
        content = self._paste_from_clipboard()
        if content:
            self.perform_search()

    def check_clipboard(self):
        try:
            content = self.clipboard_get().strip()
        except Exception:
            return
        if not content or content == self._last_seen_clipboard:
            return
        self._last_seen_clipboard = content
        if _YT_URL_RE.match(content) and content != self._dismissed_clipboard_url:
            if content != self.search_entry.get().strip():
                self.clipboard_banner.grid(row=0, column=0, sticky="ew", pady=(0, 12))

    def _apply_clipboard_url(self):
        url = self._last_seen_clipboard
        self.clipboard_banner.grid_remove()
        if url:
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, url)
            self.perform_search()

    def _dismiss_clipboard(self):
        self._dismissed_clipboard_url = self._last_seen_clipboard
        self.clipboard_banner.grid_remove()

    def _clear_results_container(self):
        for child in self.results_scroll.winfo_children():
            child.destroy()
        self.card_widgets.clear()

    def _show_empty_prompt(self):
        self._clear_results_container()
        self.results_heading.configure(text="")
        box = ctk.CTkFrame(self.results_scroll, fg_color="transparent")
        box.grid(row=0, column=0, sticky="ew", pady=48)
        ctk.CTkLabel(
            box,
            text="",
            image=get_icon("music", size=38, variant="muted"),
        ).pack(pady=(0, 12))
        ctk.CTkLabel(
            box,
            text="輸入歌名或貼上網址後按下「搜尋」",
            font=font(18, bold=True),
            text_color=COLORS["text_primary"],
        ).pack()
        ctk.CTkLabel(
            box,
            text="選取歌曲即可下載並轉存為 MP3 至系統預設的「下載」資料夾",
            font=font(15),
            text_color=COLORS["text_secondary"],
        ).pack(pady=(6, 0))

    def perform_search(self):
        query = self.search_entry.get().strip()
        if not query or self._searching:
            return

        self.logger.info("[UI_SEARCH] 使用者發起搜尋: %s", query)
        self._searching = True
        self.search_btn.configure(state="disabled", text="搜尋中")
        self.results_heading.configure(text=f"正在搜尋「{query}」...")
        self._clear_results_container()

        loading_box = ctk.CTkFrame(self.results_scroll, fg_color="transparent")
        loading_box.grid(row=0, column=0, sticky="ew", pady=40)
        ctk.CTkLabel(
            loading_box,
            text="正在取得歌曲清單，請稍候...",
            font=font(17, bold=True),
            text_color=COLORS["text_secondary"],
        ).pack()

        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query: str):
        results = ytdlp_wrapper.search_youtube(query, max_results=8, timeout=30)
        err = ytdlp_wrapper.get_last_error() if not results else ""
        if not results:
            diag = analyze_error(err)
            self.logger.warning(
                "[UI_SEARCH] 搜尋失敗 (query=%s, code=%s): %s",
                query,
                diag.code,
                err or "empty result",
            )
        else:
            self.logger.info("[UI_SEARCH] 搜尋成功: %d 筆結果 (query=%s)", len(results), query)
        self.after(0, lambda: self._on_search_finished(query, results, err))

    def _on_search_finished(self, query: str, results: List[dict], err: str):
        self._searching = False
        self.search_btn.configure(state="normal", text="搜尋")
        self.results = results
        self._clear_results_container()

        if not results:
            if err:
                diag = analyze_error(err)
            else:
                diag = TranslatedError(
                    code="NO_RESULTS",
                    category="youtube",
                    title="找不到符合的歌曲",
                    detail="找不到與輸入內容相符的歌曲或影片。",
                    suggestion="請嘗試更換歌名、歌手關鍵字，或直接貼上完整的 YouTube 影片網址。",
                )
            self.results_heading.configure(text="搜尋結果（0 筆）")
            err_box = ctk.CTkFrame(
                self.results_scroll,
                fg_color=COLORS["danger_bg"],
                border_width=1,
                border_color=COLORS["danger_border"],
                corner_radius=RADIUS["panel"],
            )
            err_box.grid(row=0, column=0, sticky="ew", pady=8)
            ctk.CTkLabel(
                err_box,
                text=f"  {diag.title}",
                image=get_icon("warning", size=20, variant="danger"),
                compound="left",
                font=font(16, bold=True),
                text_color=COLORS["danger"],
                wraplength=740,
                anchor="w",
                justify="left",
            ).pack(padx=20, pady=(16, 6), anchor="w")
            ctk.CTkLabel(
                err_box,
                text=diag.full_message(),
                font=font(14),
                text_color=COLORS["text_primary"],
                wraplength=760,
                anchor="w",
                justify="left",
            ).pack(padx=20, pady=(0, 8), anchor="w")
            ctk.CTkLabel(
                err_box,
                text=f"錯誤代碼：{diag.code}（可至右上角「設定與修復 → 複製診斷紀錄」協助排查）",
                font=font(12),
                text_color=COLORS["text_secondary"],
                wraplength=760,
                anchor="w",
                justify="left",
            ).pack(padx=20, pady=(0, 16), anchor="w")
            return

        self.results_heading.configure(text=f"搜尋結果（共 {len(results)} 筆）")
        for idx, song in enumerate(results):
            self._create_song_card(idx, song)

    def _create_song_card(self, row_idx: int, song: dict):
        card = ctk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["bg_surface"],
            border_width=1,
            border_color=COLORS["border_hairline"],
            corner_radius=RADIUS["panel"],
        )
        card.grid(row=row_idx, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(1, weight=1)

        thumb_label = ctk.CTkLabel(
            card,
            text="",
            image=self._thumb_cache.get(song["id"], self._placeholder_thumb),
        )
        thumb_label.grid(row=0, column=0, padx=(14, 14), pady=12, sticky="w")

        if song.get("thumbnail") and song["id"] not in self._thumb_cache:
            threading.Thread(
                target=self._load_thumbnail,
                args=(song["id"], song["thumbnail"], thumb_label),
                daemon=True,
            ).start()

        info_col = ctk.CTkFrame(card, fg_color="transparent")
        info_col.grid(row=0, column=1, pady=12, sticky="ew")
        info_col.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            info_col,
            text=song["title"],
            font=font(18, bold=True),
            text_color=COLORS["text_primary"],
            anchor="w",
            justify="left",
            wraplength=500,
        ).grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            info_col,
            text=f"{song['uploader']}  ·  長度 {song['duration_str']}",
            font=font(14),
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).grid(row=1, column=0, pady=(4, 0), sticky="w")

        action_col = ctk.CTkFrame(card, fg_color="transparent")
        action_col.grid(row=0, column=2, padx=16, pady=12, sticky="e")

        dl_btn = ctk.CTkButton(
            action_col,
            text="下載 MP3",
            image=get_icon("download", size=17, variant="on_accent"),
            compound="left",
            width=152,
            height=46,
            font=font(16, bold=True),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["accent_text"],
            corner_radius=RADIUS["control"],
            command=lambda s=song: self._start_song_download(s),
        )
        dl_btn.pack()

        status_label = ctk.CTkLabel(
            action_col,
            text="",
            font=font(14, bold=True),
            text_color=COLORS["text_primary"],
            wraplength=200,
        )
        progress_bar = ctk.CTkProgressBar(
            action_col,
            width=168,
            height=8,
            progress_color=COLORS["accent"],
            fg_color=COLORS["border_hairline"],
        )
        progress_bar.set(0)

        open_btn = ctk.CTkButton(
            action_col,
            text="開啟資料夾",
            image=get_icon("folder_open", size=16, variant="default"),
            compound="left",
            width=152,
            height=42,
            font=font(15, bold=True),
            fg_color=COLORS["bg_control"],
            hover_color=COLORS["bg_control_hover"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border_input"],
            corner_radius=RADIUS["control"],
            command=self._handle_open_folder,
        )

        self.card_widgets[song["url"]] = {
            "song": song,
            "dl_btn": dl_btn,
            "status_label": status_label,
            "progress_bar": progress_bar,
            "open_btn": open_btn,
            "notified_done": False,
        }

        existing_id = self.url_to_download_id.get(song["url"])
        if existing_id:
            self._sync_card_with_download(song["url"], existing_id)

    def _load_thumbnail(self, song_id: str, url: str, label: ctk.CTkLabel):
        try:
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            img = img.resize((120, 68), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(120, 68))
            self._thumb_cache[song_id] = ctk_img
            self.after(0, lambda: self._apply_thumb(label, ctk_img))
        except Exception:
            pass

    def _apply_thumb(self, label: ctk.CTkLabel, ctk_img: ctk.CTkImage):
        try:
            if label.winfo_exists():
                label.configure(image=ctk_img)
        except Exception:
            pass

    def _start_song_download(self, song: dict):
        url = song["url"]
        widgets = self.card_widgets.get(url)
        if widgets:
            widgets["dl_btn"].pack_forget()
            widgets["open_btn"].pack_forget()
            widgets["status_label"].configure(
                text="準備下載中",
                text_color=COLORS["text_secondary"],
                image=None,
            )
            widgets["status_label"].pack(pady=(0, 6))
            widgets["progress_bar"].set(0.08)
            widgets["progress_bar"].pack()
            widgets["notified_done"] = False

        def _enqueue():
            try:
                out_dir = self.settings_manager.get_output_directory()
                dl_id = self.download_manager.add_download(
                    url=url,
                    format_info={"audio_only": True, "audio_format": "mp3"},
                    output_path=out_dir,
                    video_title=song["title"],
                )
                self.url_to_download_id[url] = dl_id
                self.download_manager.add_progress_callback(
                    dl_id, lambda u=url, d=dl_id: self.after(0, lambda: self._sync_card_with_download(u, d))
                )
                self.after(0, lambda: self._sync_card_with_download(url, dl_id))
            except Exception as e:
                self.logger.error("加入下載失敗: %s", e)

        threading.Thread(target=_enqueue, daemon=True).start()

    def _sync_card_with_download(self, url: str, download_id: str):
        widgets = self.card_widgets.get(url)
        item = self.download_manager.get_download_item(download_id)
        if not widgets or not item:
            return

        status_label = widgets["status_label"]
        progress_bar = widgets["progress_bar"]
        dl_btn = widgets["dl_btn"]
        open_btn = widgets["open_btn"]

        try:
            if not status_label.winfo_exists():
                return
        except Exception:
            return

        if item.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING):
            dl_btn.pack_forget()
            open_btn.pack_forget()
            if item.stage == "converting":
                txt = "正在轉換 MP3"
                pct = 0.92
            elif item.status == DownloadStatus.PENDING:
                txt = "等待下載"
                pct = 0.08
            else:
                txt = f"下載中 {int(item.progress)}%"
                pct = max(0.08, min(0.95, item.progress / 100.0))
            status_label.configure(text=txt, text_color=COLORS["text_primary"], image=None)
            status_label.pack(pady=(0, 6))
            progress_bar.set(pct)
            progress_bar.pack()
        elif item.status == DownloadStatus.COMPLETED:
            dl_btn.pack_forget()
            progress_bar.pack_forget()
            status_label.configure(
                text=" 已完成",
                image=get_icon("check", size=15, variant="accent"),
                compound="left",
                text_color=COLORS["accent"],
            )
            status_label.pack(pady=(0, 6))
            open_btn.pack()
            if not widgets["notified_done"]:
                widgets["notified_done"] = True
                if self.on_download_completed:
                    self.on_download_completed()
        elif item.status == DownloadStatus.FAILED:
            progress_bar.pack_forget()
            open_btn.pack_forget()
            msg = getattr(item, "error_title", "") or item.error_message or "下載失敗，請再試一次"
            if len(msg) > 48:
                msg = msg[:46] + "..."
            status_label.configure(
                text=msg,
                text_color=COLORS["danger"],
                image=None,
            )
            status_label.pack(pady=(0, 6))
            dl_btn.configure(text="重試下載", image=get_icon("refresh", size=16, variant="on_accent"))
            dl_btn.pack()

    def _handle_open_folder(self):
        if self.on_open_folder:
            self.on_open_folder()
        else:
            out_dir = self.settings_manager.get_output_directory()
            if os.name == "nt":
                os.startfile(out_dir)
