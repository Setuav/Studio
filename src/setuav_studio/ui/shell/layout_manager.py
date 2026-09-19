from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QMainWindow

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


_DOCK_ALIASES = {
    "project.explorer": "core:project-explorer",
    "studio.properties": "core:properties",
}


class LayoutManager:
    """Manages unified workbench dock layout and window geometry."""

    LAYOUT_VERSION = 13
    LAYOUT_DEFAULTS_KEY = "workbench_layout_version"

    def __init__(self, window: QMainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self.restoring_layout = False
        self.layout_save_scheduled = False
        self.layout_persistence_enabled = False

    def restore_window_layout(self) -> None:
        """Restore the window geometry and unified dock layout."""
        self.restore_window_geometry()
        self.restore_dock_layout()

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
        panels = getattr(self._window, "_panels", {})

        # Default standard positions
        left_dock = self.dock("core:project-explorer")
        if left_dock is not None:
            self._window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)
            left_dock.show()

        right_dock = self.dock("core:properties")
        if right_dock is not None:
            self._window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, right_dock)
            right_dock.show()

        # Center / other docks
        viewer_dock = self.dock("studio.viewer.opengl")
        if viewer_dock is not None:
            self._window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, viewer_dock)
            viewer_dock.show()

        # Ensure all registered docks are shown unless explicitly hidden
        for _cid, (_panel_contrib, dock) in panels.items():
            if dock not in (left_dock, right_dock, viewer_dock):
                dock.show()

    def schedule_layout_save(self) -> None:
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
        target_id = _DOCK_ALIASES.get(panel_id, panel_id)
        d = self._window.findChild(QDockWidget, target_id)
        if d is not None:
            return d
        return self._window.findChild(QDockWidget, panel_id)

    def resize_visible_docks(
        self,
        docks: tuple[QDockWidget | None, ...],
        widths: list[int],
    ) -> None:
        visible_docks = [d for d in docks if d is not None and not d.isHidden()]
        if visible_docks:
            self._window.resizeDocks(
                visible_docks,
                widths[: len(visible_docks)],
                Qt.Orientation.Horizontal,
            )


__all__ = ["LayoutManager"]
