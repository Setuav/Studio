"""Backward-compatibility module re-exporting setuav_studio.ui.style.icons."""

from __future__ import annotations

from setuav_studio.ui.style.icons import (
    application_icon,
    create_color_badge_icon,
    get_icon,
    refresh_label_icon,
    register_icon,
    register_plugin_icons,
    set_label_icon,
)

__all__ = [
    "application_icon",
    "create_color_badge_icon",
    "get_icon",
    "refresh_label_icon",
    "register_icon",
    "register_plugin_icons",
    "set_label_icon",
]
