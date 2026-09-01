"""Movable native toolbar containing the active-configuration dropdown selector."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QToolBar

from setuav_studio.project.configurations import ConfigurationManager
from setuav_studio.ui.configurations.configuration_dialogs import (
    ConfigurationEditDialog,
    ManageConfigurationsDialog,
)
from setuav_studio.ui.icons import create_color_badge_icon, get_icon

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ConfigurationToolBar(QToolBar):
    """Movable toolbar containing the active configuration selector."""

    configuration_changed = Signal(object)  # active_id: str | None

    def __init__(self, api: StudioAPI, parent=None) -> None:
        super().__init__("Configurations", parent)
        self.setObjectName("studio.configuration_toolbar")
        self.setMovable(True)
        self.setFloatable(False)
        self.setAllowedAreas(Qt.ToolBarArea.AllToolBarAreas)
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        self._api = api
        self._manager: ConfigurationManager | None = None

        self.config_combo = QComboBox(self)
        self.config_combo.setObjectName("studio.configuration_combo")
        self.config_combo.setToolTip("Active Configuration")
        self.config_combo.setMinimumWidth(180)
        self.config_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.config_combo.activated.connect(self._on_combo_activated)

        self.addWidget(self.config_combo)

        self.addSeparator()

        self.add_const_act = self.addAction(get_icon("constant"), "Add Constant")
        self.add_const_act.setToolTip("Add Constant…")
        self.add_const_act.setEnabled(False)
        self.add_const_act.triggered.connect(self._add_constant)

        self.add_constraint_act = self.addAction(get_icon("constraint"), "Add Constraint")
        self.add_constraint_act.setToolTip("Add Design Constraint…")
        self.add_constraint_act.setEnabled(False)
        self.add_constraint_act.triggered.connect(self._add_constraint)

        # Listen to project events
        self._api.on_project_changed(self._on_project_changed)
        self._api.on_project_content_changed(self._on_project_content_changed)

    @property
    def manager(self) -> ConfigurationManager | None:
        return self._manager

    def _on_project_changed(self, project) -> None:
        if project is not None:
            self._manager = project.get_configuration_manager()
            if self._manager is not None:
                self._manager.add_change_listener(self._refresh_combo)
        else:
            self._manager = None
        self._refresh_combo()

    def _on_project_content_changed(self, project) -> None:
        if project is not None:
            self._manager = project.get_configuration_manager()
            if self._manager is not None:
                self._manager.add_change_listener(self._refresh_combo)
        self._refresh_combo()

    def _refresh_combo(self) -> None:
        self.config_combo.blockSignals(True)
        try:
            self.config_combo.clear()
            if self._manager is None:
                self.config_combo.addItem(get_icon("settings"), "[No Project]", None)
                self.config_combo.setEnabled(False)
                return

            # Base configuration
            base_icon = create_color_badge_icon("#2196F3")
            self.config_combo.addItem(base_icon, "[Base Configuration]", None)

            configs = self._manager.get_configurations()
            active_id = self._manager.get_active_id()
            active_idx = 0

            for i, cfg in enumerate(configs):
                tag = cfg.get("tag", "").strip()
                name = cfg.get("name", "").strip()
                label = f"[{tag}] {name}" if tag else name
                cid = cfg.get("id")
                color = cfg.get("color", "#2196F3")
                icon = create_color_badge_icon(color)
                self.config_combo.addItem(icon, label, cid)
                if str(cid) == str(active_id):
                    active_idx = i + 1  # offset by 1 for [Base]

            # Separator and management actions
            self.config_combo.insertSeparator(self.config_combo.count())
            self.config_combo.addItem(get_icon("add"), "New Configuration…", "__new__")
            self.config_combo.addItem(get_icon("settings"), "Manage Configurations…", "__manage__")

            self.config_combo.setCurrentIndex(active_idx)
            self.config_combo.setEnabled(True)

            has_project = self._manager is not None
            self.add_const_act.setEnabled(has_project)
            self.add_constraint_act.setEnabled(has_project)
        finally:
            self.config_combo.blockSignals(False)

    def _add_constant(self) -> None:
        if self._api.current_project is None:
            return
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        name, ok = QInputDialog.getText(
            self, "Add Constant", "Constant name (e.g. design_speed, air_density):"
        )
        if not ok or not name.strip():
            return
        param_name = name.strip()
        data = self._api.current_project.data
        raw = data.setdefault("parameters", {})
        if param_name in raw:
            QMessageBox.warning(self, "Duplicate Name", f"Constant '{param_name}' already exists.")
            return

        def _apply() -> None:
            raw[param_name] = 0.0

        self._api.edit_project(f"Add constant '{param_name}'", _apply)

    def _add_constraint(self) -> None:
        if self._api.current_project is None:
            return
        from setuav_studio.ui.constraints.constraints_dialog import ConstraintEditDialog

        dlg = ConstraintEditDialog(
            self,
            api=self._api,
            project_data=self._api.current_project.data,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()

            def _apply() -> None:
                if self._api.current_project is None:
                    return
                pdata = self._api.current_project.data
                pdata.setdefault("constraints", []).append(data)

            self._api.edit_project(f"Add constraint '{data['name']}'", _apply)

    def _on_combo_activated(self, index: int) -> None:
        if self._manager is None:
            return

        data = self.config_combo.itemData(index)

        if data == "__new__":
            self._create_new_config()
            return

        if data == "__manage__":
            self._manage_configs()
            return

        # Normal configuration switch
        self._manager.set_active_id(data)
        if self._api.current_project is not None:
            stack = getattr(self._api.current_project, "undo_stack", None)
            if stack is not None and hasattr(stack, "clear"):
                stack.clear()
        self.configuration_changed.emit(data)
        self._api.notify_project_content_changed()

    def _create_new_config(self) -> None:
        if self._manager is None:
            return
        dlg = ConfigurationEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            new_cfg = self._manager.create_configuration(**data)
            self._manager.set_active_id(new_cfg["id"])
            if self._api.current_project is not None:
                stack = getattr(self._api.current_project, "undo_stack", None)
                if stack is not None and hasattr(stack, "clear"):
                    stack.clear()
            self._refresh_combo()
            self._api.notify_project_content_changed()
        else:
            self._refresh_combo()

    def _manage_configs(self) -> None:
        if self._manager is None:
            return
        dlg = ManageConfigurationsDialog(self._manager, self._api, self)
        dlg.exec()
        if self._api.current_project is not None:
            stack = getattr(self._api.current_project, "undo_stack", None)
            if stack is not None and hasattr(stack, "clear"):
                stack.clear()
        self._refresh_combo()
        self._api.notify_project_content_changed()
