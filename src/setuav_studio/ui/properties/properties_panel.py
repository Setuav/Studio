from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

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

    def set_selection(self, selection: Any | None) -> None:
        if not isinstance(selection, dict):
            self._current_selection_key = None
            self._replace_widget(self._message("Select a component, parameter, or constraint"))
            return

        new_id = str(selection.get("id") or "")
        kind = str(selection.get("kind") or "")
        new_key = (kind, new_id)
        if (
            self._current_selection_key is not None
            and new_key == self._current_selection_key
            and self._current_widget is not None
        ):
            # Same item is already selected; keep current editor widget intact
            return

        self._current_selection_key = new_key

        if kind == "parameter":
            from setuav_studio.ui.parameters.parameter_property_editor import (
                ParameterPropertyEditor,
            )

            self._replace_widget(ParameterPropertyEditor(self._api, selection))
            return

        if kind == "constraint":
            from setuav_studio.ui.constraints.constraint_property_editor import (
                ConstraintPropertyEditor,
            )

            self._replace_widget(ConstraintPropertyEditor(self._api, selection))
            return

        editor = self._api.create_component_editor(selection)
        if editor is not None:
            self._replace_widget(editor)
            return

        name = str(selection.get("name") or "Unnamed component")
        component_type = str(selection.get("type") or "Unknown type")
        self._replace_widget(
            self._message(f"{name}\n\nNo properties editor is available for\n{component_type}")
        )

    def _replace_widget(self, widget: QWidget | None) -> None:
        if self._current_widget is not None:
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
