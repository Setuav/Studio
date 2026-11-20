"""Plugin icon registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from setuav_studio.ui.style.icons import get_icon, register_plugin_icons, unregister_plugin_icons
from tests._common import get_qapp

_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24"/></svg>'


def test_every_svg_registers_under_its_file_name_until_unregistered(tmp_path: Path) -> None:
    get_qapp()
    (tmp_path / "test_gear.svg").write_text(_SVG)

    register_plugin_icons("org.test.icons", tmp_path)
    assert not get_icon("test_gear").isNull()

    unregister_plugin_icons("org.test.icons")
    with pytest.raises(ValueError, match="test_gear"):
        get_icon("test_gear")


def test_a_folder_without_svg_icons_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"org\.test\.empty"):
        register_plugin_icons("org.test.empty", tmp_path)


def test_core_icons_are_the_svgs_of_the_icon_folder() -> None:
    get_qapp()
    icon_dir = Path(__file__).resolve().parents[2] / "src" / "setuav_studio" / "assets" / "icons"
    names = [path.stem for path in icon_dir.glob("*.svg")]
    assert "vehicle" in names
    for name in names:
        assert not get_icon(name).pixmap(16, 16).isNull(), name
