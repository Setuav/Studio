from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from setuav_studio_sdk import StudioAPI


class PropertiesPanel(QWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 6)
        self._layout.setSpacing(4)
        self._current_widget: QWidget | None = None
        self._current_selection_key: tuple[str, str] | None = None
        api.on_selection_changed(self.set_selection)
        api.on_project_content_changed(self._on_project_content_changed)
        api.on_project_changed(self._on_project_changed)

    def _resolve_live_component(self, comp_id: str) -> dict[str, Any] | None:
        proj = self._api.current_project
        if proj is None or not comp_id:
            return None
        if hasattr(proj, "get_component"):
            return proj.get_component(comp_id)
        if isinstance(getattr(proj, "data", None), dict):
            comps = proj.data.get("components", [])
            if isinstance(comps, list):
                return next(
                    (c for c in comps if isinstance(c, dict) and str(c.get("id") or "") == comp_id),
                    None,
                )
        return None

    def _on_project_content_changed(self, project: Any) -> None:
        if self._current_widget is None or self._current_selection_key is None:
            return
        kind, new_id = self._current_selection_key
        if not kind and new_id:
            live_comp = self._resolve_live_component(new_id)
            widget_comp = getattr(self._current_widget, "_component", None) or getattr(
                self._current_widget, "_instance", None
            )
            if live_comp is not None and widget_comp is not None and widget_comp is not live_comp:
                self._current_selection_key = None
                self.set_selection(live_comp)

    def _on_project_changed(self, _project: Any) -> None:
        self._current_selection_key = None
        self.set_selection(self._api.current_selection)

    def set_selection(self, selection: Any | None) -> None:
        if not isinstance(selection, dict):
            self._current_selection_key = None
            self._replace_widget(self._message("Select a component, parameter, or constraint"))
            return

        new_id = str(selection.get("id") or "")
        kind = str(selection.get("kind") or "")
        new_key = (kind, new_id)

        live_selection = selection
        if not kind and new_id:
            live_comp = self._resolve_live_component(new_id)
            if live_comp is not None:
                live_selection = live_comp

        if (
            self._current_selection_key is not None
            and new_key == self._current_selection_key
            and self._current_widget is not None
        ):
            widget_comp = getattr(self._current_widget, "_component", None) or getattr(
                self._current_widget, "_instance", None
            )
            if widget_comp is not None and live_selection is not widget_comp:
                # Component reference changed; fall through to rebuild editor with live component
                pass
            else:
                # Same item and still pointing to the active component
                return

        self._current_selection_key = new_key

        if kind == "parameter":
            from setuav_studio.ui.editor import ParameterPropertyEditor

            self._replace_widget(ParameterPropertyEditor(self._api, selection))
            return

        if kind == "constraint":
            from setuav_studio.ui.editor import ConstraintPropertyEditor

            self._replace_widget(ConstraintPropertyEditor(self._api, selection))
            return

        editor = self._api.create_component_editor(live_selection)
        if editor is not None:
            self._replace_widget(editor)
            return

        name = str(live_selection.get("name") or "Unnamed component")
        component_type = str(live_selection.get("type") or "Unknown type")
        self._replace_widget(
            self._message(f"{name}\n\nNo properties editor is available for\n{component_type}")
        )

    def _replace_widget(self, widget: QWidget | None) -> None:
        if self._current_widget is not None:
            focus_widget = QApplication.focusWidget()
            if focus_widget is not None and self._current_widget.isAncestorOf(focus_widget):
                focus_widget.clearFocus()

            from setuav_studio.ui.widget.table import ExpressionPropertyCell

            for cell in self._current_widget.findChildren(ExpressionPropertyCell):
                if getattr(cell, "_is_focused", False):
                    cell._on_focus_out()

            self._layout.removeWidget(self._current_widget)
            self._current_widget.setParent(None)
            self._current_widget.deleteLater()
        self._current_widget = widget
        if widget is not None:
            self._layout.addWidget(widget)

    @staticmethod
    def _message(text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def update_theme_style(self) -> None:
        if self._current_widget is not None:
            if hasattr(self._current_widget, "update_theme_style") and callable(
                self._current_widget.update_theme_style
            ):
                self._current_widget.update_theme_style()
            for child in self._current_widget.findChildren(QWidget):
                if hasattr(child, "update_theme_style") and callable(child.update_theme_style):
                    child.update_theme_style()
