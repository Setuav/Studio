from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, QPoint, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
)

from setuav_studio.ui.panels.project_explorer.context_menu import (
    ProjectExplorerContextMenu,
)
from setuav_studio.ui.panels.project_explorer.operations import (
    ProjectExplorerOperations,
)
from setuav_studio.ui.panels.project_explorer.style import (
    ProjectExplorerDelegate,
    _ProjectExplorerBranchStyle,
    format_component_name,
    format_component_type,
)
from setuav_studio.ui.panels.project_explorer.tree_builder import (
    ProjectTreeBuilder,
)

if TYPE_CHECKING:
    from setuav_studio.api import (
        ComponentTreeNodeContribution,
        ProjectTreeNodeContribution,
        StudioAPI,
    )
    from setuav_studio.project import ProjectDocument


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
        self.setIconSize(QSize(16, 16))
        self.setItemDelegate(ProjectExplorerDelegate(self))
        self._branch_style = _ProjectExplorerBranchStyle(self)
        self.setStyle(self._branch_style)

        self._api = api
        self._item_map: dict[str, QTreeWidgetItem] = {}
        self._element_map: dict[QTreeWidgetItem, dict[str, Any]] = {}
        self._project_root_item: QTreeWidgetItem | None = None
        self._parameters_group_item: QTreeWidgetItem | None = None
        self._constraints_group_item: QTreeWidgetItem | None = None
        self._analysis_group_item: QTreeWidgetItem | None = None
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
        self._saved_parameters: dict[str, Any] = {}
        self._saved_constraints: dict[str, dict[str, Any]] = {}
        self._saved_solver_configs: dict[str, dict[str, Any]] = {}
        self._saved_analysis_results: dict[str, dict[str, Any]] = {}

        self._ops = ProjectExplorerOperations(self, api)
        self._builder = ProjectTreeBuilder(self, api)
        self._context_menu = ProjectExplorerContextMenu(self, api, self._ops)

        self.currentItemChanged.connect(self._publish_selection)
        self.itemClicked.connect(self._on_item_clicked)
        self.itemChanged.connect(self._rename_item)
        self.customContextMenuRequested.connect(self._open_context_menu)

        api.on_project_changed(self.set_project)
        api.on_project_content_changed(self.refresh_project)
        api.on_selection_changed(self._sync_selection)
        api.on_modified_changed(self._on_modified_changed)

    def set_project(self, project: ProjectDocument) -> None:
        self._capture_saved_state(project)
        self._rebuild_project(project)

    def refresh_project(self, project: ProjectDocument | None = None) -> None:
        current_project = project or self._api.project
        if current_project is not None:
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
            project_item.setSelected(True)
            self.setCurrentItem(project_item)
            return project.data

        if selection_id:
            if selection_id in self._item_map:
                selected_item = self._item_map[selection_id]
                selected_item.setSelected(True)
                self.setCurrentItem(selected_item)
                return self._element_map.get(selected_item)

            for item, elem in self._element_map.items():
                if isinstance(elem, dict) and elem.get("id") == selection_id:
                    item.setSelected(True)
                    self.setCurrentItem(item)
                    return elem

        self.clearSelection()
        self.setCurrentIndex(QModelIndex())
        return None

    def _capture_saved_state(self, project: ProjectDocument) -> None:
        self._saved_components = self._snapshot_collection(project, "components")
        self._saved_parameters = deepcopy(project.data.get("parameters", {}))
        self._saved_constraints = self._snapshot_collection(project, "constraints")
        self._saved_solver_configs = {
            cid: deepcopy(cfg.to_dict()) for cid, cfg in project.solver_configs.items()
        }
        self._saved_analysis_results = self._snapshot_analysis_results(project)

    @staticmethod
    def _snapshot_analysis_results(
        project: ProjectDocument,
    ) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        plugins_data = project.data.get("plugins") or project.data.get("extensions") or {}
        if not isinstance(plugins_data, dict):
            return results
        for ns_data in plugins_data.values():
            if not isinstance(ns_data, dict):
                continue
            for list_key in ("results", "analysis_runs", "entries"):
                items = ns_data.get(list_key)
                if isinstance(items, list):
                    for entry in items:
                        if isinstance(entry, dict) and (eid := str(entry.get("id") or "")):
                            results[eid] = deepcopy(entry)
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

    def _apply_modified_color(
        self,
        item: QTreeWidgetItem,
        element: dict[str, Any],
        saved_elements: dict[str, dict[str, Any]],
    ) -> None:
        project = self._api.project
        if project is None or not project.modified:
            return
        element_id = str(element.get("id") or "")
        if element_id and saved_elements.get(element_id) != element:
            from setuav_studio.ui.style.theme import status_color

            item.setForeground(
                0,
                QBrush(QColor(status_color("warning"))),
            )

    def _on_modified_changed(self, modified: bool) -> None:
        project = self._api.project
        if project is None:
            return
        if not modified:
            self._capture_saved_state(project)
        self._refresh_modified_colors()

    def _is_element_modified(
        self,
        element: dict[str, Any],
        project: ProjectDocument | None,
    ) -> bool:
        kind = element.get("kind")
        if kind == "parameter":
            key = element.get("key")
            saved_value = self._saved_parameters.get(key) if isinstance(key, str) else None
            return saved_value != element.get("value")
        if kind == "constraint":
            cid = str(element.get("id") or "")
            raw_c = {k: v for k, v in element.items() if k != "kind"}
            return self._saved_constraints.get(cid) != raw_c
        if kind == "analysis_config":
            cid = str(element.get("id") or "")
            current_cfg = project.get_solver_config(cid) if project else None
            current_dict = current_cfg.to_dict() if current_cfg else None
            return self._saved_solver_configs.get(cid) != current_dict
        if kind in ("analysis_table", "analysis_plot"):
            return False

        element_id = str(element.get("id") or "")
        if not element_id:
            return False
        if element_id in self._saved_components:
            return self._saved_components[element_id] != element

        components = project.data.get("components", []) if project else []
        return any(c.get("id") == element_id for c in components if isinstance(c, dict))

    def _refresh_modified_colors(self) -> None:
        from setuav_studio.ui.style.theme import status_color

        project = self._api.project
        is_clean = project is None or not project.modified

        for item, element in list(self._element_map.items()):
            try:
                _ = item.text(0)
            except RuntimeError:
                continue

            if is_clean:
                item.setData(0, Qt.ItemDataRole.ForegroundRole, None)
                continue

            is_modified = False
            if item in self._virtual_items:
                analysis_id = element.get("analysis_id") if isinstance(element, dict) else None
                if analysis_id:
                    current_entries = self._snapshot_analysis_results(project) if project else {}
                    current_entry = current_entries.get(analysis_id)
                    saved_entry = self._saved_analysis_results.get(analysis_id)
                    is_modified = saved_entry != current_entry
            elif isinstance(element, dict):
                is_modified = self._is_element_modified(element, project)

            if is_modified:
                item.setForeground(0, QBrush(QColor(status_color("warning"))))
            else:
                item.setData(0, Qt.ItemDataRole.ForegroundRole, None)

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
                assert child is not None
                if apply_filter(child):
                    child_matched = True

            visible = matches_self or child_matched
            item.setHidden(not visible)
            if visible and q:
                item.setExpanded(True)
            return visible

        for i in range(self.topLevelItemCount()):
            top_level = self.topLevelItem(i)
            assert top_level is not None
            apply_filter(top_level)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        self._publish_selection(item, None)

    def _publish_selection(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current in (
            self._parameters_group_item,
            self._constraints_group_item,
            self._analysis_group_item,
        ):
            self._api.set_selection(None)
            return
        element = self._element_map.get(current) if current else None
        if isinstance(element, dict):
            kind = element.get("kind")
            if kind == "analysis_config":
                self._api.set_current_solver_config(str(element["config_id"]))
            elif kind in (
                "analysis_table",
                "analysis_plot",
                "analysis_plots_group",
                "analysis_tables_group",
            ):
                self._api.show_panel("studio:result")
        self._api.set_selection(element)

    def _sync_selection(self, selection: object | None) -> None:
        if selection is None:
            if self.currentItem() in (
                self._parameters_group_item,
                self._constraints_group_item,
                self._analysis_group_item,
            ):
                return
            self.clearSelection()
            self.setCurrentIndex(QModelIndex())
            return
        project = self._api.project
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
            self.setCurrentIndex(QModelIndex())
            return
        item = self._item_map.get(elem_id)
        if item is None:
            for itm, elem in self._element_map.items():
                if isinstance(elem, dict) and elem.get("id") == elem_id:
                    item = itm
                    break
        if item is not None:
            if self.currentItem() is not item:
                item.setSelected(True)
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)

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

    def _component_type_text(
        self,
        component: dict[str, object],
        components: list[dict[str, object]],
    ) -> str:
        return format_component_type(component, components, api=self._api)
