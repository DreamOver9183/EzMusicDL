# -*- coding: utf-8 -*-
"""
Tests for UpdateChecker:
1. Version parsing (_parse_version).
2. Asset selection and exclusion (_find_asset).
3. Checksum asset discovery and parsing (_find_checksum_asset, _parse_expected_sha256).
4. Zip extraction security against directory traversal (_safe_extract_zip).
5. Version checking across various HTTP response states (check).
6. Download verification and cleanup on SHA-256 failure (download_update).
7. Application update precondition validation (apply_update).
"""

import json
from pathlib import Path
import tempfile
import zipfile
import pytest
from packaging.version import Version

from ytdlp_gui import __version__
from ytdlp_gui.core.update_checker import UpdateChecker


class MockHttpResponse:
    """Mock HTTP response for update checking and downloading."""

    def __init__(self, status_code=200, json_data=None, text="", headers=None, content_chunks=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {}
        self._content_chunks = content_chunks or []

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, chunk_size=65536):
        for chunk in self._content_chunks:
            yield chunk


def test_parse_version():
    """Verify version string parsing with prefix v, whitespace, invalid formats, and empty strings."""
    # Prefix v / V
    v1 = UpdateChecker._parse_version("v1.2.3")
    assert v1 == Version("1.2.3")
    v2 = UpdateChecker._parse_version("V2026.11.21")
    assert v2 == Version("2026.11.21")

    # Empty string or None
    assert UpdateChecker._parse_version("") is None
    assert UpdateChecker._parse_version(None) is None
    assert UpdateChecker._parse_version("   ") is None

    # Invalid version strings
    assert UpdateChecker._parse_version("invalid_version") is None
    assert UpdateChecker._parse_version("not.a.version") is None
    assert UpdateChecker._parse_version("v..") is None


