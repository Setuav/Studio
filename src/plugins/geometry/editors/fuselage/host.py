"""Typed host contract shared by the Fuselage Editor section mixins.

The section mixins are only ever combined into ``FuselageEditor``. For the type
checker they derive from ``FuselageEditorHost``, which declares the editor
members and the cross-mixin members they rely on; at runtime it is ``object``.
Each declaration mirrors the real implementation in ``editor.py`` or in the
section module named above it, and must change together with it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, ClassVar

    from PySide6.QtWidgets import QTableWidget, QToolButton, QVBoxLayout, QWidget

    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.widget.table import PropertyTableMixin

    class FuselageEditorHost(PropertyTableMixin, QWidget):
        """Members of ``FuselageEditor`` that its section mixins use."""

        PROFILE_TYPES: ClassVar[tuple[str, ...]]

        _api: StudioAPI
        _component: dict[str, Any]
        _segment_index: int
        _section_index: int
        _loading: bool

        sections_table: QTableWidget

        # editor.py
        def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout: ...

        @staticmethod
        def _action_button(
            icon_name: str,
            tooltip: str,
            callback: Callable[[], None],
        ) -> QToolButton: ...

        def _load_component(self) -> None: ...

        def _edit_component(self, description: str, change_fn: Callable[[], Any]) -> None: ...

        def _parameters(self) -> dict[str, Any]: ...

        @staticmethod
        def _object(owner: dict[str, Any], key: str) -> dict[str, Any]: ...

        # segments_section.py
        def _segments(self) -> list[dict[str, Any]]: ...

        def _current_segment(self) -> dict[str, Any] | None: ...

        def _add_segment(self) -> None: ...

        def _update_segment_sections_cell(self) -> None: ...

        # sections_section.py
        def _sections(self) -> list[dict[str, Any]]: ...

        def _populate_sections(self) -> None: ...

        def _load_section(self, index: int) -> None: ...

        def _update_section_actions(self) -> None: ...

        def _publish_section_selection(self) -> None: ...

else:
    FuselageEditorHost = object
