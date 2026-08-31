"""Desktop shell and main application window components."""

from .layout import _WorkspaceLayoutContext
from .validation import (
    _append_entity_changes,
    _items_by_id,
    apply_runtime_validation,
)
from .window import MainWindow, StudioShell

__all__ = [
    "MainWindow",
    "StudioShell",
    "_WorkspaceLayoutContext",
    "_append_entity_changes",
    "_items_by_id",
    "apply_runtime_validation",
]
