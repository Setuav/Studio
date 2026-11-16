"""Desktop shell and main application window components."""

from .validation import (
    _append_entity_changes,
    _items_by_id,
    apply_runtime_validation,
)
from .window import MainWindow

__all__ = [
    "MainWindow",
    "_append_entity_changes",
    "_items_by_id",
    "apply_runtime_validation",
]
