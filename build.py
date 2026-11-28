#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Script for 音樂下載工具 (EasyMusicDL) - Portable --onedir Windows package.
Supports --zip to produce EasyMusicDL-v<version>-win64-portable.zip and .sha256.
"""

import argparse
import hashlib
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple
import zipfile

APP_NAME = "EasyMusicDL"
BUILD_DIR = Path("build")
DIST_DIR = Path("dist")
ASSETS_DIR = Path("assets")
EXCLUDED_BIN_FILES = frozenset({"yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"})


def read_app_version() -> str:
    """Read single-source version string from src/ytdlp_gui/__init__.py."""
    init_file = Path("src") / "ytdlp_gui" / "__init__.py"
    if init_file.exists():
        content = init_file.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if m:
            return m.group(1).strip()
    return "0.0.0"


APP_VERSION = read_app_version()


def clean_build():
    """Clean previous build artifacts."""
    print("Cleaning previous build artifacts...")
    for dir_path in [BUILD_DIR, DIST_DIR]:
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"   Removed {dir_path}")
    for spec_file in Path(".").glob("*.spec"):
        spec_file.unlink()
        print(f"   Removed {spec_file}")


def check_dependencies() -> bool:
    """Check if required dependencies are installed."""
    print("Checking dependencies...")
    required_packages = [
        ("pyinstaller", "PyInstaller"),
        ("customtkinter", "customtkinter"),
        ("pillow", "PIL"),
        ("requests", "requests"),
        ("packaging", "packaging"),
    ]
    missing = []
    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
            print(f"   [OK] {package_name}")
        except ImportError:
            missing.append(package_name)
            print(f"   [MISSING] {package_name}")

    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Install them with: pip install -r requirements.txt pyinstaller")
        return False
    return True


def create_pyinstaller_spec() -> Path:
    """Create PyInstaller --onedir spec file."""
    print("Creating PyInstaller --onedir spec file...")

    hidden_imports = [
        "customtkinter",
        "darkdetect",
        "PIL._tkinter_finder",
        "tkinter",
        "tkinter.ttk",
        "sqlite3",
        "json",
        "threading",
        "queue",
        "logging.handlers",
        "packaging",
        "packaging.version",
        "requests",
        "ytdlp_gui",
        "ytdlp_gui.main",
        "ytdlp_gui.core.binary_manager",
        "ytdlp_gui.core.cookie_manager",
        "ytdlp_gui.core.download_manager",
        "ytdlp_gui.core.history_manager",
        "ytdlp_gui.core.settings_manager",
        "ytdlp_gui.core.update_checker",
        "ytdlp_gui.core.ytdlp_wrapper",
        "ytdlp_gui.gui.theme",
        "ytdlp_gui.gui.icons",
        "ytdlp_gui.gui.main_window",
        "ytdlp_gui.gui.components.music_search_view",
        "ytdlp_gui.gui.components.my_music_view",
        "ytdlp_gui.gui.components.help_dialog",
        "ytdlp_gui.utils.error_translations",
        "ytdlp_gui.utils.logger",
        "ytdlp_gui.utils.notifications",
        "ytdlp_gui.utils.paths",
    ]

    datas = []
    if ASSETS_DIR.exists():
        datas.append((str(ASSETS_DIR), "assets"))
    pkg_assets = Path("src") / "ytdlp_gui" / "assets"
    if pkg_assets.exists():
        datas.append((str(pkg_assets), "ytdlp_gui/assets"))

    icon_file = None
    if ASSETS_DIR.exists():
        for ext in (".ico", ".png"):
            candidate = ASSETS_DIR / f"icon{ext}"
            if candidate.exists():
                icon_file = str(candidate)
                break

    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas={datas!r},
    hiddenimports={hidden_imports!r},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_file!r},
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='{APP_NAME}',
)
"""
    spec_file = Path(f"{APP_NAME}.spec")
    spec_file.write_text(spec_content, encoding="utf-8")
    print(f"   Created {spec_file}")
    return spec_file


def build_executable(spec_file: Path) -> bool:
    """Build portable directory using PyInstaller."""
    print("Building portable directory...")
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_file)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("Build completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Build failed with exit code {e.returncode}")
        print(e.stdout[-1500:] if e.stdout else "")
        print(e.stderr[-1500:] if e.stderr else "")
        return False


