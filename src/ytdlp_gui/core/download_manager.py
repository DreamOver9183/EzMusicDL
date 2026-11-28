# -*- coding: utf-8 -*-
"""
Download Manager - Pure MP3 queue manager with portable persistence,
smart fallback error preservation, and detailed diagnostics logging.
"""

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ytdlp_gui.utils.error_translations import analyze_error, is_local_cookie_error
from ytdlp_gui.utils.logger import flush_logs

from . import process_tracker, ytdlp_wrapper
from .cookie_manager import CookieManager, cookie_opts_to_cli

_RETRY_KEYWORDS = (
    "sign in",
    "confirm you",
    "not a bot",
    "bot",
    "cookie",
    "403",
    "forbidden",
    "dpapi",
    "failed to decrypt",
)


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
    error_code: str = ""
    error_title: str = ""
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
        self._save_lock = threading.Lock()
        self._cancel_events: Dict[str, threading.Event] = {}
        self._stopping: bool = False
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

        self.logger.info(
            "加入下載佇列: %s (id=%s, url=%s, out=%s)",
            download_item.title,
            download_item.id[:8],
            url,
            resolved_output,
        )
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

    def _is_shutting_down(self) -> bool:
        return self._stopping or process_tracker.tracker.shutting_down

    def stop_all_downloads(self):
        self._stopping = True
        events_to_set = []
        with self.queue_lock:
            for item in self.download_queue:
                if item.status == DownloadStatus.DOWNLOADING:
                    item.status = DownloadStatus.CANCELLED
                    item.stage = "cancelled"
                    evt = self._cancel_events.get(item.id)
                    if evt is not None:
                        events_to_set.append(evt)

        for evt in events_to_set:
            evt.set()

        process_tracker.tracker.shutdown()
        self.save_queue()

    def _get_video_info(self, download_item: DownloadItem):
        """Fetch title without downloading; try no-cookie first, skipping unavailable browsers."""
        try:
            base_args = [
                "--add-header",
                "Accept-Language: zh-TW,zh;q=0.9,en;q=0.8",
            ]
            info = None
            browsers = [None, "firefox", "edge", "chrome"]
            for idx, browser in enumerate(browsers, 1):
                if self._is_shutting_down():
                    break
                extra = list(base_args)
                if browser is None:
                    self.cookie_manager.add_cookie_file_args(extra)
                    strategy = "無瀏覽器 Cookie / cookies.txt"
                else:
                    cookie_opts = self.cookie_manager.get_cookie_options(
                        download_item.url, browser=browser
                    )
                    if not cookie_opts:
                        self.logger.debug(
                            "[INFO_FETCH] 略過不可用/未啟用的瀏覽器: %s",
                            browser,
                        )
                        continue
                    extra.extend(cookie_opts_to_cli(cookie_opts))
                    strategy = f"browser={browser}"

                self.logger.info(
                    "[INFO_FETCH] 嘗試 %d/%d (%s) url=%s",
                    idx,
                    len(browsers),
                    strategy,
                    download_item.url,
                )
                info = ytdlp_wrapper.extract_info(download_item.url, extra_args=extra)
                if info:
                    break
                if self._is_shutting_down():
                    break
                raw_err = ytdlp_wrapper.get_last_error()
                if raw_err:
                    diag = analyze_error(raw_err)
                    self.logger.warning(
                        "[INFO_FETCH] 失敗 (%s, code=%s): %s",
                        strategy,
                        diag.code,
                        raw_err,
                    )

            if info:
                download_item.title = info.get("title") or "未命名歌曲"
                download_item.file_size = ytdlp_wrapper.format_bytes(info.get("filesize") or 0)
            else:
                download_item.title = "未命名歌曲"
        except Exception as e:
            self.logger.warning("取得歌曲資訊失敗: %s", e)
            download_item.title = "未命名歌曲"

    def _process_queue(self):
        if self._stopping or process_tracker.tracker.shutting_down:
            return

        to_start = []
        with self.queue_lock:
            if self._stopping:
                return
            available_slots = self.max_concurrent_downloads - len(self.active_downloads)
            if available_slots <= 0:
                return

            for item in self.download_queue:
                if item.status == DownloadStatus.PENDING:
                    item.status = DownloadStatus.DOWNLOADING
                    item.stage = "downloading"
                    item.error_code = ""
                    item.error_title = ""
                    item.error_message = ""

                    cancel_event = threading.Event()
                    self._cancel_events[item.id] = cancel_event

                    thread = threading.Thread(
                        target=self._download_worker,
                        args=(item, cancel_event),
                        daemon=True,
                    )
                    self.active_downloads[item.id] = thread
                    to_start.append((item, thread))

                    available_slots -= 1
                    if available_slots <= 0:
                        break

        for item, thread in to_start:
            try:
                thread.start()
                self.logger.info("開始下載 MP3: %s (id=%s)", item.title, item.id[:8])
                self._notify_progress_change(item.id)
            except Exception as e:
                diag = analyze_error(e)
                with self.queue_lock:
                    self.active_downloads.pop(item.id, None)
                    self._cancel_events.pop(item.id, None)
                    if item.status == DownloadStatus.DOWNLOADING:
                        item.status = DownloadStatus.FAILED
                        item.stage = "failed"
                        item.error_code = diag.code
                        item.error_title = diag.title
                        item.error_message = diag.full_message()
                self.logger.error("無法啟動下載 (%s): %s", diag.code, e, exc_info=True)
                self._notify_progress_change(item.id)

    def _download_worker(self, download_item: DownloadItem, cancel_event: Optional[threading.Event] = None):
        """Try public download first (None), then fall back to available browser cookies on auth/403."""
        if cancel_event is None:
            with self.queue_lock:
                cancel_event = self._cancel_events.get(download_item.id)
            if cancel_event is None:
                cancel_event = threading.Event()

        short_id = download_item.id[:8]
        cookie_browsers = [None, "firefox", "edge", "chrome"]
        primary_error: Optional[Exception] = None
        last_error: Optional[Exception] = None
        attempt_logs: List[str] = []
        success = False
        is_cancelled = False
        marked_failed = False

        try:
            for idx, browser in enumerate(cookie_browsers, 1):
                if (
                    cancel_event.is_set()
                    or self._stopping
                    or process_tracker.tracker.shutting_down
                    or download_item.status == DownloadStatus.CANCELLED
                ):
                    is_cancelled = True
                    break

                strategy = "無瀏覽器 Cookie / cookies.txt" if browser is None else f"browser={browser}"
                if browser is not None:
                    cookie_opts = self.cookie_manager.get_cookie_options(
                        download_item.url, browser=browser
                    )
                    if not cookie_opts:
                        msg = f"略過 {browser}（未安裝或未啟用 Cookie）"
                        attempt_logs.append(f"{idx}. {strategy}: skipped")
                        self.logger.info("[DL %s] %s", short_id, msg)
                        continue
                else:
                    cookie_opts = None

                self.logger.info(
                    "[DL %s] 嘗試 %d/%d（策略: %s）url=%s",
                    short_id,
                    idx,
                    len(cookie_browsers),
                    strategy,
                    download_item.url,
                )
                attempt_started = time.perf_counter()
                try:
                    extra_args, format_spec, output_template = self._prepare_ydl_options(
                        download_item,
                        browser=browser,
                        use_cookies=browser is not None,
                        cookie_opts=cookie_opts,
                    )

                    def progress_callback(p):
                        self._on_subprocess_progress(p, download_item.id)

                    exit_code = ytdlp_wrapper.download(
                        download_item.url,
                        output_template,
                        format_spec,
                        extra_args=extra_args,
                        progress_callback=progress_callback,
                        cancel_event=cancel_event,
                    )

                    if (
                        cancel_event.is_set()
                        or self._stopping
                        or process_tracker.tracker.shutting_down
                        or download_item.status == DownloadStatus.CANCELLED
                    ):
                        is_cancelled = True
                        break

                    if exit_code == 0:
                        elapsed_ms = int((time.perf_counter() - attempt_started) * 1000)
                        now = time.time()
                        with self.queue_lock:
                            if (
                                download_item.status == DownloadStatus.CANCELLED
                                or cancel_event.is_set()
                                or self._stopping
                            ):
                                if download_item.status == DownloadStatus.DOWNLOADING:
                                    download_item.status = DownloadStatus.CANCELLED
                                    download_item.stage = "cancelled"
                                is_cancelled = True
                                break

                            download_item.status = DownloadStatus.COMPLETED
                            download_item.stage = "completed"
                            download_item.completed_at = now
                            download_item.progress = 100.0
                            download_item.speed = ""
                            download_item.eta = ""
                            download_item.error_code = ""
                            download_item.error_title = ""
                            download_item.error_message = ""
                            success = True

                        saved_size = 0
                        if download_item.saved_filepath:
                            try:
                                p = Path(download_item.saved_filepath)
                                if p.exists():
                                    saved_size = p.stat().st_size
                            except Exception:
                                pass

                        self.logger.info(
                            "[DL %s] 下載完成 (策略=%s, elapsed=%dms, file=%s, size=%s bytes)",
                            short_id,
                            strategy,
                            elapsed_ms,
                            download_item.saved_filepath or "(unknown)",
                            saved_size,
                        )
                        self.log_download_event(
                            "COMPLETED",
                            download_item.url,
                            f"{download_item.title} | strategy={strategy} | size={saved_size}B",
                        )

                        if self.notification_manager:
                            self.notification_manager.show_success(
                                "下載完成",
                                f"「{download_item.title}」已存成 MP3 音樂檔！",
                            )

                        break

                    real_error = ytdlp_wrapper.get_last_error()
                    raise Exception(real_error or f"yt-dlp exited with code {exit_code}")

                except Exception as e:
                    if (
                        cancel_event.is_set()
                        or self._stopping
                        or process_tracker.tracker.shutting_down
                        or download_item.status == DownloadStatus.CANCELLED
                    ):
                        is_cancelled = True
                        break

                    elapsed_ms = int((time.perf_counter() - attempt_started) * 1000)
                    if primary_error is None:
                        primary_error = e
                    last_error = e
                    diag = analyze_error(e)
                    error_msg = str(e).lower()
                    matched_kw = [kw for kw in _RETRY_KEYWORDS if kw in error_msg]
                    attempt_logs.append(
                        f"{idx}. {strategy} -> {diag.code} ({elapsed_ms}ms): {diag.raw_excerpt}"
                    )

                    self.logger.warning(
                        "[DL %s] 嘗試失敗 (策略=%s, elapsed=%dms, err_code=%s, category=%s, title=%s, retry_kw=%s): %s",
                        short_id,
                        strategy,
                        elapsed_ms,
                        diag.code,
                        diag.category,
                        diag.title,
                        matched_kw or "none",
                        e,
                    )

                    if matched_kw and idx < len(cookie_browsers):
                        continue
                    self.logger.info(
                        "[DL %s] 停止重試 (err_code=%s, matched_kw=%s)",
                        short_id,
                        diag.code,
                        matched_kw or "none",
                    )
                    break

            if (
                cancel_event.is_set()
                or self._stopping
                or process_tracker.tracker.shutting_down
                or download_item.status == DownloadStatus.CANCELLED
            ):
                is_cancelled = True

            if not success and not is_cancelled:
                effective_error = last_error
                if (
                    primary_error is not None
                    and last_error is not None
                    and primary_error is not last_error
                    and is_local_cookie_error(last_error)
                ):
                    effective_error = primary_error
                    self.logger.info(
                        "[DL %s] 保留原始錯誤供使用者診斷（避免被本機 Cookie 存取失敗覆蓋）: primary=%s | last=%s",
                        short_id,
                        analyze_error(primary_error).code,
                        analyze_error(last_error).code,
                    )

                final_diag = analyze_error(effective_error)
                with self.queue_lock:
                    if (
                        download_item.status == DownloadStatus.CANCELLED
                        or cancel_event.is_set()
                        or self._stopping
                    ):
                        is_cancelled = True
                        if download_item.status == DownloadStatus.DOWNLOADING:
                            download_item.status = DownloadStatus.CANCELLED
                            download_item.stage = "cancelled"
                    else:
                        download_item.status = DownloadStatus.FAILED
                        download_item.stage = "failed"
                        download_item.error_code = final_diag.code
                        download_item.error_title = final_diag.title
                        download_item.error_message = final_diag.full_message()
                        marked_failed = True

                if marked_failed:
                    self.logger.error(
                        "[DL %s] MP3 下載最終失敗 | code=%s | title=%s | attempts=%s",
                        short_id,
                        final_diag.code,
                        final_diag.title,
                        " ; ".join(attempt_logs),
                    )
                    self.log_download_event(
                        "FAILED",
                        download_item.url,
                        f"[{final_diag.code}] {final_diag.title} | raw={final_diag.raw_excerpt}",
                    )

                    if self.error_handler:
                        self.error_handler.handle_download_error(
                            effective_error, download_item.url, show_user=True
                        )

            if success or marked_failed:
                try:
                    self.history_manager.add_download(download_item)
                except Exception as e:
                    self.logger.error("儲存歷史紀錄失敗: %s", e)

        finally:
            with self.queue_lock:
                if is_cancelled and download_item.status == DownloadStatus.DOWNLOADING:
                    download_item.status = DownloadStatus.CANCELLED
                    download_item.stage = "cancelled"
                self.active_downloads.pop(download_item.id, None)
                self._cancel_events.pop(download_item.id, None)

            exiting = self._stopping or process_tracker.tracker.shutting_down
            if not exiting:
                self.save_queue()
                flush_logs()
                self._notify_progress_change(download_item.id)
                self._process_queue()

    def _on_subprocess_progress(self, progress: dict, download_id: str):
        try:
            if self._stopping or process_tracker.tracker.shutting_down:
                return

            diag = None
            if "error" in progress:
                diag = analyze_error(progress["error"])

            should_notify = False
            with self.queue_lock:
                item = None
                for it in self.download_queue:
                    if it.id == download_id:
                        item = it
                        break

                if not item or item.status == DownloadStatus.CANCELLED:
                    return

                if "stage" in progress:
                    item.stage = progress["stage"]
                if "filepath" in progress and progress["filepath"]:
                    item.saved_filepath = progress["filepath"]

                percent = progress.get("percent", item.progress)
                item.progress = percent
                item.speed = progress.get("speed", "")
                item.eta = progress.get("eta", "")

                total_bytes = progress.get("total_bytes", 0)
                if total_bytes > 0:
                    item.total_bytes = total_bytes
                    item.downloaded_bytes = int(total_bytes * percent / 100)

                if diag is not None:
                    item.status = DownloadStatus.FAILED
                    item.stage = "failed"
                    item.error_code = diag.code
                    item.error_title = diag.title
                    item.error_message = diag.full_message()

                should_notify = True

            if should_notify:
                self._notify_progress_change(download_id)
        except Exception as e:
            self.logger.error("更新下載進度發生錯誤: %s", e)

    def _prepare_ydl_options(
        self,
        download_item: DownloadItem,
        browser: str = None,
        use_cookies: bool = False,
        cookie_opts: Optional[Dict] = None,
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
            resolved_opts = (
                cookie_opts
                if cookie_opts is not None
                else self.cookie_manager.get_cookie_options(download_item.url, browser=browser)
            )
            if resolved_opts:
                extra_args.extend(cookie_opts_to_cli(resolved_opts))
        else:
            self.cookie_manager.add_cookie_file_args(extra_args)

        return extra_args, "bestaudio/best", output_template

    def _cancel_download(self, download_id: str):
        event_to_cancel = None
        should_notify = False
        with self.queue_lock:
            for item in self.download_queue:
                if item.id == download_id:
                    if item.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING):
                        item.status = DownloadStatus.CANCELLED
                        item.stage = "cancelled"
                        event_to_cancel = self._cancel_events.get(download_id)
                        should_notify = True
                    break

        if event_to_cancel is not None:
            process_tracker.tracker.cancel(event_to_cancel)

        if should_notify:
            self._notify_progress_change(download_id)

    def _notify_progress_change(self, download_id: str):
        if self._is_shutting_down():
            return
        if download_id in self.progress_callbacks:
            for callback in list(self.progress_callbacks[download_id]):
                try:
                    callback()
                except Exception as e:
                    self.logger.error("Progress callback error: %s", e)

    def _notify_queue_change(self):
        if self._is_shutting_down():
            return
        for callback in list(self.download_callbacks):
            try:
                callback()
            except Exception as e:
                self.logger.error("Queue callback error: %s", e)

    def _get_queue_file_path(self) -> Path:
        return self.settings_manager.settings_dir / "download_queue.json"

    def _write_json_with_timeout(self, path: Path, data, timeout: float = 3.0) -> bool:
        result = [False]
        temp_file = path.parent / f"{path.name}.{uuid.uuid4().hex}.tmp"

        def _do_write():
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_file, path)
                result[0] = True
            except Exception:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass

        thread = threading.Thread(target=_do_write, daemon=True)
        thread.start()
        thread.join(timeout)

        if not result[0]:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass

        return result[0]

    def save_queue(self):
        try:
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            with self._save_lock:
                with self.queue_lock:
                    queue_data = []
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
