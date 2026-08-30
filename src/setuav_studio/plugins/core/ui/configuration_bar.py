"""Movable native toolbar containing the active-configuration dropdown selector."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QToolBar

from setuav_studio.plugins.core.configurations import ConfigurationManager
from setuav_studio.plugins.core.ui.configuration_dialogs import (
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

        # Listen to project events
        self._api.on_project_changed(self._on_project_changed)
        self._api.on_project_content_changed(self._on_project_content_changed)

    @property
    def manager(self) -> ConfigurationManager | None:
        return self._manager

    def _on_project_changed(self, project) -> None:
        if project is not None:
            self._manager = project.get_configuration_manager()
            self._manager.add_change_listener(self._refresh_combo)
        else:
            self._manager = None
        self._refresh_combo()

    def _on_project_content_changed(self, project) -> None:
        if project is not None:
            self._manager = project.get_configuration_manager()
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
                if cid == active_id:
                    active_idx = i + 1  # offset by 1 for [Base]

            # Separator and management actions
            self.config_combo.insertSeparator(self.config_combo.count())
            self.config_combo.addItem(get_icon("file_new"), "+ New Configuration…", "__new__")
            self.config_combo.addItem(
                get_icon("settings"), "⚙ Manage Configurations…", "__manage__"
            )

            self.config_combo.setCurrentIndex(active_idx)
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
        self.configuration_changed.emit(data)
        self._api.notify_project_content_changed()

    def _create_new_config(self) -> None:
        if self._manager is None:
            return
        dlg = ConfigurationEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()

            def _apply() -> None:
                assert self._manager is not None
                new_cfg = self._manager.create_configuration(**data)
                self._manager.set_active_id(new_cfg["id"])

            self._api.edit_project(f"Create configuration '{data['name']}'", _apply)
            self._refresh_combo()
            self._api.notify_project_content_changed()
        else:
            self._refresh_combo()

    def _manage_configs(self) -> None:
        if self._manager is None:
            return
        dlg = ManageConfigurationsDialog(self._manager, self._api, self)
        dlg.exec()
        self._refresh_combo()
        self._api.notify_project_content_changed()