def write_portable_helpers(package_dir: Path) -> None:
    """Generate desktop shortcut creator batch script and Traditional Chinese guide."""
    package_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("bin", "data", "logs"):
        (package_dir / sub).mkdir(exist_ok=True)

    ico_src = ASSETS_DIR / "icon.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, package_dir / "icon.ico")

    bat_content = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "setlocal\r\n"
        "set \"APP_DIR=%~dp0\"\r\n"
        "set \"APP_DIR=%APP_DIR:~0,-1%\"\r\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -Command "
        "\"$ws = New-Object -ComObject WScript.Shell; "
        "$desktop = [Environment]::GetFolderPath('Desktop'); "
        "$lnk = $ws.CreateShortcut((Join-Path $desktop '音樂下載工具.lnk')); "
        "$lnk.TargetPath = '%APP_DIR%\\EasyMusicDL.exe'; "
        "$lnk.WorkingDirectory = '%APP_DIR%'; "
        "if (Test-Path '%APP_DIR%\\icon.ico') { $lnk.IconLocation = '%APP_DIR%\\icon.ico' }; "
        "$lnk.Save()\"\r\n"
        "echo.\r\n"
        "echo 已在桌面建立「音樂下載工具」捷徑。\r\n"
        "pause\r\n"
    )
    (package_dir / "建立桌面捷徑.bat").write_text(bat_content, encoding="utf-8")

    readme_txt = (
        "====================================================\n"
        "  音樂下載工具（純 MP3 綠色免安裝版）使用說明\n"
        "====================================================\n\n"
        "1. 第一次使用\n"
        "   - 整個資料夾複製到電腦任意位置（或隨身碟）即可使用，無需安裝。\n"
        "   - 可雙擊「建立桌面捷徑.bat」，在桌面建立「音樂下載工具」捷徑。\n"
        "   - 開啟「EasyMusicDL.exe」後，程式會自動執行三階段啟動檢查：\n"
        "       步驟 1/3：檢查環境與引擎更新\n"
        "       步驟 2/3：下載或更新必要元件（yt-dlp / FFmpeg / Deno）\n"
        "       步驟 3/3：二次檢查與驗證環境\n\n"
        "2. 下載歌曲\n"
        "   - 輸入歌名或貼上 YouTube 網址，按「搜尋」。\n"
        "   - 點擊歌曲右側「下載 MP3」，完成後自動存至系統「下載 (Downloads)」資料夾。\n\n"
        "3. 應用程式更新與設定修復\n"
        "   - 程式會自動檢查免安裝版更新，也可點右上角「設定與修復 → 檢查應用程式更新」\n"
        "     直接下載並更新；更新過程會保留 bin / data / logs 與已下載音樂。\n"
        "   - 若遇到無法下載，可於「設定與修復」執行「檢查並更新下載引擎」，\n"
        "     或點「複製診斷紀錄」協助排查。\n"
    )
    (package_dir / "使用說明.txt").write_text(readme_txt, encoding="utf-8")


def create_portable_zip(package_dir: Path, version: str, out_dir: Path = DIST_DIR) -> Tuple[Path, Path]:
    """Package portable --onedir folder into a release zip and matching .sha256 file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"{APP_NAME}-v{version}-win64-portable.zip"
    zip_path = out_dir / zip_name
    sha_path = out_dir / f"{zip_name}.sha256"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for empty_sub in ("bin", "data", "logs"):
            info = zipfile.ZipInfo(f"{APP_NAME}/{empty_sub}/")
            zf.writestr(info, b"")

        for item in sorted(package_dir.rglob("*")):
            rel = item.relative_to(package_dir)
            top = rel.parts[0]
            if top in ("data", "logs", ".update_backup") or item.name == "cookies.txt":
                continue
            if top == "bin" and item.name.lower() in EXCLUDED_BIN_FILES:
                continue
            if item.is_dir():
                if top == "bin":
                    continue
                continue
            zf.write(item, arcname=str(Path(APP_NAME) / rel))

    digest = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    sha_hex = digest.hexdigest().lower()
    sha_path.write_text(f"{sha_hex}  {zip_name}\n", encoding="utf-8")
    return zip_path, sha_path


def main():
    parser = argparse.ArgumentParser(description="Build EasyMusicDL portable Windows package")
    parser.add_argument("--zip", action="store_true", help="Also create portable .zip and .sha256")
    args = parser.parse_args()

    print(f"Building {APP_NAME} v{APP_VERSION}")
    print("=" * 50)
    print(f"Platform: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Python:   {sys.version.split()[0]}")

    if not check_dependencies():
        sys.exit(1)

    clean_build()
    BUILD_DIR.mkdir(exist_ok=True)
    DIST_DIR.mkdir(exist_ok=True)

    spec_file = create_pyinstaller_spec()
    if not build_executable(spec_file):
        sys.exit(1)

    package_dir = DIST_DIR / APP_NAME
    write_portable_helpers(package_dir)

    print("\nBuild completed successfully!")
    print(f"Portable folder: {package_dir.resolve()}")
    print(f"Executable:      {(package_dir / (APP_NAME + '.exe')).resolve()}")

    if args.zip:
        zip_path, sha_path = create_portable_zip(package_dir, APP_VERSION, DIST_DIR)
        print(f"Portable ZIP:    {zip_path.resolve()}")
        print(f"SHA-256 file:    {sha_path.resolve()}")


if __name__ == "__main__":
    main()
