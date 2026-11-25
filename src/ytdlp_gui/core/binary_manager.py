# -*- coding: utf-8 -*-
"""
Binary Manager - 3-stage environment check, auto-download/update, and re-verification.
Stores binaries portably in <app_root>/bin/.
"""

import logging
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests
from packaging.version import InvalidVersion, Version

from ytdlp_gui.utils.paths import (
    get_bin_dir as _paths_get_bin_dir,
    get_data_dir,
    get_default_downloads_dir,
    get_logs_dir,
    is_dir_writable,
)

logger = logging.getLogger(__name__)

YTDLP_EXE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_NIGHTLY_URL = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe"
YTDLP_LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_ZIP_BACKUP_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
DENO_ZIP_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"

YTDLP_PENDING_NAME = "yt-dlp-pending.exe"


@dataclass
class BootstrapReport:
    """Result of the 3-stage startup environment check -> download -> verify flow."""

    ok: bool = False
    ytdlp_ok: bool = False
    ytdlp_version: str = ""
    ytdlp_latest: str = ""
    ytdlp_updated: bool = False
    ffmpeg_ok: bool = False
    ffmpeg_version: str = ""
    ffprobe_ok: bool = False
    deno_ok: bool = False
    deno_version: str = ""
    downloads_dir: str = ""
    downloads_writable: bool = False
    data_writable: bool = False
    logs_writable: bool = False
    stages_log: List[str] = field(default_factory=list)
    error_message: str = ""


def get_bin_dir() -> Path:
    """Return portable bin directory (<app_root>/bin)."""
    return _paths_get_bin_dir()


def prepend_bin_to_path() -> Path:
    """Ensure portable bin directory is at the front of PATH."""
    bin_dir = get_bin_dir()
    bin_str = str(bin_dir)
    current_path = os.environ.get("PATH", "")
    parts = current_path.split(os.pathsep) if current_path else []
    if bin_str not in parts:
        os.environ["PATH"] = bin_str + (os.pathsep + current_path if current_path else "")
    return bin_dir


def get_ffmpeg_location() -> Optional[str]:
    ffmpeg = get_bin_dir() / "ffmpeg.exe"
    return str(ffmpeg.parent) if ffmpeg.exists() else None


