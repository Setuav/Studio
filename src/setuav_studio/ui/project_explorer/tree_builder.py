from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTreeWidgetItem

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.project_explorer.style import (
    format_assembly_icon,
    format_assembly_type,
    format_component_name,
    format_component_type,
    get_geometry_icon_source,
)

if TYPE_CHECKING:
    from setuav_studio.project import ProjectDocument
    from setuav_studio.ui.project_explorer.tree import ProjectExplorer
    from setuav_studio_sdk import (
        ProjectTreeNodeContribution,
        StudioAPI,
    )


class ProjectTreeBuilder:
    """Builds and populates the project explorer tree items from project data."""

    def __init__(self, tree: ProjectExplorer, api: StudioAPI) -> None:
        self._tree = tree
        self._api = api

    def rebuild_project(self, project: ProjectDocument) -> None:
        selection_state = self._tree._tree_selection_state(project)
        fresh_selection: dict[str, Any] | None = None
        self._tree.blockSignals(True)
        try:
            self.reset_project_tree()
            project_item = self.create_project_item(project)
            components, assemblies = self.project_elements(project)
            component_assemblies = self.component_assembly_map(assemblies)
            self.create_assembly_items(project_item, assemblies, project.read_only)
            self.create_component_items(components, project.read_only)
            self.attach_component_items(
                project_item,
                components,
                component_assemblies,
            )
            self.create_parameters_group(project_item, project)
            self.create_constraints_group(project_item, project)
            for contribution in self._api.project_tree_nodes(project):
                self.append_project_contribution(project_item, contribution)
            self._tree.expandAll()
            fresh_selection = self._tree._restore_tree_selection(
                project,
                project_item,
                selection_state,
            )
        finally:
            self._tree.blockSignals(False)

        current_selection_id = selection_state[1]
        if current_selection_id and self._api.current_selection is not fresh_selection:
            self._api.set_selection(fresh_selection)

    def reset_project_tree(self) -> None:
        self._tree.clear()
        self._tree._item_map.clear()
        self._tree._element_map.clear()
        self._tree._project_root_item = None
        self._tree._parameters_group_item = None
        self._tree._constraints_group_item = None
        self._tree._virtual_items.clear()
        self._tree._project_contributions.clear()
        self._tree._component_contributions.clear()

    def create_project_item(self, project: ProjectDocument) -> QTreeWidgetItem:
        project_name = str(project.data.get("name") or project.location.name or "Unnamed Project")
        item = QTreeWidgetItem([project_name])
        if not project.read_only:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setToolTip(0, f"Project: {project_name}")
        self._tree._element_map[item] = project.data
        self._tree._project_root_item = item
        self._tree.addTopLevelItem(item)
        return item

    @staticmethod
    def project_elements(
        project: ProjectDocument,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        components = project.data.get("components", [])
        assemblies = project.data.get("assemblies", [])
        return (
            [item for item in components if isinstance(item, dict)],
            [item for item in assemblies if isinstance(item, dict)],
        )

    def create_parameters_group(
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
        self._tree._parameters_group_item = const_group
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
            self._tree._element_map[item] = param_payload
            self._tree._item_map[f"param_{k}"] = item
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
                self._tree._element_map[item] = param_payload
                self._tree._item_map[f"param_{k}"] = item
                eq_group.addChild(item)

    def create_constraints_group(
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
        self._tree._constraints_group_item = constraint_group
        project_item.addChild(constraint_group)

        from setuav_studio.model.constraint import ConstraintChecker

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
            self._tree._element_map[item] = constraint_payload
            self._tree._item_map[cid] = item
            constraint_group.addChild(item)

    @staticmethod
    def component_assembly_map(
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

    def create_assembly_items(
        self,
        project_item: QTreeWidgetItem,
        assemblies: list[dict[str, Any]],
        read_only: bool,
    ) -> None:
        for assembly in assemblies:
            assembly_id = str(assembly.get("id") or "")
            name = str(assembly.get("name") or assembly_id or "Unnamed Assembly")
            assembly_type = format_assembly_type(assembly)
            item = QTreeWidgetItem([name])
            if not read_only:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setIcon(0, format_assembly_icon(assembly, self._api))
            item.setToolTip(0, f"{name} ({assembly_type})")
            item.setData(0, Qt.ItemDataRole.UserRole, assembly_id)
            self._tree._apply_modified_color(item, assembly, self._tree._saved_assemblies)
            self._tree._item_map[assembly_id] = item
            self._tree._element_map[item] = assembly
            project_item.addChild(item)

    def create_component_items(
        self,
        components: list[dict[str, Any]],
        read_only: bool,
    ) -> None:
        for component in components:
            component_id = str(component.get("id") or "")
            name = format_component_name(component)
            component_type = format_component_type(component, components)
            item = QTreeWidgetItem([name])
            if not read_only:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            icon_source = get_geometry_icon_source(component, components)
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
            self._tree._apply_modified_color(item, component, self._tree._saved_components)
            self._tree._item_map[component_id] = item
            self._tree._element_map[item] = component
            self.append_component_contributions(item, component)

    def append_component_contributions(
        self,
        parent: QTreeWidgetItem,
        component: dict[str, Any],
    ) -> None:
        for contribution in self._api.component_tree_nodes(component):
            child = QTreeWidgetItem([contribution.title])
            if contribution.rename is not None and self._tree._can_edit_project():
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if contribution.icon is not None:
                child.setIcon(0, get_icon(contribution.icon))
            child.setToolTip(0, contribution.tooltip or contribution.title)
            child.setData(0, Qt.ItemDataRole.UserRole, contribution.id)
            self._tree._item_map[contribution.id] = child
            self._tree._element_map[child] = contribution.selection
            self._tree._virtual_items.add(child)
            self._tree._component_contributions[child] = contribution
            parent.addChild(child)

    def attach_component_items(
        self,
        project_item: QTreeWidgetItem,
        components: list[dict[str, Any]],
        component_assemblies: dict[str, str],
    ) -> None:
        for component in components:
            component_id = str(component.get("id") or "")
            item = self._tree._item_map.get(component_id)
            if item is None:
                continue
            parent_id = str(component.get("parent") or component.get("attach_to") or "")
            parent_item = self._tree._item_map.get(parent_id) if parent_id else None
            target = self.component_tree_parent(
                project_item,
                component,
                component_id,
                item,
                parent_item,
                component_assemblies,
                components,
            )
            target.addChild(item)

    def component_tree_parent(
        self,
        project_item: QTreeWidgetItem,
        component: dict[str, Any],
        component_id: str,
        item: QTreeWidgetItem,
        parent_item: QTreeWidgetItem | None,
        component_assemblies: dict[str, str],
        components: list[dict[str, Any]],
    ) -> QTreeWidgetItem:
        if component_id in component_assemblies:
            return self._tree._item_map.get(component_assemblies[component_id]) or project_item
        if parent_item is not None and parent_item is not item:
            return parent_item
        return project_item

    def append_project_contribution(
        self,
        parent: QTreeWidgetItem,
        contribution: ProjectTreeNodeContribution,
    ) -> None:
        item = QTreeWidgetItem([contribution.title])
        if contribution.rename is not None and self._tree._can_edit_project():
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        else:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if contribution.icon is not None:
            item.setIcon(0, get_icon(contribution.icon))
        item.setToolTip(0, contribution.tooltip or contribution.title)
        item.setData(0, Qt.ItemDataRole.UserRole, contribution.id)
        self._tree._item_map[contribution.id] = item
        self._tree._element_map[item] = contribution.selection
        self._tree._virtual_items.add(item)
        self._tree._project_contributions[item] = contribution

        analysis_id = (
            contribution.selection.get("analysis_id")
            if isinstance(contribution.selection, dict)
            else None
        )
        if analysis_id:
            project = self._api.current_project
            current_entries = self._tree._snapshot_analysis_results(project) if project else {}
            current_entry = current_entries.get(analysis_id)
            saved_entry = self._tree._saved_analysis_results.get(analysis_id)
            if saved_entry != current_entry:
                from setuav_studio.ui.theme import status_color

                item.setForeground(
                    0,
                    QBrush(QColor(status_color("warning"))),
                )

        parent.addChild(item)
        for child in contribution.children:
            self.append_project_contribution(item, child)
