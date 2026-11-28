# -*- coding: utf-8 -*-
"""
Tests for download cancellation, deadlock prevention, process termination, and atomic queue persistence.
"""

import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ytdlp_gui.core import process_tracker, ytdlp_wrapper
from ytdlp_gui.core.download_manager import DownloadItem, DownloadManager, DownloadStatus
from ytdlp_gui.core.process_tracker import kill_process_tree
from ytdlp_gui.core.settings_manager import SettingsManager


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            WAIT_TIMEOUT = 258
            res = kernel32.WaitForSingleObject(handle, 0)
            if res == WAIT_TIMEOUT:
                return True
            exit_code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return exit_code.value == 259
            return False
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def wait_until(condition_fn, timeout: float = 5.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return bool(condition_fn())


def wait_for_pid(pid_file: Path, timeout: float = 6.0, interval: float = 0.05) -> int:
    deadline = time.time() + timeout
    pid_path = Path(pid_file)
    while time.time() < deadline:
        try:
            if pid_path.exists():
                text = pid_path.read_text(encoding="utf-8").strip()
                if text.isdigit():
                    return int(text)
        except OSError:
            pass
        time.sleep(interval)
    try:
        if pid_path.exists():
            text = pid_path.read_text(encoding="utf-8").strip()
            if text.isdigit():
                return int(text)
    except OSError:
        pass
    assert False, f"Child PID file was not ready within {timeout}s: {pid_file}"


def safe_terminate(proc_or_pid):
    if isinstance(proc_or_pid, int):
        if is_pid_running(proc_or_pid):
            if platform.system() == "Windows":
                try:
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(proc_or_pid)],
                        capture_output=True,
                        creationflags=flags,
                        timeout=3,
                    )
                except Exception:
                    pass
            else:
                try:
                    os.kill(proc_or_pid, 9)
                except OSError:
                    pass
    elif proc_or_pid is not None:
        try:
            kill_process_tree(proc_or_pid)
        except Exception:
            pass
        try:
            proc_or_pid.kill()
        except OSError:
            pass


def call_with_timeout(fn, *args, timeout: float = 3.0, **kwargs):
    exc = []
    res = []

    def target():
        try:
            res.append(fn(*args, **kwargs))
        except BaseException as e:
            exc.append(e)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    assert not thread.is_alive(), f"Call to {getattr(fn, '__name__', str(fn))} timed out after {timeout}s"
    if exc:
        raise exc[0]
    return res[0] if res else None


