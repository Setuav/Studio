"""Persistent settings pages for the geometry plugin."""

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QWidget

from .viewport.palettes import DEFAULT_PALETTE, palette_names, set_active_palette


_VIEWER_PROJECTION_KEY = "geometry/viewer/default_projection"
_VIEWER_PALETTE_KEY = "geometry/viewer/default_palette"
_VIEWER_GRID_KEY = "geometry/viewer/show_grid"
_VIEWER_SOLID_KEY = "geometry/viewer/show_solid"
_VIEWER_WIRE_KEY = "geometry/viewer/show_wireframe"

_EDITOR_AUTO_FIT_KEY = "geometry/editor/auto_fit_sections"
_EDITOR_GRID_KEY = "geometry/editor/show_section_grid"
_EDITOR_LOFT_METHOD_KEY = "geometry/editor/default_loft_method"


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _combo_value(combo: QComboBox, key: str, fallback: str) -> None:
    value = str(QSettings().value(key, fallback)).lower()
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)


def create_viewer_settings_page() -> QWidget:
    settings = QSettings()
    page = QWidget()
    form = QFormLayout(page)

    projection = QComboBox()
    projection.setObjectName("defaultProjection")
    projection.addItem("Orthographic", "orthographic")
    projection.addItem("Perspective", "perspective")
    _combo_value(projection, _VIEWER_PROJECTION_KEY, "orthographic")
    form.addRow("Default projection:", projection)

    palette = QComboBox()
    palette.setObjectName("defaultPalette")
    for name in palette_names():
        palette.addItem(name.capitalize(), name)
    _combo_value(palette, _VIEWER_PALETTE_KEY, DEFAULT_PALETTE)
    form.addRow("Default palette:", palette)

    show_grid = QCheckBox("Show reference grid")
    show_grid.setObjectName("showGrid")
    show_grid.setChecked(_as_bool(settings.value(_VIEWER_GRID_KEY, True), True))
    form.addRow(show_grid)

    show_solid = QCheckBox("Show solid surfaces")
    show_solid.setObjectName("showSolid")
    show_solid.setChecked(_as_bool(settings.value(_VIEWER_SOLID_KEY, True), True))
    form.addRow(show_solid)

    show_wire = QCheckBox("Show wireframe")
    show_wire.setObjectName("showWireframe")
    show_wire.setChecked(_as_bool(settings.value(_VIEWER_WIRE_KEY, True), True))
    form.addRow(show_wire)
    return page


def apply_viewer_settings(page: QWidget) -> None:
    settings = QSettings()
    projection = page.findChild(QComboBox, "defaultProjection")
    palette = page.findChild(QComboBox, "defaultPalette")
    show_grid = page.findChild(QCheckBox, "showGrid")
    show_solid = page.findChild(QCheckBox, "showSolid")
    show_wire = page.findChild(QCheckBox, "showWireframe")
    if projection is not None:
        settings.setValue(_VIEWER_PROJECTION_KEY, projection.currentData())
    if palette is not None:
        value = str(palette.currentData())
        settings.setValue(_VIEWER_PALETTE_KEY, value)
        set_active_palette(value)
    if show_grid is not None:
        settings.setValue(_VIEWER_GRID_KEY, show_grid.isChecked())
    if show_solid is not None:
        settings.setValue(_VIEWER_SOLID_KEY, show_solid.isChecked())
    if show_wire is not None:
        settings.setValue(_VIEWER_WIRE_KEY, show_wire.isChecked())


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

    loft_method = QComboBox()
    loft_method.setObjectName("defaultLoftMethod")
    for name in ("auto", "smooth", "ruled"):
        loft_method.addItem(name.capitalize(), name)
    _combo_value(loft_method, _EDITOR_LOFT_METHOD_KEY, "smooth")
    form.addRow("Default loft method:", loft_method)
    return page


def apply_editor_settings(page: QWidget) -> None:
    settings = QSettings()
    auto_fit = page.findChild(QCheckBox, "autoFitSections")
    show_grid = page.findChild(QCheckBox, "showSectionGrid")
    loft_method = page.findChild(QComboBox, "defaultLoftMethod")
    if auto_fit is not None:
        settings.setValue(_EDITOR_AUTO_FIT_KEY, auto_fit.isChecked())
    if show_grid is not None:
        settings.setValue(_EDITOR_GRID_KEY, show_grid.isChecked())
    if loft_method is not None:
        settings.setValue(_EDITOR_LOFT_METHOD_KEY, loft_method.currentData())


def viewer_setting(key: str, fallback: object) -> object:
    return QSettings().value(key, fallback)


def editor_setting(key: str, fallback: object) -> object:
    return QSettings().value(key, fallback)


__all__ = [
    "_EDITOR_AUTO_FIT_KEY",
    "_EDITOR_GRID_KEY",
    "_EDITOR_LOFT_METHOD_KEY",
    "_VIEWER_GRID_KEY",
    "_VIEWER_PALETTE_KEY",
    "_VIEWER_PROJECTION_KEY",
    "_VIEWER_SOLID_KEY",
    "_VIEWER_WIRE_KEY",
    "apply_editor_settings",
    "apply_viewer_settings",
    "create_editor_settings_page",
    "create_viewer_settings_page",
    "editor_setting",
    "viewer_setting",
]
