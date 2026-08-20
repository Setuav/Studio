from pathlib import Path
from typing import Any
import logging
import qtawesome as qta
from PySide6.QtGui import QIcon

logger = logging.getLogger(__name__)

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
    "fit": "fa6s.expand",
    "log": "mdi6.message-text-outline",
    # Default Component Types
    "component": "fa6s.cube",
    "instance": "fa6s.clone",
}


def get_icon(
    icon_source: str | Path | QIcon,
    color: str | None = None,
    **kwargs: Any,
) -> QIcon:
    """Return a QIcon for a logical name, QtAwesome specifier, SVG/file path, or existing QIcon."""
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
        specifier = _ICON_MAP.get(icon_source, icon_source)
        try:
            if color:
                return qta.icon(specifier, color=color, **kwargs)
            return qta.icon(specifier, **kwargs)
        except Exception as exc:
            logger.warning("Failed to load icon %r: %s", specifier, exc)
            return QIcon()

    return QIcon()
