from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QDockWidget

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.shell.window import MainWindow


class LayoutManager:
    """Manages unified workbench dock layout and window geometry."""

    LAYOUT_VERSION = 3
    LAYOUT_DEFAULTS_KEY = "workbench_layout_version"

    def __init__(self, window: MainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self.restoring_layout = False
        self.layout_save_scheduled = False
        self.layout_persistence_enabled = False

    def restore_window_geometry(self) -> None:
        """Restore only the top-level window geometry."""
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if geometry is not None:
            self._window.restoreGeometry(geometry)

    def restore_dock_layout(self) -> None:
        """Restore the unified dock layout from settings, or apply default layout."""
        settings = QSettings()
        self._check_version_reset(settings)

        saved_state = settings.value("main_window/state")
        self.restoring_layout = True
        try:
            restored = False
            if saved_state is not None:
                restored = self._window.restoreState(saved_state, self.LAYOUT_VERSION)
            if not restored:
                self.apply_default_layout()
        finally:
            self.restoring_layout = False

    def _check_version_reset(self, settings: QSettings) -> None:
        """Clear saved dock state when layout version upgrades."""
        if str(settings.value(self.LAYOUT_DEFAULTS_KEY, "")) == str(self.LAYOUT_VERSION):
            return
        settings.remove("main_window/state")
        settings.setValue(self.LAYOUT_DEFAULTS_KEY, self.LAYOUT_VERSION)

    def apply_default_layout(self) -> None:
        """Arrange panels into standard unified CAE workbench positions."""
        panels = self._window._panels

        tree_dock = self.dock("studio:project-explorer")
        prop_dock = self.dock("studio:properties")
        view_dock = self.dock("studio:viewer-3d")
        result_dock = self.dock("studio:result")

        # Explorer, 3D viewer and properties side by side in one dock area, so a wider
        # window widens all three in proportion.
        area = Qt.DockWidgetArea.LeftDockWidgetArea
        previous: QDockWidget | None = None
        for dock in (tree_dock, view_dock, prop_dock):
            if dock is None:
                continue
            if previous is None:
                self._window.addDockWidget(area, dock)
            else:
                self._window.splitDockWidget(previous, dock, Qt.Orientation.Horizontal)
            dock.show()
            previous = dock

        # 3. Tabify Result with 3D Viewer in Center
        if view_dock is not None and result_dock is not None:
            self._window.tabifyDockWidget(view_dock, result_dock)
            view_dock.raise_()
            result_dock.show()

        # 4. Proportional default sizing (Left: ~260px, Center: ~720px, Right: ~300px)
        if tree_dock is not None and view_dock is not None and prop_dock is not None:
            self._window.resizeDocks(
                [tree_dock, view_dock, prop_dock],
                [260, 720, 300],
                Qt.Orientation.Horizontal,
            )

        # Ensure all registered docks are shown unless explicitly configured hidden
        for _cid, (panel_contrib, dock) in panels.items():
            if dock not in (tree_dock, prop_dock, view_dock, result_dock):
                if panel_contrib.default_visible:
                    dock.show()
                else:
                    dock.hide()

    def schedule_layout_save(self, *_signal_args: object) -> None:
        """Schedule saving the current dock layout to persistent settings."""
        if (
            not self.layout_persistence_enabled
            or self.restoring_layout
            or self._window.isMaximized()
            or self._window.isFullScreen()
        ):
            return
        if self.layout_save_scheduled:
            return
        self.layout_save_scheduled = True
        QTimer.singleShot(0, self.save_layout)

    def save_layout(self) -> None:
        """Save the current dock layout state."""
        self.layout_save_scheduled = False
        if self.restoring_layout or self._window.isMaximized() or self._window.isFullScreen():
            return
        state = self._window.saveState(self.LAYOUT_VERSION)
        QSettings().setValue("main_window/state", state)

    def enable_layout_persistence(self) -> None:
        self.layout_persistence_enabled = True

    def reset_layout(self) -> None:
        """Reset the dock layout to the standard default configuration."""
        settings = QSettings()
        settings.remove("main_window/state")
        self.apply_default_layout()
        self.save_layout()

    def dock(self, panel_id: str) -> QDockWidget | None:
        return self._window.findChild(QDockWidget, panel_id)


__all__ = ["LayoutManager"]
