from collections.abc import Callable
from copy import deepcopy
from typing import Any

from PySide6.QtCore import QLine, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProxyStyle,
    QStyle,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.project import ProjectDocument
from setuav_studio.ui.icons import get_icon
from setuav_studio_sdk import (
    ComponentTreeNodeContribution,
    ProjectTreeNodeContribution,
    StudioAPI,
)

_GEOMETRY_COMPONENT_ICONS = {
    "org.setuav.core:fuselage": "geometry_add_fuselage",
    "org.setuav.core:lifting-surface": "geometry_add_lifting_surface",
    "org.setuav.core:control-surface": "geometry_add_control_surface",
}


class _ProjectExplorerBranchStyle(QProxyStyle):
    """Draw classic dotted tree branches with square expand controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__()
        if parent is not None:
            self.setParent(parent)

    def sizeFromContents(self, contents_type, option, size, widget=None) -> QSize:
        result = super().sizeFromContents(contents_type, option, size, widget)
        if contents_type == QStyle.ContentsType.CT_ItemViewItem:
            result.setHeight(result.height() + 4)
        return result

    def drawPrimitive(self, element, option, painter, widget=None) -> None:
        if element != QStyle.PrimitiveElement.PE_IndicatorBranch:
            super().drawPrimitive(element, option, painter, widget)
            return

        rect = option.rect
        if rect.isEmpty():
            return

        state = option.state
        has_item = bool(state & QStyle.StateFlag.State_Item)
        has_sibling = bool(state & QStyle.StateFlag.State_Sibling)
        has_children = bool(state & QStyle.StateFlag.State_Children)
        is_open = bool(state & QStyle.StateFlag.State_Open)
        center_x = rect.center().x()
        center_y = rect.center().y()

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

            branch_color = option.palette.color(QPalette.ColorRole.Text)
            branch_color.setAlpha(120)
            branch_pen = QPen(branch_color)
            branch_pen.setWidth(1)
            branch_pen.setCosmetic(True)
            branch_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(branch_pen)

            if has_sibling:
                painter.drawLine(QLine(center_x, rect.top(), center_x, rect.bottom()))
            elif has_item:
                painter.drawLine(QLine(center_x, rect.top(), center_x, center_y))

            if has_item:
                painter.drawLine(QLine(center_x, center_y, rect.right(), center_y))

            if has_children:
                box_size = min(9, max(5, rect.height() - 2))
                if box_size % 2 == 0:
                    box_size -= 1
                half = box_size // 2
                box = QRect(
                    center_x - half,
                    center_y - half,
                    box_size,
                    box_size,
                )
                painter.fillRect(box, option.palette.color(QPalette.ColorRole.Base))

                control_pen = QPen(option.palette.color(QPalette.ColorRole.Text))
                control_pen.setWidth(1)
                control_pen.setCosmetic(True)
                painter.setPen(control_pen)
                painter.drawRect(box.adjusted(0, 0, -1, -1))
                painter.drawLine(QLine(box.left() + 2, center_y, box.right() - 2, center_y))
                if not is_open:
                    painter.drawLine(QLine(center_x, box.top() + 2, center_x, box.bottom() - 2))
        finally:
            painter.restore()


class ProjectExplorerPanel(QWidget):
    """Panel containing search box and the clean model tree."""

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search bar
        search_box = QWidget()
        s_layout = QHBoxLayout(search_box)
        s_layout.setContentsMargins(2, 2, 2, 2)
        s_layout.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter model...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(
            get_icon("fa6s.magnifying-glass"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        s_layout.addWidget(self.search_edit)
        self.expand_all_button = self._tree_action_button(
            "fa6s.square-plus",
            "Expand All",
            self._expand_all,
        )
        s_layout.addWidget(self.expand_all_button)
        self.collapse_all_button = self._tree_action_button(
            "fa6s.square-minus",
            "Collapse All",
            self._collapse_all,
        )
        s_layout.addWidget(self.collapse_all_button)
        layout.addWidget(search_box)

        self.explorer = ProjectExplorer(api)
        layout.addWidget(self.explorer, 1)

        self.search_edit.textChanged.connect(self.explorer.filter_items)

    def _expand_all(self) -> None:
        self.explorer.expandAll()

    def _collapse_all(self) -> None:
        self.explorer.collapseAll()

    @staticmethod
    def _tree_action_button(
        icon_name: str,
        tooltip: str,
        callback: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton()
        button.setIcon(get_icon(icon_name))
        button.setToolTip(tooltip)
        button.setStatusTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setAutoRaise(True)
        button.setFixedSize(26, 26)
        button.clicked.connect(callback)
        return button

    def update_theme_style(self) -> None:
        self.explorer.refresh_project()
        self.explorer.viewport().update()


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

        self.currentItemChanged.connect(self._publish_selection)
        self.itemChanged.connect(self._rename_item)
        self.customContextMenuRequested.connect(self._open_context_menu)
        self._api = api
        self._item_map: dict[str, QTreeWidgetItem] = {}
        self._element_map: dict[QTreeWidgetItem, dict[str, Any]] = {}
        self._project_root_item: QTreeWidgetItem | None = None
        self._geometry_group_item: QTreeWidgetItem | None = None
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

        api.on_project_changed(self.set_project)
        api.on_project_content_changed(self.refresh_project)
        api.on_selection_changed(self._sync_selection)
        api.on_modified_changed(self._on_modified_changed)

    def set_project(self, project: ProjectDocument) -> None:
        if hasattr(project, "get_configuration_manager"):
            self._last_active_config_id = project.get_configuration_manager().get_active_id()
        self._capture_saved_state(project)
        self._rebuild_project(project)

    def _rebuild_project(self, project: ProjectDocument) -> None:
        selection_state = self._tree_selection_state(project)
        fresh_selection: dict[str, Any] | None = None
        self.blockSignals(True)
        try:
            self._reset_project_tree()
            project_item = self._create_project_item(project)
            components, assemblies = self._project_elements(project)
            self._create_geometry_group(project_item, components)
            component_assemblies = self._component_assembly_map(assemblies)
            self._create_assembly_items(project_item, assemblies, project.read_only)
            self._create_component_items(components, project.read_only)
            self._attach_component_items(
                project_item,
                components,
                component_assemblies,
            )
            self._create_parameters_group(project_item, project)
            self._create_constraints_group(project_item, project)
            for contribution in self._api.project_tree_nodes(project):
                self._append_project_contribution(project_item, contribution)
            self.expandAll()
            fresh_selection = self._restore_tree_selection(
                project,
                project_item,
                selection_state,
            )
        finally:
            self.blockSignals(False)

        current_selection_id = selection_state[2]
        if current_selection_id and self._api.current_selection is not fresh_selection:
            self._api.set_selection(fresh_selection)

    def _tree_selection_state(
        self,
        project: ProjectDocument,
    ) -> tuple[bool, bool, str | None]:
        current_selection = self._api.current_selection
        return (
            current_selection is project.data,
            self.currentItem() is self._geometry_group_item,
            (current_selection.get("id") if isinstance(current_selection, dict) else None),
        )

    def _reset_project_tree(self) -> None:
        self.clear()
        self._item_map.clear()
        self._element_map.clear()
        self._project_root_item = None
        self._geometry_group_item = None
        self._parameters_group_item = None
        self._constraints_group_item = None
        self._virtual_items.clear()
        self._project_contributions.clear()
        self._component_contributions.clear()

    def _create_project_item(self, project: ProjectDocument) -> QTreeWidgetItem:
        project_name = str(project.data.get("name") or project.location.name or "Unnamed Project")
        item = QTreeWidgetItem([project_name])
        if not project.read_only:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setToolTip(0, f"Project: {project_name}")
        self._element_map[item] = project.data
        self._project_root_item = item
        self.addTopLevelItem(item)
        return item

    @staticmethod
    def _project_elements(
        project: ProjectDocument,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        components = project.data.get("components", [])
        assemblies = project.data.get("assemblies", [])
        return (
            [item for item in components if isinstance(item, dict)],
            [item for item in assemblies if isinstance(item, dict)],
        )

    def _create_geometry_group(
        self,
        project_item: QTreeWidgetItem,
        components: list[dict[str, Any]],
    ) -> None:
        if not any(
            self._geometry_icon_source(component, components) is not None
            for component in components
        ):
            return
        geometry_group = QTreeWidgetItem(["Geometry"])
        geometry_group.setIcon(0, get_icon("fa6s.shapes"))
        geometry_group.setToolTip(0, "Geometry components")
        self._geometry_group_item = geometry_group
        project_item.addChild(geometry_group)

    def _create_parameters_group(
        self,
        project_item: QTreeWidgetItem,
        project: ProjectDocument,
    ) -> None:
        raw_params = project.data.get("parameters", {})
        constants: dict[str, Any] = {}
        equations: dict[str, Any] = {}

        for k, v in raw_params.items():
            raw_val = v.get("value") if isinstance(v, dict) and "value" in v else v
            if isinstance(raw_val, str) and raw_val.strip().startswith("="):
                equations[k] = v
            else:
                constants[k] = v

        # 1. Constants Group
        const_group = QTreeWidgetItem(["Constants"])
        const_group.setIcon(0, get_icon("constant"))
        const_group.setToolTip(0, "Project Design Constants")
        self._parameters_group_item = const_group
        project_item.addChild(const_group)

        for k, v in constants.items():
            item = QTreeWidgetItem([str(k)])
            item.setIcon(0, get_icon("constant"))
            if isinstance(v, dict):
                unit_str = f" {v.get('unit')}" if v.get("unit") else ""
                val_disp = f"{v.get('value', '')}{unit_str}"
            else:
                val_disp = str(v)
            item.setToolTip(0, f"Constant: {k}\nValue: {val_disp}")
            param_payload = {"kind": "parameter", "id": f"param_{k}", "key": k, "value": v}
            self._element_map[item] = param_payload
            self._item_map[f"param_{k}"] = item
            const_group.addChild(item)

        # 2. Equations Group (if any exist)
        if equations:
            eq_group = QTreeWidgetItem(["Equations"])
            eq_group.setIcon(0, get_icon("equation"))
            eq_group.setToolTip(0, "Project Formulas & Equations")
            project_item.addChild(eq_group)

            for k, v in equations.items():
                item = QTreeWidgetItem([str(k)])
                item.setIcon(0, get_icon("equation"))
                raw_val = v.get("value") if isinstance(v, dict) and "value" in v else v
                item.setToolTip(0, f"Equation: {k}\nFormula: {raw_val}")
                param_payload = {"kind": "parameter", "id": f"param_{k}", "key": k, "value": v}
                self._element_map[item] = param_payload
                self._item_map[f"param_{k}"] = item
                eq_group.addChild(item)

    def _create_constraints_group(
        self,
        project_item: QTreeWidgetItem,
        project: ProjectDocument,
    ) -> None:
        constraints = project.data.get("constraints", [])
        if not isinstance(constraints, list):
            return

        constraint_group = QTreeWidgetItem(["Design Constraints"])
        constraint_group.setIcon(0, get_icon("constraint"))
        constraint_group.setToolTip(0, "Design Rules & Limits")
        self._constraints_group_item = constraint_group
        project_item.addChild(constraint_group)

        from setuav_studio.plugins.core.constraints import ConstraintChecker

        checker = ConstraintChecker()

        for c in constraints:
            if not isinstance(c, dict):
                continue
            cid = c.get("id", "")
            name = c.get("name", cid)
            enabled = c.get("enabled", True)
            expr = c.get("expression", "")

            res = checker.check_constraint(c, project.data)
            if not enabled:
                status_icon_name = "fa6s.circle"
                status_tip = "Disabled"
            elif res.error:
                status_icon_name = "error"
                status_tip = f"Error: {res.error}"
            elif res.passed:
                status_icon_name = "success"
                status_tip = "Passed"
            else:
                status_icon_name = "warning"
                status_tip = f"Violated: {res.message or expr}"

            item = QTreeWidgetItem([name])
            item.setIcon(0, get_icon(status_icon_name))
            item.setToolTip(0, f"Constraint: {name}\nExpression: {expr}\nStatus: {status_tip}")
            constraint_payload = {"kind": "constraint", "id": cid, **c}
            self._element_map[item] = constraint_payload
            self._item_map[cid] = item
            constraint_group.addChild(item)

    @staticmethod
    def _component_assembly_map(
        assemblies: list[dict[str, Any]],
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for assembly in assemblies:
            assembly_id = str(assembly.get("id") or "")
            members = assembly.get("members")
            members = members if isinstance(members, dict) else {}
            for value in members.values():
                references = value if isinstance(value, list) else [value]
                for reference in references:
                    if isinstance(reference, str):
                        result[reference] = assembly_id
        return result

    def _create_assembly_items(
        self,
        project_item: QTreeWidgetItem,
        assemblies: list[dict[str, Any]],
        read_only: bool,
    ) -> None:
        for assembly in assemblies:
            assembly_id = str(assembly.get("id") or "")
            name = str(assembly.get("name") or assembly_id or "Unnamed Assembly")
            assembly_type = self._assembly_type_text(assembly)
            item = QTreeWidgetItem([name])
            if not read_only:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setIcon(0, self._assembly_icon(assembly))
            item.setToolTip(0, f"{name} ({assembly_type})")
            item.setData(0, Qt.ItemDataRole.UserRole, assembly_id)
            self._apply_modified_color(item, assembly, self._saved_assemblies)
            self._item_map[assembly_id] = item
            self._element_map[item] = assembly
            project_item.addChild(item)

    def _create_component_items(
        self,
        components: list[dict[str, Any]],
        read_only: bool,
    ) -> None:
        for component in components:
            component_id = str(component.get("id") or "")
            name = self._component_name_text(component)
            component_type = self._component_type_text(component, components)
            item = QTreeWidgetItem([name])
            if not read_only:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            icon_source = self._geometry_icon_source(component, components)
            item.setIcon(
                0,
                (
                    self._api.get_component_icon(component)
                    if icon_source is None
                    else get_icon(icon_source)
                ),
            )
            item.setToolTip(0, f"{name} ({component_type})")
            item.setData(0, Qt.ItemDataRole.UserRole, component_id)
            self._apply_modified_color(item, component, self._saved_components)
            self._item_map[component_id] = item
            self._element_map[item] = component
            self._append_component_contributions(item, component)

    def _append_component_contributions(
        self,
        parent: QTreeWidgetItem,
        component: dict[str, Any],
    ) -> None:
        for contribution in self._api.component_tree_nodes(component):
            child = QTreeWidgetItem([contribution.title])
            if contribution.rename is not None and self._can_edit_project():
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if contribution.icon is not None:
                child.setIcon(0, get_icon(contribution.icon))
            child.setToolTip(0, contribution.tooltip or contribution.title)
            child.setData(0, Qt.ItemDataRole.UserRole, contribution.id)
            self._item_map[contribution.id] = child
            self._element_map[child] = contribution.selection
            self._virtual_items.add(child)
            self._component_contributions[child] = contribution
            parent.addChild(child)

    def _attach_component_items(
        self,
        project_item: QTreeWidgetItem,
        components: list[dict[str, Any]],
        component_assemblies: dict[str, str],
    ) -> None:
        for component in components:
            component_id = str(component.get("id") or "")
            item = self._item_map.get(component_id)
            if item is None:
                continue
            parent_id = str(component.get("parent") or "")
            parent_item = self._item_map.get(parent_id) if parent_id else None
            target = self._component_tree_parent(
                project_item,
                component,
                component_id,
                item,
                parent_item,
                component_assemblies,
                components,
            )
            target.addChild(item)

    def _component_tree_parent(
        self,
        project_item: QTreeWidgetItem,
        component: dict[str, Any],
        component_id: str,
        item: QTreeWidgetItem,
        parent_item: QTreeWidgetItem | None,
        component_assemblies: dict[str, str],
        components: list[dict[str, Any]],
    ) -> QTreeWidgetItem:
        if parent_item is not None and parent_item is not item:
            return parent_item
        if component_id in component_assemblies:
            return self._item_map.get(component_assemblies[component_id]) or project_item
        if (
            self._geometry_group_item is not None
            and self._geometry_icon_source(component, components) is not None
        ):
            return self._geometry_group_item
        return project_item

    def _restore_tree_selection(
        self,
        project: ProjectDocument,
        project_item: QTreeWidgetItem,
        selection_state: tuple[bool, bool, str | None],
    ) -> dict[str, Any] | None:
        project_selected, geometry_selected, selection_id = selection_state
        if project_selected:
            self.setCurrentItem(project_item)
            return project.data
        if geometry_selected and self._geometry_group_item is not None:
            self.setCurrentItem(self._geometry_group_item)
            return None
        if selection_id and selection_id in self._item_map:
            selected_item = self._item_map[selection_id]
            self.setCurrentItem(selected_item)
            return self._element_map.get(selected_item)
        return None

    def _append_project_contribution(
        self,
        parent: QTreeWidgetItem,
        contribution: ProjectTreeNodeContribution,
    ) -> None:
        item = QTreeWidgetItem([contribution.title])
        if contribution.rename is not None and self._can_edit_project():
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        else:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if contribution.icon is not None:
            item.setIcon(0, get_icon(contribution.icon))
        item.setToolTip(0, contribution.tooltip or contribution.title)
        item.setData(0, Qt.ItemDataRole.UserRole, contribution.id)
        self._item_map[contribution.id] = item
        self._element_map[item] = contribution.selection
        self._virtual_items.add(item)
        self._project_contributions[item] = contribution

        analysis_id = (
            contribution.selection.get("analysis_id")
            if isinstance(contribution.selection, dict)
            else None
        )
        if analysis_id:
            project = self._api.current_project
            current_entries = self._snapshot_analysis_results(project) if project else {}
            current_entry = current_entries.get(analysis_id)
            saved_entry = self._saved_analysis_results.get(analysis_id)
            if saved_entry != current_entry:
                from setuav_studio.ui.theme import status_color

                item.setForeground(
                    0,
                    QBrush(QColor(status_color("warning"))),
                )

        parent.addChild(item)
        for child in contribution.children:
            self._append_project_contribution(item, child)

    def refresh_project(self, project: ProjectDocument | None = None) -> None:
        current_project = project or self._api.current_project
        if current_project is not None:
            if hasattr(current_project, "get_configuration_manager"):
                curr_active_id = current_project.get_configuration_manager().get_active_id()
                if curr_active_id != self._last_active_config_id:
                    self._last_active_config_id = curr_active_id
                    self._capture_saved_state(current_project)
            self._rebuild_project(current_project)

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
            from setuav_studio.plugins.aerodynamics.analysis_store import (
                analysis_entries as aero_entries,
            )

            for entry in aero_entries(project):
                if isinstance(entry, dict) and (eid := str(entry.get("id") or "")):
                    results[eid] = deepcopy(entry)
        except Exception:
            pass

        try:
            from setuav_studio.plugins.flight_performance.analysis_store import (
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

    @staticmethod
    def _component_name_text(component: dict[str, object]) -> str:
        ctype = str(component.get("type") or component.get("kind") or "")
        params = (
            component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
        )
        geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}

        if ctype == "org.setuav.core:control-surface":
            name = str(component.get("name") or "").strip()
            tag = str(geom.get("tag") or "").strip()
            return name or tag or str(component.get("id") or "Unnamed")

        return str(component.get("name") or component.get("id") or "Unnamed")

    @staticmethod
    def _assembly_type_text(assembly: dict[str, object]) -> str:
        atype = str(assembly.get("type") or "Assembly")
        if atype == "org.setuav.core:electric-propulsion-system":
            return "Electric Propulsion System"
        return atype

    def _assembly_icon(self, assembly: dict[str, object]) -> Any:
        atype = str(assembly.get("type") or "")
        if atype == "org.setuav.core:electric-propulsion-system":
            return get_icon("component_propulsion_system")
        if atype in self._api._component_icons:
            return get_icon(self._api._component_icons[atype])
        return get_icon("assembly_generic")

    @staticmethod
    def _component_type_text(
        component: dict[str, object],
        components: list[dict[str, object]],
    ) -> str:
        if component.get("kind") == "instance":
            source_id = str(component.get("source") or "")
            source_name = source_id
            for candidate in components:
                if str(candidate.get("id") or "") == source_id:
                    source_name = str(candidate.get("name") or source_id)
                    break
            return f"Instance of {source_name}" if source_name else "Instance"

        ctype = str(component.get("type") or component.get("kind") or "")
        params = (
            component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
        )
        geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}

        if ctype == "org.setuav.core:control-surface":
            cs_type = str(geom.get("type", "aileron")).capitalize()
            return f"Control Surface ({cs_type})"
        if ctype == "org.setuav.core:lifting-surface":
            is_mirrored = geom.get("mirror") is True or component.get("mirror") is True
            return "Lifting Surface (Bilateral)" if is_mirrored else "Lifting Surface"
        labels = {
            "org.setuav.core:fuselage": "Fuselage",
            "org.setuav.core:motor": "Electric Motor",
            "org.setuav.core:propeller": "Propeller",
            "org.setuav.core:rotor": "Rotor",
            "org.setuav.core:esc": "ESC (Speed Controller)",
            "org.setuav.core:battery": "Battery",
        }
        return labels.get(ctype, ctype)

    @staticmethod
    def _geometry_icon_source(
        component: dict[str, Any],
        components: list[dict[str, Any]],
    ) -> str | None:
        component_type = component.get("type")
        if isinstance(component_type, str):
            icon_source = _GEOMETRY_COMPONENT_ICONS.get(component_type)
            if icon_source is not None:
                return icon_source
        if component.get("kind") != "instance":
            return None

        source_id = component.get("source")
        source = next(
            (candidate for candidate in components if candidate.get("id") == source_id),
            None,
        )
        if source is None:
            return None
        source_type = source.get("type")
        return _GEOMETRY_COMPONENT_ICONS.get(source_type) if isinstance(source_type, str) else None

    def _publish_selection(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current in (
            self._geometry_group_item,
            self._parameters_group_item,
            self._constraints_group_item,
        ):
            self._api.set_selection(None)
            return
        element = self._element_map.get(current) if current else None
        self._api.set_selection(element)

    def _sync_selection(self, selection: object | None) -> None:
        if selection is None and self.currentItem() in (
            self._geometry_group_item,
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
            self._delete_item(self.currentItem())
            event.accept()
            return
        super().keyPressEvent(event)

    def _open_context_menu(self, position: QPoint) -> None:
        item = self.itemAt(position)
        if item is None or item is self._geometry_group_item:
            return

        if item in self._virtual_items:
            self._open_virtual_context_menu(item, position)
            return

        self.setCurrentItem(item)
        can_edit = self._can_edit_project()

        if item is self._parameters_group_item or (
            item and item.text(0) in ("Constants", "Equations")
        ):
            self._open_parameters_group_menu(item, position, can_edit)
            return

        if item is self._constraints_group_item:
            self._open_constraints_group_menu(position, can_edit)
            return

        element = self._element_map.get(item)
        if element and element.get("kind") == "parameter":
            self._open_parameter_element_menu(item, element, position, can_edit)
            return

        if element and element.get("kind") == "constraint":
            self._open_constraint_element_menu(item, element, position, can_edit)
            return

        self._open_default_context_menu(item, position, can_edit)

    def _open_parameters_group_menu(
        self, item: QTreeWidgetItem, position: QPoint, can_edit: bool
    ) -> None:
        menu = QMenu(self)
        is_const = item.text(0) == "Constants"
        action_label = "Add Constant…" if is_const else "Add Parameter…"
        add_param_act = menu.addAction(get_icon("constant"), action_label)
        add_param_act.setEnabled(can_edit)
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen is add_param_act:
            self._add_parameter_action(is_constant=is_const)

    def _open_constraints_group_menu(self, position: QPoint, can_edit: bool) -> None:
        menu = QMenu(self)
        add_c_act = menu.addAction(get_icon("constraint"), "Add Constraint…")
        add_c_act.setEnabled(can_edit)
        manage_c_act = menu.addAction(get_icon("constraint"), "Manage Constraints…")
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen is add_c_act:
            self._add_constraint_action()
        elif chosen is manage_c_act:
            from setuav_studio.plugins.core.ui.constraints_dialog import ManageConstraintsDialog

            ManageConstraintsDialog(self._api, parent=self).exec()

    def _open_parameter_element_menu(
        self, item: QTreeWidgetItem, element: dict[str, Any], position: QPoint, can_edit: bool
    ) -> None:
        menu = QMenu(self)
        fx_act = menu.addAction(get_icon("settings"), "Edit with fx Assistant…")
        fx_act.setEnabled(can_edit)
        del_act = menu.addAction(get_icon("remove"), "Delete")
        del_act.setEnabled(can_edit)
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen is fx_act:
            self._edit_parameter_fx(element)
        elif chosen is del_act:
            self._delete_item(item)

    def _open_constraint_element_menu(
        self, item: QTreeWidgetItem, element: dict[str, Any], position: QPoint, can_edit: bool
    ) -> None:
        menu = QMenu(self)
        fx_act = menu.addAction(get_icon("settings"), "Edit with fx Assistant…")
        fx_act.setEnabled(can_edit)
        toggle_act = menu.addAction("Toggle Enabled")
        toggle_act.setEnabled(can_edit)
        del_act = menu.addAction(get_icon("remove"), "Delete")
        del_act.setEnabled(can_edit)
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen is fx_act:
            self._edit_constraint_fx(element)
        elif chosen is toggle_act:
            self._toggle_constraint(element)
        elif chosen is del_act:
            self._delete_item(item)

    def _open_default_context_menu(
        self, item: QTreeWidgetItem, position: QPoint, can_edit: bool
    ) -> None:
        menu = QMenu(self)
        rename_action = menu.addAction(get_icon("edit"), "Rename")
        rename_action.setEnabled(can_edit)
        delete_action = None
        if item is not self._project_root_item:
            delete_action = menu.addAction(get_icon("remove"), "Delete")
            delete_action.setEnabled(can_edit)

        chosen_action = menu.exec(self.viewport().mapToGlobal(position))
        if chosen_action is rename_action:
            self.editItem(item, 0)
        elif delete_action is not None and chosen_action is delete_action:
            self._delete_item(item)

    def _open_virtual_context_menu(self, item: QTreeWidgetItem, position: QPoint) -> None:
        contribution = self._project_contributions.get(item) or self._component_contributions.get(
            item
        )
        if contribution is None or (contribution.rename is None and contribution.delete is None):
            return
        self.setCurrentItem(item)
        menu = QMenu(self)
        rename_action = menu.addAction(get_icon("edit"), "Rename") if contribution.rename else None
        delete_action = (
            menu.addAction(get_icon("remove"), "Delete") if contribution.delete else None
        )
        for action in (rename_action, delete_action):
            if action is not None:
                action.setEnabled(self._can_edit_project())
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if rename_action is not None and chosen is rename_action:
            self.editItem(item, 0)
        elif delete_action is not None and chosen is delete_action:
            self._delete_item(item)

    def _rename_item(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        contribution = self._project_contributions.get(item) or self._component_contributions.get(
            item
        )
        if contribution is not None:
            self._rename_contribution(item, contribution)
            return
        element = self._element_map.get(item)
        if element is None:
            return

        element_id = str(element.get("id") or "")
        kind = "project" if item is self._project_root_item else self._element_kind(element_id)
        old_name = str(element.get("name") or "").strip()
        old_label = (
            str(element.get("name") or element_id or "Unnamed Project")
            if kind in {"project", "assembly"}
            else self._component_name_text(element)
        )
        new_name = item.text(0).strip()
        if not self._can_edit_project():
            self._restore_item_text(item, old_label)
            return
        if not new_name:
            self._restore_item_text(item, old_label)
            self._api.show_status("Name cannot be empty", "warning", 3000)
            return
        if new_name == old_name:
            self._restore_item_text(item, new_name)
            return

        def change() -> None:
            fresh_element = self._find_element(element_id, kind)
            if fresh_element is not None:
                fresh_element["name"] = new_name

        description = (
            f"Rename project to {new_name}"
            if kind == "project"
            else f"Rename {old_label} to {new_name}"
        )
        self._api.edit_project(description, change)
        fresh_element = self._find_element(element_id, kind)
        if fresh_element is not None:
            self._api.set_selection(fresh_element)
        self._api.show_status(f'Renamed "{old_label}" to "{new_name}"', "success", 3000)

    def _rename_contribution(
        self, item: QTreeWidgetItem, contribution: ProjectTreeNodeContribution
    ) -> None:
        old_name = contribution.title
        new_name = item.text(0).strip()
        if not self._can_edit_project() or contribution.rename is None:
            self._restore_item_text(item, old_name)
            return
        if not new_name:
            self._restore_item_text(item, old_name)
            self._api.show_status("Name cannot be empty", "warning", 3000)
            return
        if new_name == old_name:
            return
        contribution.rename(new_name)
        self._api.show_status(f'Renamed "{old_name}" to "{new_name}"', "success", 3000)

    def _delete_item(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        if item in self._virtual_items:
            self._delete_virtual_item(item)
            return
        if item in (
            self._project_root_item,
            self._geometry_group_item,
            self._parameters_group_item,
            self._constraints_group_item,
        ):
            return
        if not self._can_edit_project():
            self._api.show_status("This project is read-only", "warning", 3000)
            return

        element = self._element_map.get(item)
        if element is None:
            return

        kind = element.get("kind")
        if kind == "parameter":
            self._delete_parameter_item(element)
        elif kind == "constraint":
            self._delete_constraint_item(element)
        else:
            self._delete_component_item(element)

    def _delete_parameter_item(self, element: dict[str, Any]) -> None:
        param_name = str(element.get("key") or "")
        if not self._confirm_delete(f"Parameter '{param_name}'", []):
            return

        def _apply_param_del() -> None:
            pdata = self._api.current_project.data if self._api.current_project else {}
            pdata.get("parameters", {}).pop(param_name, None)

        self._api.set_selection(None)
        self._api.edit_project(f"Delete parameter '{param_name}'", _apply_param_del)
        self._api.show_status(f'Deleted parameter "{param_name}"', "success", 3000)

    def _delete_constraint_item(self, element: dict[str, Any]) -> None:
        cid = str(element.get("id") or "")
        cname = str(element.get("name") or cid)
        if not self._confirm_delete(f"Constraint '{cname}'", []):
            return

        def _apply_c_del() -> None:
            pdata = self._api.current_project.data if self._api.current_project else {}
            constraints = pdata.get("constraints", [])
            pdata["constraints"] = [c for c in constraints if c.get("id") != cid]

        self._api.set_selection(None)
        self._api.edit_project(f"Delete constraint '{cname}'", _apply_c_del)
        self._api.show_status(f'Deleted constraint "{cname}"', "success", 3000)

    def _delete_component_item(self, element: dict[str, Any]) -> None:
        element_id = str(element.get("id") or "")
        if not element_id:
            return
        element_name = str(element.get("name") or element_id)
        kind = self._element_kind(element_id)
        component_ids, assembly_ids = self._deletion_scope(
            element,
            element_id,
            kind,
        )
        details = self._deletion_details(
            element_id,
            kind,
            component_ids,
            assembly_ids,
        )
        if not self._confirm_delete(element_name, details):
            return

        def change() -> None:
            self._apply_deletion(component_ids, assembly_ids)

        self._api.set_selection(None)
        self._api.edit_project(f"Delete {element_name}", change)
        self._api.show_status(f'Deleted "{element_name}"', "success", 3000)

    def _delete_virtual_item(self, item: QTreeWidgetItem) -> None:
        contribution = self._project_contributions.get(item) or self._component_contributions.get(
            item
        )
        if contribution is None or contribution.delete is None:
            return
        if not self._can_edit_project():
            self._api.show_status("This project is read-only", "warning", 3000)
            return
        confirmed = self._confirm_delete(contribution.title, [])
        if confirmed:
            contribution.delete()

    def _deletion_scope(
        self,
        element: dict[str, Any],
        element_id: str,
        kind: str,
    ) -> tuple[set[str], set[str]]:
        if kind == "assembly":
            member_ids = self._assembly_member_ids(element)
            component_ids = self._dependent_component_ids_from(member_ids)
            assembly_ids = {element_id}
            assembly_ids.update(self._assemblies_invalidated_by(component_ids))
            return component_ids, assembly_ids
        component_ids = self._dependent_component_ids(element_id)
        return component_ids, self._assemblies_invalidated_by(component_ids)

    @staticmethod
    def _deletion_details(
        element_id: str,
        kind: str,
        component_ids: set[str],
        assembly_ids: set[str],
    ) -> list[str]:
        details: list[str] = []
        if kind == "assembly" and component_ids:
            details.append(
                f"All {len(component_ids)} member and dependent component(s) will also be deleted."
            )
        elif kind != "assembly":
            dependent_count = max(0, len(component_ids) - 1)
            if dependent_count:
                details.append(
                    f"{dependent_count} structurally dependent item(s) will also be deleted."
                )
        additional_assemblies = assembly_ids - {element_id}
        if additional_assemblies:
            details.append(
                f"{len(additional_assemblies)} other assembly group(s) that would "
                "become invalid will also be removed; their remaining components will be kept."
            )
        return details

    def _confirm_delete(self, title: str, details: list[str]) -> bool:
        detail_text = "\n\n" + "\n".join(details) if details else ""
        answer = QMessageBox.question(
            self,
            "Delete Project Item",
            f'Delete "{title}"?{detail_text}\n\nThis action can be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _apply_deletion(
        self,
        component_ids: set[str],
        assembly_ids: set[str],
    ) -> None:
        project = self._api.current_project
        if project is None:
            return
        components = project.data.get("components")
        if isinstance(components, list) and component_ids:
            components[:] = [
                component
                for component in components
                if not (
                    isinstance(component, dict) and str(component.get("id") or "") in component_ids
                )
            ]
            self._clear_deleted_component_links(components, component_ids)

        assemblies = project.data.get("assemblies")
        if isinstance(assemblies, list):
            assemblies[:] = [
                assembly
                for assembly in assemblies
                if not (
                    isinstance(assembly, dict) and str(assembly.get("id") or "") in assembly_ids
                )
            ]
            self._remove_assembly_member_references(assemblies, component_ids)

    @staticmethod
    def _clear_deleted_component_links(
        components: list[Any],
        component_ids: set[str],
    ) -> None:
        for component in components:
            if not isinstance(component, dict):
                continue
            if str(component.get("attach_to") or "") in component_ids:
                component["attach_to"] = None
            if str(component.get("parent") or "") in component_ids:
                component["parent"] = None

    def _can_edit_project(self) -> bool:
        project = self._api.current_project
        return project is not None and not project.read_only

    def _element_kind(self, element_id: str) -> str:
        project = self._api.current_project
        if project is not None:
            assemblies = project.data.get("assemblies")
            if isinstance(assemblies, list):
                for assembly in assemblies:
                    if isinstance(assembly, dict) and str(assembly.get("id") or "") == element_id:
                        return "assembly"
        return "component"

    def _find_element(
        self,
        element_id: str,
        kind: str,
    ) -> dict[str, Any] | None:
        project = self._api.current_project
        if project is None:
            return None
        if kind == "project":
            return project.data
        collection_name = "assemblies" if kind == "assembly" else "components"
        collection = project.data.get(collection_name)
        if not isinstance(collection, list):
            return None
        return next(
            (
                element
                for element in collection
                if isinstance(element, dict) and str(element.get("id") or "") == element_id
            ),
            None,
        )

    def _dependent_component_ids(self, root_id: str) -> set[str]:
        return self._dependent_component_ids_from({root_id})

    def _dependent_component_ids_from(self, root_ids: set[str]) -> set[str]:
        project = self._api.current_project
        components = project.data.get("components") if project is not None else None
        if not isinstance(components, list):
            return set(root_ids)

        deleted_ids = set(root_ids)
        changed = True
        while changed:
            changed = False
            for component in components:
                if not isinstance(component, dict):
                    continue
                component_id = str(component.get("id") or "")
                if not component_id or component_id in deleted_ids:
                    continue
                structural_parent = str(component.get("parent") or "")
                source = str(component.get("source") or "")
                if structural_parent in deleted_ids or source in deleted_ids:
                    deleted_ids.add(component_id)
                    changed = True
        return deleted_ids

    @staticmethod
    def _assembly_member_ids(assembly: dict[str, Any]) -> set[str]:
        members = assembly.get("members")
        if not isinstance(members, dict):
            return set()
        member_ids: set[str] = set()
        for member in members.values():
            if isinstance(member, str) and member:
                member_ids.add(member)
            elif isinstance(member, list):
                member_ids.update(value for value in member if isinstance(value, str) and value)
        return member_ids

    def _assemblies_invalidated_by(self, component_ids: set[str]) -> set[str]:
        project = self._api.current_project
        assemblies = project.data.get("assemblies") if project is not None else None
        if not isinstance(assemblies, list) or not component_ids:
            return set()

        invalidated: set[str] = set()
        for assembly in assemblies:
            if not isinstance(assembly, dict):
                continue
            members = assembly.get("members")
            if not isinstance(members, dict):
                continue
            for member in members.values():
                if isinstance(member, str) and member in component_ids:
                    invalidated.add(str(assembly.get("id") or ""))
                    break
                if isinstance(member, list):
                    remaining = [value for value in member if value not in component_ids]
                    if member and not remaining:
                        invalidated.add(str(assembly.get("id") or ""))
                        break
        invalidated.discard("")
        return invalidated

    @staticmethod
    def _remove_assembly_member_references(
        assemblies: list[Any],
        component_ids: set[str],
    ) -> None:
        if not component_ids:
            return
        for assembly in assemblies:
            if not isinstance(assembly, dict):
                continue
            members = assembly.get("members")
            if not isinstance(members, dict):
                continue
            for role, member in list(members.items()):
                if isinstance(member, str) and member in component_ids:
                    members.pop(role)
                elif isinstance(member, list):
                    members[role] = [value for value in member if value not in component_ids]

    def _restore_item_text(self, item: QTreeWidgetItem, text: str) -> None:
        previous = self.blockSignals(True)
        try:
            item.setText(0, text)
        finally:
            self.blockSignals(previous)

    def _add_parameter_action(self, is_constant: bool = False) -> None:
        from PySide6.QtWidgets import QDialog

        from setuav_studio.plugins.core.ui.parameters_dialog import AddParameterDialog

        data = self._api.current_project.data if self._api.current_project else {}
        raw = data.setdefault("parameters", {})
        dlg = AddParameterDialog(
            api=self._api,
            existing_names=set(raw.keys()),
            is_constant=is_constant,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            param_name, param_val = dlg.get_data()

            def _apply() -> None:
                pdata = self._api.current_project.data if self._api.current_project else {}
                pdata.setdefault("parameters", {})[param_name] = param_val

            action_name = "constant" if is_constant else "parameter"
            self._api.edit_project(f"Add {action_name} '{param_name}'", _apply)

    def _add_constraint_action(self) -> None:
        from PySide6.QtWidgets import QDialog

        from setuav_studio.plugins.core.ui.constraints_dialog import ConstraintEditDialog

        dlg = ConstraintEditDialog(
            self,
            api=self._api,
            project_data=self._api.current_project.data if self._api.current_project else {},
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()

            def _apply() -> None:
                pdata = self._api.current_project.data if self._api.current_project else {}
                pdata.setdefault("constraints", []).append(data)

            self._api.edit_project(f"Add constraint '{data['name']}'", _apply)

    def _edit_parameter_fx(self, element: dict[str, Any]) -> None:
        from PySide6.QtWidgets import QDialog

        from setuav_studio.plugins.core.ui.expression_dialog import AdvancedExpressionDialog

        param_key = str(element.get("key") or "")
        val = str(element.get("value") or "")
        dlg = AdvancedExpressionDialog(
            self._api,
            initial_expression=val,
            title=f"Equation Assistant — {param_key}",
            is_boolean_constraint=False,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_expr = dlg.get_expression()

            def _apply() -> None:
                pdata = self._api.current_project.data if self._api.current_project else {}
                pdata.setdefault("parameters", {})[param_key] = new_expr

            self._api.edit_project(f"Edit parameter '{param_key}'", _apply)

    def _edit_constraint_fx(self, element: dict[str, Any]) -> None:
        from PySide6.QtWidgets import QDialog

        from setuav_studio.plugins.core.ui.constraints_dialog import ConstraintEditDialog

        cid = str(element.get("id") or "")
        dlg = ConstraintEditDialog(
            self,
            initial_data=element,
            api=self._api,
            project_data=self._api.current_project.data if self._api.current_project else {},
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_data()

            def _apply() -> None:
                pdata = self._api.current_project.data if self._api.current_project else {}
                constraints = pdata.get("constraints", [])
                for i, c in enumerate(constraints):
                    if c.get("id") == cid:
                        constraints[i] = updated
                        break

            self._api.edit_project(f"Edit constraint '{updated['name']}'", _apply)

    def _toggle_constraint(self, element: dict[str, Any]) -> None:
        cid = str(element.get("id") or "")

        def _apply() -> None:
            pdata = self._api.current_project.data if self._api.current_project else {}
            for c in pdata.get("constraints", []):
                if c.get("id") == cid:
                    c["enabled"] = not c.get("enabled", True)
                    break

        self._api.edit_project("Toggle constraint", _apply)