def _download_file(url: str, dest: Path, timeout: int = 90) -> None:
    """Download a file with a per-request timeout. Raises on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "EasyMusicDL/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def _suppress_windows_loader_dialogs() -> None:
    if platform.system() == "Windows":
        try:
            import ctypes

            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x8000)
        except Exception:
            pass


def _run_version_cmd(path: Path, version_flag: str = "-version") -> Optional[str]:
    """Run binary with version flag and return first output line on exit code 0."""
    if not path.exists():
        return None
    flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
    _suppress_windows_loader_dialogs()
    try:
        result = subprocess.run(
            [str(path), version_flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            creationflags=flags,
        )
        if result.returncode != 0:
            return None
        for line in (result.stdout or result.stderr or "").splitlines():
            clean = line.strip()
            if clean:
                return clean
        return "ok"
    except Exception:
        return None


def _check_executable(path: Path, version_flag: str = "-version") -> bool:
    return _run_version_cmd(path, version_flag=version_flag) is not None


def _validate_ytdlp(path: Path) -> str:
    """Raise if a downloaded yt-dlp binary is truncated or cannot run; return version."""
    size = path.stat().st_size
    if size < 1_000_000:
        raise RuntimeError(f"{path.name} 檔案過小 ({size} bytes)")
    ver = _run_version_cmd(path, version_flag="--version")
    if not ver:
        raise RuntimeError(f"{path.name} 無法在此電腦正常執行")
    return ver


def _download_ytdlp_to(url: str, target_path: Path) -> str:
    """Download yt-dlp to a temporary file, validate, and atomically move to target."""
    tmp_path = target_path.with_name(target_path.name + ".tmp")
    try:
        _download_file(url, tmp_path, timeout=90)
        ver = _validate_ytdlp(tmp_path)
        tmp_path.replace(target_path)
        return ver
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def apply_pending_update() -> bool:
    """Apply yt-dlp-pending.exe if present before any yt-dlp subprocess launches."""
    bin_dir = get_bin_dir()
    exe = bin_dir / "yt-dlp.exe"
    pending = bin_dir / YTDLP_PENDING_NAME
    if not pending.exists():
        return False

    try:
        _validate_ytdlp(pending)
    except Exception as e:
        logger.warning("捨棄無效的待更新 yt-dlp 檔案: %s", e)
        pending.unlink(missing_ok=True)
        return False

    try:
        os.replace(pending, exe)
        logger.info("已套用待更新的 yt-dlp.exe")
        return True
    except OSError:
        logger.info("yt-dlp.exe 正在使用中，將於下次啟動套用更新")
        return False


def fetch_latest_ytdlp_tag(timeout: int = 6) -> Optional[str]:
    """Query GitHub Releases API for latest yt-dlp version tag. Returns None offline."""
    try:
        resp = requests.get(
            YTDLP_LATEST_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "EasyMusicDL/1.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        tag = (resp.json().get("tag_name") or "").strip().lstrip("v")
        return tag or None
    except Exception as e:
        logger.warning("檢查 yt-dlp 最新版本失敗（可能離線或 GitHub 忙碌）: %s", e)
        return None


def _is_newer_version(latest: str, current: str) -> bool:
    if not latest or not current:
        return False
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return latest.strip() != current.strip()


def _download_and_extract_ffmpeg(bin_dir: Path, report_fn: Callable[[str, int], None]) -> bool:
    ffmpeg_path = bin_dir / "ffmpeg.exe"
    ffprobe_path = bin_dir / "ffprobe.exe"
    zip_path = bin_dir / "ffmpeg.zip"
    created: List[Path] = []

    sources = [("GitHub (BtbN)", FFMPEG_ZIP_BACKUP_URL)]
    if platform.system() == "Windows" and sys.getwindowsversion().build < 19041:
        sources = []
    sources.append(("gyan.dev", FFMPEG_ZIP_URL))

    for source, url in sources:
        try:
            report_fn(f"正在下載音樂轉檔元件 FFmpeg（來源：{source}）...", 50)
            _download_file(url, zip_path, timeout=120)
            zip_size = zip_path.stat().st_size
            if zip_size < 20_000_000:
                raise RuntimeError(f"ffmpeg.zip 下載不完整 ({zip_size} bytes)")

            report_fn("正在解壓縮 FFmpeg 轉檔元件...", 65)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    name = Path(member).name
                    if name in ("ffmpeg.exe", "ffprobe.exe"):
                        dest = bin_dir / name
                        tmp = bin_dir / f"{name}.tmp"
                        with zf.open(member) as src, open(tmp, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        tmp.replace(dest)
                        created.append(dest)
            zip_path.unlink(missing_ok=True)

            for path in created:
                if path.stat().st_size < 1_000_000:
                    raise RuntimeError(f"{path.name} 檔案不完整")
            if not _check_executable(ffmpeg_path) or not _check_executable(ffprobe_path):
                raise RuntimeError("FFmpeg 無法在此電腦執行")

            report_fn("FFmpeg 下載完成", 72)
            return True
        except Exception as e:
            logger.warning("從 %s 下載 FFmpeg 失敗: %s", source, e)
            zip_path.unlink(missing_ok=True)
            for path in created:
                path.unlink(missing_ok=True)
            created.clear()
    return False


def _download_and_extract_deno(bin_dir: Path, report_fn: Callable[[str, int], None]) -> bool:
    deno_path = bin_dir / "deno.exe"
    zip_path = bin_dir / "deno.zip"
    try:
        report_fn("正在下載輔助元件 Deno...", 75)
        _download_file(DENO_ZIP_URL, zip_path, timeout=90)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if Path(member).name.lower() == "deno.exe":
                    tmp = bin_dir / "deno.exe.tmp"
                    with zf.open(member) as src, open(tmp, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    tmp.replace(deno_path)
                    break
        zip_path.unlink(missing_ok=True)
        if deno_path.exists() and _check_executable(deno_path, "--version"):
            report_fn("Deno 輔助元件準備完成", 78)
            return True
    except Exception as e:
        logger.warning("Deno 下載失敗（不影響基本功能）: %s", e)
        zip_path.unlink(missing_ok=True)
        deno_path.unlink(missing_ok=True)
    return False


def run_environment_bootstrap(
    progress_callback: Optional[Callable[[int, str, str, int], None]] = None,
    force_update: bool = False,
    downloads_dir: Optional[Path] = None,
) -> BootstrapReport:
    """
    Execute the 3-stage startup pipeline:
    1) Check environment & update availability
    2) Download / update missing or outdated components
    3) Re-verify all binaries and writable folders from disk
    """
    report = BootstrapReport()
    bin_dir = prepend_bin_to_path()
    data_dir = get_data_dir()
    logs_dir = get_logs_dir()
    target_downloads = Path(downloads_dir) if downloads_dir else get_default_downloads_dir()
    report.downloads_dir = str(target_downloads)

    def emit(stage_num: int, stage_title: str, detail: str, pct: int) -> None:
        line = f"[步驟 {stage_num}/3] {stage_title} - {detail}"
        report.stages_log.append(line)
        logger.info(line)
        if progress_callback:
            try:
                progress_callback(stage_num, stage_title, detail, pct)
            except Exception:
                pass

    ytdlp_path = bin_dir / "yt-dlp.exe"
    ffmpeg_path = bin_dir / "ffmpeg.exe"
    ffprobe_path = bin_dir / "ffprobe.exe"
    deno_path = bin_dir / "deno.exe"

    # ---------------- Stage 1: 檢查環境（含更新） ----------------
    s1 = "檢查環境與引擎更新"
    emit(1, s1, "正在檢查資料夾讀寫權限...", 5)
    apply_pending_update()

    report.data_writable = is_dir_writable(data_dir)
    report.logs_writable = is_dir_writable(logs_dir)
    report.downloads_writable = is_dir_writable(target_downloads)

    emit(1, s1, "正在檢查現有下載與轉檔元件...", 12)
    cur_ytdlp_ver = _run_version_cmd(ytdlp_path, "--version") if ytdlp_path.exists() else None
    cur_ffmpeg_ver = _run_version_cmd(ffmpeg_path, "-version") if ffmpeg_path.exists() else None
    cur_ffprobe_ok = _check_executable(ffprobe_path, "-version") if ffprobe_path.exists() else False
    cur_deno_ver = _run_version_cmd(deno_path, "--version") if deno_path.exists() else None

    emit(1, s1, "正在檢查 yt-dlp 是否有新版本...", 20)
    latest_ytdlp = fetch_latest_ytdlp_tag(timeout=6)
    report.ytdlp_latest = latest_ytdlp or ""

    need_ytdlp = (
        cur_ytdlp_ver is None
        or force_update
        or (latest_ytdlp is not None and _is_newer_version(latest_ytdlp, cur_ytdlp_ver))
    )
    need_ffmpeg = (cur_ffmpeg_ver is None) or (not cur_ffprobe_ok)
    need_deno = cur_deno_ver is None

    emit(
        1,
        s1,
        f"檢查完成（yt-dlp: {cur_ytdlp_ver or '缺少'} / 最新: {latest_ytdlp or '離線略過'}，"
        f"FFmpeg: {'正常' if not need_ffmpeg else '缺少'}）",
        25,
    )

    # ---------------- Stage 2: 下載 / 更新元件 ----------------
    s2 = "下載與更新元件"
    if not need_ytdlp and not need_ffmpeg and not need_deno:
        emit(2, s2, "所有元件皆為最新狀態，免下載", 78)
    else:
        if need_ytdlp:
            action_label = "正在下載最新版 yt-dlp..." if cur_ytdlp_ver is None else f"發現新版 {latest_ytdlp or 'yt-dlp'}，正在更新..."
            emit(2, s2, action_label, 32)
            updated_ok = False
            for src_name, url in (("官方穩定版", YTDLP_EXE_URL), ("Nightly 修復版", YTDLP_NIGHTLY_URL)):
                try:
                    new_ver = _download_ytdlp_to(url, ytdlp_path)
                    report.ytdlp_updated = True
                    emit(2, s2, f"yt-dlp ({src_name} {new_ver}) 下載完成", 45)
                    updated_ok = True
                    break
                except PermissionError:
                    # Locked by running process -> save pending
                    try:
                        pending = bin_dir / YTDLP_PENDING_NAME
                        _download_ytdlp_to(url, pending)
                        emit(2, s2, "yt-dlp 更新檔已備妥，下次開啟生效", 45)
                        updated_ok = True
                        break
                    except Exception as pe:
                        logger.warning("儲存待更新 yt-dlp 失敗: %s", pe)
                except Exception as e:
                    logger.warning("下載 yt-dlp (%s) 失敗: %s", src_name, e)
            if not updated_ok and cur_ytdlp_ver is not None:
                emit(2, s2, "更新下載失敗，保留現有可用的 yt-dlp 版本繼續", 45)
        else:
            emit(2, s2, f"yt-dlp 已是最新 ({cur_ytdlp_ver})", 45)

        if need_ffmpeg:
            _download_and_extract_ffmpeg(
                bin_dir, lambda msg, pct: emit(2, s2, msg, pct)
            )
        else:
            emit(2, s2, "FFmpeg 轉檔元件已就緒", 72)

        if need_deno:
            _download_and_extract_deno(
                bin_dir, lambda msg, pct: emit(2, s2, msg, pct)
            )
        else:
            emit(2, s2, "Deno 輔助元件已就緒", 78)

    # ---------------- Stage 3: 二次檢查與驗證 ----------------
    s3 = "二次檢查與驗證環境"
    emit(3, s3, "正在重新驗證 yt-dlp.exe 可執行性...", 84)
    prepend_bin_to_path()

    v_ytdlp = (
        _run_version_cmd(ytdlp_path, "--version")
        if ytdlp_path.exists() and ytdlp_path.stat().st_size >= 1_000_000
        else None
    )
    report.ytdlp_ok = v_ytdlp is not None
    report.ytdlp_version = v_ytdlp or ""

    emit(3, s3, "正在重新驗證 FFmpeg / FFprobe 轉檔元件...", 91)
    v_ffmpeg = (
        _run_version_cmd(ffmpeg_path, "-version")
        if ffmpeg_path.exists() and ffmpeg_path.stat().st_size >= 1_000_000
        else None
    )
    v_ffprobe = (
        _check_executable(ffprobe_path, "-version")
        if ffprobe_path.exists() and ffprobe_path.stat().st_size >= 1_000_000
        else False
    )
    report.ffmpeg_ok = v_ffmpeg is not None
    report.ffmpeg_version = (v_ffmpeg.split()[2] if v_ffmpeg and len(v_ffmpeg.split()) >= 3 else (v_ffmpeg or ""))
    report.ffprobe_ok = v_ffprobe

    emit(3, s3, "正在確認 Deno 與下載資料夾讀寫...", 96)
    v_deno = _run_version_cmd(deno_path, "--version") if deno_path.exists() else None
    report.deno_ok = v_deno is not None
    report.deno_version = v_deno or ""
    report.downloads_writable = is_dir_writable(target_downloads)

    missing_items = []
    if not report.ytdlp_ok:
        missing_items.append("下載引擎 yt-dlp.exe")
    if not report.ffmpeg_ok or not report.ffprobe_ok:
        missing_items.append("音樂轉檔元件 FFmpeg / FFprobe")
    if not report.downloads_writable:
        missing_items.append(f"無法寫入下載資料夾 ({target_downloads})")

    if missing_items:
        report.ok = False
        report.error_message = (
            "環境檢查未通過，缺少或無法驗證：\n• "
            + "\n• ".join(missing_items)
            + "\n\n請確認網路連線正常後點選「重試檢查」。"
        )
        emit(3, s3, f"二次檢查失敗：{', '.join(missing_items)}", 100)
    else:
        report.ok = True
        emit(
            3,
            s3,
            f"二次檢查全部通過！yt-dlp={report.ytdlp_version}, "
            f"FFmpeg={report.ffmpeg_version or 'OK'}, "
            f"Deno={'OK' if report.deno_ok else '略過'}",
            100,
        )

    return report


def ensure_binaries(progress_callback: Callable[[str, int], None] = None) -> bool:
    """Compatibility wrapper running the 3-stage bootstrap."""
    def _adapter(_stage: int, _title: str, detail: str, pct: int):
        if progress_callback:
            progress_callback(detail, pct)

    res = run_environment_bootstrap(progress_callback=_adapter)
    return res.ok


def update_ytdlp(is_busy: Optional[Callable[[], bool]] = None) -> None:
    """Download latest yt-dlp binary to pending if not busy."""
    try:
        if is_busy and is_busy():
            return
        bin_dir = get_bin_dir()
        exe = bin_dir / "yt-dlp.exe"
        if not exe.exists():
            return
        pending = bin_dir / YTDLP_PENDING_NAME
        for url in (YTDLP_EXE_URL, YTDLP_NIGHTLY_URL):
            try:
                _download_ytdlp_to(url, pending)
                return
            except Exception:
                continue
    except Exception as e:
        logger.debug("背景更新 yt-dlp 略過: %s", e)


def get_engine_status() -> Dict[str, str]:
    """Return current verified status strings of portable tools for the Help dialog."""
    bin_dir = get_bin_dir()
    ytdlp_ver = _run_version_cmd(bin_dir / "yt-dlp.exe", "--version")
    ffmpeg_raw = _run_version_cmd(bin_dir / "ffmpeg.exe", "-version")
    ffprobe_ok = _check_executable(bin_dir / "ffprobe.exe", "-version")
    deno_raw = _run_version_cmd(bin_dir / "deno.exe", "--version")

    ffmpeg_ver = ""
    if ffmpeg_raw:
        parts = ffmpeg_raw.split()
        ffmpeg_ver = parts[2] if len(parts) >= 3 else ffmpeg_raw[:30]

    return {
        "bin_dir": str(bin_dir),
        "ytdlp": ytdlp_ver or "未安裝或損壞",
        "ffmpeg": f"{ffmpeg_ver} (正常)" if (ffmpeg_raw and ffprobe_ok) else "未安裝或損壞",
        "deno": deno_raw.split()[1] if deno_raw and len(deno_raw.split()) >= 2 else (deno_raw or "未安裝（不影響一般使用）"),
    }
