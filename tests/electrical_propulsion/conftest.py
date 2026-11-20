"""Fixtures for the electrical propulsion plugin tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import plugins.electrical_propulsion
from setuav_studio.ui.style.icons import register_plugin_icons


@pytest.fixture(autouse=True)
def propulsion_icons() -> None:
    """The propulsion editors name the icons the plugin registers when it activates."""
    register_plugin_icons(
        "org.setuav.studio.electrical_propulsion",
        Path(plugins.electrical_propulsion.__file__).parent / "assets" / "icons",
    )
