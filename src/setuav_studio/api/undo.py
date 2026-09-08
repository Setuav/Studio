from collections.abc import Callable
from copy import deepcopy
from typing import Any

from PySide6.QtGui import QUndoCommand

from setuav_studio.project import ProjectDocument


class _ComponentEditCommand(QUndoCommand):
    def __init__(
        self,
        component: dict[str, Any],
        before: dict[str, Any],
        after: dict[str, Any],
        description: str,
        changed: Callable[[], None],
    ) -> None:
        super().__init__(description)
        self._component = component
        self._before = before
        self._after = after
        self._changed = changed

    def undo(self) -> None:
        self._apply(self._before)

    def redo(self) -> None:
        self._apply(self._after)

    def _apply(self, value: dict[str, Any]) -> None:
        self._component.clear()
        self._component.update(deepcopy(value))
        self._changed()


class _ProjectEditCommand(QUndoCommand):
    def __init__(
        self,
        project: ProjectDocument,
        before: dict[str, Any],
        after: dict[str, Any],
        description: str,
        changed: Callable[[], None],
    ) -> None:
        super().__init__(description)
        self._project = project
        self._before = before
        self._after = after
        self._changed = changed

    def undo(self) -> None:
        self._apply(self._before)

    def redo(self) -> None:
        self._apply(self._after)

    def _apply(self, value: dict[str, Any]) -> None:
        self._project.data.clear()
        self._project.data.update(deepcopy(value))
        self._changed()


__all__ = ["_ComponentEditCommand", "_ProjectEditCommand"]
