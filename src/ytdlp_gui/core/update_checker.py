# -*- coding: utf-8 -*-
"""
Application Self-Updater for Windows Portable (--onedir) EasyMusicDL.
Checks GitHub Releases, verifies SHA-256 and archive integrity, preserves
user data/engine directories (bin/, data/, logs/, cookies.txt), backs up
old files with automatic rollback, and relaunches after replacing.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple
import zipfile

from packaging.version import InvalidVersion, Version
import requests

from ytdlp_gui import __version__
from ytdlp_gui.core import process_tracker
from ytdlp_gui.utils.logger import flush_logs
from ytdlp_gui.utils.paths import get_app_root as _paths_get_app_root, get_logs_dir, is_dir_writable

DEFAULT_GITHUB_REPO = "DreamOver9183/EzMusicDL"
PRESERVED_NAMES = frozenset({"bin", "data", "logs", "cookies.txt", ".update_backup"})
_SHA256_RE = re.compile(r"\b([a-fA-F0-9]{64})\b")


def _get_powershell_path() -> str:
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    candidate = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if os.path.exists(candidate):
        return candidate
    return "powershell.exe"


def _ps_quote(value: str) -> str:
    """Wrap a string in PowerShell single quotes with embedded single quotes escaped."""
    return "'" + str(value).replace("'", "''") + "'"


class UpdateChecker:
    """Check GitHub Releases and apply portable application updates."""

    HANDSHAKE_TIMEOUT_S: float = 10.0

    def __init__(self, settings_manager=None, repo: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self._settings = settings_manager
        self._apply_lock = threading.Lock()
        configured_repo = ""
        if settings_manager is not None:
            configured_repo = (settings_manager.get("update_repo", "") or "").strip()
        self.repo = (repo or configured_repo or DEFAULT_GITHUB_REPO).strip()
        self.api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        self.releases_page_url = f"https://github.com/{self.repo}/releases"
        self._current_version = self._parse_version(__version__)

    @staticmethod
    def _parse_version(version_str: str) -> Optional[Version]:
        clean = (version_str or "").strip().lstrip("vV")
        if not clean:
            return None
        try:
            return Version(clean)
        except InvalidVersion:
            return None

    def is_frozen(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    def get_app_root(self) -> Path:
        return _paths_get_app_root()

    def get_current_version(self) -> str:
        return __version__

    def _load_cache(self) -> Optional[Dict]:
        if not self._settings:
            return None
        try:
            raw = self._settings.get("latest_update_info", "")
            if not raw:
                return None
            info = json.loads(raw)
            if not isinstance(info, dict):
                return None
            if info.get("current_version") != __version__ or info.get("repo") != self.repo:
                self.logger.info(
                    "[UPDATE] 清除舊版本/不同來源的更新快取 (cached_ver=%s, cur=%s, cached_repo=%s)",
                    info.get("current_version"),
                    __version__,
                    info.get("repo"),
                )
                return None
            return info
        except Exception as e:
            self.logger.warning("[UPDATE] 讀取更新快取失敗: %s", e)
            return None

    def _save_cache(self, info: Dict) -> None:
        if not self._settings:
            return
        try:
            self._settings.set("latest_update_info", json.dumps(info, ensure_ascii=False))
            self._settings.save_settings()
        except Exception as e:
            self.logger.warning("[UPDATE] 儲存更新快取失敗: %s", e)

    @staticmethod
    def _find_asset(release_data: dict) -> Tuple[Optional[dict], Optional[str]]:
        """Select portable zip first, then standalone exe fallback."""
        assets = release_data.get("assets") or []
        zip_candidates: List[Tuple[int, dict]] = []
        exe_candidates: List[Tuple[int, dict]] = []

        for asset in assets:
            name = (asset.get("name") or "").strip()
            low = name.lower()
            if not name or not asset.get("browser_download_url"):
                continue
            if low.endswith((".sha256", ".sha256sum", ".sig", ".asc", ".txt")):
                continue

            if low.endswith(".zip"):
                score = 0
                if "easymusicdl" in low:
                    score += 30
                if "portable" in low:
                    score += 20
                if "win" in low or "win64" in low or "amd64" in low:
                    score += 10
                if "source" in low or "src" in low:
                    score -= 50
                zip_candidates.append((score, asset))
            elif low.endswith(".exe"):
                if any(bad in low for bad in ("yt-dlp", "ffmpeg", "ffprobe", "deno", "setup", "installer")):
                    continue
                score = 20 if "easymusicdl" in low else 5
                exe_candidates.append((score, asset))

        if zip_candidates:
            zip_candidates.sort(key=lambda pair: pair[0], reverse=True)
            best_score, best = zip_candidates[0]
            if best_score >= 0:
                return best, "portable_zip"

        if exe_candidates:
            exe_candidates.sort(key=lambda pair: pair[0], reverse=True)
            return exe_candidates[0][1], "single_exe"

        return None, None

    @staticmethod
    def _find_checksum_asset(release_data: dict, asset_name: str) -> Optional[str]:
        """Locate matching .sha256 sidecar or checksums.txt URL if present."""
        assets = release_data.get("assets") or []
        target_sidecar = f"{asset_name}.sha256".lower()
        fallback_url = None
        for asset in assets:
            name = (asset.get("name") or "").strip().lower()
            url = asset.get("browser_download_url")
            if not url:
                continue
            if name == target_sidecar:
                return url
            if name in ("checksums.txt", "sha256sums.txt", "sha256.txt"):
                fallback_url = url
        return fallback_url

    def check(self, force: bool = False) -> Dict:
        """Query GitHub Releases API for the latest application version."""
        cached = None if force else self._load_cache()
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"EasyMusicDL/{__version__}",
        }
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]

        started = time.perf_counter()
        self.logger.info(
            "[UPDATE] 檢查應用程式更新 (repo=%s, current=%s, force=%s)",
            self.repo,
            __version__,
            force,
        )
        try:
            resp = requests.get(self.api_url, timeout=10, headers=headers)
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            if resp.status_code == 304 and cached is not None:
                self.logger.info("[UPDATE] 版本資訊未變更 (304, elapsed=%dms)", elapsed_ms)
                return {**cached, "from_cache": True}

            if resp.status_code == 404:
                self.logger.info("[UPDATE] 尚未發布任何 Release (404, elapsed=%dms)", elapsed_ms)
                result = {
                    "available": False,
                    "status": "no_release",
                    "repo": self.repo,
                    "current_version": __version__,
                    "latest_version": __version__,
                    "release_url": self.releases_page_url,
                    "message": "目前尚無已發布的應用程式更新版本。",
                }
                return result

            if resp.status_code in (403, 429):
                self.logger.warning(
                    "[UPDATE] GitHub API 速率限制 (status=%s, elapsed=%dms)",
                    resp.status_code,
                    elapsed_ms,
                )
                if cached is not None:
                    return {**cached, "from_cache": True}
                return {
                    "available": False,
                    "status": "error",
                    "repo": self.repo,
                    "current_version": __version__,
                    "release_url": self.releases_page_url,
                    "message": "GitHub 更新伺服器目前連線次數過多，請稍後再試。",
                }

            resp.raise_for_status()
            data = resp.json()
            tag = (data.get("tag_name") or "").strip()
            latest_str = tag.lstrip("vV")
            latest_ver = self._parse_version(latest_str)
            if not latest_ver:
                self.logger.warning("[UPDATE] 無法解析遠端版本號 tag=%s", tag)
                return {
                    "available": False,
                    "status": "error",
                    "repo": self.repo,
                    "current_version": __version__,
                    "release_url": data.get("html_url") or self.releases_page_url,
                    "message": f"無法解析遠端版本格式：{tag or '未知'}",
                }

            result: Dict = {
                "available": False,
                "status": "up_to_date",
                "repo": self.repo,
                "current_version": __version__,
                "latest_version": latest_str,
                "release_notes": data.get("body", "") or "",
                "release_url": data.get("html_url") or self.releases_page_url,
                "message": f"目前已是最新版本（v{__version__}）。",
            }
            etag = resp.headers.get("ETag")
            if etag:
                result["etag"] = etag

            if self._current_version and latest_ver > self._current_version:
                asset, asset_type = self._find_asset(data)
                if not asset or not asset_type:
                    result["status"] = "no_asset"
                    result["message"] = (
                        f"發現新版本 v{latest_str}，但找不到可用的免安裝更新壓縮檔，請至發佈頁面手動下載。"
                    )
                    self.logger.warning(
                        "[UPDATE] 發現新版本 v%s 但找不到相容資產 (assets=%d)",
                        latest_str,
                        len(data.get("assets") or []),
                    )
                else:
                    asset_name = asset.get("name", "")
                    result["available"] = True
                    result["status"] = "update_available"
                    result["download_url"] = asset.get("browser_download_url", "")
                    result["asset_name"] = asset_name
                    result["asset_size"] = int(asset.get("size") or 0)
                    result["asset_type"] = asset_type
                    checksum_url = self._find_checksum_asset(data, asset_name)
                    if checksum_url:
                        result["checksum_url"] = checksum_url
                    result["message"] = f"發現新版本 v{latest_str}（目前為 v{__version__}）"
                    self.logger.info(
                        "[UPDATE] 發現新版本 v%s (type=%s, asset=%s, size=%s, elapsed=%dms)",
                        latest_str,
                        asset_type,
                        asset_name,
                        result["asset_size"],
                        elapsed_ms,
                    )
            else:
                self.logger.info(
                    "[UPDATE] 已是最新 (current=%s, latest=%s, elapsed=%dms)",
                    __version__,
                    latest_str,
                    elapsed_ms,
                )

            self._save_cache(result)
            return result

        except requests.RequestException as e:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.logger.warning("[UPDATE] 檢查更新失敗 (elapsed=%dms): %s", elapsed_ms, e)
            if cached is not None:
                return {**cached, "from_cache": True}
            return {
                "available": False,
                "status": "error",
                "repo": self.repo,
                "current_version": __version__,
                "release_url": self.releases_page_url,
                "message": f"無法連線檢查更新：{e}",
            }
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            self.logger.warning("[UPDATE] 解析更新回應失敗: %s", e)
            return {
                "available": False,
                "status": "error",
                "repo": self.repo,
                "current_version": __version__,
                "release_url": self.releases_page_url,
                "message": f"解析更新資訊失敗：{e}",
            }

    @staticmethod
    def _parse_expected_sha256(text: str, asset_name: str) -> Optional[str]:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        target_low = (asset_name or "").lower()
        for ln in lines:
            if target_low and target_low in ln.lower():
                m = _SHA256_RE.search(ln)
                if m:
                    return m.group(1).lower()
        for ln in lines:
            m = _SHA256_RE.search(ln)
            if m:
                return m.group(1).lower()
        return None

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()

    @staticmethod
    def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
        dest_root = dest_dir.resolve()
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_member = zf.testzip()
            if bad_member is not None:
                raise RuntimeError(f"更新壓縮檔損毀（{bad_member}）")

            for member in zf.infolist():
                target = (dest_root / member.filename).resolve()
                try:
                    target.relative_to(dest_root)
                except ValueError as exc:
                    raise RuntimeError(f"更新壓縮檔包含不安全路徑：{member.filename}") from exc

            zf.extractall(dest_root)

    @staticmethod
    def _locate_payload_root(extracted_dir: Path, preferred_exe_name: str) -> Tuple[Path, str]:
        """Locate the folder (depth 0 or 1) containing the application executable."""
        candidates = [preferred_exe_name, "EasyMusicDL.exe"]
        search_dirs = [extracted_dir] + [p for p in extracted_dir.iterdir() if p.is_dir()]
        for folder in search_dirs:
            for exe_name in candidates:
                exe_path = folder / exe_name
                if exe_path.is_file():
                    return folder, exe_name
        raise RuntimeError(f"解壓縮後的更新檔找不到主程式 ({preferred_exe_name})")

    def download_update(
        self,
        update_info: Dict,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Dict:
        """Download, verify, extract, and stage a portable update package."""
        def emit(msg: str, pct: float) -> None:
            if progress_callback:
                try:
                    progress_callback(msg, pct)
                except Exception:
                    pass

        app_root = self.get_app_root()
        if self.is_frozen() and not is_dir_writable(app_root):
            return {
                "ok": False,
                "error": (
                    f"程式資料夾沒有寫入權限（{app_root}）。"
                    "請將免安裝資料夾移至「桌面」或「文件」等一般資料夾後再更新。"
                ),
            }

        url = (update_info or {}).get("download_url") or ""
        asset_type = (update_info or {}).get("asset_type") or ""
        asset_name = (update_info or {}).get("asset_name") or (
            "EasyMusicDL-update.zip" if asset_type == "portable_zip" else "EasyMusicDL.exe"
        )
        checksum_url = (update_info or {}).get("checksum_url") or ""
        target_version = (update_info or {}).get("latest_version") or ""

        if not url or asset_type not in ("portable_zip", "single_exe"):
            return {"ok": False, "error": "缺少可用的更新下載連結或檔案格式不支援。"}

        staging_dir = Path(tempfile.mkdtemp(prefix="EasyMusicDL_update_"))
        download_path = staging_dir / asset_name
        started = time.perf_counter()
        self.logger.info(
            "[UPDATE] 開始下載更新檔: version=%s | type=%s | url=%s | staging=%s",
            target_version,
            asset_type,
            url,
            staging_dir,
        )

        try:
            emit("正在連線並下載應用程式更新檔...", 0.05)
            resp = requests.get(
                url,
                stream=True,
                timeout=30,
                headers={"User-Agent": f"EasyMusicDL/{__version__}"},
            )
            resp.raise_for_status()
            total_size = int(resp.headers.get("content-length") or update_info.get("asset_size") or 0)
            downloaded = 0

            with open(download_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        frac = min(1.0, downloaded / total_size)
                        emit(f"正在下載更新檔 ({int(frac * 100)}%)...", 0.05 + frac * 0.65)

            dl_ms = int((time.perf_counter() - started) * 1000)
            actual_size = download_path.stat().st_size
            self.logger.info(
                "[UPDATE] 下載完成: file=%s | size=%s bytes | elapsed=%dms",
                download_path.name,
                actual_size,
                dl_ms,
            )

            if checksum_url:
                emit("正在驗證檔案完整性 (SHA-256)...", 0.75)
                cs_resp = requests.get(
                    checksum_url,
                    timeout=15,
                    headers={"User-Agent": f"EasyMusicDL/{__version__}"},
                )
                cs_resp.raise_for_status()
                expected_hash = self._parse_expected_sha256(cs_resp.text, asset_name)
                if not expected_hash:
                    raise RuntimeError("無法解析 SHA-256 校驗檔內容")
                actual_hash = self._compute_sha256(download_path)
                if actual_hash != expected_hash:
                    raise RuntimeError(
                        f"SHA-256 驗證失敗 (expected={expected_hash[:12]}..., actual={actual_hash[:12]}...)"
                    )
                self.logger.info("[UPDATE] SHA-256 驗證通過 (%s)", actual_hash[:16])

            preferred_exe_name = Path(sys.executable).name if self.is_frozen() else "EasyMusicDL.exe"
            if asset_type == "portable_zip":
                emit("正在解壓縮並檢查更新檔...", 0.82)
                extracted_dir = staging_dir / "extracted"
                extracted_dir.mkdir(parents=True, exist_ok=True)
                self._safe_extract_zip(download_path, extracted_dir)
                payload_root, exe_name = self._locate_payload_root(extracted_dir, preferred_exe_name)

                exe_size = (payload_root / exe_name).stat().st_size
                if exe_size < 500_000:
                    raise RuntimeError(f"更新檔主程式過小 ({exe_size} bytes)")

                for preserved in PRESERVED_NAMES:
                    extra_dir = payload_root / preserved
                    if extra_dir.exists():
                        if extra_dir.is_dir():
                            shutil.rmtree(extra_dir, ignore_errors=True)
                        else:
                            extra_dir.unlink(missing_ok=True)

                has_internal = (payload_root / "_internal").is_dir()
                self.logger.info(
                    "[UPDATE] 免安裝包驗證通過: payload=%s | exe=%s (%s bytes) | _internal=%s",
                    payload_root,
                    exe_name,
                    exe_size,
                    has_internal,
                )
            else:
                emit("正在驗證執行檔...", 0.85)
                if actual_size < 1_000_000:
                    raise RuntimeError(f"更新執行檔過小 ({actual_size} bytes)")
                with open(download_path, "rb") as f:
                    magic = f.read(2)
                if magic != b"MZ":
                    raise RuntimeError("下載的檔案不是有效的 Windows 執行檔")
                payload_root = staging_dir / "single_payload"
                payload_root.mkdir(parents=True, exist_ok=True)
                exe_name = preferred_exe_name
                shutil.move(str(download_path), str(payload_root / exe_name))
                self.logger.info(
                    "[UPDATE] 獨立執行檔驗證通過: exe=%s (%s bytes)",
                    exe_name,
                    actual_size,
                )

            emit("更新檔準備完成，即將套用更新...", 1.0)
            return {
                "ok": True,
                "staging_dir": str(staging_dir),
                "payload_root": str(payload_root),
                "exe_name": exe_name,
                "asset_type": asset_type,
                "version": target_version,
            }
        except Exception as e:
            self.logger.error("[UPDATE] 準備更新檔失敗: %s", e, exc_info=True)
            shutil.rmtree(staging_dir, ignore_errors=True)
            return {"ok": False, "error": f"下載或驗證更新檔失敗：{e}"}

    @staticmethod
    def build_windows_updater_script(
        staging_dir: Path,
        payload_root: Path,
        app_root: Path,
        exe_name: str,
        asset_type: str,
        parent_pid: int,
        log_path: Path,
        relaunch: bool = True,
        *,
        parent_wait_seconds: int = 30,
        popup_seconds: int = 15,
        alive_seconds: int = 10,
        relaunch_delays: Tuple[int, ...] = (2, 4, 6, 8),
        fallback_log_path: Optional[Path] = None,
    ) -> str:
        """Build a rollback-safe PowerShell updater script for Windows portable folders."""
        preserved_literal = ", ".join(_ps_quote(name) for name in sorted(PRESERVED_NAMES))
        delays_literal = ", ".join(str(int(d)) for d in relaunch_delays)
        fallback_log_expr = (
            _ps_quote(str(fallback_log_path))
            if fallback_log_path is not None
            else "Join-Path ([System.IO.Path]::GetTempPath()) 'EasyMusicDL_updater.log'"
        )
        relaunch_val = "$true" if relaunch else "$false"

        header = (
            "$ErrorActionPreference = 'Stop'\n"
            f"$parentPid = {int(parent_pid)}\n"
            f"$stagingDir = {_ps_quote(str(staging_dir))}\n"
            f"$payloadRoot = {_ps_quote(str(payload_root))}\n"
            f"$appRoot = {_ps_quote(str(app_root))}\n"
            f"$exeName = {_ps_quote(str(exe_name))}\n"
            f"$assetType = {_ps_quote(str(asset_type))}\n"
            f"$logPath = {_ps_quote(str(log_path))}\n"
            f"$fallbackLogPath = {fallback_log_expr}\n"
            f"$backupDir = Join-Path $appRoot '.update_backup'\n"
            f"$preserved = @({preserved_literal})\n"
            f"$parentWaitSeconds = {int(parent_wait_seconds)}\n"
            f"$popupSeconds = {int(popup_seconds)}\n"
            f"$aliveSeconds = {int(alive_seconds)}\n"
            f"$relaunchDelays = @({delays_literal})\n"
            f"$relaunch = {relaunch_val}\n"
        )

        body = (
            "function Write-UpdaterLog([string]$msg) {\n"
            "    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')\n"
            "    $line = \"[$ts] $msg\"\n"
            "    try {\n"
            "        $dir = Split-Path -Parent $logPath\n"
            "        if ($dir -and -not (Test-Path -LiteralPath $dir)) {\n"
            "            New-Item -ItemType Directory -Path $dir -Force | Out-Null\n"
            "        }\n"
            "        Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8\n"
            "    } catch {\n"
            "        try {\n"
            "            $fbDir = Split-Path -Parent $fallbackLogPath\n"
            "            if ($fbDir -and -not (Test-Path -LiteralPath $fbDir)) {\n"
            "                New-Item -ItemType Directory -Path $fbDir -Force | Out-Null\n"
            "            }\n"
            "            Add-Content -LiteralPath $fallbackLogPath -Value $line -Encoding UTF8\n"
            "        } catch {\n"
            "        }\n"
            "    }\n"
            "}\n"
            "\n"
            "function Show-UpdaterPopup([string]$text, [string]$title, [int]$icon) {\n"
            "    try {\n"
            "        $ws = New-Object -ComObject WScript.Shell\n"
            "        $ws.Popup($text, $popupSeconds, $title, $icon) | Out-Null\n"
            "    } catch {\n"
            "    }\n"
            "}\n"
            "\n"
            "function Test-AppDirWritable([string]$dir) {\n"
            "    $probePath = $null\n"
            "    try {\n"
            "        if (-not (Test-Path -LiteralPath $dir -PathType Container)) {\n"
            "            return $false\n"
            "        }\n"
            "        $probeName = '.probe_' + [System.Guid]::NewGuid().ToString('N') + '.tmp'\n"
            "        $probePath = Join-Path $dir $probeName\n"
            "        [System.IO.File]::WriteAllText($probePath, 'probe')\n"
            "        return $true\n"
            "    } catch {\n"
            "        return $false\n"
            "    } finally {\n"
            "        if ($probePath -and (Test-Path -LiteralPath $probePath)) {\n"
            "            try {\n"
            "                [System.IO.File]::Delete($probePath)\n"
            "            } catch {\n"
            "                try { Remove-Item -LiteralPath $probePath -Force -ErrorAction SilentlyContinue } catch {}\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
            "\n"
            "function Move-ItemAtomic([string]$src, [string]$dst) {\n"
            "    for ($i = 1; $i -le 5; $i++) {\n"
            "        try {\n"
            "            if ([System.IO.Directory]::Exists($src)) {\n"
            "                [System.IO.Directory]::Move($src, $dst)\n"
            "            } elseif ([System.IO.File]::Exists($src)) {\n"
            "                [System.IO.File]::Move($src, $dst)\n"
            "            } else {\n"
            "                throw \"Source item not found: $src\"\n"
            "            }\n"
            "            return\n"
            "        } catch {\n"
            "            if ($i -eq 5) { throw }\n"
            "            Start-Sleep -Milliseconds 500\n"
            "        }\n"
            "    }\n"
            "}\n"
            "\n"
            "function Get-Sha256Hex([string]$path) {\n"
            "    $sha256 = $null\n"
            "    $stream = $null\n"
            "    try {\n"
            "        $sha256 = [System.Security.Cryptography.SHA256]::Create()\n"
            "        $stream = [System.IO.File]::OpenRead($path)\n"
            "        $hashBytes = $sha256.ComputeHash($stream)\n"
            "        $sb = New-Object System.Text.StringBuilder\n"
            "        foreach ($b in $hashBytes) {\n"
            "            $null = $sb.Append($b.ToString('x2'))\n"
            "        }\n"
            "        return $sb.ToString()\n"
            "    } finally {\n"
            "        if ($stream) { $stream.Dispose() }\n"
            "        if ($sha256) { $sha256.Dispose() }\n"
            "    }\n"
            "}\n"
            "\n"
            "function Copy-UpdateItem([string]$src, [string]$dst) {\n"
            "    Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force\n"
            "}\n"
            "\n"
            "function Remove-ItemVerified([string]$path) {\n"
            "    if (-not (Test-Path -LiteralPath $path)) {\n"
            "        return\n"
            "    }\n"
            "    for ($i = 1; $i -le 5; $i++) {\n"
            "        try {\n"
            "            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop\n"
            "        } catch {\n"
            "        }\n"
            "        if (-not (Test-Path -LiteralPath $path)) {\n"
            "            return\n"
            "        }\n"
            "        Start-Sleep -Milliseconds 500\n"
            "    }\n"
            "    if (Test-Path -LiteralPath $path) {\n"
            "        throw \"Failed to remove path: $path\"\n"
            "    }\n"
            "}\n"
            "\n"
            "function Invoke-LaunchProcess([string]$exe, [string]$workDir) {\n"
            "    return (Start-Process -FilePath $exe -WorkingDirectory $workDir -PassThru)\n"
            "}\n"
            "\n"
            "function Start-UpdatedApp([string]$targetExe, [string]$workDir) {\n"
            "    $proc = $null\n"
            "    $launched = $false\n"
            "    for ($attempt = 1; $attempt -le 5; $attempt++) {\n"
            "        try {\n"
            "            Write-UpdaterLog \"Launching updated app (attempt ${attempt}): $targetExe\"\n"
            "            $proc = Invoke-LaunchProcess -exe $targetExe -workDir $workDir\n"
            "            if ($proc) {\n"
            "                try { $null = $proc.Handle } catch {}\n"
            "            }\n"
            "            $launched = $true\n"
            "            break\n"
            "        } catch {\n"
            "            $exMsg = $_.Exception.Message\n"
            "            Write-UpdaterLog \"Launch failed on attempt ${attempt}: $exMsg\"\n"
            "            if ($attempt -lt 5) {\n"
            "                $delayIdx = $attempt - 1\n"
            "                $delaySec = 2\n"
            "                if ($delayIdx -lt $relaunchDelays.Length) {\n"
            "                    $delaySec = $relaunchDelays[$delayIdx]\n"
            "                }\n"
            "                Write-UpdaterLog \"Waiting ${delaySec} seconds before retry...\"\n"
            "                Start-Sleep -Seconds $delaySec\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "\n"
            "    if ($launched -and $proc) {\n"
            "        $aliveWaited = 0.0\n"
            "        $step = 0.5\n"
            "        $earlyExited = $false\n"
            "        while ($aliveWaited -lt $aliveSeconds) {\n"
            "            if ($proc.HasExited) {\n"
            "                $earlyExited = $true\n"
            "                break\n"
            "            }\n"
            "            Start-Sleep -Milliseconds 500\n"
            "            $aliveWaited += $step\n"
            "        }\n"
            "        if (-not $earlyExited -and -not $proc.HasExited) {\n"
            "            Write-UpdaterLog \"Updated app is alive after ${aliveSeconds} s (pid=$($proc.Id)). Update succeeded.\"\n"
            "            try {\n"
            "                Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue\n"
            "            } catch {\n"
            "                Write-UpdaterLog \"Warning: Failed to remove backupDir: $_\"\n"
            "            }\n"
            "            try {\n"
            "                Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue\n"
            "            } catch {\n"
            "                Write-UpdaterLog \"Warning: Failed to remove stagingDir: $_\"\n"
            "            }\n"
            "            Write-UpdaterLog \"=== Updater finished successfully ===\"\n"
            "            exit 0\n"
            "        } else {\n"
            "            $ec = try { $proc.ExitCode } catch { 'unknown' }\n"
            "            Write-UpdaterLog \"Updated app exited prematurely (ExitCode=${ec}). Will not restart.\"\n"
            "            $msg = \"EasyMusicDL 已更新完成，但自動啟動後提早結束（結束代碼：${ec}）。`n請手動開啟：${targetExe}`n`n備份檔案保留於：${backupDir}`n如需手動復原，請將備份目錄中的檔案複製回程式目錄。`n詳細紀錄：${logPath}\"\n"
            "            Show-UpdaterPopup -text $msg -title \"應用程式更新完成（需手動啟動）\" -icon 48\n"
            "            exit 2\n"
            "        }\n"
            "    } else {\n"
            "        Write-UpdaterLog \"All 5 launch attempts failed. Update files preserved.\"\n"
            "        $msg = \"EasyMusicDL 已更新完成，請手動開啟 ${exeName}。`n`n程式路徑：${targetExe}`n詳細紀錄：${logPath}\"\n"
            "        Show-UpdaterPopup -text $msg -title \"應用程式更新完成（請手動開啟）\" -icon 48\n"
            "        exit 2\n"
            "    }\n"
            "}\n"
            "\n"
            "# --- main ---\n"
            "$startedMarker = Join-Path $stagingDir 'updater.started'\n"
            "try {\n"
            "    [System.IO.File]::WriteAllText($startedMarker, \"$PID\")\n"
            "} catch {\n"
            "    try { Set-Content -LiteralPath $startedMarker -Value \"$PID\" -Force } catch {}\n"
            "}\n"
            "\n"
            "Write-UpdaterLog \"=== Updater started (parentPid=${parentPid}, assetType=${assetType}, appRoot=${appRoot}) ===\"\n"
            "\n"
            "$waited = 0\n"
            "$maxWaitLoops = [int]($parentWaitSeconds * 2)\n"
            "while ($waited -lt $maxWaitLoops) {\n"
            "    if (-not (Get-Process -Id $parentPid -ErrorAction SilentlyContinue)) { break }\n"
            "    Start-Sleep -Milliseconds 500\n"
            "    $waited++\n"
            "}\n"
            "if (Get-Process -Id $parentPid -ErrorAction SilentlyContinue) {\n"
            "    Write-UpdaterLog \"ERROR: Parent process ${parentPid} did not exit within ${parentWaitSeconds} s; aborting safely.\"\n"
            "    Show-UpdaterPopup -text \"更新程式逾時：主程式未在時限內結束。`n請關閉程式後重試。\" -title \"應用程式更新失敗\" -icon 16\n"
            "    exit 1\n"
            "}\n"
            "Start-Sleep -Milliseconds 500\n"
            "\n"
            "$backupExistsAndNotEmpty = $false\n"
            "if (Test-Path -LiteralPath $backupDir) {\n"
            "    try {\n"
            "        $existingBackupItems = Get-ChildItem -LiteralPath $backupDir -Force -ErrorAction Stop\n"
            "        if ($existingBackupItems -and $existingBackupItems.Count -gt 0) {\n"
            "            $backupExistsAndNotEmpty = $true\n"
            "        }\n"
            "    } catch {\n"
            "        $enumErr = $_.Exception.Message\n"
            "        Write-UpdaterLog \"ERROR: Failed to enumerate existing backup directory: $enumErr\"\n"
            "        $enumMsg = \"無法讀取現有備份資料夾內容，更新程序中止。`n安裝內容未被更動。`n備份目錄：${backupDir}`n詳細紀錄：${logPath}\"\n"
            "        Show-UpdaterPopup -text $enumMsg -title \"應用程式更新中止\" -icon 16\n"
            "        exit 1\n"
            "    }\n"
            "}\n"
            "\n"
            "$destExe = Join-Path $appRoot $exeName\n"
            "$hasExe = Test-Path -LiteralPath $destExe\n"
            "$backupInternal = Join-Path $backupDir '_internal'\n"
            "$backupHasInternal = Test-Path -LiteralPath $backupInternal\n"
            "$appInternal = Join-Path $appRoot '_internal'\n"
            "$appHasInternal = Test-Path -LiteralPath $appInternal\n"
            "\n"
            "if ($backupExistsAndNotEmpty) {\n"
            "    $needsManualRecovery = (-not $hasExe) -or ($backupHasInternal -and (-not $appHasInternal))\n"
            "    if ($needsManualRecovery) {\n"
            "        Write-UpdaterLog \"ERROR: Detected non-empty backup from a previous failed update and damaged installation. Preserving backup.\"\n"
            "        $recMsg = \"偵測到上次更新中斷且程式安裝不完整。`n備份檔案保留於：${backupDir}`n請手動復原備份檔案至程式資料夾後再試。`n詳細紀錄：${logPath}\"\n"
            "        Show-UpdaterPopup -text $recMsg -title \"應用程式更新中止\" -icon 16\n"
            "        exit 1\n"
            "    }\n"
            "}\n"
            "\n"
            "if (-not (Test-AppDirWritable -dir $appRoot)) {\n"
            "    Write-UpdaterLog \"ERROR: Application directory is not writable: $appRoot\"\n"
            "    Show-UpdaterPopup -text \"程式資料夾沒有寫入權限（${appRoot}）。`n請確認檔案未被鎖定或移至可寫入目錄後重試。\" -title \"應用程式更新失敗\" -icon 16\n"
            "    exit 1\n"
            "}\n"
            "\n"
            "try {\n"
            "    if (Test-Path -LiteralPath $backupDir) {\n"
            "        Remove-ItemVerified -path $backupDir\n"
            "    }\n"
            "    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null\n"
            "} catch {\n"
            "    $prepErr = $_.Exception.Message\n"
            "    Write-UpdaterLog \"ERROR: Failed to initialize clean backup directory: $prepErr\"\n"
            "    $prepMsg = \"無法重設備份資料夾，更新未進行。`n安裝未被更動。`n備份目錄：${backupDir}`n詳細紀錄：${logPath}\"\n"
            "    Show-UpdaterPopup -text $prepMsg -title \"應用程式更新中止\" -icon 16\n"
            "    exit 1\n"
            "}\n"
            "\n"
            "$journal = New-Object System.Collections.Generic.List[psobject]\n"
            "\n"
            "try {\n"
            "    $items = Get-ChildItem -LiteralPath $payloadRoot -Force\n"
            "    foreach ($item in $items) {\n"
            "        if ($preserved -contains $item.Name) {\n"
            "            Write-UpdaterLog \"Skipping preserved item: $($item.Name)\"\n"
            "            continue\n"
            "        }\n"
            "        $dest = Join-Path $appRoot $item.Name\n"
            "        $bak = Join-Path $backupDir $item.Name\n"
            "        $hadOriginal = Test-Path -LiteralPath $dest\n"
            "\n"
            "        $record = [PSCustomObject]@{\n"
            "            Name = $item.Name\n"
            "            HadOriginal = [bool]$hadOriginal\n"
            "        }\n"
            "        $journal.Add($record) | Out-Null\n"
            "\n"
            "        if ($hadOriginal) {\n"
            "            Write-UpdaterLog \"Backing up existing: $($item.Name)\"\n"
            "            Move-ItemAtomic -src $dest -dst $bak\n"
            "        }\n"
            "\n"
            "        Write-UpdaterLog \"Installing new: $($item.Name)\"\n"
            "        Copy-UpdateItem -src $item.FullName -dst $dest\n"
            "    }\n"
            "\n"
            "    if (-not (Test-Path -LiteralPath $destExe)) {\n"
            "        throw \"Verification failed: Destination executable missing (${destExe})\"\n"
            "    }\n"
            "    $payloadExe = Join-Path $payloadRoot $exeName\n"
            "    if (-not (Test-Path -LiteralPath $payloadExe)) {\n"
            "        throw \"Verification failed: Payload executable missing (${payloadExe})\"\n"
            "    }\n"
            "    $destHash = Get-Sha256Hex -path $destExe\n"
            "    $payloadHash = Get-Sha256Hex -path $payloadExe\n"
            "    if ($destHash -ne $payloadHash) {\n"
            "        throw \"Verification failed: SHA-256 mismatch for ${exeName} (dest=${destHash}, payload=${payloadHash})\"\n"
            "    }\n"
            "\n"
            "    $payloadInternal = Join-Path $payloadRoot '_internal'\n"
            "    if (Test-Path -LiteralPath $payloadInternal) {\n"
            "        $destInternal = Join-Path $appRoot '_internal'\n"
            "        if (-not (Test-Path -LiteralPath $destInternal)) {\n"
            "            throw \"Verification failed: Destination _internal directory missing (${destInternal})\"\n"
            "        }\n"
            "    }\n"
            "    Write-UpdaterLog \"Verification passed: executable hash and internal directory verified.\"\n"
            "} catch {\n"
            "    $rollbackError = $_.Exception.Message\n"
            "    Write-UpdaterLog \"ERROR: Update failed (${rollbackError}); rolling back.\"\n"
            "\n"
            "    $rollbackFailedItems = New-Object System.Collections.Generic.List[string]\n"
            "\n"
            "    $count = $journal.Count\n"
            "    for ($i = $count - 1; $i -ge 0; $i--) {\n"
            "        $entry = $journal[$i]\n"
            "        $entryName = $entry.Name\n"
            "        $hadOriginal = $entry.HadOriginal\n"
            "        $dest = Join-Path $appRoot $entryName\n"
            "        $bak = Join-Path $backupDir $entryName\n"
            "\n"
            "        try {\n"
            "            if ($hadOriginal) {\n"
            "                if (Test-Path -LiteralPath $bak) {\n"
            "                    Write-UpdaterLog \"Rolling back: Restoring ${entryName} from backup\"\n"
            "                    if (Test-Path -LiteralPath $dest) {\n"
            "                        Remove-ItemVerified -path $dest\n"
            "                    }\n"
            "                    Move-ItemAtomic -src $bak -dst $dest\n"
            "                } else {\n"
            "                    Write-UpdaterLog \"Skipping rollback for ${entryName}: Not present in backup (original untouched)\"\n"
            "                }\n"
            "            } else {\n"
            "                if (Test-Path -LiteralPath $dest) {\n"
            "                    Write-UpdaterLog \"Rolling back: Removing newly installed ${entryName}\"\n"
            "                    Remove-ItemVerified -path $dest\n"
            "                }\n"
            "            }\n"
            "        } catch {\n"
            "            $itemErr = $_.Exception.Message\n"
            "            Write-UpdaterLog \"ERROR: Rollback failed for item ${entryName}: $itemErr\"\n"
            "            $rollbackFailedItems.Add($entryName) | Out-Null\n"
            "        }\n"
            "    }\n"
            "\n"
            "    $isOccupied = ($rollbackError -match 'used by another process|being used|access is denied|存取被拒|程式正在使用|檔案已開啟')\n"
            "    $occupiedHint = if ($isOccupied) { \"`n請關閉所有程式視窗後重試。\" } else { \"\" }\n"
            "\n"
            "    if ($rollbackFailedItems.Count -gt 0) {\n"
            "        $failedList = $rollbackFailedItems -join ', '\n"
            "        Write-UpdaterLog \"ROLLBACK INCOMPLETE: Failed to restore items: ${failedList}. Preserving ${backupDir}\"\n"
            "        $popupMsg = \"EasyMusicDL 更新失敗，且部分檔案自動還原未完成。${occupiedHint}`n失敗項目：${failedList}`n備份檔案保留於：${backupDir}`n如需手動復原，請將備份目錄中的檔案複製回程式目錄。`n詳細紀錄：${logPath}\"\n"
            "        Show-UpdaterPopup -text $popupMsg -title \"應用程式更新失敗（還原未完成）\" -icon 16\n"
            "    } else {\n"
            "        Write-UpdaterLog \"Rollback completed.\"\n"
            "        $popupMsg = \"EasyMusicDL 更新失敗，已自動還原為原本版本。${occupiedHint}`n詳細紀錄：${logPath}\"\n"
            "        Show-UpdaterPopup -text $popupMsg -title \"應用程式更新失敗\" -icon 16\n"
            "    }\n"
            "    exit 1\n"
            "}\n"
            "\n"
            "if (-not $relaunch) {\n"
            "    Write-UpdaterLog \"Update succeeded (relaunch skipped); removing backup and staging directories.\"\n"
            "    try {\n"
            "        Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue\n"
            "    } catch {}\n"
            "    try {\n"
            "        Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue\n"
            "    } catch {}\n"
            "    Write-UpdaterLog \"=== Updater finished successfully ===\"\n"
            "    exit 0\n"
            "}\n"
            "\n"
            "try {\n"
            "    Start-UpdatedApp -targetExe $destExe -workDir $appRoot\n"
            "} catch {\n"
            "    $cErr = $_.Exception.Message\n"
            "    Write-UpdaterLog \"Error during relaunch phase: ${cErr}. Preserving update.\"\n"
            "    $msg = \"EasyMusicDL 已更新完成，請手動開啟 ${exeName}。`n`n程式路徑：${destExe}`n詳細紀錄：${logPath}\"\n"
            "    Show-UpdaterPopup -text $msg -title \"應用程式更新完成（請手動開啟）\" -icon 48\n"
            "    exit 2\n"
            "}\n"
        )

        return header + "\n" + body

    @staticmethod
    def _clean_env() -> dict:
        """Strip PyInstaller _PYI_* bootloader env vars so relaunched exe passes validation."""
        return {k: v for k, v in os.environ.items() if not k.startswith("_PYI_")}

    def apply_update(self, prepared: Dict) -> bool:
        """Spawn detached Windows PowerShell updater to swap portable files and relaunch."""
        if not prepared or not prepared.get("ok"):
            self.logger.warning("[UPDATE] apply_update 收到無效的 prepared 狀態")
            return False

        if platform.system() != "Windows":
            self.logger.warning("[UPDATE] 目前僅支援 Windows 免安裝版自我更新")
            return False

        if not self.is_frozen():
            self.logger.warning("[UPDATE] 非免安裝執行檔（原始碼模式），略過檔案替換")
            return False

        if not self._apply_lock.acquire(blocking=False):
            self.logger.warning("[UPDATE] 更新程序已在進行中或已完成，略過重複呼叫")
            return False

        success = False
        proc: Optional[subprocess.Popen] = None
        try:
            try:
                staging_dir = Path(prepared["staging_dir"])
                payload_root = Path(prepared["payload_root"])
                app_root = self.get_app_root()
                exe_name = prepared.get("exe_name") or Path(sys.executable).name
                asset_type = prepared.get("asset_type") or "portable_zip"
                parent_pid = os.getpid()
                log_path = get_logs_dir() / "updater.log"

                ps_script = self.build_windows_updater_script(
                    staging_dir=staging_dir,
                    payload_root=payload_root,
                    app_root=app_root,
                    exe_name=exe_name,
                    asset_type=asset_type,
                    parent_pid=parent_pid,
                    log_path=log_path,
                    relaunch=True,
                )
                ps_file = staging_dir / "updater.ps1"
                ps_file.write_text(ps_script, encoding="utf-8-sig")

                started_marker = staging_dir / "updater.started"
                if started_marker.exists():
                    try:
                        started_marker.unlink()
                    except OSError:
                        pass

                powershell_exe = _get_powershell_path()
                creation_flags = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                    | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                )

                proc = subprocess.Popen(
                    [
                        powershell_exe,
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-WindowStyle",
                        "Hidden",
                        "-File",
                        str(ps_file),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    env=self._clean_env(),
                    creationflags=creation_flags,
                )

                timeout = getattr(self, "HANDSHAKE_TIMEOUT_S", 10.0)
                start_time = time.perf_counter()
                handshake_ok = False

                while time.perf_counter() - start_time < timeout:
                    if started_marker.exists():
                        handshake_ok = True
                        break
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)

                if not handshake_ok and started_marker.exists():
                    handshake_ok = True

                if handshake_ok:
                    self.logger.info(
                        "[UPDATE] 已啟動更新背景行程 (updater_pid=%s, parent_pid=%s, script=%s)",
                        proc.pid,
                        parent_pid,
                        ps_file,
                    )
                    flush_logs()
                    success = True
                    return True
                else:
                    self.logger.error(
                        "[UPDATE] 更新背景行程握手失敗 (pid=%s, poll=%s, timeout=%ss)",
                        proc.pid,
                        proc.poll(),
                        timeout,
                    )
                    process_tracker.kill_process_tree(proc)
                    return False
            except Exception as e:
                self.logger.error("[UPDATE] apply_update 發生例外: %s", e, exc_info=True)
                if proc is not None:
                    try:
                        process_tracker.kill_process_tree(proc)
                    except Exception:
                        pass
                return False
        finally:
            if not success:
                self._apply_lock.release()
