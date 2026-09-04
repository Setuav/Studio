"""Clean widget for selecting and managing active configurations in the Project Explorer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

from setuav_studio.model.configuration import ConfigurationManager
from setuav_studio.ui.configuration.dialog import (
    ConfigurationEditDialog,
    ManageConfigurationsDialog,
)
from setuav_studio.ui.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ConfigurationSelectorWidget(QWidget):
    """Clean widget for selecting and managing active project configurations."""

    configuration_changed = Signal(object)  # active_id: str | None

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("studio.configuration_selector")
        self._api = api
        self._manager: ConfigurationManager | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self.config_combo = QComboBox(self)
        self.config_combo.setObjectName("studio.configuration_combo")
        self.config_combo.setToolTip("Active Configuration")
        self.config_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.config_combo.activated.connect(self._on_combo_activated)
        layout.addWidget(self.config_combo, 1)

        self.manage_button = QToolButton(self)
        self.manage_button.setIcon(get_icon("settings"))
        self.manage_button.setToolTip("Manage Configurations…")
        self.manage_button.setStatusTip("Manage Configurations…")
        self.manage_button.setAccessibleName("Manage Configurations…")
        self.manage_button.setAutoRaise(True)
        self.manage_button.setFixedSize(26, 26)
        self.manage_button.clicked.connect(self._manage_configs)
        layout.addWidget(self.manage_button)

        # Listen to project events
        self._api.on_project_changed(self._on_project_changed)
        self._api.on_project_content_changed(self._on_project_content_changed)

        if self._api.current_project is not None:
            self._on_project_changed(self._api.current_project)

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
                self.config_combo.addItem("[No Project]", None)
                self.config_combo.setEnabled(False)
                self.manage_button.setEnabled(False)
                return

            # Base configuration
            self.config_combo.addItem("[Base Configuration]", None)

            configs = self._manager.get_configurations()
            active_id = self._manager.get_active_id()
            active_idx = 0

            for i, cfg in enumerate(configs):
                tag = cfg.get("tag", "").strip()
                name = cfg.get("name", "").strip()
                label = f"[{tag}] {name}" if tag else name
                cid = cfg.get("id")
                self.config_combo.addItem(label, cid)
                if str(cid) == str(active_id):
                    active_idx = i + 1  # offset by 1 for [Base]

            # Separator and management action
            self.config_combo.insertSeparator(self.config_combo.count())
            self.config_combo.addItem("New Configuration…", "__new__")

            self.config_combo.setCurrentIndex(active_idx)
            self.config_combo.setEnabled(True)
            self.manage_button.setEnabled(True)
        finally:
            self.config_combo.blockSignals(False)

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


# Backward compatibility alias
ConfigurationToolBar = ConfigurationSelectorWidget
