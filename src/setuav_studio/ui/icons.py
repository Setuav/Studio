import logging
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

import qtawesome as qta
from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

logger = logging.getLogger(__name__)

_ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "icons"
_ICON_MANIFEST = _ASSET_ROOT / "manifest.toml"
_APPLICATION_ICON = _ASSET_ROOT / "studio.svg"

_ICON_MAP = {
    # File / Project actions
    "file_open": "fa6s.file-code",
    "folder_open": "fa6s.folder-open",
    "project_folder": "fa6s.folder",
    "save": "fa6s.floppy-disk",
    "save_as": "fa6s.floppy-disk",
    "exit": "fa6s.right-from-bracket",
    # Edit actions
    "undo": "fa6s.rotate-left",
    "redo": "fa6s.rotate-right",
    "settings": "fa6s.gear",
    # Panels & Workspaces
    "project_explorer": "fa6s.folder-tree",
    "properties": "fa6s.sliders",
    "viewer_3d": "fa6s.cube",
    "dock_float": "fa6s.up-right-and-down-left-from-center",
    "dock_close": "fa6s.xmark",
    # Toolbar & General actions
    "add": "fa6s.plus",
    "remove": "fa6s.trash-can",
    "edit": "fa6s.pen-to-square",
    "pencil": "mdi6.pencil",
    "pen": "fa6s.pen",
    "split": "mdi6.call-split",
    "call_split": "mdi6.call-split",
    "fit": "fa6s.expand",
    "log": "mdi6.message-text-outline",
    "export_csv": "fa6s.file-export",
    # QtAwesome controls intentionally used inside 3D viewers
    "view_colored": "fa6s.palette",
    "view_grid": "mdi6.grid",
    "view_palette": "fa6s.eye-dropper",
    "view_fit": "fa6s.expand",
    # Default Component Types
    "component": "fa6s.cube",
    "instance": "fa6s.clone",
    "assembly_generic": "fa6s.cubes",
    "component_fuselage": "fa6s.shuttle-space",
    "component_lifting_surface": "fa6s.plane",
    "component_control_surface": "fa6s.sliders",
    "component_propulsion_system": "fa6s.bolt",
}

_LABEL_ICON_SOURCE = "setuavThemeIconSource"
_LABEL_ICON_SIZE = "setuavThemeIconSize"


def application_icon() -> QIcon:
    """Return the Setuav Studio application icon."""
    return QIcon(str(_APPLICATION_ICON))


@lru_cache(maxsize=1)
def _asset_icon_map() -> dict[str, str]:
    """Load logical icon names from the vendored asset manifest."""
    try:
        with _ICON_MANIFEST.open("rb") as stream:
            values = tomllib.load(stream).get("icons", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("Could not load icon manifest %s: %s", _ICON_MANIFEST, exc)
        return {}
    return {
        str(name): str(relative_path)
        for name, relative_path in values.items()
        if isinstance(relative_path, str)
    }


def _asset_icon(icon_source: str) -> QIcon | None:
    relative_path = _asset_icon_map().get(icon_source)
    if relative_path is None:
        return None
    icon_path = _ASSET_ROOT / relative_path
    if not icon_path.is_file():
        logger.warning("Mapped icon asset is missing: %s", icon_path)
        return None
    return QIcon(str(icon_path))


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

    if isinstance(icon_source, str):
        asset_icon = _asset_icon(icon_source)
        if asset_icon is not None:
            return asset_icon
        specifier = _ICON_MAP.get(icon_source, icon_source)
        try:
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
        except Exception as exc:
            logger.warning("Failed to load icon %r: %s", specifier, exc)
            return QIcon()

    return QIcon()


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
