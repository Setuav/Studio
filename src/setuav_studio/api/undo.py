from collections.abc import Callable
from copy import deepcopy
from typing import Any

from PySide6.QtGui import QUndoCommand

from setuav_studio.project import ProjectDocument

_ABSENT = object()


def compute_dict_diff(
    before: dict[str, Any],
    after: dict[str, Any],
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], Any, Any]]:
    """Compute granular field-level diffs between two nested dictionaries.

    Returns list of (path_tuple, old_value, new_value).
    """
    diffs: list[tuple[tuple[str, ...], Any, Any]] = []

    # Check keys present in before
    for k, v_before in before.items():
        if k not in after:
            diffs.append(((*path, k), deepcopy(v_before), _ABSENT))
        else:
            v_after = after[k]
            if v_before != v_after:
                if isinstance(v_before, dict) and isinstance(v_after, dict):
                    diffs.extend(compute_dict_diff(v_before, v_after, (*path, k)))
                else:
                    diffs.append(((*path, k), deepcopy(v_before), deepcopy(v_after)))

    # Check keys added in after
    for k, v_after in after.items():
        if k not in before:
            diffs.append(((*path, k), _ABSENT, deepcopy(v_after)))

    return diffs


def apply_diff(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    """Apply a single diff to a target dictionary along path."""
    curr: Any = target
    for key in path[:-1]:
        if not isinstance(curr, dict):
            return
        if key not in curr or not isinstance(curr[key], dict):
            curr[key] = {}
        curr = curr[key]

    if not isinstance(curr, dict) or not path:
        return

    last_key = path[-1]
    if value is _ABSENT:
        curr.pop(last_key, None)
    else:
        curr[last_key] = deepcopy(value) if isinstance(value, (dict, list)) else value


class _ComponentEditCommand(QUndoCommand):
    def __init__(
        self,
        component: dict[str, Any],
        diffs: list[tuple[tuple[str, ...], Any, Any]],
        description: str,
        changed: Callable[[], None],
        source: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(description)
        self._component = component
        self._diffs = diffs
        self._changed = changed
        self._source = source
        self._applied = False

    def undo(self) -> None:
        self._apply_diffs(forward=False)
        self._changed()

    def redo(self) -> None:
        if not self._applied:
            self._applied = True
            self._changed()
            return
        self._apply_diffs(forward=True)
        self._changed()

    def _apply_diffs(self, forward: bool) -> None:
        items = self._diffs if forward else list(reversed(self._diffs))
        for path, old_val, new_val in items:
            val = new_val if forward else old_val
            apply_diff(self._component, path, val)
            if self._source is not None and self._source is not self._component:
                apply_diff(self._source, path, val)


class _ProjectEditCommand(QUndoCommand):
    def __init__(
        self,
        project: ProjectDocument,
        diffs: list[tuple[tuple[str, ...], Any, Any]],
        description: str,
        changed: Callable[[], None],
    ) -> None:
        super().__init__(description)
        self._project = project
        self._diffs = diffs
        self._changed = changed
        self._applied = False

    def undo(self) -> None:
        self._apply_diffs(forward=False)
        self._changed()

    def redo(self) -> None:
        if not self._applied:
            self._applied = True
            self._changed()
            return
        self._apply_diffs(forward=True)
        self._changed()

    def _apply_diffs(self, forward: bool) -> None:
        items = self._diffs if forward else list(reversed(self._diffs))
        for path, old_val, new_val in items:
            val = new_val if forward else old_val
            apply_diff(self._project.data, path, val)


__all__ = [
    "_ComponentEditCommand",
    "_ProjectEditCommand",
    "apply_diff",
    "compute_dict_diff",
]
