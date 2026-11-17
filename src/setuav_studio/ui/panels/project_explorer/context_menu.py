from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QTreeWidgetItem

from setuav_studio.api.events import StudioEvents
from setuav_studio.ui.style.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.api import ComponentMenuItemContribution, StudioAPI
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

        if (element and element.get("kind") == "analysis_plots_group") or (
            item is not None and item.text(0) == "Plots"
        ):
            self.open_analysis_plots_group_menu(item, element, position)
            return

        if (element and element.get("kind") == "analysis_tables_group") or (
            item is not None and item.text(0) == "Tables"
        ):
            self.open_analysis_tables_group_menu(item, element, position)
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

        if element is None or element.get("kind") == "vehicle":
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
        menu = self.default_context_menu(item, can_edit)
        menu.exec(self._tree.viewport().mapToGlobal(position))
        menu.deleteLater()

    def default_context_menu(self, item: QTreeWidgetItem, can_edit: bool) -> QMenu:
        """Menu of a component item: contributed commands, then Rename and Delete."""
        menu = QMenu(self._tree)
        menu.setToolTipsVisible(True)
        element = self._tree._element_map.get(item)
        component = (
            self._ops.find_component(str(element.get("id") or ""))
            if isinstance(element, dict)
            else None
        )
        if component is not None:
            contributions = self._api.component_menu_items(component)
            for contribution in contributions:
                self._add_contributed_item(menu, contribution)
            if contributions:
                menu.addSeparator()

        rename_action = menu.addAction(get_icon("edit"), "Rename")
        rename_action.setEnabled(can_edit)
        rename_action.triggered.connect(lambda _checked=False: self._tree.editItem(item, 0))
        delete_action = menu.addAction(get_icon("remove"), "Delete")
        delete_action.setEnabled(can_edit)
        delete_action.triggered.connect(lambda _checked=False: self._ops.delete_item(item))
        return menu

    @staticmethod
    def _add_contributed_item(menu: QMenu, contribution: ComponentMenuItemContribution) -> None:
        icon = get_icon(contribution.icon) if contribution.icon is not None else QIcon()
        if contribution.children:
            submenu = menu.addMenu(icon, contribution.title)
            submenu.setEnabled(contribution.enabled)
            submenu.setToolTipsVisible(True)
            if contribution.tooltip:
                submenu.menuAction().setToolTip(contribution.tooltip)
            for child in contribution.children:
                ProjectExplorerContextMenu._add_contributed_item(submenu, child)
            return
        action = menu.addAction(icon, contribution.title)
        action.setEnabled(contribution.enabled)
        if contribution.tooltip:
            action.setToolTip(contribution.tooltip)
        callback = contribution.callback
        if callback is not None:
            action.triggered.connect(lambda _checked=False: callback())

    def open_virtual_context_menu(self, item: QTreeWidgetItem, position: QPoint) -> None:
        contribution = self._tree._project_contributions.get(
            item
        ) or self._tree._component_contributions.get(item)
        if contribution is None or (contribution.rename is None and contribution.delete is None):
            return
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
        config_id = str(element["config_id"])

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

    def open_analysis_plots_group_menu(
        self,
        item: QTreeWidgetItem,
        element: dict[str, Any] | None,
        position: QPoint,
    ) -> None:
        elem = element or self._tree._element_map.get(item)
        menu = QMenu(self._tree)
        open_all_act = menu.addAction(get_icon("fa6s.chart-line"), "Open All Plots")
        add_to_view_act = menu.addAction(get_icon("fa6s.table-columns"), "Görünüme Ekle")
        add_plot_act = menu.addAction(get_icon("fa6s.chart-line"), "Add Plot…")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is open_all_act:
            if elem:
                self._api.set_selection(elem)
                self._api.show_panel("studio:result")
        elif chosen is add_to_view_act:
            if elem:
                self._api.publish(str(StudioEvents.ANALYSIS_ADD_TO_VIEW), elem)
                self._api.show_panel("studio:result")
        elif chosen is add_plot_act:
            self._ops.add_plot_action(elem)

    def open_analysis_tables_group_menu(
        self,
        item: QTreeWidgetItem,
        element: dict[str, Any] | None,
        position: QPoint,
    ) -> None:
        elem = element or self._tree._element_map.get(item)
        menu = QMenu(self._tree)
        open_all_act = menu.addAction(get_icon("fa6s.table"), "Open All Tables")
        add_to_view_act = menu.addAction(get_icon("fa6s.table-columns"), "Görünüme Ekle")
        add_plot_act = menu.addAction(get_icon("fa6s.chart-line"), "Add Plot…")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is open_all_act:
            if elem:
                self._api.set_selection(elem)
                self._api.show_panel("studio:result")
        elif chosen is add_to_view_act:
            if elem:
                self._api.publish(str(StudioEvents.ANALYSIS_ADD_TO_VIEW), elem)
                self._api.show_panel("studio:result")
        elif chosen is add_plot_act:
            self._ops.add_plot_action(elem)

    def open_analysis_table_menu(
        self,
        _item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
    ) -> None:
        menu = QMenu(self._tree)
        open_act = menu.addAction(get_icon("fa6s.table-cells"), "Open Table")
        add_to_view_act = menu.addAction(get_icon("fa6s.table-columns"), "Görünüme Ekle")
        add_plot_act = menu.addAction(get_icon("fa6s.chart-line"), "Add Plot…")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is open_act:
            self._api.set_selection(element)
            self._api.show_panel("studio:result")
        elif chosen is add_to_view_act:
            self._api.publish(str(StudioEvents.ANALYSIS_ADD_TO_VIEW), element)
            self._api.show_panel("studio:result")
        elif chosen is add_plot_act:
            self._ops.add_plot_action(element)

    def open_analysis_plot_menu(
        self,
        _item: QTreeWidgetItem,
        element: dict[str, Any],
        position: QPoint,
    ) -> None:
        menu = QMenu(self._tree)
        open_act = menu.addAction(get_icon("fa6s.chart-simple"), "Open Chart")
        add_to_view_act = menu.addAction(get_icon("fa6s.table-columns"), "Görünüme Ekle")
        del_act = menu.addAction(get_icon("remove"), "Delete Plot")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(position))
        if chosen is open_act:
            self._api.set_selection(element)
            self._api.show_panel("studio:result")
        elif chosen is add_to_view_act:
            self._api.publish(str(StudioEvents.ANALYSIS_ADD_TO_VIEW), element)
            self._api.show_panel("studio:result")
        elif chosen is del_act:
            self._ops.delete_plot_action(element)