def test_find_asset():
    """Verify asset ranking: zip preferred over exe, source zip skipped, external tools excluded."""
    # 1. Zip preferred over standalone exe
    release_both = {
        "assets": [
            {
                "name": "EasyMusicDL-2026.11.21-windows.zip",
                "browser_download_url": "https://example.com/portable.zip",
            },
            {
                "name": "EasyMusicDL.exe",
                "browser_download_url": "https://example.com/standalone.exe",
            },
        ]
    }
    asset, asset_type = UpdateChecker._find_asset(release_both)
    assert asset_type == "portable_zip"
    assert asset["name"] == "EasyMusicDL-2026.11.21-windows.zip"

    # 2. Source code zip skipped (negative score)
    release_source = {
        "assets": [
            {
                "name": "source-code.zip",
                "browser_download_url": "https://example.com/source.zip",
            },
        ]
    }
    asset, asset_type = UpdateChecker._find_asset(release_source)
    assert asset is None
    assert asset_type is None

    # 3. Third-party engine binaries and installer executables skipped
    release_tools = {
        "assets": [
            {"name": "yt-dlp.exe", "browser_download_url": "https://example.com/yt-dlp.exe"},
            {"name": "ffmpeg.exe", "browser_download_url": "https://example.com/ffmpeg.exe"},
            {"name": "deno.exe", "browser_download_url": "https://example.com/deno.exe"},
            {"name": "setup.exe", "browser_download_url": "https://example.com/setup.exe"},
            {"name": "installer.exe", "browser_download_url": "https://example.com/installer.exe"},
        ]
    }
    asset, asset_type = UpdateChecker._find_asset(release_tools)
    assert asset is None
    assert asset_type is None

    # 4. No available assets
    assert UpdateChecker._find_asset({}) == (None, None)
    assert UpdateChecker._find_asset({"assets": []}) == (None, None)
    assert UpdateChecker._find_asset({
        "assets": [
            {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
            {"name": "readme.txt", "browser_download_url": "https://example.com/readme.txt"},
        ]
    }) == (None, None)


def test_find_checksum_asset_and_parse_sha256():
    """Verify checksum asset selection and parsing."""
    asset_name = "EasyMusicDL-v9999.1.1-windows.zip"

    # 1. Matching .sha256 sidecar preferred over checksums.txt
    release_sidecar = {
        "assets": [
            {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
            {"name": f"{asset_name}.sha256", "browser_download_url": "https://example.com/sidecar.sha256"},
        ]
    }
    url = UpdateChecker._find_checksum_asset(release_sidecar, asset_name)
    assert url == "https://example.com/sidecar.sha256"

    # 2. Fallback to checksums.txt when sidecar is not present
    release_fallback = {
        "assets": [
            {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
            {"name": "other-archive.zip.sha256", "browser_download_url": "https://example.com/other.sha256"},
        ]
    }
    url = UpdateChecker._find_checksum_asset(release_fallback, asset_name)
    assert url == "https://example.com/checksums.txt"

    # 3. No checksum asset found
    release_none = {
        "assets": [
            {"name": "other-file.zip", "browser_download_url": "https://example.com/file.zip"}
        ]
    }
    assert UpdateChecker._find_checksum_asset(release_none, asset_name) is None

    # 4. _parse_expected_sha256 extraction
    hash_val = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    other_hash = "1111111111111111111111111111111111111111111111111111111111111111"

    # Matching line with target filename
    text = f"{other_hash}  other.zip\n{hash_val}  {asset_name}\n"
    assert UpdateChecker._parse_expected_sha256(text, asset_name) == hash_val

    # Single hash in sidecar file
    assert UpdateChecker._parse_expected_sha256(f"{hash_val}\n", asset_name) == hash_val

    # Empty or invalid string
    assert UpdateChecker._parse_expected_sha256("", asset_name) is None
    assert UpdateChecker._parse_expected_sha256("no valid hash present", asset_name) is None


def test_safe_extract_zip(tmp_path: Path):
    """Verify that _safe_extract_zip rejects zip files containing path traversal entries."""
    bad_zip = tmp_path / "traversal.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../evil.txt", "harmful content")

    dest_dir = tmp_path / "extract_dest"
    dest_dir.mkdir()

    with pytest.raises(RuntimeError, match="不安全路徑"):
        UpdateChecker._safe_extract_zip(bad_zip, dest_dir)

    assert not (tmp_path / "evil.txt").exists()

    # Valid zip extracts cleanly
    good_zip = tmp_path / "normal.zip"
    with zipfile.ZipFile(good_zip, "w") as zf:
        zf.writestr("sub/hello.txt", "safe content")

    good_dest = tmp_path / "normal_dest"
    good_dest.mkdir()
    UpdateChecker._safe_extract_zip(good_zip, good_dest)
    assert (good_dest / "sub" / "hello.txt").read_text(encoding="utf-8") == "safe content"


def test_check_new_version_with_checksum(monkeypatch: pytest.MonkeyPatch):
    """Verify check() detects a newer version and resolves download and checksum assets."""
    release_data = {
        "tag_name": "v9999.1.1",
        "body": "Update 9999.1.1 release notes",
        "html_url": "https://github.com/DreamOver9183/EzMusicDL/releases/tag/v9999.1.1",
        "assets": [
            {
                "name": "EasyMusicDL-v9999.1.1-windows.zip",
                "browser_download_url": "https://example.com/dl.zip",
                "size": 50000000,
            },
            {
                "name": "EasyMusicDL-v9999.1.1-windows.zip.sha256",
                "browser_download_url": "https://example.com/dl.zip.sha256",
            },
        ],
    }
    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.requests.get",
        lambda url, *args, **kwargs: MockHttpResponse(200, json_data=release_data, headers={"ETag": '"etag99"'}),
    )

    checker = UpdateChecker()
    res = checker.check()
    assert res["available"] is True
    assert res["status"] == "update_available"
    assert res["latest_version"] == "9999.1.1"
    assert res["asset_name"] == "EasyMusicDL-v9999.1.1-windows.zip"
    assert res["checksum_url"] == "https://example.com/dl.zip.sha256"


def test_check_up_to_date(monkeypatch: pytest.MonkeyPatch):
    """Verify check() reports up_to_date when remote tag matches current version."""
    release_data = {
        "tag_name": f"v{__version__}",
        "body": "Current version",
        "html_url": "https://example.com/current",
        "assets": [],
    }
    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.requests.get",
        lambda url, *args, **kwargs: MockHttpResponse(200, json_data=release_data),
    )

    checker = UpdateChecker()
    res = checker.check()
    assert res["available"] is False
    assert res["status"] == "up_to_date"


def test_check_new_version_no_asset(monkeypatch: pytest.MonkeyPatch):
    """Verify check() reports no_asset when remote version is newer but lacks usable assets."""
    release_data = {
        "tag_name": "v9999.1.1",
        "body": "No asset release",
        "html_url": "https://example.com/no-asset",
        "assets": [],
    }
    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.requests.get",
        lambda url, *args, **kwargs: MockHttpResponse(200, json_data=release_data),
    )

    checker = UpdateChecker()
    res = checker.check()
    assert res["available"] is False
    assert res["status"] == "no_asset"


