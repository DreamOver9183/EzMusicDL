# -*- coding: utf-8 -*-
"""
Minimal network marker test verifying test boundary and fixtures:
1. When marked with @pytest.mark.network, offline guard is not applied.
2. Wrapper functions remain untouched.
3. app_root path isolation remains active.
4. real_bin_dir resolves correctly outside app_root.
"""

from pathlib import Path
import pytest

from ytdlp_gui.core import ytdlp_wrapper
from ytdlp_gui.utils import paths


@pytest.mark.network
def test_network_marker_boundary(app_root: Path, real_bin_dir: Path, original_wrapper_functions):
    """Verify that network-marked test retains real wrapper functions and isolated app root."""
    assert ytdlp_wrapper.extract_info is original_wrapper_functions.extract_info
    assert ytdlp_wrapper.download is original_wrapper_functions.download
    assert ytdlp_wrapper.search_youtube is original_wrapper_functions.search_youtube

    assert paths.get_app_root() == app_root

    assert real_bin_dir.name == "bin"
    try:
        is_sub = real_bin_dir.resolve().is_relative_to(app_root.resolve())
    except ValueError:
        is_sub = False
    assert not is_sub
