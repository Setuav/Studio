"""Typed view of the lifting surface editor shared by its section mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from PySide6.QtWidgets import QTableWidget, QToolButton, QVBoxLayout, QWidget

    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.widget.table import PropertyTableMixin

    class LiftingSurfaceEditorHost(PropertyTableMixin, QWidget):
        """Members of ``LiftingSurfaceEditor`` that its section mixins use from one another.

        Each member is implemented by ``LiftingSurfaceEditor`` itself or by the section
        mixin named in the group comment; signatures mirror those implementations.
        """

        _api: StudioAPI
        _component: dict[str, Any]
        _loading: bool
        _section_index: int
        _control_surface_index: int
        _sweep_loc: float

        # SectionsSectionMixin
        sections_table: QTableWidget

        # LiftingSurfaceEditor
        def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout: ...

        @staticmethod
        def _action_button(
            icon_name: str,
            tooltip: str,
            callback: Callable[[], None],
        ) -> QToolButton: ...

        def _edit_control_surface_item(
            self, cs: dict[str, Any], description: str, change_fn: Callable[[], None]
        ) -> None: ...

        def _edit_component(self, description: str, change_fn: Callable[[], None]) -> None: ...

        def _geometry(self) -> dict[str, Any]: ...

        def _profiles(self) -> list[dict[str, Any]]: ...

        def _cs_geom(self, cs: dict[str, Any]) -> dict[str, Any]: ...

        def _control_surfaces(self) -> list[dict[str, Any]]: ...

        @staticmethod
        def _format_airfoil_label(value: object) -> str: ...

        @staticmethod
        def _clear_property_values(table: QTableWidget) -> None: ...

        # PlanformSectionMixin
        def _refresh_planform_table(self) -> None: ...

        # SectionsSectionMixin
        def _get_sections(self) -> list[dict[str, Any]]: ...

        def _populate_sections(self) -> None: ...

        def _load_section(self, idx: int) -> None: ...

        # ControlSurfacesSectionMixin
        def _sync_control_surfaces_with_surface(self) -> None: ...

else:
    LiftingSurfaceEditorHost = object
