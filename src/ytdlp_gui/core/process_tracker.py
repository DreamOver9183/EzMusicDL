# -*- coding: utf-8 -*-
"""
Process Tracker - Track, cancel, and terminate subprocess trees for yt-dlp, FFmpeg, and helpers.
"""

import logging
import os
import platform
import subprocess
import threading
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ProcessCancelled(Exception):
    """Raised when process spawn is cancelled or tracker is shutting down."""
    pass


def _get_taskkill_path() -> str:
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    candidate = os.path.join(system_root, "System32", "taskkill.exe")
    if os.path.exists(candidate):
        return candidate
    return "taskkill"


def kill_process_tree(proc: subprocess.Popen) -> None:
    """
    Terminate a process and its child processes.
    Uses taskkill /T /F on Windows; falls back to proc.kill() on failure, timeout, or non-Windows.
    Never raises exceptions.
    """
    if proc is None or proc.poll() is not None:
        return

    killed = False
    if platform.system() == "Windows":
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            taskkill_cmd = _get_taskkill_path()
            res = subprocess.run(
                [taskkill_cmd, "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                creationflags=flags,
                timeout=5,
            )
            if res.returncode == 0:
                killed = True
        except Exception:
            killed = False

    if not killed:
        try:
            proc.kill()
        except OSError:
            pass

    try:
        proc.wait(timeout=2)
    except Exception:
        pass


class ProcessTracker:
    """Thread-safe tracker for running child processes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._shutting_down = False
        self._active: Dict[subprocess.Popen, Dict] = {}
        self._terminated_procs: Set[subprocess.Popen] = set()

    @property
    def shutting_down(self) -> bool:
        with self._lock:
            return self._shutting_down

    def spawn(
        self,
        cmd,
        *,
        group: str,
        cancel_event: Optional[threading.Event] = None,
        **popen_kwargs,
    ) -> subprocess.Popen:
        """
        Atomically check shutdown & cancellation, launch subprocess, and register it.
        Raises ProcessCancelled if shutting down or cancel_event is set.
        """
        with self._lock:
            if self._shutting_down:
                raise ProcessCancelled("ProcessTracker is shutting down")
            if cancel_event is not None and cancel_event.is_set():
                raise ProcessCancelled("Process has already been cancelled")

            proc = subprocess.Popen(cmd, **popen_kwargs)
            self._active[proc] = {
                "group": group,
                "cancel_event": cancel_event,
            }
            return proc

    def release(self, proc: subprocess.Popen) -> None:
        """Remove process from active tracking. Safe to call multiple times."""
        with self._lock:
            self._active.pop(proc, None)

    def cancel(self, cancel_event: threading.Event) -> None:
        """
        Set cancel_event and collect matching processes under lock, then terminate outside lock.
        """
        procs_to_kill: List[subprocess.Popen] = []
        with self._lock:
            cancel_event.set()
            for proc, info in list(self._active.items()):
                if info.get("cancel_event") is cancel_event:
                    procs_to_kill.append(proc)
                    setattr(proc, "_tracker_terminated", True)
                    self._terminated_procs.add(proc)
                    self._active.pop(proc, None)

        for proc in procs_to_kill:
            kill_process_tree(proc)

    def terminate_group(self, group: str) -> None:
        """
        Terminate all active processes in group outside lock.
        """
        procs_to_kill: List[subprocess.Popen] = []
        with self._lock:
            for proc, info in list(self._active.items()):
                if info.get("group") == group:
                    procs_to_kill.append(proc)
                    setattr(proc, "_tracker_terminated", True)
                    self._terminated_procs.add(proc)
                    evt = info.get("cancel_event")
                    if evt is not None:
                        evt.set()
                    self._active.pop(proc, None)

        for proc in procs_to_kill:
            kill_process_tree(proc)

    def shutdown(self) -> None:
        """
        Mark tracker as shutting down, signal events, and terminate all processes outside lock.
        Idempotent. Subsequent spawn calls will raise ProcessCancelled.
        """
        procs_to_kill: List[subprocess.Popen] = []
        with self._lock:
            self._shutting_down = True
            for proc, info in list(self._active.items()):
                procs_to_kill.append(proc)
                setattr(proc, "_tracker_terminated", True)
                self._terminated_procs.add(proc)
                evt = info.get("cancel_event")
                if evt is not None:
                    evt.set()
            self._active.clear()

        for proc in procs_to_kill:
            kill_process_tree(proc)

    def was_terminated(self, proc: subprocess.Popen) -> bool:
        """
        Check if process was terminated by tracker. Queryable even after release().
        """
        if proc is None:
            return False
        if getattr(proc, "_tracker_terminated", False):
            return True
        with self._lock:
            return proc in self._terminated_procs


tracker = ProcessTracker()
