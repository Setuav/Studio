from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu, QTreeWidgetItem

from setuav_studio.ui.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.ui.project_explorer.operations import (
        ProjectExplorerOperations,
    )
    from setuav_studio.ui.project_explorer.tree import ProjectExplorer
    from setuav_studio_sdk import StudioAPI


class ProjectExplorerContextMenu:
    """Manages context menus for tree items in the project explorer."""

    def __init__(
        self,
        tree: ProjectExplorer,
        api: StudioAPI,
        operations: ProjectExplorerOperations,
    ) -> None:
        self._tree = tree
        self._api = api
        self._ops = operations

    def open_context_menu(self, position: QPoint) -> None:
        item = self._tree.itemAt(position)
        if item is None or item is self._tree._geometry_group_item:
            return

        if item in self._tree._virtual_items:
            self.open_virtual_context_menu(item, position)
            return

        self._tree.setCurrentItem(item)
        can_edit = self._ops.can_edit_project()

        if item is self._tree._parameters_group_item or (
            item and item.text(0) in ("Constants", "Equations")
        ):
            self.open_parameters_group_menu(item, position, can_edit)
            return

        if item is self._tree._constraints_group_item:
            self.open_constraints_group_menu(position, can_edit)
            return

        element = self._tree._element_map.get(item)
        if element and element.get("kind") == "parameter":
            self.open_parameter_element_menu(item, element, position, can_edit)
            return

        if element and element.get("kind") == "constraint":
            self.open_constraint_element_menu(item, element, position, can_edit)
            return

        self.open_default_context_menu(item, position, can_edit)

    def open_parameters_group_menu(
        self,
        item: QTreeWidgetItem,
        position: QPoint,
        can_edit: bool,
    ) -> None:
        menu = QMenu(self._tree)
        is_const = item.text(0) == "Constants"
        action_label = "Add Constant…" if is_const else "Add Parameter…"
        add_param_act = menu.addAction(get_icon("constant"), action_label)
        add_param_act.setEnabled(can_edit)
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is add_param_act:
            self._ops.add_parameter_action(is_constant=is_const)

    def open_constraints_group_menu(self, position: QPoint, can_edit: bool) -> None:
        menu = QMenu(self._tree)
        add_c_act = menu.addAction(get_icon("constraint"), "Add Constraint…")
        add_c_act.setEnabled(can_edit)
        manage_c_act = menu.addAction(get_icon("constraint"), "Manage Constraints…")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is add_c_act:
            self._ops.add_constraint_action()
        elif chosen is manage_c_act:
            from setuav_studio.ui.constraints.constraints_dialog import ManageConstraintsDialog

            ManageConstraintsDialog(self._api, parent=self._tree).exec()

    def open_parameter_element_menu(
        self,
        item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
        can_edit: bool,
    ) -> None:
        menu = QMenu(self._tree)
        fx_act = menu.addAction(get_icon("settings"), "Edit with fx Assistant…")
        fx_act.setEnabled(can_edit)
        del_act = menu.addAction(get_icon("remove"), "Delete")
        del_act.setEnabled(can_edit)
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is fx_act:
            self._ops.edit_parameter_fx(element)
        elif chosen is del_act:
            self._ops.delete_item(item)

    def open_constraint_element_menu(
        self,
        item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
        can_edit: bool,
    ) -> None:
        menu = QMenu(self._tree)
        fx_act = menu.addAction(get_icon("settings"), "Edit with fx Assistant…")
        fx_act.setEnabled(can_edit)
        toggle_act = menu.addAction("Toggle Enabled")
        toggle_act.setEnabled(can_edit)
        del_act = menu.addAction(get_icon("remove"), "Delete")
        del_act.setEnabled(can_edit)
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is fx_act:
            self._ops.edit_constraint_fx(element)
        elif chosen is toggle_act:
            self._ops.toggle_constraint(element)
        elif chosen is del_act:
            self._ops.delete_item(item)

    def open_default_context_menu(
        self,
        item: QTreeWidgetItem,
        position: QPoint,
        can_edit: bool,
    ) -> None:
        menu = QMenu(self._tree)
        rename_action = menu.addAction(get_icon("edit"), "Rename")
        rename_action.setEnabled(can_edit)
        delete_action = None
        if item is not self._tree._project_root_item:
            delete_action = menu.addAction(get_icon("remove"), "Delete")
            delete_action.setEnabled(can_edit)

        chosen_action = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen_action is rename_action:
            self._tree.editItem(item, 0)
        elif delete_action is not None and chosen_action is delete_action:
            self._ops.delete_item(item)

    def open_virtual_context_menu(self, item: QTreeWidgetItem, position: QPoint) -> None:
        contribution = self._tree._project_contributions.get(
            item
        ) or self._tree._component_contributions.get(item)
        if contribution is None or (contribution.rename is None and contribution.delete is None):
            return
        self._tree.setCurrentItem(item)
        menu = QMenu(self._tree)
        rename_action = menu.addAction(get_icon("edit"), "Rename") if contribution.rename else None
        delete_action = (
            menu.addAction(get_icon("remove"), "Delete") if contribution.delete else None
        )
        for action in (rename_action, delete_action):
            if action is not None:
                action.setEnabled(self._ops.can_edit_project())
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if rename_action is not None and chosen is rename_action:
            self._tree.editItem(item, 0)
        elif delete_action is not None and chosen is delete_action:
            self._ops.delete_item(item)
