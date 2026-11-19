from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QMessageBox, QTreeWidgetItem, QWidget

from setuav_studio.ui.panels.project_explorer.style import (
    format_component_name,
)

if TYPE_CHECKING:
    from setuav_studio.api import (
        ComponentTreeNodeContribution,
        ProjectTreeNodeContribution,
        StudioAPI,
    )
    from setuav_studio.ui.panels.project_explorer.tree import ProjectExplorer


class ProjectExplorerOperations:
    """Handles project explorer data mutations, deletions, renaming, and dialogs."""

    def __init__(self, tree: ProjectExplorer, api: StudioAPI) -> None:
        self._tree = tree
        self._api = api

    def can_edit_project(self) -> bool:
        project = self._api.project
        return project is not None and not project.read_only

    def find_component(self, component_id: str) -> dict[str, Any] | None:
        project = self._api.project
        return project.get_component(component_id) if project is not None else None

    @staticmethod
    def deletion_details(component_ids: frozenset[str]) -> list[str]:
        details: list[str] = []
        dependent_count = max(0, len(component_ids) - 1)
        if dependent_count:
            details.append(f"{dependent_count} subpart(s) and instance(s) will also be deleted.")
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

    def delete_item(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        if item in self._tree._virtual_items:
            self.delete_virtual_item(item)
            return
        if item in (
            self._tree._vehicle_item,
            self._tree._parameters_group_item,
            self._tree._constraints_group_item,
            self._tree._analysis_group_item,
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
        elif kind == "analysis_config":
            self.delete_analysis_config_item(element)
        elif kind in ("analysis_table", "analysis_plot"):
            return
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
        pdata = self._api.project.data if self._api.project else {}
        from setuav_studio.model.expression import find_symbol_usages_in_project

        usages = find_symbol_usages_in_project(pdata, param_name)
        details: list[str] = []
        if usages:
            details.append(f"WARNING: Referenced in {len(usages)} expression(s):")
            for loc, expr in usages[:5]:
                details.append(f"• {loc}: {expr}")
            if len(usages) > 5:
                details.append(f"... and {len(usages) - 5} more")
            details.append("Deleting will break these expressions (#REF!).")

        if not self.confirm_delete(f"Parameter '{param_name}'", details):
            return

        def _apply_param_del() -> None:
            pdata = self._api.project.data if self._api.project else {}
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
            pdata = self._api.project.data if self._api.project else {}
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
        component_ids = self._api.component_deletion_scope({element_id})
        details = self.deletion_details(component_ids)

        pdata = self._api.project.data if self._api.project else {}
        from setuav_studio.model.expression import find_symbol_usages_in_project

        all_usages: list[tuple[str, str]] = []
        for cid in component_ids:
            all_usages.extend(find_symbol_usages_in_project(pdata, cid))

        if all_usages:
            details.append(f"WARNING: Referenced in {len(all_usages)} expression(s):")
            for loc, expr in all_usages[:5]:
                details.append(f"• {loc}: {expr}")
            if len(all_usages) > 5:
                details.append(f"... and {len(all_usages) - 5} more")
            details.append("Deleting will break these expressions (#REF!).")

        if not self.confirm_delete(element_name, details):
            return

        self._api.set_selection(None)
        self._api.delete_components(component_ids, f"Delete {element_name}")
        self._api.show_status(f'Deleted "{element_name}"', "success", 3000)

    def delete_analysis_config_item(self, element: dict[str, Any]) -> None:
        config_id = str(element["config_id"])
        name = str(element.get("name") or "Analysis")

        project = self._api.project
        if project is None:
            return

        matching_results = [
            r_id
            for r_id, r in project.solver_results.items()
            if getattr(getattr(r, "config", None), "config_id", None) == config_id
        ]
        details: list[str] = []
        if matching_results:
            details.append(
                f"{len(matching_results)} completed analysis result(s) will also be deleted."
            )

        if not self.confirm_delete(f"Analysis '{name}'", details):
            return

        for r_id in matching_results:
            project.remove_solver_result(r_id)

        self._api.remove_solver_config(config_id)
        self._api.set_selection(None)
        self._api.show_status(f"Deleted analysis '{name}'", "info", 3000)

    def rename_analysis_config_item(self, item: QTreeWidgetItem, element: dict[str, Any]) -> None:
        config_id = str(element["config_id"])
        old_name = str(element.get("name") or "Analysis").strip()
        new_name = item.text(0).strip()
        if not self.can_edit_project():
            self.restore_item_text(item, old_name)
            return
        if not new_name:
            self.restore_item_text(item, old_name)
            self._api.show_status("Name cannot be empty", "warning", 3000)
            return
        if new_name == old_name:
            self.restore_item_text(item, new_name)
            return
        project = self._api.project
        if project is not None:
            config = project.get_solver_config(config_id)
            if config is not None:
                config.name = new_name
                self._api.add_solver_config(config)
                self._api.notify_project_content_changed()
                self._api.show_status(f'Renamed analysis to "{new_name}"', "success", 3000)

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

        if element.get("kind") == "analysis_config":
            self.rename_analysis_config_item(item, element)
            return

        element_id = str(element.get("id") or "")
        old_name = str(element.get("name") or "").strip()
        old_label = format_component_name(element)
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
            fresh_element = self.find_component(element_id)
            if fresh_element is not None:
                fresh_element["name"] = new_name

        self._api.edit_project(f"Rename {old_label} to {new_name}", change)
        fresh_element = self.find_component(element_id)
        if fresh_element is not None:
            self._api.set_selection(fresh_element)
        self._api.show_status(f'Renamed "{old_label}" to "{new_name}"', "success", 3000)

    def rename_contribution(
        self,
        item: QTreeWidgetItem,
        contribution: ProjectTreeNodeContribution | ComponentTreeNodeContribution,
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
        from setuav_studio.ui.panels.project_explorer.dialog_actions import (
            add_parameter_action,
        )

        add_parameter_action(self._api, self._tree, is_constant=is_constant, parent=parent)

    def add_constraint_action(self, parent: QWidget | None = None) -> None:
        from setuav_studio.ui.panels.project_explorer.dialog_actions import (
            add_constraint_action,
        )

        add_constraint_action(self._api, self._tree, parent=parent)

    def toggle_constraint(self, element: dict[str, Any]) -> None:
        from setuav_studio.ui.panels.project_explorer.dialog_actions import (
            toggle_constraint,
        )

        toggle_constraint(self._api, self._tree, element)

    def run_analysis(self, config_id: str | None = None) -> None:
        from setuav_studio.solver.launch import run_analysis

        run_analysis(self._api, config_id)

    def add_plot_action(
        self,
        element: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> Any | None:
        from setuav_studio.ui.panels.project_explorer.dialog_actions import (
            add_plot_action,
        )

        return add_plot_action(self._api, element, parent or self._tree)

    def delete_plot_action(self, element: dict[str, Any]) -> None:
        result_id = str(element.get("result_id") or "")
        plot_id = str(element.get("plot_id") or "")
        result = self._api.get_solver_result(result_id)
        if result is None or plot_id not in result.plots:
            return
        plot = result.plots[plot_id]
        plot_title = plot.title or plot_id

        def _apply() -> None:
            if plot_id in result.plots:
                del result.plots[plot_id]
            if self._api.project is not None:
                self._api.project.add_solver_result(result)

        self._api.edit_project(f"Delete plot '{plot_title}'", _apply)
        self._api.set_selection(None)
