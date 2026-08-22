"""Native Qt button variants backed by the active application palette."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractButton, QApplication

from setuav_studio.ui.icons import get_icon


_ROLE_PROPERTY = "setuavButtonRole"
_VARIANT_PROPERTY = "setuavButtonVariant"
_ICON_PROPERTY = "setuavButtonIconSource"


def set_button_role(
    button: QAbstractButton,
    role: str,
    icon_source: str | None = None,
    *,
    variant: str = "filled",
) -> None:
    """Assign a semantic, theme-aware role to a native Qt button.

    ``filled`` colors the native button surface and its contents. ``icon``
    keeps the native neutral surface and colors only the icon.
    """
    button.setProperty(_ROLE_PROPERTY, role)
    button.setProperty(_VARIANT_PROPERTY, variant)
    if icon_source:
        button.setProperty(_ICON_PROPERTY, icon_source)
    refresh_button_role(button)


def refresh_button_role(button: QAbstractButton) -> None:
    """Reapply a registered button role after an application theme change."""
    role = button.property(_ROLE_PROPERTY)
    if not isinstance(role, str) or not role:
        return

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return

    from setuav_studio.ui.theme import semantic_color

    variant = button.property(_VARIANT_PROPERTY)
    variant = variant if variant in {"filled", "icon"} else "filled"
    role_color = QColor(semantic_color(role))
    app_palette = app.palette()
    disabled_text = app_palette.color(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
    )

    if variant == "filled":
        foreground = _contrasting_foreground(role_color)
        palette = QPalette(app_palette)
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            palette.setColor(group, QPalette.ColorRole.Button, role_color)
            palette.setColor(group, QPalette.ColorRole.ButtonText, foreground)
            palette.setColor(group, QPalette.ColorRole.Highlight, role_color)
            palette.setColor(group, QPalette.ColorRole.HighlightedText, foreground)
            palette.setColor(group, QPalette.ColorRole.Accent, role_color)
        button.setPalette(palette)
        icon_color = foreground
    else:
        # Do not leave a stale per-widget palette behind if a button changes
        # from filled to icon-only at runtime.
        button.setPalette(app_palette)
        icon_color = role_color

    icon_source = button.property(_ICON_PROPERTY)
    if isinstance(icon_source, str) and icon_source:
        button.setIcon(
            get_icon(
                icon_source,
                color=icon_color.name(),
                color_disabled=disabled_text.name(),
            )
        )

    button.update()


def refresh_all_button_roles(app: QApplication) -> None:
    """Refresh all semantic buttons owned by an application."""
    for widget in app.allWidgets():
        if isinstance(widget, QAbstractButton):
            refresh_button_role(widget)


def _contrasting_foreground(background: QColor) -> QColor:
    """Choose a readable near-black or near-white foreground."""
    def linear(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    luminance = (
        0.2126 * linear(background.redF())
        + 0.7152 * linear(background.greenF())
        + 0.0722 * linear(background.blueF())
    )
    return QColor("#171717") if luminance > 0.42 else QColor("#ffffff")
