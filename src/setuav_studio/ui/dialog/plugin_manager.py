"""Plugin status and lifecycle management dialog."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
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
        self.setMinimumSize(620, 420)

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

        layout.addWidget(QLabel("Discovery and activation issues", self))
        self._issues = QListWidget(self)
        self._issues.setAlternatingRowColors(True)
        layout.addWidget(self._issues)

        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        self._discover = QPushButton("Discover plugins", self)
        self._refresh = QPushButton("Refresh list", self)
        actions.addButton(self._discover, QDialogButtonBox.ButtonRole.ActionRole)
        actions.addButton(self._refresh, QDialogButtonBox.ButtonRole.ActionRole)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

        self._discover.clicked.connect(self._discover_plugins)
        self._refresh.clicked.connect(self._refresh_plugins)
        self._refresh_plugins()

    def refresh(self) -> None:
        """Refresh the displayed state without reactivating plugins."""
        self._refresh_plugins()

    def _discover_plugins(self) -> None:
        self._manager.discover()
        self._refresh_plugins()

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
