import logging
from pathlib import Path
from typing import Any

import qtawesome as qta
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

logger = logging.getLogger(__name__)

_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
# Each icon is ``<name>.svg`` in this folder; ``get_icon("<name>")`` finds it.
_ICON_DIR = _ASSETS / "icons"
# Use the librsvg-rendered fallback at runtime. Qt's SVG renderer does not
# preserve the logo's clip paths, while this PNG is generated from the same
# canonical SVG and retains the complete typography artwork.
_APPLICATION_ICON = _ASSETS / "application" / "studio.png"

_ICON_MAP = {
    # File / Project actions
    # Edit actions
    # Panels
    "project_explorer": "fa6s.folder-tree",
    "properties": "fa6s.sliders",
    "viewer_3d": "fa6s.cube",
    "dock_float": "fa6s.up-right-and-down-left-from-center",
    "dock_close": "fa6s.xmark",
    # Toolbar & General actions
    "add": "fa6s.plus",
    "remove": "fa6s.trash-can",
    "delete": "fa6s.trash-can",
    "edit": "fa6s.pen-to-square",
    "pencil": "mdi6.pencil",
    "pen": "fa6s.pen",
    "split": "mdi6.call-split",
    "call_split": "mdi6.call-split",
    "fit": "fa6s.expand",
    "export_csv": "fa6s.file-export",
    "success": "fa6s.check",
    "check": "fa6s.check",
    "fx": "mdi6.function-variant",
    "equation": "fa6s.code",
    "plugin": "fa6s.box-open",
    "tasks": "ei.tasks",
    # 3D Viewport Controls & Overlays
    "view_solid": "mdi6.cube",
    "view_wireframe": "mdi6.cube-outline",
    "view_transparent": "mdi6.cube-scan",
    "view_palette": "fa6s.palette",
    "palette": "fa6s.palette",
    "view_fit": "fa6s.expand",
    "camera_perspective": "mdi6.perspective-more",
    "camera_iso": "mdi6.cube-unfolded",
    "camera_top": "mdi6.arrow-down-bold-box-outline",
    "camera_bottom": "mdi6.arrow-up-bold-box-outline",
    "camera_front": "mdi6.arrow-right-bold-box-outline",
    "camera_side": "mdi6.arrow-left-bold-box-outline",
    "layers": "fa6s.layer-group",
    "coordinate_system": "fa6s.arrows-up-down-left-right",
    "physical_envelope": "fa6s.box",
    # Default Component Types
    "component": "fa6s.cube",
    "instance": "fa6s.clone",
    "component_fuselage": "fa6s.shuttle-space",
    "component_lifting_surface": "fa6s.plane",
    "component_control_surface": "fa6s.sliders",
}

_LABEL_ICON_SOURCE = "setuavThemeIconSource"
_LABEL_ICON_SIZE = "setuavThemeIconSize"


def application_icon() -> QIcon:
    """Return the Setuav Studio application icon."""
    return QIcon(str(_APPLICATION_ICON))


_PLUGIN_ICON_MAP: dict[str, Path] = {}
_PLUGIN_ICON_NAMES: dict[str, tuple[str, ...]] = {}


def register_icon(name: str, icon_path_or_specifier: str | Path | QIcon) -> None:
    """Register a custom logical icon name mapped to an asset file or QtAwesome specifier."""
    if isinstance(icon_path_or_specifier, (str, Path)):
        p = Path(icon_path_or_specifier)
        if p.is_file():
            _PLUGIN_ICON_MAP[name] = p.resolve()
            return
    if isinstance(icon_path_or_specifier, str):
        _ICON_MAP[name] = icon_path_or_specifier


def register_plugin_icons(plugin_id: str, assets_dir: Path | str) -> None:
    """Register every SVG in a plugin's icon folder under its file name.

    ``<assets_dir>/servo.svg`` becomes the icon ``servo``. A folder without SVG
    icons raises. :func:`unregister_plugin_icons` removes the registration.
    """
    dir_path = Path(assets_dir).resolve()
    icons = {path.stem: path for path in sorted(dir_path.glob("*.svg"))}
    if not icons:
        raise FileNotFoundError(f"Plugin {plugin_id!r} has no SVG icons in {dir_path}")
    _PLUGIN_ICON_NAMES[plugin_id] = tuple(icons)
    _PLUGIN_ICON_MAP.update(icons)


def unregister_plugin_icons(plugin_id: str) -> None:
    """Remove the icons :func:`register_plugin_icons` registered for ``plugin_id``."""
    for name in _PLUGIN_ICON_NAMES.pop(plugin_id):
        _PLUGIN_ICON_MAP.pop(name, None)


