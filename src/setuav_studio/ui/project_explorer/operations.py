from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QMessageBox, QTreeWidgetItem, QWidget

from setuav_studio.ui.project_explorer.style import (
    format_component_name,
)

if TYPE_CHECKING:
    from setuav_studio.ui.project_explorer.tree import ProjectExplorer
    from setuav_studio_sdk import ProjectTreeNodeContribution, StudioAPI


class ProjectExplorerOperations:
    """Handles project explorer data mutations, deletions, renaming, and dialogs."""

    def __init__(self, tree: ProjectExplorer, api: StudioAPI) -> None:
        self._tree = tree
        self._api = api

    def can_edit_project(self) -> bool:
        project = self._api.current_project
        return project is not None and not project.read_only

    def element_kind(self, element_id: str) -> str:
        project = self._api.current_project
        if project is not None:
            assemblies = project.data.get("assemblies")
            if isinstance(assemblies, list):
                for assembly in assemblies:
                    if isinstance(assembly, dict) and str(assembly.get("id") or "") == element_id:
                        return "assembly"
        return "component"

    def find_element(self, element_id: str, kind: str) -> dict[str, Any] | None:
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

    def dependent_component_ids(self, root_id: str) -> set[str]:
        return self.dependent_component_ids_from({root_id})

    def dependent_component_ids_from(self, root_ids: set[str]) -> set[str]:
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
    def assembly_member_ids(assembly: dict[str, Any]) -> set[str]:
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

    def assemblies_invalidated_by(self, component_ids: set[str]) -> set[str]:
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

    def deletion_scope(
        self,
        element: dict[str, Any],
        element_id: str,
        kind: str,
    ) -> tuple[set[str], set[str]]:
        if kind == "assembly":
            member_ids = self.assembly_member_ids(element)
            component_ids = self.dependent_component_ids_from(member_ids)
            assembly_ids = {element_id}
            assembly_ids.update(self.assemblies_invalidated_by(component_ids))
            return component_ids, assembly_ids
        component_ids = self.dependent_component_ids(element_id)
        return component_ids, self.assemblies_invalidated_by(component_ids)

    @staticmethod
    def deletion_details(
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

    def confirm_delete(
        self,
        title: str,
        details: list[str],
        parent: QWidget | None = None,
    ) -> bool:
        detail_text = "\n\n" + "\n".join(details) if details else ""
        widget = parent or self._tree
        answer = QMessageBox.question(
            widget,
            "Delete Project Item",
            f'Delete "{title}"?{detail_text}\n\nThis action can be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def apply_deletion(
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
            self.clear_deleted_component_links(components, component_ids)

        assemblies = project.data.get("assemblies")
        if isinstance(assemblies, list):
            assemblies[:] = [
                assembly
                for assembly in assemblies
                if not (
                    isinstance(assembly, dict) and str(assembly.get("id") or "") in assembly_ids
                )
            ]
            self.remove_assembly_member_references(assemblies, component_ids)

    @staticmethod
    def clear_deleted_component_links(
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

    @staticmethod
    def remove_assembly_member_references(
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

    def delete_item(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        if item in self._tree._virtual_items:
            self.delete_virtual_item(item)
            return
        if item in (
            self._tree._project_root_item,
            self._tree._geometry_group_item,
            self._tree._parameters_group_item,
            self._tree._constraints_group_item,
        ):
            return
        if not self.can_edit_project():
            self._api.show_status("This project is read-only", "warning", 3000)
            return

        element = self._tree._element_map.get(item)
        if element is None:
            return

        kind = element.get("kind")
        if kind == "parameter":
            self.delete_parameter_item(element)
        elif kind == "constraint":
            self.delete_constraint_item(element)
        else:
            self.delete_component_item(element)

    def delete_virtual_item(self, item: QTreeWidgetItem) -> None:
        contribution = self._tree._project_contributions.get(
            item
        ) or self._tree._component_contributions.get(item)
        if contribution is None or contribution.delete is None:
            return
        if not self.can_edit_project():
            self._api.show_status("This project is read-only", "warning", 3000)
            return
        confirmed = self.confirm_delete(contribution.title, [])
        if confirmed:
            contribution.delete()

    def delete_parameter_item(self, element: dict[str, Any]) -> None:
        param_name = str(element.get("key") or "")
        if not self.confirm_delete(f"Parameter '{param_name}'", []):
            return

        def _apply_param_del() -> None:
            pdata = self._api.current_project.data if self._api.current_project else {}
            pdata.get("parameters", {}).pop(param_name, None)

        self._api.set_selection(None)
        self._api.edit_project(f"Delete parameter '{param_name}'", _apply_param_del)
        self._api.show_status(f'Deleted parameter "{param_name}"', "success", 3000)

    def delete_constraint_item(self, element: dict[str, Any]) -> None:
        cid = str(element.get("id") or "")
        cname = str(element.get("name") or cid)
        if not self.confirm_delete(f"Constraint '{cname}'", []):
            return

        def _apply_c_del() -> None:
            pdata = self._api.current_project.data if self._api.current_project else {}
            constraints = pdata.get("constraints", [])
            pdata["constraints"] = [c for c in constraints if c.get("id") != cid]

        self._api.set_selection(None)
        self._api.edit_project(f"Delete constraint '{cname}'", _apply_c_del)
        self._api.show_status(f'Deleted constraint "{cname}"', "success", 3000)

    def delete_component_item(self, element: dict[str, Any]) -> None:
        element_id = str(element.get("id") or "")
        if not element_id:
            return
        element_name = str(element.get("name") or element_id)
        kind = self.element_kind(element_id)
        component_ids, assembly_ids = self.deletion_scope(
            element,
            element_id,
            kind,
        )
        details = self.deletion_details(
            element_id,
            kind,
            component_ids,
            assembly_ids,
        )
        if not self.confirm_delete(element_name, details):
            return

        def change() -> None:
            self.apply_deletion(component_ids, assembly_ids)

        self._api.set_selection(None)
        self._api.edit_project(f"Delete {element_name}", change)
        self._api.show_status(f'Deleted "{element_name}"', "success", 3000)

    def rename_item(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        contribution = self._tree._project_contributions.get(
            item
        ) or self._tree._component_contributions.get(item)
        if contribution is not None:
            self.rename_contribution(item, contribution)
            return
        element = self._tree._element_map.get(item)
        if element is None:
            return

        element_id = str(element.get("id") or "")
        kind = "project" if item is self._tree._project_root_item else self.element_kind(element_id)
        old_name = str(element.get("name") or "").strip()
        old_label = (
            str(element.get("name") or element_id or "Unnamed Project")
            if kind in {"project", "assembly"}
            else format_component_name(element)
        )
        new_name = item.text(0).strip()
        if not self.can_edit_project():
            self.restore_item_text(item, old_label)
            return
        if not new_name:
            self.restore_item_text(item, old_label)
            self._api.show_status("Name cannot be empty", "warning", 3000)
            return
        if new_name == old_name:
            self.restore_item_text(item, new_name)
            return

        def change() -> None:
            fresh_element = self.find_element(element_id, kind)
            if fresh_element is not None:
                fresh_element["name"] = new_name

        description = (
            f"Rename project to {new_name}"
            if kind == "project"
            else f"Rename {old_label} to {new_name}"
        )
        self._api.edit_project(description, change)
        fresh_element = self.find_element(element_id, kind)
        if fresh_element is not None:
            self._api.set_selection(fresh_element)
        self._api.show_status(f'Renamed "{old_label}" to "{new_name}"', "success", 3000)

    def rename_contribution(
        self,
        item: QTreeWidgetItem,
        contribution: ProjectTreeNodeContribution,
    ) -> None:
        old_name = contribution.title
        new_name = item.text(0).strip()
        if not self.can_edit_project() or contribution.rename is None:
            self.restore_item_text(item, old_name)
            return
        if not new_name:
            self.restore_item_text(item, old_name)
            self._api.show_status("Name cannot be empty", "warning", 3000)
            return
        if new_name == old_name:
            return
        contribution.rename(new_name)
        self._api.show_status(f'Renamed "{old_name}" to "{new_name}"', "success", 3000)

    def restore_item_text(self, item: QTreeWidgetItem, text: str) -> None:
        previous = self._tree.blockSignals(True)
        try:
            item.setText(0, text)
        finally:
            self._tree.blockSignals(previous)

    def add_parameter_action(
        self, is_constant: bool = False, parent: QWidget | None = None
    ) -> None:
        from setuav_studio.ui.project_explorer.dialog_actions import (
            add_parameter_action,
        )

        add_parameter_action(self._api, self._tree, is_constant=is_constant, parent=parent)

    def add_constraint_action(self, parent: QWidget | None = None) -> None:
        from setuav_studio.ui.project_explorer.dialog_actions import (
            add_constraint_action,
        )

        add_constraint_action(self._api, self._tree, parent=parent)

    def edit_parameter_fx(self, element: dict[str, Any], parent: QWidget | None = None) -> None:
        from setuav_studio.ui.project_explorer.dialog_actions import (
            edit_parameter_fx,
        )

        edit_parameter_fx(self._api, self._tree, element, parent=parent)

    def edit_constraint_fx(self, element: dict[str, Any], parent: QWidget | None = None) -> None:
        from setuav_studio.ui.project_explorer.dialog_actions import (
            edit_constraint_fx,
        )

        edit_constraint_fx(self._api, self._tree, element, parent=parent)

    def toggle_constraint(self, element: dict[str, Any]) -> None:
        from setuav_studio.ui.project_explorer.dialog_actions import (
            toggle_constraint,
        )

        toggle_constraint(self._api, self._tree, element)
