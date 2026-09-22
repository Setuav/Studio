"""Backward-compatibility module re-exporting setuav_studio.ui.style.theme."""

from __future__ import annotations

from setuav_studio.ui.style.theme import (
    ACCENT_COLOR,
    DEFAULT_FONT_SIZE,
    FONT_FAMILY,
    STATUS_COLORS,
    ComboBoxWheelFilter,
    accent_color,
    apply_theme,
    chart_color,
    current_theme_mode,
    semantic_color,
    status_color,
    tokens,
)

__all__ = [
    "ACCENT_COLOR",
    "DEFAULT_FONT_SIZE",
    "FONT_FAMILY",
    "STATUS_COLORS",
    "ComboBoxWheelFilter",
    "accent_color",
    "apply_theme",
    "chart_color",
    "current_theme_mode",
    "semantic_color",
    "status_color",
    "tokens",
]
