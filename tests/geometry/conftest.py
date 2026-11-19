"""Fixtures for the geometry plugin tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import plugins.geometry
from setuav_studio.ui.style.icons import register_plugin_icons


@pytest.fixture(autouse=True)
def geometry_icons() -> None:
    """The geometry editors name the icons the plugin registers when it activates."""
    register_plugin_icons(
        "org.setuav.studio.airframe_design",
        Path(plugins.geometry.__file__).parent / "assets" / "icons",
    )
