from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QBrush, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
)

from setuav_studio.ui.project_explorer.context_menu import (
    ProjectExplorerContextMenu,
)
from setuav_studio.ui.project_explorer.operations import (
    ProjectExplorerOperations,
)
from setuav_studio.ui.project_explorer.style import (
    _ProjectExplorerBranchStyle,
    format_assembly_icon,
    format_assembly_type,
    format_component_name,
    format_component_type,
    get_geometry_icon_source,
)
from setuav_studio.ui.project_explorer.tree_builder import (
    ProjectTreeBuilder,
)

if TYPE_CHECKING:
    from setuav_studio.project import ProjectDocument
    from setuav_studio_sdk import (
        ComponentTreeNodeContribution,
        ProjectTreeNodeContribution,
        StudioAPI,
    )


class ProjectExplorer(QTreeWidget):
    """Clean, single-column model tree with hierarchy."""

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAlternatingRowColors(False)
        self.setAnimated(False)
        self.setIndentation(20)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self._branch_style = _ProjectExplorerBranchStyle(self)
        self.setStyle(self._branch_style)

        self._api = api
        self._item_map: dict[str, QTreeWidgetItem] = {}
        self._element_map: dict[QTreeWidgetItem, dict[str, Any]] = {}
        self._project_root_item: QTreeWidgetItem | None = None
        self._parameters_group_item: QTreeWidgetItem | None = None
        self._constraints_group_item: QTreeWidgetItem | None = None
        self._virtual_items: set[QTreeWidgetItem] = set()
        self._project_contributions: dict[
            QTreeWidgetItem,
            ProjectTreeNodeContribution,
        ] = {}
        self._component_contributions: dict[
            QTreeWidgetItem,
            ComponentTreeNodeContribution,
        ] = {}
        self._saved_components: dict[str, dict[str, Any]] = {}
        self._saved_assemblies: dict[str, dict[str, Any]] = {}
        self._saved_analysis_results: dict[str, dict[str, Any]] = {}
        self._last_active_config_id: str | None = None

        self._ops = ProjectExplorerOperations(self, api)
        self._builder = ProjectTreeBuilder(self, api)
        self._context_menu = ProjectExplorerContextMenu(self, api, self._ops)

        self.currentItemChanged.connect(self._publish_selection)
        self.itemChanged.connect(self._rename_item)
        self.customContextMenuRequested.connect(self._open_context_menu)

        api.on_project_changed(self.set_project)
        api.on_project_content_changed(self.refresh_project)
        api.on_selection_changed(self._sync_selection)
        api.on_modified_changed(self._on_modified_changed)

    def set_project(self, project: ProjectDocument) -> None:
        if hasattr(project, "get_configuration_manager"):
            self._last_active_config_id = project.get_configuration_manager().get_active_id()
        self._capture_saved_state(project)
        self._rebuild_project(project)

    def refresh_project(self, project: ProjectDocument | None = None) -> None:
        current_project = project or self._api.current_project
        if current_project is not None:
            if hasattr(current_project, "get_configuration_manager"):
                curr_active_id = current_project.get_configuration_manager().get_active_id()
                if curr_active_id != self._last_active_config_id:
                    self._last_active_config_id = curr_active_id
                    self._capture_saved_state(current_project)
            self._rebuild_project(current_project)

    def _rebuild_project(self, project: ProjectDocument) -> None:
        self._builder.rebuild_project(project)

    def _tree_selection_state(
        self,
        project: ProjectDocument,
    ) -> tuple[bool, str | None]:
        current_selection = self._api.current_selection
        return (
            current_selection is project.data,
            (current_selection.get("id") if isinstance(current_selection, dict) else None),
        )

    def _restore_tree_selection(
        self,
        project: ProjectDocument,
        project_item: QTreeWidgetItem,
        selection_state: tuple[bool, str | None],
    ) -> dict[str, Any] | None:
        project_selected, selection_id = selection_state
        if project_selected:
            self.setCurrentItem(project_item)
            return project.data
        if selection_id and selection_id in self._item_map:
            selected_item = self._item_map[selection_id]
            self.setCurrentItem(selected_item)
            return self._element_map.get(selected_item)
        return None

    def _capture_saved_state(self, project: ProjectDocument) -> None:
        self._saved_components = self._snapshot_collection(project, "components")
        self._saved_assemblies = self._snapshot_collection(project, "assemblies")
        self._saved_analysis_results = self._snapshot_analysis_results(project)

    @staticmethod
    def _snapshot_analysis_results(
        project: ProjectDocument,
    ) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        try:
            from plugins.aerodynamics.analysis_store import (
                analysis_entries as aero_entries,
            )

            for entry in aero_entries(project):
                if isinstance(entry, dict) and (eid := str(entry.get("id") or "")):
                    results[eid] = deepcopy(entry)
        except Exception:
            pass

        try:
            from plugins.flight_performance.analysis_store import (
                analysis_entries as perf_entries,
            )

            for entry in perf_entries(project):
                if isinstance(entry, dict) and (eid := str(entry.get("id") or "")):
                    results[eid] = deepcopy(entry)
        except Exception:
            pass

        return results

    @staticmethod
    def _snapshot_collection(
        project: ProjectDocument,
        collection_name: str,
    ) -> dict[str, dict[str, Any]]:
        collection = project.data.get(collection_name)
        if not isinstance(collection, list):
            return {}
        return {
            element_id: deepcopy(element)
            for element in collection
            if isinstance(element, dict) and (element_id := str(element.get("id") or ""))
        }

    @staticmethod
    def _apply_modified_color(
        item: QTreeWidgetItem,
        element: dict[str, Any],
        saved_elements: dict[str, dict[str, Any]],
    ) -> None:
        element_id = str(element.get("id") or "")
        if element_id and saved_elements.get(element_id) != element:
            from setuav_studio.ui.theme import status_color

            item.setForeground(
                0,
                QBrush(QColor(status_color("warning"))),
            )

    def _on_modified_changed(self, modified: bool) -> None:
        if modified:
            return
        project = self._api.current_project
        if project is None:
            return
        if hasattr(project, "get_configuration_manager"):
            self._last_active_config_id = project.get_configuration_manager().get_active_id()
        self._capture_saved_state(project)
        self._rebuild_project(project)

    def filter_items(self, query: str) -> None:
        """Filter tree items based on search query."""
        q = query.strip().lower()

        def apply_filter(item: QTreeWidgetItem) -> bool:
            name = item.text(0).lower()
            tooltip = item.toolTip(0).lower()
            matches_self = (q in name) or (q in tooltip) if q else True

            child_matched = False
            for i in range(item.childCount()):
                child = item.child(i)
                if apply_filter(child):
                    child_matched = True

            visible = matches_self or child_matched
            item.setHidden(not visible)
            if visible and q:
                item.setExpanded(True)
            return visible

        for i in range(self.topLevelItemCount()):
            apply_filter(self.topLevelItem(i))

    def _publish_selection(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current in (
            self._parameters_group_item,
            self._constraints_group_item,
        ):
            self._api.set_selection(None)
            return
        element = self._element_map.get(current) if current else None
        self._api.set_selection(element)

    def _sync_selection(self, selection: object | None) -> None:
        if selection is None and self.currentItem() in (
            self._parameters_group_item,
            self._constraints_group_item,
        ):
            return
        project = self._api.current_project
        if project is not None and selection is project.data:
            if (
                self._project_root_item is not None
                and self.currentItem() is not self._project_root_item
            ):
                self.setCurrentItem(self._project_root_item)
            return

        elem_id = selection.get("id") if isinstance(selection, dict) else None
        if not isinstance(elem_id, str):
            self.clearSelection()
            return
        item = self._item_map.get(elem_id)
        if item is not None:
            if self.currentItem() is not item:
                self.setCurrentItem(item)
        else:
            self.clearSelection()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
            and self.state() != QAbstractItemView.State.EditingState
        ):
            self._ops.delete_item(self.currentItem())
            event.accept()
            return
        super().keyPressEvent(event)

    def _open_context_menu(self, position: QPoint) -> None:
        self._context_menu.open_context_menu(position)

    def _rename_item(self, item: QTreeWidgetItem, column: int) -> None:
        self._ops.rename_item(item, column)

    def _delete_item(self, item: QTreeWidgetItem | None) -> None:
        self._ops.delete_item(item)

    def _can_edit_project(self) -> bool:
        return self._ops.can_edit_project()

    @staticmethod
    def _component_name_text(component: dict[str, object]) -> str:
        return format_component_name(component)

    @staticmethod
    def _assembly_type_text(assembly: dict[str, object]) -> str:
        return format_assembly_type(assembly)

    def _assembly_icon(self, assembly: dict[str, object]) -> Any:
        return format_assembly_icon(assembly, self._api)

    @staticmethod
    def _component_type_text(
        component: dict[str, object],
        components: list[dict[str, object]],
    ) -> str:
        return format_component_type(component, components)

    @staticmethod
    def _geometry_icon_source(
        component: dict[str, Any],
        components: list[dict[str, Any]],
    ) -> str | None:
        return get_geometry_icon_source(component, components)
