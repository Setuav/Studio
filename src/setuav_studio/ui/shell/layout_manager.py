from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QMainWindow

from .layout import _WorkspaceLayoutContext

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


class LayoutManager:
    """Manages workspace perspectives, dock layouts, and window geometry."""

    LAYOUT_VERSION = 12
    LAYOUT_DEFAULTS_KEY = "workspace_layout_defaults_version"

    def __init__(self, window: QMainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self.workspace_states: dict[str, Any] = {}
        self.restoring_workspace_layout = False
        self.layout_save_scheduled = False
        self.layout_persistence_enabled = False

    def restore_window_layout(self) -> None:
        """Restore the window geometry and active workspace layout."""
        self._window.restore_window_geometry()
        self._window.restore_workspace_layout()

    def restore_window_geometry(self) -> None:
        """Restore only the top-level window geometry."""
        settings = QSettings()
        geometry = settings.value("main_window/geometry")
        if geometry is not None:
            self._window.restoreGeometry(geometry)

    def restore_workspace_layout(self) -> None:
        """Restore the active dock perspective after the window is exposed."""
        settings = QSettings()
        self._window._reset_outdated_workspace_perspectives(settings)
        active_workspace = settings.value("active_workspace")
        workspaces = getattr(self._window, "_workspaces", {})
        if active_workspace and str(active_workspace) in workspaces:
            self._api.switch_workspace(str(active_workspace))
        elif self._api.current_workspace_id:
            self._api.switch_workspace(self._api.current_workspace_id)
        elif "studio.workspace.design" in workspaces:
            self._api.switch_workspace("studio.workspace.design")

    def reset_outdated_workspace_perspectives(self, settings: QSettings) -> None:
        """Clear saved dock state once when the built-in defaults change."""
        if str(settings.value(self.LAYOUT_DEFAULTS_KEY, "")) == str(self.LAYOUT_VERSION):
            return
        workspaces = getattr(self._window, "_workspaces", {})
        for workspace_id in workspaces:
            settings.remove(f"workspace_perspective/{workspace_id}")
        self.workspace_states.clear()
        settings.setValue(self.LAYOUT_DEFAULTS_KEY, self.LAYOUT_VERSION)

    def switch_workspace(self, workspace_id: str) -> None:
        workspaces = getattr(self._window, "_workspaces", {})
        if workspace_id not in workspaces:
            return

        current_workspace_id = getattr(self._window, "_current_workspace_id", None)
        if current_workspace_id is not None and current_workspace_id != workspace_id:
            prev_state = self._window.saveState(self.LAYOUT_VERSION)
            self.workspace_states[current_workspace_id] = prev_state
            QSettings().setValue(
                f"workspace_perspective/{current_workspace_id}",
                prev_state,
            )

        self._window._current_workspace_id = workspace_id
        if hasattr(self._window, "_workspace_toolbar"):
            self._window._workspace_toolbar.set_current_workspace(workspace_id)
        if hasattr(self._window, "_rebuild_toolbar_tools"):
            self._window._rebuild_toolbar_tools()

        settings = QSettings()
        saved_state = self.workspace_states.get(workspace_id) or settings.value(
            f"workspace_perspective/{workspace_id}"
        )
        self.restoring_workspace_layout = True
        try:
            restored = saved_state is not None and self._window.restoreState(
                saved_state, self.LAYOUT_VERSION
            )
            panels = getattr(self._window, "_panels", {})
            if restored:
                for _cid, (panel_contrib, dock) in panels.items():
                    if not panel_contrib.is_in_workspace(workspace_id):
                        dock.hide()
            else:
                self._window._apply_default_workspace_layout(workspace_id)
        finally:
            self.restoring_workspace_layout = False

        if hasattr(self._window, "_update_view_menu"):
            self._window._update_view_menu(workspace_id)

    def schedule_workspace_layout_save(self) -> None:
        current_workspace_id = getattr(self._window, "_current_workspace_id", None)
        if (
            not self.layout_persistence_enabled
            or self.restoring_workspace_layout
            or current_workspace_id is None
        ):
            return
        if self.layout_save_scheduled:
            return
        self.layout_save_scheduled = True
        QTimer.singleShot(0, self._window._save_current_workspace_layout)

    def save_current_workspace_layout(self) -> None:
        self.layout_save_scheduled = False
        workspace_id = getattr(self._window, "_current_workspace_id", None)
        if workspace_id is None or self.restoring_workspace_layout:
            return
        state = self._window.saveState(self.LAYOUT_VERSION)
        self.workspace_states[workspace_id] = state
        QSettings().setValue(f"workspace_perspective/{workspace_id}", state)

    def enable_layout_persistence(self) -> None:
        self.layout_persistence_enabled = True

    def apply_default_workspace_layout(self, workspace_id: str) -> None:
        self._window._hide_panels_outside_workspace(workspace_id)
        workspaces = getattr(self._window, "_workspaces", {})
        workspace = workspaces.get(workspace_id)
        if workspace is not None and workspace.default_layout is not None:
            workspace.default_layout(_WorkspaceLayoutContext(self._window, workspace_id))
            return
        panels = getattr(self._window, "_panels", {})
        for panel_contribution, dock in panels.values():
            dock.setVisible(panel_contribution.is_in_workspace(workspace_id))

    def hide_panels_outside_workspace(self, workspace_id: str) -> None:
        panels = getattr(self._window, "_panels", {})
        for panel_contribution, dock in panels.values():
            if not panel_contribution.is_in_workspace(workspace_id):
                dock.hide()

    def dock(self, panel_id: str) -> QDockWidget | None:
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

    def reset_current_workspace_layout(self) -> None:
        current_id = (
            getattr(self._window, "_current_workspace_id", None) or self._api.current_workspace_id
        )
        if current_id is None:
            return
        settings = QSettings()
        settings.remove(f"workspace_perspective/{current_id}")
        self.workspace_states.pop(current_id, None)
        self._window._apply_default_workspace_layout(current_id)
        self._window._save_current_workspace_layout()


__all__ = ["LayoutManager"]
