from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu, QTreeWidgetItem

from setuav_studio.ui.style.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.panels.project_explorer.operations import (
        ProjectExplorerOperations,
    )
    from setuav_studio.ui.panels.project_explorer.tree import ProjectExplorer


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
        if item is None:
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

        if item is self._tree._constraints_group_item or (
            item is not None and item.text(0) == "Constraints"
        ):
            self.open_constraints_group_menu(position, can_edit)
            return

        element = self._tree._element_map.get(item)
        if element and element.get("kind") == "parameter":
            self.open_parameter_element_menu(item, element, position, can_edit)
            return

        if element and element.get("kind") == "constraint":
            self.open_constraint_element_menu(item, element, position, can_edit)
            return

        if element and element.get("kind") == "analysis_config":
            self.open_analysis_config_menu(item, element, position, can_edit)
            return

        if element and element.get("kind") == "analysis_table":
            self.open_analysis_table_menu(item, element, position)
            return

        if element and element.get("kind") == "analysis_plot":
            self.open_analysis_plot_menu(item, element, position)
            return

        if element is None and item is not self._tree._project_root_item:
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
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is add_c_act:
            self._ops.add_constraint_action()

    def open_parameter_element_menu(
        self,
        item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
        can_edit: bool,
    ) -> None:
        menu = QMenu(self._tree)
        del_act = menu.addAction(get_icon("remove"), "Delete")
        del_act.setEnabled(can_edit)
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is del_act:
            self._ops.delete_item(item)

    def open_constraint_element_menu(
        self,
        item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
        can_edit: bool,
    ) -> None:
        menu = QMenu(self._tree)
        toggle_act = menu.addAction("Toggle Enabled")
        toggle_act.setEnabled(can_edit)
        del_act = menu.addAction(get_icon("remove"), "Delete")
        del_act.setEnabled(can_edit)
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is toggle_act:
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
        add_const_act = None
        add_constr_act = None
        if item is not self._tree._project_root_item:
            delete_action = menu.addAction(get_icon("remove"), "Delete")
            delete_action.setEnabled(can_edit)
        else:
            menu.addSeparator()
            add_const_act = menu.addAction(get_icon("constant"), "Add Constant…")
            add_const_act.setEnabled(can_edit)
            add_constr_act = menu.addAction(get_icon("constraint"), "Add Constraint…")
            add_constr_act.setEnabled(can_edit)

        chosen_action = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen_action is rename_action:
            self._tree.editItem(item, 0)
        elif delete_action is not None and chosen_action is delete_action:
            self._ops.delete_item(item)
        elif add_const_act is not None and chosen_action is add_const_act:
            self._ops.add_parameter_action(is_constant=True)
        elif add_constr_act is not None and chosen_action is add_constr_act:
            self._ops.add_constraint_action()

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

    def open_analysis_config_menu(
        self,
        item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
        can_edit: bool,
    ) -> None:
        menu = QMenu(self._tree)
        config_id = str(element.get("config_id") or element.get("id") or "")

        run_act = menu.addAction(get_icon("fa6s.play"), "Run Analysis")
        menu.addSeparator()
        rename_act = menu.addAction(get_icon("edit"), "Rename")
        rename_act.setEnabled(can_edit)
        del_act = menu.addAction(get_icon("remove"), "Delete")
        del_act.setEnabled(can_edit)

        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is run_act:
            self._ops.run_analysis(config_id)
        elif chosen is rename_act:
            self._tree.editItem(item, 0)
        elif chosen is del_act:
            self._ops.delete_item(item)

    def open_analysis_table_menu(
        self,
        _item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
    ) -> None:
        menu = QMenu(self._tree)
        open_act = menu.addAction(get_icon("fa6s.table-cells"), "Open Table")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is open_act:
            self._api.set_selection(element)
            self._api.show_panel("core:result")

    def open_analysis_plot_menu(
        self,
        _item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
    ) -> None:
        menu = QMenu(self._tree)
        open_act = menu.addAction(get_icon("fa6s.chart-simple"), "Open Chart")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is open_act:
            self._api.set_selection(element)
            self._api.show_panel("core:result")
