# -*- coding: utf-8 -*-
"""
Download Manager - Pure MP3 queue manager with portable persistence.
"""

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ytdlp_gui.utils.error_translations import translate_error
from ytdlp_gui.utils.logger import flush_logs

from . import ytdlp_wrapper
from .cookie_manager import CookieManager, cookie_opts_to_cli


class DownloadStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    url: str = ""
    title: str = ""
    format_info: Dict = field(default_factory=dict)
    output_path: str = ""
    status: DownloadStatus = DownloadStatus.PENDING
    stage: str = "preparing"
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    file_size: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    saved_filepath: str = ""
    error_message: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


class DownloadManager:
    """Pure MP3 download manager."""

    def __init__(self, settings_manager):
        self.logger = logging.getLogger(__name__)
        self.settings_manager = settings_manager
        self.cookie_manager = CookieManager(settings_manager)
        self.download_queue: List[DownloadItem] = []
        self.active_downloads: Dict[str, threading.Thread] = {}
        self.download_callbacks: List[Callable] = []
        self.queue_lock = threading.Lock()
        self.max_concurrent_downloads = settings_manager.get("max_concurrent_downloads", 2)
        self.progress_callbacks: Dict[str, List[Callable]] = {}
        self.queue_file = self._get_queue_file_path()

        from ytdlp_gui.core.history_manager import HistoryManager

        self.history_manager = HistoryManager(settings_manager)

        try:
            from ytdlp_gui.utils.logger import log_download_event
            from ytdlp_gui.utils.notifications import get_error_handler, get_notification_manager

            self.notification_manager = get_notification_manager()
            self.error_handler = get_error_handler()
            self.log_download_event = log_download_event
        except ImportError:
            self.notification_manager = None
            self.error_handler = None
            self.log_download_event = lambda *args: None

        self.load_queue()

    def add_download(
        self,
        url: str,
        format_info: Optional[Dict] = None,
        output_path: Optional[str] = None,
        video_title: Optional[str] = None,
    ) -> str:
        """Add a new Pure MP3 download to the queue."""
        resolved_output = output_path or self.settings_manager.get_output_directory()
        mp3_format = {
            "audio_only": True,
            "audio_format": "mp3",
            "audio_quality": "0",
            "format_id": "bestaudio/best",
        }
        if format_info:
            mp3_format.update(format_info)
            mp3_format["audio_only"] = True
            mp3_format["audio_format"] = "mp3"

        download_item = DownloadItem(
            url=url,
            format_info=mp3_format,
            output_path=resolved_output,
            stage="preparing",
        )

        if video_title:
            download_item.title = video_title
        else:
            self._get_video_info(download_item)

        with self.queue_lock:
            self.download_queue.append(download_item)

        self.logger.info("加入下載佇列: %s (%s)", download_item.title, download_item.id)
        self.log_download_event("ADDED", url, download_item.title)

        self.save_queue()
        self._notify_queue_change()
        self._process_queue()
        return download_item.id

    def get_queue(self) -> List[DownloadItem]:
        with self.queue_lock:
            return self.download_queue.copy()

    def get_download_item(self, download_id: str) -> Optional[DownloadItem]:
        with self.queue_lock:
            for item in self.download_queue:
                if item.id == download_id:
                    return item
            return None

    def add_progress_callback(self, download_id: str, callback: Callable):
        if download_id not in self.progress_callbacks:
            self.progress_callbacks[download_id] = []
        self.progress_callbacks[download_id].append(callback)

    def add_queue_callback(self, callback: Callable):
        self.download_callbacks.append(callback)

    def stop_all_downloads(self):
        with self.queue_lock:
            for download_id in list(self.active_downloads.keys()):
                self._cancel_download(download_id)
        self.save_queue()

    def _get_video_info(self, download_item: DownloadItem):
        """Fetch title without downloading; try no-cookie first."""
        try:
            base_args = [
                "--add-header",
                "Accept-Language: zh-TW,zh;q=0.9,en;q=0.8",
            ]
            info = None
            for browser in [None, "firefox", "edge", "chrome"]:
                extra = list(base_args)
                if browser is None:
                    self.cookie_manager.add_cookie_file_args(extra)
                else:
                    cookie_opts = self.cookie_manager.get_cookie_options(
                        download_item.url, browser=browser
                    )
                    if cookie_opts:
                        extra.extend(cookie_opts_to_cli(cookie_opts))
                info = ytdlp_wrapper.extract_info(download_item.url, extra_args=extra)
                if info:
                    break

            if info:
                download_item.title = info.get("title") or "未命名歌曲"
                download_item.file_size = ytdlp_wrapper.format_bytes(info.get("filesize") or 0)
            else:
                download_item.title = "未命名歌曲"
        except Exception as e:
            self.logger.warning("取得歌曲資訊失敗: %s", e)
            download_item.title = "未命名歌曲"

    def _process_queue(self):
        with self.queue_lock:
            if len(self.active_downloads) >= self.max_concurrent_downloads:
                return
            for item in self.download_queue:
                if item.status == DownloadStatus.PENDING:
                    self._start_download(item)
                    if len(self.active_downloads) >= self.max_concurrent_downloads:
                        break

    def _start_download(self, download_item: DownloadItem):
        try:
            download_item.status = DownloadStatus.DOWNLOADING
            download_item.stage = "downloading"
            thread = threading.Thread(
                target=self._download_worker, args=(download_item,), daemon=True
            )
            self.active_downloads[download_item.id] = thread
            thread.start()
            self.logger.info("開始下載 MP3: %s", download_item.title)
            self._notify_progress_change(download_item.id)
        except Exception as e:
            self.logger.error("無法啟動下載: %s", e)
            download_item.status = DownloadStatus.FAILED
            download_item.stage = "failed"
            download_item.error_message = translate_error(e)
            self._notify_progress_change(download_item.id)

    def _download_worker(self, download_item: DownloadItem):
        """Try public download first (None), then fall back to browser cookies only on auth/403."""
        cookie_browsers = [None, "firefox", "edge", "chrome"]
        last_error = None
        success = False

        for browser in cookie_browsers:
            try:
                extra_args, format_spec, output_template = self._prepare_ydl_options(
                    download_item, browser=browser, use_cookies=browser is not None
                )

                def progress_callback(p):
                    self._on_subprocess_progress(p, download_item.id)

                exit_code = ytdlp_wrapper.download(
                    download_item.url,
                    output_template,
                    format_spec,
                    extra_args=extra_args,
                    progress_callback=progress_callback,
                )

                if exit_code == 0:
                    download_item.status = DownloadStatus.COMPLETED
                    download_item.stage = "completed"
                    download_item.completed_at = time.time()
                    download_item.progress = 100.0
                    download_item.speed = ""
                    download_item.eta = ""

                    self.logger.info("下載完成 (MP3): %s", download_item.title)
                    self.log_download_event("COMPLETED", download_item.url, download_item.title)

                    if self.notification_manager:
                        self.notification_manager.show_success(
                            "下載完成",
                            f"「{download_item.title}」已存成 MP3 音樂檔！",
                        )

                    success = True
                    break
                else:
                    real_error = ytdlp_wrapper.get_last_error()
                    raise Exception(real_error or f"yt-dlp exited with code {exit_code}")

            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                self.logger.warning("嘗試下載失敗 (%s): %s", browser or "無 Cookie", e)

                if any(
                    kw in error_msg
                    for kw in [
                        "sign in",
                        "confirm you",
                        "bot",
                        "cookie",
                        "403",
                        "forbidden",
                        "dpapi",
                        "failed to decrypt",
                    ]
                ):
                    if browser != cookie_browsers[-1]:
                        continue
                break

        if not success:
            self.logger.error("MP3 下載失敗: %s", last_error)
            download_item.status = DownloadStatus.FAILED
            download_item.stage = "failed"
            download_item.error_message = translate_error(last_error)
            self.log_download_event("FAILED", download_item.url, str(last_error))

            if self.error_handler:
                self.error_handler.handle_download_error(
                    last_error, download_item.url, show_user=True
                )

        try:
            self.history_manager.add_download(download_item)
        except Exception as e:
            self.logger.error("儲存歷史紀錄失敗: %s", e)

        if download_item.id in self.active_downloads:
            del self.active_downloads[download_item.id]

        self.save_queue()
        self._notify_progress_change(download_item.id)
        self._process_queue()

    def _on_subprocess_progress(self, progress: dict, download_id: str):
        try:
            download_item = self.get_download_item(download_id)
            if not download_item:
                return

            if "stage" in progress:
                download_item.stage = progress["stage"]
            if "filepath" in progress and progress["filepath"]:
                download_item.saved_filepath = progress["filepath"]

            percent = progress.get("percent", download_item.progress)
            download_item.progress = percent
            download_item.speed = progress.get("speed", "")
            download_item.eta = progress.get("eta", "")

            total_bytes = progress.get("total_bytes", 0)
            if total_bytes > 0:
                download_item.total_bytes = total_bytes
                download_item.downloaded_bytes = int(total_bytes * percent / 100)

            if "error" in progress:
                download_item.status = DownloadStatus.FAILED
                download_item.stage = "failed"
                download_item.error_message = translate_error(Exception(progress["error"]))

            self._notify_progress_change(download_id)
        except Exception as e:
            self.logger.error("更新下載進度發生錯誤: %s", e)

    def _prepare_ydl_options(
        self, download_item: DownloadItem, browser: str = None, use_cookies: bool = False
    ):
        """Always prepare pure high-quality MP3 extraction arguments."""
        output_path = Path(download_item.output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        output_template = str(output_path / "%(title)s.%(ext)s")

        extra_args = [
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--add-metadata",
            "--windows-filenames",
            "--no-check-certificate",
            "--add-header",
            "Accept-Language: zh-TW,zh;q=0.9,en;q=0.8",
            "--add-header",
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        if use_cookies and browser:
            cookie_opts = self.cookie_manager.get_cookie_options(
                download_item.url, browser=browser
            )
            if cookie_opts:
                extra_args.extend(cookie_opts_to_cli(cookie_opts))
        else:
            self.cookie_manager.add_cookie_file_args(extra_args)

        return extra_args, "bestaudio/best", output_template

    def _cancel_download(self, download_id: str):
        if download_id in self.active_downloads:
            item = self.get_download_item(download_id)
            if item:
                item.status = DownloadStatus.CANCELLED
                item.stage = "cancelled"
                self._notify_progress_change(download_id)

    def _notify_progress_change(self, download_id: str):
        if download_id in self.progress_callbacks:
            for callback in list(self.progress_callbacks[download_id]):
                try:
                    callback()
                except Exception as e:
                    self.logger.error("Progress callback error: %s", e)

    def _notify_queue_change(self):
        for callback in list(self.download_callbacks):
            try:
                callback()
            except Exception as e:
                self.logger.error("Queue callback error: %s", e)

    def _get_queue_file_path(self) -> Path:
        return self.settings_manager.settings_dir / "download_queue.json"

    def _write_json_with_timeout(self, path: Path, data, timeout: float = 3.0) -> bool:
        result = [False]

        def _do_write():
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                result[0] = True
            except Exception:
                pass

        thread = threading.Thread(target=_do_write, daemon=True)
        thread.start()
        thread.join(timeout)
        return result[0]

    def save_queue(self):
        try:
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            queue_data = []
            with self.queue_lock:
                for item in self.download_queue:
                    item_dict = asdict(item)
                    item_dict["status"] = item.status.value
                    queue_data.append(item_dict)

            if not self._write_json_with_timeout(self.queue_file, queue_data):
                self.logger.warning("寫入下載佇列逾時")
                return
            flush_logs()
        except Exception as e:
            self.logger.error("儲存下載佇列失敗: %s", e)

    def load_queue(self):
        try:
            if not self.queue_file.exists():
                return

            with open(self.queue_file, "r", encoding="utf-8") as f:
                queue_data = json.load(f)

            valid_fields = {f.name for f in fields(DownloadItem)}
            loaded_items = []
            for raw_dict in queue_data:
                item_dict = {k: v for k, v in raw_dict.items() if k in valid_fields}
                try:
                    status = DownloadStatus(item_dict.get("status", "pending"))
                except ValueError:
                    status = DownloadStatus.PENDING
                item_dict["status"] = status
                download_item = DownloadItem(**item_dict)

                if download_item.status == DownloadStatus.CANCELLED:
                    continue
                if download_item.status == DownloadStatus.DOWNLOADING:
                    download_item.status = DownloadStatus.PENDING
                    download_item.stage = "preparing"
                    download_item.progress = 0.0
                    download_item.speed = ""
                    download_item.eta = ""
                loaded_items.append(download_item)

            with self.queue_lock:
                self.download_queue = loaded_items

            self._cleanup_old_failed_downloads()
            self._process_queue()
        except Exception as e:
            self.logger.error("讀取下載佇列失敗: %s", e)

    def _cleanup_old_failed_downloads(self):
        try:
            current_time = time.time()
            cleanup_threshold = 24 * 60 * 60
            with self.queue_lock:
                self.download_queue = [
                    item
                    for item in self.download_queue
                    if not (
                        item.status == DownloadStatus.FAILED
                        and current_time - item.created_at > cleanup_threshold
                    )
                ]
        except Exception as e:
            self.logger.error("清理過期失敗佇列錯誤: %s", e)

    def get_download_history(self, status_filter: Optional[str] = None, limit: Optional[int] = None):
        try:
            return self.history_manager.get_download_history(status_filter, limit)
        except Exception as e:
            self.logger.error("讀取歷史紀錄失敗: %s", e)
            return []

    def clear_failed_downloads(self):
        try:
            with self.queue_lock:
                before = len(self.download_queue)
                self.download_queue = [
                    item for item in self.download_queue if item.status != DownloadStatus.FAILED
                ]
                cleared = before - len(self.download_queue)
            if cleared > 0:
                self.save_queue()
                self._notify_queue_change()
            return cleared
        except Exception:
            return 0

    def clear_completed_downloads_simple(self):
        try:
            with self.queue_lock:
                before = len(self.download_queue)
                self.download_queue = [
                    item
                    for item in self.download_queue
                    if item.status
                    not in [
                        DownloadStatus.COMPLETED,
                        DownloadStatus.FAILED,
                        DownloadStatus.CANCELLED,
                    ]
                ]
                return before - len(self.download_queue)
        except Exception:
            return 0

    def clear_history(self, status_filter: Optional[str] = None) -> bool:
        try:
            return self.history_manager.clear_history(status_filter)
        except Exception:
            return False
