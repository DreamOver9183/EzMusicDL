# -*- coding: utf-8 -*-
"""
Tests for ProcessTracker and process tree cancellation.
"""

import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ytdlp_gui.core import process_tracker
from ytdlp_gui.core.process_tracker import ProcessCancelled, kill_process_tree


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


def test_process_tree_termination(tmp_path: Path, process_tracker_instance):
    pid_file = tmp_path / "child.pid"
    partial_file = str(pid_file) + ".partial"
    parent_script = (
        "import os, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"with open({repr(partial_file)}, 'w') as f:\n"
        "    f.write(str(child.pid))\n"
        f"os.replace({repr(partial_file)}, {repr(str(pid_file))})\n"
        "time.sleep(60)\n"
    )

    proc = process_tracker_instance.spawn(
        [sys.executable, "-c", parent_script],
        group="test",
    )
    child_pid = None
    try:
        child_pid = wait_for_pid(pid_file)

        assert is_pid_running(proc.pid), "Parent process should be running"
        assert is_pid_running(child_pid), "Child process should be running"

        kill_process_tree(proc)

        assert wait_until(lambda: not is_pid_running(proc.pid), timeout=6.0), "Parent process should be terminated"
        assert wait_until(lambda: not is_pid_running(child_pid), timeout=6.0), "Child process tree should be terminated"
    finally:
        safe_terminate(proc)
        if child_pid:
            safe_terminate(child_pid)


def test_shutdown_blocks_spawn(process_tracker_instance, monkeypatch: pytest.MonkeyPatch):
    process_tracker_instance.shutdown()
    assert process_tracker_instance.shutting_down is True

    popen_called = []
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: popen_called.append(args),
    )

    with pytest.raises(ProcessCancelled):
        process_tracker_instance.spawn([sys.executable, "-c", "pass"], group="test")

    assert len(popen_called) == 0, "Popen must not be called when shutting down"


def test_cancel_event_already_set_blocks_spawn(process_tracker_instance, monkeypatch: pytest.MonkeyPatch):
    evt = threading.Event()
    evt.set()

    popen_called = []
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: popen_called.append(args),
    )

    with pytest.raises(ProcessCancelled):
        process_tracker_instance.spawn([sys.executable, "-c", "pass"], group="test", cancel_event=evt)

    assert len(popen_called) == 0, "Popen must not be called when cancel_event is set"


def test_cancel_only_terminates_target_event(process_tracker_instance):
    evt1 = threading.Event()
    evt2 = threading.Event()

    proc1 = process_tracker_instance.spawn(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        group="test",
        cancel_event=evt1,
    )
    proc2 = process_tracker_instance.spawn(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        group="test",
        cancel_event=evt2,
    )

    try:
        assert is_pid_running(proc1.pid)
        assert is_pid_running(proc2.pid)

        process_tracker_instance.cancel(evt1)

        assert wait_until(lambda: not is_pid_running(proc1.pid), timeout=6.0)
        assert process_tracker_instance.was_terminated(proc1) is True
        # Queryable even after release
        process_tracker_instance.release(proc1)
        assert process_tracker_instance.was_terminated(proc1) is True

        assert is_pid_running(proc2.pid) is True
        assert process_tracker_instance.was_terminated(proc2) is False
    finally:
        process_tracker_instance.cancel(evt2)
        safe_terminate(proc1)
        safe_terminate(proc2)


def test_terminate_group_only_terminates_target_group(process_tracker_instance):
    proc1 = process_tracker_instance.spawn(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        group="groupA",
    )
    proc2 = process_tracker_instance.spawn(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        group="groupB",
    )

    try:
        assert is_pid_running(proc1.pid)
        assert is_pid_running(proc2.pid)

        process_tracker_instance.terminate_group("groupA")

        assert wait_until(lambda: not is_pid_running(proc1.pid), timeout=6.0)
        assert process_tracker_instance.was_terminated(proc1) is True
        assert is_pid_running(proc2.pid) is True
        assert process_tracker_instance.was_terminated(proc2) is False
    finally:
        process_tracker_instance.terminate_group("groupB")
        safe_terminate(proc1)
        safe_terminate(proc2)


def test_taskkill_failure_falls_back_to_proc_kill(process_tracker_instance, monkeypatch: pytest.MonkeyPatch):
    proc = process_tracker_instance.spawn(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        group="test",
    )
    try:
        assert is_pid_running(proc.pid)

        # Force taskkill failure
        def mock_run(*args, **kwargs):
            raise RuntimeError("taskkill failed")

        monkeypatch.setattr(subprocess, "run", mock_run)

        kill_called = []
        orig_kill = proc.kill

        def spy_kill():
            kill_called.append(True)
            orig_kill()

        monkeypatch.setattr(proc, "kill", spy_kill)

        kill_process_tree(proc)

        assert len(kill_called) > 0, "proc.kill() must be called when taskkill fails"
        assert wait_until(lambda: not is_pid_running(proc.pid), timeout=6.0)
    finally:
        safe_terminate(proc)


