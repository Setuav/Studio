"""Plugin status and lifecycle management dialog."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import PluginManager


class PluginManagerDialog(QDialog):
    """Display discovered plugins and safely manage their lifecycle."""

    _CORE_PLUGIN_ID = "org.setuav.studio.core"

    def __init__(self, manager: PluginManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self.setObjectName("pluginManagerDialog")
        self.setWindowTitle("Plugin Manager")
        self.setMinimumSize(640, 540)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Active plugins", self))

        self._plugins = QTreeWidget(self)
        self._plugins.setHeaderLabels(["Enabled", "Plugin", "Priority", "Status"])
        self._plugins.setRootIsDecorated(False)
        self._plugins.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        header = self._plugins.header()
        header.setStretchLastSection(False)
        for column, width in ((0, 70), (2, 90), (3, 100)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self._plugins.setColumnWidth(column, width)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._plugins)

        # Custom plugin search directories table section
        layout.addWidget(QLabel("Custom plugin search directories", self))
        folders_layout = QHBoxLayout()
        self._custom_folders_table = QTableWidget(self)
        self._custom_folders_table.setColumnCount(2)
        self._custom_folders_table.setHorizontalHeaderLabels(["Folder Path", "Status"])
        self._custom_folders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._custom_folders_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._custom_folders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._custom_folders_table.setMinimumHeight(100)
        folders_header = self._custom_folders_table.horizontalHeader()
        folders_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        folders_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._custom_folders_table.setColumnWidth(1, 100)
        folders_layout.addWidget(self._custom_folders_table)

        folder_buttons = QVBoxLayout()
        self._add_folder_btn = QPushButton("Add Folder...", self)
        self._remove_folder_btn = QPushButton("Remove Folder", self)
        folder_buttons.addWidget(self._add_folder_btn)
        folder_buttons.addWidget(self._remove_folder_btn)
        folder_buttons.addStretch()
        folders_layout.addLayout(folder_buttons)
        layout.addLayout(folders_layout)

        layout.addWidget(QLabel("Discovery and activation issues", self))
        self._issues = QListWidget(self)
        self._issues.setAlternatingRowColors(True)
        self._issues.setMaximumHeight(90)
        layout.addWidget(self._issues)

        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        self._install = QPushButton("Install Archive...", self)
        self._open_folder = QPushButton("Open Plugins Folder", self)
        self._discover = QPushButton("Discover plugins", self)
        self._refresh = QPushButton("Refresh list", self)
        actions.addButton(self._install, QDialogButtonBox.ButtonRole.ActionRole)
        actions.addButton(self._open_folder, QDialogButtonBox.ButtonRole.ActionRole)
        actions.addButton(self._discover, QDialogButtonBox.ButtonRole.ActionRole)
        actions.addButton(self._refresh, QDialogButtonBox.ButtonRole.ActionRole)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

        self._install.clicked.connect(self._install_archive)
        self._open_folder.clicked.connect(self._open_plugins_folder)
        self._discover.clicked.connect(self._discover_plugins)
        self._refresh.clicked.connect(self._refresh_plugins)
        self._add_folder_btn.clicked.connect(self._add_custom_folder)
        self._remove_folder_btn.clicked.connect(self._remove_custom_folder)

        self._refresh_plugins()

    def refresh(self) -> None:
        """Refresh the displayed state without reactivating plugins."""
        self._refresh_plugins()

    def _discover_plugins(self) -> None:
        self._manager.discover()
        self._refresh_plugins()

    def _add_custom_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Plugin Search Directory",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not folder_path:
            return
        if self._manager.add_custom_folder(folder_path):
            self._manager.discover()
            self._refresh_plugins()

    def _remove_custom_folder(self) -> None:
        row = self._custom_folders_table.currentRow()
        if row < 0:
            return
        item = self._custom_folders_table.item(row, 0)
        if item is not None:
            folder_path = item.text()
            if self._manager.remove_custom_folder(folder_path):
                self._manager.discover()
                self._refresh_plugins()

    def _install_archive(self) -> None:
        filter_str = (
            "Plugin Archives (*.zip *.tar.gz *.tgz *.tar.bz2 *.tbz2 *.tar.xz *.txz *.tar *.rar);;"
            "ZIP Archives (*.zip);;"
            "TAR Archives (*.tar.gz *.tgz *.tar.bz2 *.tbz2 *.tar.xz *.tar);;"
            "RAR Archives (*.rar);;"
            "All Files (*)"
        )
        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Install Plugin Archive",
            "",
            filter_str,
        )
        if not archive_path:
            return

        try:
            installed = self._manager.install_archive(archive_path)
            self._refresh_plugins()
            QMessageBox.information(
                self,
                "Plugin Installed",
                f"Successfully installed plugin archive:\n{installed.name}\n\n"
                f"Directory:\n{installed}",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Installation Failed",
                f"Could not install plugin archive:\n{exc}",
            )

    def _open_plugins_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from setuav_studio.api.installer import get_user_plugins_dir

        user_plugins = get_user_plugins_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_plugins)))

    def _refresh_plugins(self) -> None:
        self._plugins.clear()
        for plugin in self._manager.known_plugins:
            active = self._manager.is_active(plugin.id)
            disabled = self._manager.is_disabled(plugin.id)
            item = QTreeWidgetItem(
                [
                    "",
                    plugin.id,
                    str(getattr(plugin, "priority", 100)),
                    "Active" if active else "Disabled" if disabled else "Inactive",
                ]
            )
            item.setData(1, Qt.ItemDataRole.UserRole, plugin.id)
            self._plugins.addTopLevelItem(item)

            toggle = QCheckBox(self._plugins)
            toggle.setObjectName(f"pluginEnabled_{plugin.id.replace('.', '_').replace(':', '_')}")
            toggle.setAccessibleName(f"Enable {plugin.id}")
            toggle.setToolTip(f"Enable or disable {plugin.id}")
            toggle.setChecked(active)
            toggle.setEnabled(plugin.id != self._CORE_PLUGIN_ID)
            toggle.toggled.connect(
                lambda enabled, plugin_id=plugin.id: self._toggle_plugin(plugin_id, enabled)
            )
            self._plugins.setItemWidget(item, 0, toggle)

        # Refresh custom plugin search directories table
        self._custom_folders_table.setRowCount(len(self._manager.custom_folders))
        for row, folder in enumerate(self._manager.custom_folders):
            path_item = QTableWidgetItem(str(folder))
            path_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            status_item = QTableWidgetItem("Found" if folder.is_dir() else "Missing")
            status_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._custom_folders_table.setItem(row, 0, path_item)
            self._custom_folders_table.setItem(row, 1, status_item)

        self._issues.clear()
        for issue in self._manager.load_issues:
            self._issues.addItem(f"{issue.source}: {issue.message}")
        if not self._manager.load_issues:
            self._issues.addItem("No discovery or activation issues.")

    def _toggle_plugin(self, plugin_id: str, enabled: bool) -> None:
        if plugin_id == self._CORE_PLUGIN_ID:
            return
        try:
            if enabled and not self._manager.is_active(plugin_id):
                self._manager.activate_plugin(plugin_id)
            elif not enabled and self._manager.is_active(plugin_id):
                self._manager.deactivate(plugin_id)
        except Exception as exc:
            QMessageBox.critical(self, "Plugin Manager", f"Could not toggle plugin:\n{exc}")
            checkbox = self.sender()
            if isinstance(checkbox, QCheckBox):
                with QSignalBlocker(checkbox):
                    checkbox.setChecked(not enabled)
            return
        self._refresh_plugins()
