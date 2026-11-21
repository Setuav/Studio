"""Persistent settings pages for the geometry plugin."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QCheckBox, QFormLayout, QWidget

_EDITOR_AUTO_FIT_KEY = "airframe_design/editor/auto_fit_sections"
_EDITOR_GRID_KEY = "airframe_design/editor/show_section_grid"


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def create_editor_settings_page() -> QWidget:
    settings = QSettings()
    page = QWidget()
    form = QFormLayout(page)

    auto_fit = QCheckBox("Fit section preview when opening or changing section")
    auto_fit.setObjectName("autoFitSections")
    auto_fit.setChecked(_as_bool(settings.value(_EDITOR_AUTO_FIT_KEY, True), True))
    form.addRow(auto_fit)

    show_grid = QCheckBox("Show section preview grid")
    show_grid.setObjectName("showSectionGrid")
    show_grid.setChecked(_as_bool(settings.value(_EDITOR_GRID_KEY, True), True))
    form.addRow(show_grid)
    return page


def apply_editor_settings(page: QWidget) -> None:
    settings = QSettings()
    auto_fit = page.findChild(QCheckBox, "autoFitSections")
    show_grid = page.findChild(QCheckBox, "showSectionGrid")
    if auto_fit is not None:
        settings.setValue(_EDITOR_AUTO_FIT_KEY, auto_fit.isChecked())
    if show_grid is not None:
        settings.setValue(_EDITOR_GRID_KEY, show_grid.isChecked())


def editor_setting(key: str, fallback: object) -> object:
    return QSettings().value(key, fallback)


__all__ = [
    "_EDITOR_AUTO_FIT_KEY",
    "_EDITOR_GRID_KEY",
    "apply_editor_settings",
    "create_editor_settings_page",
    "editor_setting",
]