def _asset_icon(icon_source: str) -> QIcon | None:
    if icon_source in _PLUGIN_ICON_MAP:
        return QIcon(str(_PLUGIN_ICON_MAP[icon_source]))
    icon_path = _ICON_DIR / f"{icon_source}.svg"
    if icon_path.is_file():
        return QIcon(str(icon_path))
    return None


class _ThemeIconEngine(QIconEngine):
    """Render a QtAwesome glyph from the palette in effect at paint time."""

    def __init__(
        self,
        specifier: str,
        color: str | None = None,
        color_disabled: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._specifier = specifier
        self._color = color
        self._color_disabled = color_disabled
        self._options = dict(options or {})

    def clone(self) -> QIconEngine:
        return _ThemeIconEngine(
            self._specifier,
            self._color,
            self._color_disabled,
            self._options,
        )

    def key(self) -> str:
        return "SetuavThemeIconEngine"

    def pixmap(
        self,
        size: QSize,
        mode: QIcon.Mode,
        state: QIcon.State,
    ) -> QPixmap:
        palette = QApplication.palette()
        normal = (
            self._color
            or palette.color(
                QPalette.ColorGroup.Active,
                QPalette.ColorRole.ButtonText,
            ).name()
        )
        disabled = (
            self._color_disabled
            or palette.color(
                QPalette.ColorGroup.Disabled,
                QPalette.ColorRole.ButtonText,
            ).name()
        )
        selected = palette.color(
            QPalette.ColorGroup.Active,
            QPalette.ColorRole.HighlightedText,
        ).name()
        icon = qta.icon(
            self._specifier,
            color=normal,
            color_active=normal,
            color_disabled=disabled,
            color_selected=selected,
            **self._options,
        )
        return icon.pixmap(size, mode, state)

    def paint(
        self,
        painter: QPainter,
        rect: QRect,
        mode: QIcon.Mode,
        state: QIcon.State,
    ) -> None:
        painter.drawPixmap(rect, self.pixmap(rect.size(), mode, state))


def get_icon(
    icon_source: str | Path | QIcon,
    color: str | None = None,
    color_disabled: str | None = None,
    **kwargs: Any,
) -> QIcon:
    """Return a theme-aware QIcon for a logical name, QtAwesome specifier, or file path."""
    if isinstance(icon_source, QIcon):
        return icon_source

    if isinstance(icon_source, Path) or (
        isinstance(icon_source, str)
        and (
            icon_source.endswith(".svg")
            or icon_source.endswith(".png")
            or Path(icon_source).is_file()
        )
    ):
        return QIcon(str(icon_source))

    asset_icon = _asset_icon(icon_source)
    if asset_icon is not None:
        return asset_icon
    specifier = _ICON_MAP.get(icon_source, icon_source)
    try:
        qta.icon(specifier, **kwargs)
    except Exception as exc:
        # QtAwesome reports an unknown glyph with a bare Exception.
        raise ValueError(f"Unknown icon {specifier!r}") from exc
    # A custom icon engine avoids storing the current theme color in the
    # QIcon. Existing actions and buttons therefore repaint correctly
    # after an application palette change without rebuilding each icon.
    return QIcon(
        _ThemeIconEngine(
            specifier,
            color=color,
            color_disabled=color_disabled,
            options=kwargs,
        )
    )


def set_label_icon(label: QLabel, icon_source: str, size: int = 14) -> None:
    """Set and remember a palette-aware icon rendered into a QLabel pixmap."""
    label.setProperty(_LABEL_ICON_SOURCE, icon_source)
    label.setProperty(_LABEL_ICON_SIZE, size)
    label.setPixmap(get_icon(icon_source).pixmap(size, size))


def refresh_label_icon(label: QLabel) -> None:
    """Refresh a QLabel pixmap previously assigned with :func:`set_label_icon`."""
    icon_source = label.property(_LABEL_ICON_SOURCE)
    if not isinstance(icon_source, str) or not icon_source:
        return
    size = label.property(_LABEL_ICON_SIZE)
    icon_size = int(size) if isinstance(size, int) and size > 0 else 14
    label.setPixmap(get_icon(icon_source).pixmap(icon_size, icon_size))


def create_color_badge_icon(color_hex: str, size: int = 16) -> QIcon:
    """Create a crisp circular color dot icon for configurations and tags."""
    from PySide6.QtGui import QColor, QPainter, QPixmap

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor(color_hex) if color_hex else QColor("#2196F3")
    painter.setBrush(col)
    painter.setPen(col.darker(130))
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.end()
    return QIcon(pixmap)


__all__ = [
    "application_icon",
    "create_color_badge_icon",
    "get_icon",
    "refresh_label_icon",
    "register_icon",
    "register_plugin_icons",
    "set_label_icon",
]
