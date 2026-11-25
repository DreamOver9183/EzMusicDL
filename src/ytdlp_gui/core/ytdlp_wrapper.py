# -*- coding: utf-8 -*-
"""
yt-dlp CLI wrapper - UTF-8 safe subprocess calls for search, metadata, and MP3 download.
"""

import json
import logging
import os
import platform
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import binary_manager

logger = logging.getLogger(__name__)

_last_error = threading.local()


def _set_last_error(msg: str):
    _last_error.msg = msg


def get_last_error() -> str:
    """Get the last yt-dlp error message from current thread."""
    return getattr(_last_error, "msg", "")


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
    Returns normalized list of song dicts. Sets last error on failure.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        _set_last_error("請輸入歌名、歌手或貼上網址")
        return []

    is_url = bool(re.match(r"^https?://\S+", clean_query, re.IGNORECASE))
    target = clean_query if is_url else f"ytsearch{max_results}:{clean_query}"

    cmd = [
        find_ytdlp(),
        "--dump-single-json",
        "--no-warnings",
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

    logger.info("[SEARCH] %s", _cmd_str(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_create_no_window_flag(),
            env=_subprocess_env(),
        )
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "").strip()[:500]
            _set_last_error(msg or f"搜尋失敗 (code={result.returncode})")
            logger.warning("[SEARCH] yt-dlp 失敗: %s", msg)
            return []

        raw = (result.stdout or "").strip()
        if not raw:
            _set_last_error("找不到符合的歌曲")
            return []

        data = json.loads(raw)
        results: List[dict] = []
        if is_url and data.get("_type") != "playlist":
            item = _normalize_entry(data, fallback_url=clean_query)
            if item:
                results.append(item)
        else:
            for entry in data.get("entries") or []:
                item = _normalize_entry(entry)
                if item:
                    results.append(item)

        _set_last_error("" if results else "找不到符合的歌曲，請換個關鍵字試試")
        logger.info("[SEARCH] 找到 %d 筆結果 (query=%s)", len(results), clean_query)
        return results
    except subprocess.TimeoutExpired:
        msg = "搜尋逾時，請檢查網路連線後再試一次"
        _set_last_error(msg)
        logger.warning("[SEARCH] 逾時: %s", clean_query)
        return []
    except Exception as e:
        msg = str(e)
        _set_last_error(msg)
        logger.error("[SEARCH] 例外: %s", e)
        return []


def extract_info(url: str, extra_args: List[str] = None, timeout: int = 30) -> Optional[dict]:
    """Run yt-dlp --dump-json and return parsed info."""
    cmd = [
        find_ytdlp(),
        "--dump-json",
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        "--no-check-certificate",
    ]
    cmd.extend(_ffmpeg_args())
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)

    logger.info("[INFO] %s", _cmd_str(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_create_no_window_flag(),
            env=_subprocess_env(),
        )
        if result.returncode != 0:
            msg = (result.stderr or "").strip()[:500]
            _set_last_error(msg)
            logger.warning("yt-dlp extract_info 失敗: %s", msg)
            return None
        _set_last_error("")
        return json.loads(result.stdout) if (result.stdout or "").strip() else None
    except subprocess.TimeoutExpired:
        msg = f"連線逾時 ({timeout}s)"
        _set_last_error(msg)
        logger.warning("%s for %s", msg, url)
        return None
    except Exception as e:
        msg = str(e)
        _set_last_error(msg)
        logger.warning("yt-dlp extract_info 錯誤: %s", e)
        return None


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
) -> int:
    """Download audio using yt-dlp subprocess with UTF-8 output parsing."""
    cmd = [
        find_ytdlp(),
        "--newline",
        "--no-warnings",
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

    logger.info("[CMD] %s", _cmd_str(cmd))
    flags = _create_no_window_flag()
    stderr_lines: List[str] = []
    last_error_line = ""
    detected_filepath = ""

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=flags,
            env=_subprocess_env(),
        )

        def _collect_stderr():
            for raw_line in iter(proc.stderr.readline, b""):
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                stderr_lines.append(line)
                total = sum(len(l) for l in stderr_lines)
                while total > 2000 and len(stderr_lines) > 1:
                    total -= len(stderr_lines.pop(0))

        stderr_thread = threading.Thread(target=_collect_stderr, daemon=True)
        stderr_thread.start()

        for raw_line in iter(proc.stdout.readline, b""):
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if "ERROR:" in line:
                logger.error("yt-dlp: %s", line[:400])
                last_error_line = line

            dest_match = _DEST_RE.search(line)
            if dest_match:
                candidate = dest_match.group(1).strip()
                if candidate.lower().endswith(".mp3"):
                    detected_filepath = candidate

            if "[ExtractAudio]" in line or "[Metadata]" in line or "[EmbedThumbnail]" in line:
                if progress_callback:
                    update = {"stage": "converting", "percent": 94.0}
                    if detected_filepath:
                        update["filepath"] = detected_filepath
                    progress_callback(update)
                continue

            progress = _parse_progress(line)
            if progress and progress_callback:
                progress_callback(progress)

        proc.wait()
        stderr_thread.join(timeout=2.0)
        try:
            proc.stderr.close()
        except Exception:
            pass

        if proc.returncode == 0:
            _set_last_error("")
            if progress_callback:
                done_payload = {"percent": 100.0, "stage": "completed"}
                if detected_filepath:
                    done_payload["filepath"] = detected_filepath
                progress_callback(done_payload)
        else:
            reason = "\n".join(stderr_lines[-5:]).strip() or last_error_line.strip()
            if not reason:
                reason = f"yt-dlp exited with code {proc.returncode}"
            logger.error("[CMD_ERR] %s", reason)
            _set_last_error(reason)
            if progress_callback:
                progress_callback({"percent": 0, "stage": "failed"})

        return proc.returncode
    except Exception as e:
        logger.error("yt-dlp download failed: %s", e)
        _set_last_error(str(e) or f"yt-dlp download failed: {e}")
        if progress_callback:
            progress_callback({"error": str(e), "stage": "failed"})
        return -1
