"""Plugin icon registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from setuav_studio.ui.style.icons import get_icon, register_plugin_icons, unregister_plugin_icons
from tests._common import get_qapp

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def test_registered_icons_resolve_until_unregistered(tmp_path: Path) -> None:
    get_qapp()
    (tmp_path / "gear.png").write_bytes(_PNG)
    (tmp_path / "manifest.toml").write_text('[icons]\ntest_gear = "gear.png"\n')

    register_plugin_icons("org.test.icons", tmp_path)
    assert not get_icon("test_gear").isNull()

    unregister_plugin_icons("org.test.icons")
    with pytest.raises(ValueError, match="test_gear"):
        get_icon("test_gear")


def test_a_manifest_naming_a_missing_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text('[icons]\ntest_missing = "missing.png"\n')
    with pytest.raises(FileNotFoundError, match="test_missing"):
        register_plugin_icons("org.test.missing", tmp_path)