def test_stop_all_downloads_deadlock_regression(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    dl_started = threading.Event()

    def mock_download(*args, cancel_event=None, **kwargs):
        dl_started.set()
        if cancel_event:
            cancel_event.wait(timeout=10.0)
        return -1

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    dm.add_download("https://www.youtube.com/watch?v=deadlock_test", video_title="Deadlock Test")
    assert dl_started.wait(timeout=5.0), "Download worker did not start"

    t0 = time.time()
    call_with_timeout(dm.stop_all_downloads, timeout=3.0)
    elapsed = time.time() - t0

    assert elapsed < 3.0


def test_real_download_cancel_kills_tree_and_no_failure_callback(
    original_wrapper_functions,
    process_tracker_instance,
    tmp_path: Path,
):
    pid_file = tmp_path / "dl_tree_child.pid"
    partial_file = str(pid_file) + ".partial"
    script = (
        "import os, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"with open({repr(partial_file)}, 'w') as f:\n"
        "    f.write(str(child.pid))\n"
        f"os.replace({repr(partial_file)}, {repr(str(pid_file))})\n"
        "time.sleep(60)\n"
    )

    orig_spawn = process_tracker_instance.spawn
    parent_procs = []

    def wrapped_spawn(cmd, *args, **kwargs):
        p = orig_spawn([sys.executable, "-c", script], *args, **kwargs)
        parent_procs.append(p)
        return p

    process_tracker_instance.spawn = wrapped_spawn

    cancel_event = threading.Event()
    received_callbacks = []

    def progress_cb(payload):
        received_callbacks.append(payload)

    dl_thread = threading.Thread(
        target=original_wrapper_functions.download,
        args=("https://www.youtube.com/watch?v=dummy", str(tmp_path / "out.mp3"), "bestaudio/best"),
        kwargs={"progress_callback": progress_cb, "cancel_event": cancel_event},
        daemon=True,
    )
    dl_thread.start()

    child_pid = None
    try:
        child_pid = wait_for_pid(pid_file)

        assert len(parent_procs) == 1
        parent_proc = parent_procs[0]
        assert is_pid_running(parent_proc.pid)
        assert is_pid_running(child_pid)

        process_tracker_instance.cancel(cancel_event)

        dl_thread.join(timeout=5.0)
        assert not dl_thread.is_alive(), "download function did not return promptly on cancel"

        assert wait_until(lambda: not is_pid_running(parent_proc.pid), timeout=6.0)
        assert wait_until(lambda: not is_pid_running(child_pid), timeout=6.0)

        # Verify no failure / error callback was delivered
        for cb in received_callbacks:
            assert cb.get("stage") != "failed", f"Unexpected failed callback: {cb}"
            assert "error" not in cb, f"Unexpected error callback: {cb}"
            assert cb.get("stage") != "completed", f"Unexpected completed callback: {cb}"
    finally:
        if parent_procs:
            safe_terminate(parent_procs[0])
        if child_pid:
            safe_terminate(child_pid)


def test_stop_status_and_queue_file(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    dl_started = threading.Event()

    def mock_download(*args, cancel_event=None, **kwargs):
        dl_started.set()
        if cancel_event:
            cancel_event.wait(timeout=5.0)
        return -1

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    item_id = dm.add_download("https://www.youtube.com/watch?v=status_test", video_title="Status Test")
    assert dl_started.wait(timeout=5.0)

    call_with_timeout(dm.stop_all_downloads)

    item = dm.get_download_item(item_id)
    assert item is not None
    assert item.status == DownloadStatus.CANCELLED

    # Check persisted queue file
    assert dm.queue_file.exists()
    content = json.loads(dm.queue_file.read_text(encoding="utf-8"))
    assert isinstance(content, list)
    saved_item = next((it for it in content if it["id"] == item_id), None)
    assert saved_item is not None
    assert saved_item["status"] == "cancelled"


def test_pending_items_not_started_after_stop(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)
    dm.max_concurrent_downloads = 1

    first_started = threading.Event()

    def mock_download(url, *args, cancel_event=None, **kwargs):
        if "item1" in url:
            first_started.set()
            if cancel_event:
                cancel_event.wait(timeout=5.0)
            return -1
        return 0

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    id1 = dm.add_download("https://www.youtube.com/watch?v=item1", video_title="Item 1")
    id2 = dm.add_download("https://www.youtube.com/watch?v=item2", video_title="Item 2")

    assert first_started.wait(timeout=5.0)
    assert dm.get_download_item(id1).status == DownloadStatus.DOWNLOADING
    assert dm.get_download_item(id2).status == DownloadStatus.PENDING

    call_with_timeout(dm.stop_all_downloads)

    assert wait_until(lambda: id1 not in dm.active_downloads, timeout=5.0)
    assert dm.get_download_item(id1).status == DownloadStatus.CANCELLED
    # Item 2 must remain PENDING
    assert dm.get_download_item(id2).status == DownloadStatus.PENDING
    assert id2 not in dm.active_downloads


def test_retry_keywords_no_browser_retry_on_cancel(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    call_count = [0]

    def mock_download(*args, cancel_event=None, **kwargs):
        call_count[0] += 1
        if cancel_event:
            cancel_event.set()
        raise Exception("HTTP Error 403: Forbidden - sign in required")

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    item_id = dm.add_download("https://www.youtube.com/watch?v=retry_test", video_title="Retry Test")
    assert wait_until(lambda: item_id not in dm.active_downloads, timeout=5.0)

    item = dm.get_download_item(item_id)
    assert item is not None
    assert call_count[0] == 1, "Must not retry other browsers when cancelled"
    assert item.status == DownloadStatus.CANCELLED


def test_exit_code_zero_stays_cancelled(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    def mock_download(*args, cancel_event=None, **kwargs):
        if cancel_event:
            cancel_event.set()
        return 0

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    item_id = dm.add_download("https://www.youtube.com/watch?v=zero_test", video_title="Zero Test")
    assert wait_until(lambda: item_id not in dm.active_downloads, timeout=5.0)

    item = dm.get_download_item(item_id)
    assert item is not None
    assert item.status == DownloadStatus.CANCELLED


def test_cancel_via_item_status_return_zero(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)
    call_count = [0]

    def mock_download(*args, cancel_event=None, **kwargs):
        call_count[0] += 1
        item = dm.get_download_item(item_id)
        with dm.queue_lock:
            item.status = DownloadStatus.CANCELLED
        return 0

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    item_id = dm.add_download("https://www.youtube.com/watch?v=status_zero", video_title="Status Zero")
    assert wait_until(lambda: item_id not in dm.active_downloads, timeout=5.0)

    item = dm.get_download_item(item_id)
    assert item is not None
    assert item.status == DownloadStatus.CANCELLED
    assert call_count[0] == 1
    assert item.error_code == ""


def test_cancel_via_item_status_raises_403(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)
    call_count = [0]

    def mock_download(*args, cancel_event=None, **kwargs):
        call_count[0] += 1
        item = dm.get_download_item(item_id)
        with dm.queue_lock:
            item.status = DownloadStatus.CANCELLED
        raise Exception("HTTP Error 403: Forbidden - sign in required")

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    item_id = dm.add_download("https://www.youtube.com/watch?v=status_403", video_title="Status 403")
    assert wait_until(lambda: item_id not in dm.active_downloads, timeout=5.0)

    item = dm.get_download_item(item_id)
    assert item is not None
    assert item.status == DownloadStatus.CANCELLED
    assert call_count[0] == 1
    assert item.error_code == ""


def test_thread_start_failure_marks_failed(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    orig_start = threading.Thread.start

    def mock_start(self):
        target_name = getattr(getattr(self, "_target", None), "__name__", "")
        if target_name == "_download_worker":
            raise RuntimeError("Failed to start worker thread")
        return orig_start(self)

    monkeypatch.setattr(threading.Thread, "start", mock_start)

    item_id = dm.add_download("https://www.youtube.com/watch?v=thread_fail", video_title="Thread Fail")
    item = dm.get_download_item(item_id)
    assert item is not None
    assert item.status == DownloadStatus.FAILED
    assert item.error_code != ""
    assert item_id not in dm.active_downloads


def test_single_cancel_starts_next_pending(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)
    dm.max_concurrent_downloads = 1

    first_started = threading.Event()
    second_started = threading.Event()

    def mock_download(url, *args, cancel_event=None, **kwargs):
        if "first" in url:
            first_started.set()
            if cancel_event:
                cancel_event.wait(timeout=5.0)
            return -1
        elif "second" in url:
            second_started.set()
            return 0
        return 0

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    id1 = dm.add_download("https://www.youtube.com/watch?v=first", video_title="First")
    id2 = dm.add_download("https://www.youtube.com/watch?v=second", video_title="Second")

    assert first_started.wait(timeout=5.0)
    assert dm.get_download_item(id1).status == DownloadStatus.DOWNLOADING
    assert dm.get_download_item(id2).status == DownloadStatus.PENDING

    call_with_timeout(dm._cancel_download, id1)

    assert wait_until(lambda: dm.get_download_item(id1).status == DownloadStatus.CANCELLED, timeout=5.0)
    assert second_started.wait(timeout=5.0), "Next PENDING download did not start after single cancel"


def test_progress_callback_lock_not_held(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    lock_acquire_results = []
    worker_finished = threading.Event()
    callback_registered = threading.Event()

    def mock_download(url, output_path, format_spec, extra_args=None, progress_callback=None, cancel_event=None):
        assert callback_registered.wait(timeout=5.0), "Callback was not registered in time"
        if progress_callback:
            progress_callback({"percent": 50.0, "stage": "downloading"})
        worker_finished.set()
        return 0

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    item_id = dm.add_download("https://www.youtube.com/watch?v=lock_test", video_title="Lock Test")

    def on_progress():
        acquired = dm.queue_lock.acquire(blocking=False)
        if acquired:
            dm.queue_lock.release()
        lock_acquire_results.append(acquired)

    dm.add_progress_callback(item_id, on_progress)
    callback_registered.set()

    assert worker_finished.wait(timeout=5.0)
    assert len(lock_acquire_results) > 0
    assert all(lock_acquire_results), "queue_lock must not be held while invoking progress callbacks"


def test_ui_callbacks_not_invoked_during_shutdown(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    progress_cb_called = []
    queue_cb_called = []

    dm.add_progress_callback("dummy_id", lambda: progress_cb_called.append(True))
    dm.add_queue_callback(lambda: queue_cb_called.append(True))

    dm._stopping = True

    dm._notify_progress_change("dummy_id")
    dm._notify_queue_change()

    assert len(progress_cb_called) == 0, "Progress callback must not be invoked during shutdown"
    assert len(queue_cb_called) == 0, "Queue callback must not be invoked during shutdown"


def test_concurrent_save_queue_json_valid_and_no_tmp_files(app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    for i in range(5):
        dm.download_queue.append(
            DownloadItem(id=f"item_{i}", url=f"http://example.com/{i}", title=f"Title {i}")
        )

    errors = []

    def save_worker():
        try:
            for _ in range(5):
                dm.save_queue()
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=save_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive()

    assert len(errors) == 0

    assert dm.queue_file.exists()
    content = json.loads(dm.queue_file.read_text(encoding="utf-8"))
    assert len(content) == 5

    tmp_files = list(dm.queue_file.parent.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Found lingering temporary files: {tmp_files}"


def test_add_download_after_stop_does_not_start(monkeypatch: pytest.MonkeyPatch, app_root: Path):
    sm = SettingsManager()
    dm = DownloadManager(sm)

    call_count = [0]

    def mock_download(*args, **kwargs):
        call_count[0] += 1
        return 0

    monkeypatch.setattr(ytdlp_wrapper, "download", mock_download)

    call_with_timeout(dm.stop_all_downloads)

    item_id = dm.add_download("https://www.youtube.com/watch?v=after_stop", video_title="After Stop")

    item = dm.get_download_item(item_id)
    assert item is not None
    assert item.status == DownloadStatus.PENDING
    assert item_id not in dm.active_downloads
    assert call_count[0] == 0
    assert any(it.id == item_id for it in dm.get_queue())
