"""Undo/Redo commands for 2D fuselage cross-section editing."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from .fuselage_section_dialog import FuselageSectionDialog


class MoveVertexCommand(QUndoCommand):
    """Move a vertex in the cross-section polygon."""

    def __init__(
        self,
        dialog: FuselageSectionDialog,
        vertex_idx: int,
        old_pos: tuple[float, float],
        new_pos: tuple[float, float],
    ) -> None:
        super().__init__(f"Move Vertex P{vertex_idx + 1}")
        self.dialog = dialog
        self.vertex_idx = vertex_idx
        self.old_pos = old_pos
        self.new_pos = new_pos

    def redo(self) -> None:
        self.dialog._apply_vertex_pos(self.vertex_idx, self.new_pos[0], self.new_pos[1])

    def undo(self) -> None:
        self.dialog._apply_vertex_pos(self.vertex_idx, self.old_pos[0], self.old_pos[1])


class AddVertexCommand(QUndoCommand):
    """Insert a new vertex into the polygon."""

    def __init__(
        self,
        dialog: FuselageSectionDialog,
        insert_idx: int,
        vertex_data: dict[str, float],
    ) -> None:
        super().__init__(f"Add Vertex P{insert_idx + 1}")
        self.dialog = dialog
        self.insert_idx = insert_idx
        self.vertex_data = copy.deepcopy(vertex_data)

    def redo(self) -> None:
        self.dialog._insert_vertex_internal(self.insert_idx, self.vertex_data)

    def undo(self) -> None:
        self.dialog._remove_vertex_internal(self.insert_idx)


class DeleteVertexCommand(QUndoCommand):
    """Delete a vertex from the polygon."""

    def __init__(
        self,
        dialog: FuselageSectionDialog,
        delete_idx: int,
        vertex_data: dict[str, float],
    ) -> None:
        super().__init__(f"Delete Vertex P{delete_idx + 1}")
        self.dialog = dialog
        self.delete_idx = delete_idx
        self.vertex_data = copy.deepcopy(vertex_data)

    def redo(self) -> None:
        self.dialog._remove_vertex_internal(self.delete_idx)

    def undo(self) -> None:
        self.dialog._insert_vertex_internal(self.delete_idx, self.vertex_data)


class ChangePropertyCommand(QUndoCommand):
    """Change a single profile property (width, height, etc.)."""

    def __init__(
        self,
        dialog: FuselageSectionDialog,
        key: str,
        old_val: Any,
        new_val: Any,
    ) -> None:
        super().__init__(f"Edit {key}")
        self.dialog = dialog
        self.key = key
        self.old_val = old_val
        self.new_val = new_val

    def redo(self) -> None:
        self.dialog._apply_profile_property(self.key, self.new_val)

    def undo(self) -> None:
        self.dialog._apply_profile_property(self.key, self.old_val)


class ChangeProfileTypeCommand(QUndoCommand):
    """Change profile shape type (e.g. circle -> rectangle)."""

    def __init__(
        self,
        dialog: FuselageSectionDialog,
        old_profile: dict[str, Any],
        new_profile: dict[str, Any],
    ) -> None:
        super().__init__(f"Change Profile to {new_profile.get('type')}")
        self.dialog = dialog
        self.old_profile = copy.deepcopy(old_profile)
        self.new_profile = copy.deepcopy(new_profile)

    def redo(self) -> None:
        self.dialog._apply_full_profile(self.new_profile)

    def undo(self) -> None:
        self.dialog._apply_full_profile(self.old_profile)


__all__ = [
    "AddVertexCommand",
    "ChangeProfileTypeCommand",
    "ChangePropertyCommand",
    "DeleteVertexCommand",
    "MoveVertexCommand",
]