def test_check_404(monkeypatch: pytest.MonkeyPatch):
    """Verify check() handles 404 response (no release published)."""
    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.requests.get",
        lambda url, *args, **kwargs: MockHttpResponse(404),
    )

    checker = UpdateChecker()
    res = checker.check()
    assert res["available"] is False
    assert res["status"] == "no_release"


def test_check_403_no_cache(monkeypatch: pytest.MonkeyPatch):
    """Verify check() handles 403 rate limit without cached info."""
    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.requests.get",
        lambda url, *args, **kwargs: MockHttpResponse(403),
    )

    checker = UpdateChecker()
    res = checker.check()
    assert res["available"] is False
    assert res["status"] == "error"


def test_check_304_with_cache(monkeypatch: pytest.MonkeyPatch):
    """Verify check() returns cached data when GitHub returns HTTP 304 Not Modified."""
    class MockSettingsManager:
        def __init__(self, cached_dict):
            self._storage = {"latest_update_info": json.dumps(cached_dict)}

        def get(self, key, default=None):
            return self._storage.get(key, default)

        def set(self, key, value):
            self._storage[key] = value

        def save_settings(self):
            pass

    checker = UpdateChecker(repo="DreamOver9183/EzMusicDL")
    cached_info = {
        "current_version": __version__,
        "repo": checker.repo,
        "etag": '"cached-etag-12345"',
        "status": "up_to_date",
        "available": False,
        "latest_version": __version__,
    }
    checker._settings = MockSettingsManager(cached_info)

    monkeypatch.setattr(
        "ytdlp_gui.core.update_checker.requests.get",
        lambda url, *args, **kwargs: MockHttpResponse(304),
    )

    res = checker.check()
    assert res.get("from_cache") is True
    assert res["current_version"] == __version__


def test_check_connection_error(monkeypatch: pytest.MonkeyPatch):
    """Verify check() handles requests.ConnectionError gracefully."""
    def raise_conn_error(*args, **kwargs):
        import requests
        raise requests.ConnectionError("Network resolution failed")

    monkeypatch.setattr("ytdlp_gui.core.update_checker.requests.get", raise_conn_error)

    checker = UpdateChecker()
    res = checker.check()
    assert res["available"] is False
    assert res["status"] == "error"
    assert "無法連線" in res["message"]


def test_download_update_sha256_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify that download_update() fails and cleans up the staging directory on SHA-256 mismatch."""
    created_staging_dirs = []
    real_mkdtemp = tempfile.mkdtemp

    def tracked_mkdtemp(prefix=""):
        d = real_mkdtemp(prefix=prefix, dir=str(tmp_path))
        created_staging_dirs.append(Path(d))
        return d

    monkeypatch.setattr(tempfile, "mkdtemp", tracked_mkdtemp)

    def mock_get(url, *args, **kwargs):
        if "checksum" in url or url.endswith(".sha256"):
            # Provide an invalid expected hash
            return MockHttpResponse(
                200,
                text="0000000000000000000000000000000000000000000000000000000000000000  EasyMusicDL-update.zip\n",
            )
        # Downloaded payload chunk
        return MockHttpResponse(
            200,
            headers={"content-length": "25"},
            content_chunks=[b"fake binary zip contents"],
        )

    monkeypatch.setattr("ytdlp_gui.core.update_checker.requests.get", mock_get)

    checker = UpdateChecker()
    update_info = {
        "download_url": "https://example.com/download.zip",
        "asset_type": "portable_zip",
        "asset_name": "EasyMusicDL-update.zip",
        "checksum_url": "https://example.com/checksum.sha256",
        "latest_version": "9999.1.1",
    }

    result = checker.download_update(update_info)

    assert result["ok"] is False
    assert "SHA-256 驗證失敗" in result["error"]
    assert len(created_staging_dirs) == 1
    staging_dir = created_staging_dirs[0]
    assert not staging_dir.exists()


def test_apply_update(tmp_path: Path):
    """Verify that apply_update() returns False for invalid prepared state or non-frozen source mode."""
    checker = UpdateChecker()

    # 1. Invalid prepared states
    assert checker.apply_update({}) is False
    assert checker.apply_update(None) is False
    assert checker.apply_update({"ok": False}) is False

    # 2. Valid prepared dictionary but in non-frozen (source) mode
    valid_prepared = {
        "ok": True,
        "staging_dir": str(tmp_path / "staging"),
        "payload_root": str(tmp_path / "payload"),
        "exe_name": "EasyMusicDL.exe",
        "asset_type": "portable_zip",
        "version": "9999.1.1",
    }
    assert checker.is_frozen() is False
    assert checker.apply_update(valid_prepared) is False
