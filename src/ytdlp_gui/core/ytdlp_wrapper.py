# -*- coding: utf-8 -*-
"""
yt-dlp CLI wrapper - UTF-8 safe subprocess calls for search, metadata, and MP3 download,
with rich structured logging and warning/error preservation.
"""

import json
import logging
import os
import platform
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ytdlp_gui.utils.error_translations import analyze_error

from . import binary_manager, process_tracker

logger = logging.getLogger(__name__)

_last_error = threading.local()
_last_warnings = threading.local()
_last_stderr = threading.local()


def _set_last_error(msg: str):
    _last_error.msg = msg


def get_last_error() -> str:
    """Get the last yt-dlp error message from current thread."""
    return getattr(_last_error, "msg", "")


def _set_last_diagnostics(warnings: List[str], stderr_text: str):
    _last_warnings.items = list(warnings)
    _last_stderr.text = stderr_text


def get_last_warnings() -> List[str]:
    """Get yt-dlp warnings captured during the last call on current thread."""
    return list(getattr(_last_warnings, "items", []))


def get_last_stderr() -> str:
    """Get full stderr output captured during the last call on current thread."""
    return getattr(_last_stderr, "text", "")


def _create_no_window_flag() -> int:
    if platform.system() == "Windows":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _subprocess_env() -> Dict[str, str]:
    """Return environment with portable bin/ prepended to PATH so ffmpeg & deno are found."""
    env = os.environ.copy()
    bin_str = str(binary_manager.get_bin_dir())
    current_path = env.get("PATH", "")
    parts = current_path.split(os.pathsep) if current_path else []
    if bin_str not in parts:
        env["PATH"] = bin_str + (os.pathsep + current_path if current_path else "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def find_ytdlp() -> str:
    """Locate yt-dlp executable in portable bin/ first, then PATH."""
    bin_exe = binary_manager.get_bin_dir() / "yt-dlp.exe"
    if bin_exe.exists():
        return str(bin_exe)
    return "yt-dlp"


def _ffmpeg_args() -> List[str]:
    loc = binary_manager.get_ffmpeg_location()
    return ["--ffmpeg-location", loc] if loc else []


def _cmd_str(cmd: List[str]) -> str:
    return " ".join(f'"{c}"' if " " in c else c for c in cmd)


def _split_stderr_lines(stderr_text: str) -> Tuple[List[str], List[str]]:
    """Split stderr into non-empty lines and extract WARNING lines."""
    lines = [ln.strip() for ln in (stderr_text or "").splitlines() if ln.strip()]
    warnings = [ln for ln in lines if "WARNING:" in ln]
    return lines, warnings


def _log_stderr_lines(lines: List[str], tag: str) -> None:
    """Log yt-dlp stderr lines by severity."""
    for line in lines:
        if "ERROR:" in line:
            logger.error("%s [YTDLP_ERR] %s", tag, line[:500])
        elif "WARNING:" in line:
            logger.warning("%s [YTDLP_WARN] %s", tag, line[:500])
        else:
            logger.debug("%s [YTDLP_STDERR] %s", tag, line[:500])


def _extract_primary_error(stderr_lines: List[str], fallback: str = "") -> str:
    """Prefer explicit ERROR: lines over trailing hints or warnings."""
    error_lines = [ln for ln in stderr_lines if "ERROR:" in ln]
    if error_lines:
        return "\n".join(error_lines[-3:])[:1500]
    if stderr_lines:
        return "\n".join(stderr_lines[-6:])[:1500]
    return (fallback or "").strip()[:1500]


def _format_duration(seconds: Optional[float]) -> str:
    if not seconds:
        return "未知長度"
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "未知長度"
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _pick_thumbnail(entry: dict) -> str:
    thumb = entry.get("thumbnail") or ""
    if thumb:
        return thumb
    thumbs = entry.get("thumbnails") or []
    if isinstance(thumbs, list) and thumbs:
        last = thumbs[-1]
        if isinstance(last, dict):
            return last.get("url", "")
    vid = entry.get("id")
    if vid and len(str(vid)) == 11:
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return ""


def _normalize_entry(entry: dict, fallback_url: str = "") -> Optional[dict]:
    if not isinstance(entry, dict):
        return None
    vid = entry.get("id") or ""
    url = entry.get("webpage_url") or entry.get("url") or fallback_url
    if url and not str(url).startswith("http"):
        if vid:
            url = f"https://www.youtube.com/watch?v={vid}"
        else:
            url = f"https://www.youtube.com/watch?v={url}"
    title = (entry.get("title") or "").strip()
    if not title or not url:
        return None
    duration = entry.get("duration")
    duration_str = entry.get("duration_string") or _format_duration(duration)
    uploader = entry.get("uploader") or entry.get("channel") or "YouTube 頻道"
    return {
        "id": str(vid or url),
        "title": title,
        "uploader": uploader,
        "duration": duration or 0,
        "duration_str": duration_str,
        "thumbnail": _pick_thumbnail(entry),
        "url": url,
    }


def search_youtube(query: str, max_results: int = 8, timeout: int = 30) -> List[dict]:
    """
    Search YouTube using yt-dlp ytsearch or inspect a pasted URL.
    Returns normalized list of song dicts. Sets last error & diagnostics on completion.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        _set_last_error("請輸入歌名、歌手或貼上網址")
        _set_last_diagnostics([], "")
        return []

    is_url = bool(re.match(r"^https?://\S+", clean_query, re.IGNORECASE))
    mode = "url" if is_url else "keyword"
    target = clean_query if is_url else f"ytsearch{max_results}:{clean_query}"

    cmd = [
        find_ytdlp(),
        "--dump-single-json",
        "--no-check-certificate",
        "--add-header",
        "Accept-Language: zh-TW,zh;q=0.9,en;q=0.8",
    ]
    if is_url:
        cmd.append("--no-playlist")
    else:
        cmd.append("--flat-playlist")
    cmd.extend(_ffmpeg_args())
    cmd.append(target)

    logger.info(
        "[SEARCH] 開始 (mode=%s, timeout=%ss, target=%s) | cmd=%s",
        mode,
        timeout,
        target,
        _cmd_str(cmd),
    )
    started = time.perf_counter()
    proc = None
    try:
        proc = process_tracker.tracker.spawn(
            cmd,
            group="parse",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_create_no_window_flag(),
            env=_subprocess_env(),
        )
        try:
            stdout_text, stderr_text = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process_tracker.kill_process_tree(proc)
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if process_tracker.tracker.was_terminated(proc):
                logger.info("[SEARCH] 已取消 (elapsed=%dms, target=%s)", elapsed_ms, clean_query)
                _set_last_error("已取消")
                return []
            msg = f"搜尋逾時 ({timeout}s)，請檢查網路連線後再試一次"
            _set_last_error(msg)
            _set_last_diagnostics([], msg)
            logger.warning("[SEARCH] 逾時 (elapsed=%dms, target=%s)", elapsed_ms, clean_query)
            return []

        if process_tracker.tracker.was_terminated(proc):
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("[SEARCH] 已取消 (elapsed=%dms, target=%s)", elapsed_ms, clean_query)
            _set_last_error("已取消")
            return []

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        stderr_raw = (stderr_text or "").strip()
        stderr_lines, warnings = _split_stderr_lines(stderr_raw)
        _set_last_diagnostics(warnings, stderr_raw[:4000])
        _log_stderr_lines(stderr_lines, "[SEARCH]")

        if proc.returncode != 0:
            msg = _extract_primary_error(stderr_lines, fallback=(stdout_text or ""))
            diag = analyze_error(msg)
            _set_last_error(msg or f"搜尋失敗 (code={proc.returncode})")
            logger.error(
                "[SEARCH] 失敗 (rc=%s, elapsed=%dms, err_code=%s, warnings=%d): %s",
                proc.returncode,
                elapsed_ms,
                diag.code,
                len(warnings),
                stderr_raw[:4000] or msg,
            )
            return []

        raw = (stdout_text or "").strip()
        if not raw:
            _set_last_error("找不到符合的歌曲")
            logger.warning("[SEARCH] 回傳空結果 (elapsed=%dms, query=%s)", elapsed_ms, clean_query)
            return []

        data = json.loads(raw)
        results: List[dict] = []
        if is_url and data.get("_type") != "playlist":
            logger.info(
                "[SEARCH] URL 解析結果: id=%s, title=%s, age_limit=%s, availability=%s, duration=%s, formats=%d",
                data.get("id"),
                data.get("title"),
                data.get("age_limit"),
                data.get("availability"),
                data.get("duration"),
                len(data.get("formats") or []),
            )
            item = _normalize_entry(data, fallback_url=clean_query)
            if item:
                results.append(item)
        else:
            for entry in data.get("entries") or []:
                item = _normalize_entry(entry)
                if item:
                    results.append(item)

        _set_last_error("" if results else "找不到符合的歌曲，請換個關鍵字試試")
        logger.info(
            "[SEARCH] 完成: 找到 %d 筆結果 (mode=%s, elapsed=%dms, warnings=%d, query=%s)",
            len(results),
            mode,
            elapsed_ms,
            len(warnings),
            clean_query,
        )
        return results
    except process_tracker.ProcessCancelled:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("[SEARCH] 已取消 (elapsed=%dms, target=%s)", elapsed_ms, clean_query)
        _set_last_error("已取消")
        return []
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        msg = str(e)
        _set_last_error(msg)
        _set_last_diagnostics([], msg)
        logger.error("[SEARCH] 例外 (elapsed=%dms): %s", elapsed_ms, e, exc_info=True)
        return []
    finally:
        if proc is not None:
            if proc.poll() is None:
                process_tracker.kill_process_tree(proc)
            process_tracker.tracker.release(proc)


def extract_info(url: str, extra_args: List[str] = None, timeout: int = 30) -> Optional[dict]:
    """Run yt-dlp --dump-json and return parsed info."""
    cmd = [
        find_ytdlp(),
        "--dump-json",
        "--no-playlist",
        "--no-progress",
        "--no-check-certificate",
    ]
    cmd.extend(_ffmpeg_args())
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)

    logger.info("[INFO] %s", _cmd_str(cmd))
    started = time.perf_counter()
    proc = None
    try:
        proc = process_tracker.tracker.spawn(
            cmd,
            group="info",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_create_no_window_flag(),
            env=_subprocess_env(),
        )
        try:
            stdout_text, stderr_text = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process_tracker.kill_process_tree(proc)
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if process_tracker.tracker.was_terminated(proc):
                logger.info("[INFO] 已取消 (elapsed=%dms, url=%s)", elapsed_ms, url)
                _set_last_error("已取消")
                return None
            msg = f"連線逾時 ({timeout}s)"
            _set_last_error(msg)
            _set_last_diagnostics([], msg)
            logger.warning("[INFO] %s for %s (elapsed=%dms)", msg, url, elapsed_ms)
            return None

        if process_tracker.tracker.was_terminated(proc):
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("[INFO] 已取消 (elapsed=%dms, url=%s)", elapsed_ms, url)
            _set_last_error("已取消")
            return None

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        stderr_raw = (stderr_text or "").strip()
        stderr_lines, warnings = _split_stderr_lines(stderr_raw)
        _set_last_diagnostics(warnings, stderr_raw[:4000])
        _log_stderr_lines(stderr_lines, "[INFO]")

        if proc.returncode != 0:
            msg = _extract_primary_error(stderr_lines, fallback=(stdout_text or ""))
            diag = analyze_error(msg)
            _set_last_error(msg or f"extract_info failed (code={proc.returncode})")
            logger.warning(
                "[INFO] 失敗 (rc=%s, elapsed=%dms, err_code=%s, warnings=%d): %s",
                proc.returncode,
                elapsed_ms,
                diag.code,
                len(warnings),
                stderr_raw[:4000] or msg,
            )
            return None

        _set_last_error("")
        parsed = json.loads(stdout_text) if (stdout_text or "").strip() else None
        if isinstance(parsed, dict):
            logger.info(
                "[INFO] 成功 (elapsed=%dms, warnings=%d): id=%s, title=%s, age_limit=%s, availability=%s, formats=%d",
                elapsed_ms,
                len(warnings),
                parsed.get("id"),
                parsed.get("title"),
                parsed.get("age_limit"),
                parsed.get("availability"),
                len(parsed.get("formats") or []),
            )
        return parsed
    except process_tracker.ProcessCancelled:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("[INFO] 已取消 (elapsed=%dms, url=%s)", elapsed_ms, url)
        _set_last_error("已取消")
        return None
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        msg = str(e)
        _set_last_error(msg)
        _set_last_diagnostics([], msg)
        logger.warning("[INFO] 錯誤 (elapsed=%dms): %s", elapsed_ms, e, exc_info=True)
        return None
    finally:
        if proc is not None:
            if proc.poll() is None:
                process_tracker.kill_process_tree(proc)
            process_tracker.tracker.release(proc)


def extract_info_flat(url: str, extra_args: List[str] = None) -> Optional[dict]:
    args = ["--extract-flat"] + (extra_args or [])
    return extract_info(url, extra_args=args, timeout=15)


def is_playlist(url: str, extra_args: List[str] = None) -> bool:
    info = extract_info_flat(url, extra_args)
    return info is not None and info.get("_type") == "playlist"


def get_playlist_info(url: str, extra_args: List[str] = None) -> dict:
    info = extract_info_flat(url, extra_args)
    if info and info.get("_type") == "playlist":
        return {
            "title": info.get("title", "Unknown Playlist"),
            "uploader": info.get("uploader", "Unknown"),
            "entry_count": len(info.get("entries", [])),
            "entries": info.get("entries", []),
        }
    return {}


_PROGRESS_RE = re.compile(
    r"\[download\]\s+(\d+(?:\.\d+)?)%"
    r"(?:\s+of\s+~?\s*(\d+(?:\.\d+)?\s*[KMGTP]?i?B))?"
    r"(?:\s+at\s+([\d.]+\s*[KMGTP]?i?B/s))?"
    r"(?:\s+ETA\s+(\S+))?"
)

_DEST_RE = re.compile(r"\[(?:ExtractAudio|download)\]\s+Destination:\s+(.+)$")

_LIFECYCLE_MARKERS = (
    "[youtube]",
    "[youtube:tab]",
    "[info]",
    "[download] Destination:",
    "[download] 100%",
    "[ExtractAudio]",
    "[Metadata]",
    "[EmbedThumbnail]",
    "[Fixup",
    "Extracting cookies",
    "WARNING:",
    "ERROR:",
)

_SIZE_UNITS = {
    "B": 1,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
}


def _parse_size_to_bytes(size_str: str) -> int:
    if not size_str:
        return 0
    m = re.match(r"([\d.]+)\s*([KMGTP]?i?B)", size_str.strip())
    if not m:
        return 0
    return int(float(m.group(1)) * _SIZE_UNITS.get(m.group(2), 1))


def format_bytes(bytes_value: int) -> str:
    if bytes_value == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def _parse_progress(line: str) -> Optional[dict]:
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    result = {"percent": float(m.group(1)), "speed": "", "eta": "", "stage": "downloading"}
    if m.group(2):
        result["total_bytes"] = _parse_size_to_bytes(m.group(2))
    if m.group(3):
        result["speed"] = m.group(3)
    if m.group(4):
        result["eta"] = m.group(4)
    return result


def download(
    url: str,
    output_path: str,
    format_spec: str,
    extra_args: List[str] = None,
    progress_callback: Callable = None,
    cancel_event: Optional[threading.Event] = None,
) -> int:
    """Download audio using yt-dlp subprocess with UTF-8 output parsing and rich logging."""
    ytdlp_exe = find_ytdlp()
    cmd = [
        ytdlp_exe,
        "--newline",
        "--no-check-certificate",
        "-o",
        output_path,
        "-f",
        format_spec,
    ]
    cmd.extend(_ffmpeg_args())
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)

    logger.info(
        "[CMD] ytdlp=%s | format=%s | output=%s | cmd=%s",
        ytdlp_exe,
        format_spec,
        output_path,
        _cmd_str(cmd),
    )
    started = time.perf_counter()
    flags = _create_no_window_flag()
    stderr_lines: List[str] = []
    warning_lines: List[str] = []
    last_error_line = ""
    detected_filepath = ""
    logged_milestones = set()

    proc = None
    try:
        proc = process_tracker.tracker.spawn(
            cmd,
            group="download",
            cancel_event=cancel_event,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=flags,
            env=_subprocess_env(),
        )

        def _is_cancelled() -> bool:
            if cancel_event is not None and cancel_event.is_set():
                return True
            if proc is not None and process_tracker.tracker.was_terminated(proc):
                return True
            return False

        def _collect_stderr():
            for raw_line in iter(proc.stderr.readline, b""):
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                stderr_lines.append(line)
                if "WARNING:" in line:
                    warning_lines.append(line)
                    logger.warning("[CMD_WARN] %s", line[:500])
                elif "ERROR:" in line:
                    logger.error("[CMD_STDERR] %s", line[:500])
                else:
                    logger.debug("[CMD_STDERR] %s", line[:500])

                total = sum(len(l) for l in stderr_lines)
                while (total > 8000 or len(stderr_lines) > 40) and len(stderr_lines) > 1:
                    total -= len(stderr_lines.pop(0))

        stderr_thread = threading.Thread(target=_collect_stderr, daemon=True)
        stderr_thread.start()

        for raw_line in iter(proc.stdout.readline, b""):
            if _is_cancelled():
                break

            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if "ERROR:" in line:
                logger.error("yt-dlp: %s", line[:500])
                last_error_line = line
            elif "WARNING:" in line:
                warning_lines.append(line)
                logger.warning("yt-dlp: %s", line[:500])
            elif any(marker in line for marker in _LIFECYCLE_MARKERS):
                logger.info("[YTDLP] %s", line[:400])

            dest_match = _DEST_RE.search(line)
            if dest_match:
                candidate = dest_match.group(1).strip()
                if candidate.lower().endswith(".mp3"):
                    detected_filepath = candidate

            if "[ExtractAudio]" in line or "[Metadata]" in line or "[EmbedThumbnail]" in line:
                if progress_callback and not _is_cancelled():
                    update = {"stage": "converting", "percent": 94.0}
                    if detected_filepath:
                        update["filepath"] = detected_filepath
                    progress_callback(update)
                continue

            progress = _parse_progress(line)
            if progress:
                pct = progress["percent"]
                for milestone in (25, 50, 75):
                    if pct >= milestone and milestone not in logged_milestones:
                        logged_milestones.add(milestone)
                        logger.debug(
                            "[YTDLP_PROGRESS] %d%% (speed=%s, eta=%s)",
                            milestone,
                            progress.get("speed", ""),
                            progress.get("eta", ""),
                        )
                if progress_callback and not _is_cancelled():
                    progress_callback(progress)

        if _is_cancelled() and proc.poll() is None:
            process_tracker.kill_process_tree(proc)

        proc.wait()
        stderr_thread.join(timeout=2.0)
        try:
            proc.stderr.close()
        except Exception:
            pass

        if _is_cancelled():
            _set_last_error("")
            return -1

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        full_stderr = "\n".join(stderr_lines)
        _set_last_diagnostics(warning_lines, full_stderr[:8000])

        if proc.returncode == 0:
            _set_last_error("")
            file_size = 0
            if detected_filepath:
                try:
                    p = Path(detected_filepath)
                    if p.exists():
                        file_size = p.stat().st_size
                except Exception:
                    pass
            logger.info(
                "[CMD_OK] 下載與轉檔完成 (elapsed=%dms, warnings=%d, file=%s, size=%s bytes)",
                elapsed_ms,
                len(warning_lines),
                detected_filepath or "(unknown)",
                file_size,
            )
            if progress_callback and not _is_cancelled():
                done_payload = {"percent": 100.0, "stage": "completed"}
                if detected_filepath:
                    done_payload["filepath"] = detected_filepath
                progress_callback(done_payload)
        else:
            reason = _extract_primary_error(stderr_lines, fallback=last_error_line)
            if not reason:
                reason = f"yt-dlp exited with code {proc.returncode}"
            diag = analyze_error(reason)
            logger.error(
                "[CMD_ERR] rc=%s | elapsed=%dms | warnings=%d | err_code=%s | reason=%s",
                proc.returncode,
                elapsed_ms,
                len(warning_lines),
                diag.code,
                reason,
            )
            _set_last_error(reason)
            if progress_callback and not _is_cancelled():
                progress_callback({"percent": 0, "stage": "failed"})

        return proc.returncode
    except process_tracker.ProcessCancelled:
        _set_last_error("")
        return -1
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            _set_last_error("")
            return -1
        if proc is not None and process_tracker.tracker.was_terminated(proc):
            _set_last_error("")
            return -1
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.error("[CMD_EXC] yt-dlp download failed (elapsed=%dms): %s", elapsed_ms, e, exc_info=True)
        _set_last_error(str(e) or f"yt-dlp download failed: {e}")
        _set_last_diagnostics(warning_lines, str(e))
        if progress_callback:
            progress_callback({"error": str(e), "stage": "failed"})
        return -1
    finally:
        if proc is not None:
            if proc.poll() is None:
                process_tracker.kill_process_tree(proc)
            process_tracker.tracker.release(proc)