def test_finished_process_termination_no_exception(process_tracker_instance):
    proc = process_tracker_instance.spawn(
        [sys.executable, "-c", "import sys; sys.exit(0)"],
        group="test",
    )
    proc.wait(timeout=3)
    # Must not raise
    kill_process_tree(proc)
    process_tracker_instance.release(proc)


def test_shutdown_idempotent(process_tracker_instance):
    proc = process_tracker_instance.spawn(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        group="test",
    )
    try:
        process_tracker_instance.shutdown()
        assert wait_until(lambda: not is_pid_running(proc.pid), timeout=6.0)
        assert process_tracker_instance.shutting_down is True

        # Second shutdown call must succeed without errors
        process_tracker_instance.shutdown()
        assert process_tracker_instance.shutting_down is True
    finally:
        safe_terminate(proc)


def test_real_search_youtube_timeout_kills_tree(
    original_wrapper_functions,
    process_tracker_instance,
    tmp_path: Path,
):
    pid_file = tmp_path / "search_child.pid"
    partial_file = str(pid_file) + ".partial"
    child_script = (
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
        p = orig_spawn([sys.executable, "-c", child_script], *args, **kwargs)
        parent_procs.append(p)
        return p

    process_tracker_instance.spawn = wrapped_spawn

    res = original_wrapper_functions.search_youtube("timeout query", timeout=1)
    assert res == []

    assert len(parent_procs) == 1
    parent_proc = parent_procs[0]
    child_pid = None
    try:
        child_pid = wait_for_pid(pid_file)

        assert wait_until(lambda: not is_pid_running(parent_proc.pid), timeout=6.0), "Parent proc should be killed on timeout"
        assert wait_until(lambda: not is_pid_running(child_pid), timeout=6.0), "Child proc tree should be killed on timeout"
    finally:
        safe_terminate(parent_proc)
        if child_pid:
            safe_terminate(child_pid)


def test_real_download_cancel_event_only_kills_tree_and_no_failure_callback(
    original_wrapper_functions,
    process_tracker_instance,
    tmp_path: Path,
):
    pid_file = tmp_path / "dl_cancel_child.pid"
    partial_file = str(pid_file) + ".partial"
    script = (
        "import os, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"with open({repr(partial_file)}, 'w') as f:\n"
        "    f.write(str(child.pid))\n"
        f"os.replace({repr(partial_file)}, {repr(str(pid_file))})\n"
        "for _ in range(300):\n"
        "    print('[download] 10%', flush=True)\n"
        "    time.sleep(0.1)\n"
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
        args=("https://www.youtube.com/watch?v=cancel_only", str(tmp_path / "out.mp3"), "bestaudio/best"),
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

        t0 = time.time()
        # Only set cancel_event - DO NOT call tracker methods!
        cancel_event.set()

        dl_thread.join(timeout=5.0)
        elapsed = time.time() - t0
        assert not dl_thread.is_alive(), "download() did not return in 5s"
        assert elapsed < 5.0, f"download() took too long to return: {elapsed}s"

        assert wait_until(lambda: not is_pid_running(parent_proc.pid), timeout=6.0), "Parent process should be killed"
        assert wait_until(lambda: not is_pid_running(child_pid), timeout=6.0), "Child process tree should be killed"

        for cb in received_callbacks:
            assert cb.get("stage") != "failed", f"Unexpected failed callback: {cb}"
            assert "error" not in cb, f"Unexpected error callback: {cb}"
            assert cb.get("stage") != "completed", f"Unexpected completed callback: {cb}"
    finally:
        if parent_procs:
            safe_terminate(parent_procs[0])
        if child_pid:
            safe_terminate(child_pid)


def test_real_extract_info_shutdown_kills_tree_and_returns_none(
    original_wrapper_functions,
    process_tracker_instance,
    tmp_path: Path,
):
    pid_file = tmp_path / "extract_child.pid"
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

    result = []

    def run_extract():
        res = original_wrapper_functions.extract_info("https://www.youtube.com/watch?v=shutdown_test", timeout=30)
        result.append(res)

    extract_thread = threading.Thread(target=run_extract, daemon=True)
    extract_thread.start()

    child_pid = None
    try:
        child_pid = wait_for_pid(pid_file)

        assert len(parent_procs) == 1
        parent_proc = parent_procs[0]
        assert is_pid_running(parent_proc.pid)
        assert is_pid_running(child_pid)

        # Call shutdown during execution
        process_tracker_instance.shutdown()

        extract_thread.join(timeout=5.0)
        assert not extract_thread.is_alive(), "extract_info thread did not finish within timeout"

        assert len(result) == 1
        assert result[0] is None, f"Expected None on cancelled extract_info, got {result[0]}"

        assert wait_until(lambda: not is_pid_running(parent_proc.pid), timeout=6.0)
        assert wait_until(lambda: not is_pid_running(child_pid), timeout=6.0)
    finally:
        if parent_procs:
            safe_terminate(parent_procs[0])
        if child_pid:
            safe_terminate(child_pid)
