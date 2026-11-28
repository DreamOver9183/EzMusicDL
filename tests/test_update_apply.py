# -*- coding: utf-8 -*-
"""
Tests for UpdateChecker.apply_update(), make_progress_logger(), and kill_process_tree():
1. Handshake success, startup flags, System32 powershell.exe path, and UTF-8 BOM script encoding.
2. Handshake timeout terminates child process tree and returns False.
3. Premature child process exit returns False promptly without waiting for full timeout.
4. Existing stale marker is cleaned up before launch and cannot cause false positives.
5. Popen exception returns False and allows subsequent retry.
6. Non-blocking re-entrancy protection (in-progress, post-success, post-failure retry).
7. Download progress throttling (600 callbacks <= 20 log lines, stage changes always logged).
8. kill_process_tree uses full System32 taskkill path on Windows.
9. Preparation/write exception returns False, releases lock, and permits subsequent retry.
"""

import os
from pathlib import Path
import subprocess
import time
import types
from typing import List

import pytest

from ytdlp_gui.core.process_tracker import kill_process_tree
from ytdlp_gui.core.update_checker import UpdateChecker, _get_powershell_path
from ytdlp_gui.main import make_progress_logger


class MockPopen:
    """Mock subprocess.Popen tracking arguments, process state, and termination."""

    def __init__(self, cmd, on_init=None, exit_code=None, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        self.pid = 12345
        self._returncode = exit_code
        self.killed = False
        if on_init:
            on_init(self)

    def poll(self):
        return self._returncode

    def kill(self):
        self.killed = True
        self._returncode = -9

    def wait(self, timeout=None):
        return self._returncode


@pytest.fixture
def apply_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide isolated application directory, staging directory, logs, and mock environment."""
    app_root = tmp_path / "app_root"
    app_root.mkdir(parents=True, exist_ok=True)
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    payload_root = tmp_path / "payload"
    payload_root.mkdir(parents=True, exist_ok=True)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    killed_procs: List[MockPopen] = []
    monkeypatch.setattr(
        "ytdlp_gui.core.process_tracker.kill_process_tree",
        lambda proc: killed_procs.append(proc),
    )

    monkeypatch.setattr("ytdlp_gui.core.update_checker.platform.system", lambda: "Windows")
    monkeypatch.setattr("ytdlp_gui.core.update_checker.get_logs_dir", lambda: logs_dir)

    checker = UpdateChecker()
    monkeypatch.setattr(checker, "is_frozen", lambda: True)
    monkeypatch.setattr(checker, "get_app_root", lambda: app_root)
    checker.HANDSHAKE_TIMEOUT_S = 0.5

    prepared = {
        "ok": True,
        "staging_dir": str(staging_dir),
        "payload_root": str(payload_root),
        "exe_name": "EasyMusicDL.exe",
        "asset_type": "portable_zip",
        "version": "9999.1.1",
    }
    return types.SimpleNamespace(
        checker=checker,
        prepared=prepared,
        staging_dir=staging_dir,
        payload_root=payload_root,
        app_root=app_root,
        logs_dir=logs_dir,
        killed=killed_procs,
    )


def test_apply_update_handshake_success_and_flags(apply_context, monkeypatch: pytest.MonkeyPatch):
    """Verify handshake success, process creation flags, standard streams, System32 path, and BOM."""
    staging_dir = apply_context.staging_dir
    captured_proc = []

    def on_init(proc):
        captured_proc.append(proc)
        # Simulate updater.ps1 writing handshake marker immediately upon start
        (staging_dir / "updater.started").write_text(str(proc.pid), encoding="utf-8")

    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.subprocess.Popen",
        lambda cmd, **kwargs: MockPopen(cmd, on_init=on_init, **kwargs),
    )

    result = apply_context.checker.apply_update(apply_context.prepared)
    assert result is True
    assert len(captured_proc) == 1
    proc = captured_proc[0]

    flags = proc.kwargs.get("creationflags", 0)
    # Must NOT have DETACHED_PROCESS (0x00000008)
    assert (flags & 0x00000008) == 0
    # Must have CREATE_NO_WINDOW (0x08000000)
    assert (flags & 0x08000000) != 0
    # Must have CREATE_NEW_PROCESS_GROUP (0x00000200)
    assert (flags & 0x00000200) != 0

    # Three streams must be DEVNULL
    assert proc.kwargs.get("stdin") == subprocess.DEVNULL
    assert proc.kwargs.get("stdout") == subprocess.DEVNULL
    assert proc.kwargs.get("stderr") == subprocess.DEVNULL
    assert proc.kwargs.get("close_fds") is True

    # Executable path must be System32 powershell.exe when available
    cmd = proc.cmd
    expected_ps = _get_powershell_path()
    assert cmd[0].lower() == expected_ps.lower()
    assert "-NoProfile" in cmd
    assert "-ExecutionPolicy" in cmd
    assert "Bypass" in cmd

    # Generated updater.ps1 must start with UTF-8 BOM
    ps_file = staging_dir / "updater.ps1"
    assert ps_file.exists()
    assert ps_file.read_bytes().startswith(b"\xef\xbb\xbf")


def test_apply_update_handshake_timeout(apply_context, monkeypatch: pytest.MonkeyPatch):
    """Verify that handshake timeout terminates child process tree and returns False."""
    apply_context.checker.HANDSHAKE_TIMEOUT_S = 0.2

    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.subprocess.Popen",
        lambda cmd, **kwargs: MockPopen(cmd, on_init=None, **kwargs),
    )

    result = apply_context.checker.apply_update(apply_context.prepared)
    assert result is False
    assert len(apply_context.killed) == 1
    assert apply_context.killed[0].pid == 12345


def test_apply_update_child_exits_early_without_marker(apply_context, monkeypatch: pytest.MonkeyPatch):
    """Verify that child process exiting early without marker returns False without waiting full timeout."""
    apply_context.checker.HANDSHAKE_TIMEOUT_S = 5.0

    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.subprocess.Popen",
        lambda cmd, **kwargs: MockPopen(cmd, on_init=None, exit_code=1, **kwargs),
    )

    t0 = time.perf_counter()
    result = apply_context.checker.apply_update(apply_context.prepared)
    elapsed = time.perf_counter() - t0

    assert result is False
    assert elapsed < 1.5


def test_apply_update_cleans_old_stale_marker(apply_context, monkeypatch: pytest.MonkeyPatch):
    """Verify that old stale marker is unlinked before launch and does not cause false positives."""
    stale_marker = apply_context.staging_dir / "updater.started"
    stale_marker.write_text("old_stale_pid", encoding="utf-8")
    apply_context.checker.HANDSHAKE_TIMEOUT_S = 0.2

    # Child never writes new marker and exits
    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.subprocess.Popen",
        lambda cmd, **kwargs: MockPopen(cmd, on_init=None, exit_code=1, **kwargs),
    )

    result = apply_context.checker.apply_update(apply_context.prepared)
    assert result is False
    assert not stale_marker.exists()


def test_apply_update_popen_exception_allows_retry(apply_context, monkeypatch: pytest.MonkeyPatch):
    """Verify that Popen exception logs, returns False, releases lock, and permits subsequent retry."""
    def raise_popen(*args, **kwargs):
        raise OSError("Simulated spawn failure")

    monkeypatch.setattr("ytdlp_gui.core.update_checker.subprocess.Popen", raise_popen)
    result1 = apply_context.checker.apply_update(apply_context.prepared)
    assert result1 is False

    # Second attempt succeeds
    def on_init(proc):
        (apply_context.staging_dir / "updater.started").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.subprocess.Popen",
        lambda cmd, **kwargs: MockPopen(cmd, on_init=on_init, **kwargs),
    )
    result2 = apply_context.checker.apply_update(apply_context.prepared)
    assert result2 is True


def test_apply_update_reentrancy_guards(apply_context, monkeypatch: pytest.MonkeyPatch):
    """Verify non-blocking lock prevents concurrent calls, retains lock on success, and releases on failure."""
    popen_calls: List[MockPopen] = []

    def on_init(proc):
        popen_calls.append(proc)
        (apply_context.staging_dir / "updater.started").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.subprocess.Popen",
        lambda cmd, **kwargs: MockPopen(cmd, on_init=on_init, **kwargs),
    )

    # 1. While first call holds lock, second call is rejected without Popen
    assert apply_context.checker._apply_lock.acquire(blocking=False)
    try:
        assert apply_context.checker.apply_update(apply_context.prepared) is False
        assert len(popen_calls) == 0
    finally:
        apply_context.checker._apply_lock.release()

    # 2. Successful call holds lock; subsequent call returns False without spawning Popen
    first_res = apply_context.checker.apply_update(apply_context.prepared)
    assert first_res is True
    assert len(popen_calls) == 1

    second_res = apply_context.checker.apply_update(apply_context.prepared)
    assert second_res is False
    assert len(popen_calls) == 1  # No second Popen spawned


def test_apply_update_write_failure_releases_lock_and_allows_retry(apply_context, monkeypatch: pytest.MonkeyPatch):
    """Verify that failure during script creation/preparation returns False, releases lock, and permits retry."""
    def raise_perm():
        raise PermissionError("Simulated unwritable logs directory")

    monkeypatch.setattr("ytdlp_gui.core.update_checker.get_logs_dir", raise_perm)

    res1 = apply_context.checker.apply_update(apply_context.prepared)
    assert res1 is False

    # Restore valid logs dir and verify retry succeeds
    monkeypatch.setattr("ytdlp_gui.core.update_checker.get_logs_dir", lambda: apply_context.logs_dir)

    def on_init(proc):
        (apply_context.staging_dir / "updater.started").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.subprocess.Popen",
        lambda cmd, **kwargs: MockPopen(cmd, on_init=on_init, **kwargs),
    )
    res2 = apply_context.checker.apply_update(apply_context.prepared)
    assert res2 is True


def test_make_progress_logger_throttling():
    """Verify download progress throttles to <= 20 lines for 600 callbacks and always logs stage changes."""
    logged_lines: List[str] = []
    fake_logger = types.SimpleNamespace(
        info=lambda msg, *args: logged_lines.append(msg % args if args else msg)
    )

    logger_fn = make_progress_logger(fake_logger)

    # 1. Simulate 600 download progress callbacks from 0.05 to 1.0 within download stage
    for i in range(600):
        frac = i / 599.0
        pct = 0.05 + frac * 0.95
        logger_fn(f"正在下載更新檔 ({int(pct * 100)}%)...", pct)

    assert len(logged_lines) <= 20
    assert len(logged_lines) >= 10

    # 2. Verify stage transitions are always written immediately
    stage_lines: List[str] = []
    stage_logger = types.SimpleNamespace(
        info=lambda msg, *args: stage_lines.append(msg % args if args else msg)
    )
    stage_fn = make_progress_logger(stage_logger)

    stage_fn("正在連線並下載應用程式更新檔...", 0.05)
    stage_fn("正在下載更新檔 (5%)...", 0.05)
    stage_fn("正在驗證檔案完整性 (SHA-256)...", 0.75)
    stage_fn("正在解壓縮並檢查更新檔...", 0.82)
    stage_fn("更新檔準備完成，即將套用更新...", 1.0)

    assert len(stage_lines) == 5


def test_kill_process_tree_system32_taskkill(monkeypatch: pytest.MonkeyPatch):
    """Verify kill_process_tree invokes System32 taskkill path on Windows."""
    executed_commands: List[List[str]] = []

    def mock_run(cmd, *args, **kwargs):
        executed_commands.append(cmd)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr("ytdlp_gui.core.process_tracker.platform.system", lambda: "Windows")
    monkeypatch.setattr("ytdlp_gui.core.process_tracker.subprocess.run", mock_run)

    dummy_proc = types.SimpleNamespace(
        pid=98765,
        poll=lambda: None,
        kill=lambda: None,
        wait=lambda timeout=None: None,
    )

    kill_process_tree(dummy_proc)
    assert len(executed_commands) == 1
    taskkill_bin = executed_commands[0][0]

    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    expected_path = os.path.join(system_root, "System32", "taskkill.exe")
    if os.path.exists(expected_path):
        assert taskkill_bin.lower() == expected_path.lower()
    else:
        assert taskkill_bin == "taskkill"
