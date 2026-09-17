"""Styling, theme management, and icon utilities for Setuav Studio UI."""

from __future__ import annotations

from setuav_studio.ui.style import icons, theme
from setuav_studio.ui.style.icons import (
    application_icon,
    create_color_badge_icon,
    get_icon,
    refresh_label_icon,
    set_label_icon,
)
from setuav_studio.ui.style.theme import (
    ACCENT_COLOR,
    DEFAULT_FONT_SIZE,
    FONT_FAMILY,
    STATUS_COLORS,
    accent_color,
    apply_theme,
    chart_color,
    current_theme_mode,
    is_light_theme,
    semantic_color,
    status_color,
    tokens,
)

__all__ = [
    "ACCENT_COLOR",
    "DEFAULT_FONT_SIZE",
    "FONT_FAMILY",
    "STATUS_COLORS",
    "accent_color",
    "application_icon",
    "apply_theme",
    "chart_color",
    "create_color_badge_icon",
    "current_theme_mode",
    "get_icon",
    "icons",
    "is_light_theme",
    "refresh_label_icon",
    "semantic_color",
    "set_label_icon",
    "status_color",
    "theme",
    "tokens",
]
