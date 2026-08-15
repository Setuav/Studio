from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from setuav_studio.plugin_system import StudioAPI


class PropertiesPanel(QWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 6)
        self._layout.setSpacing(4)
        self._current_widget: QWidget | None = None
        api.on_selection_changed(self.set_selection)

    def set_selection(self, selection: Any | None) -> None:
        self._replace_widget(None)

        if not isinstance(selection, dict):
            self._replace_widget(self._message("Select a component"))
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
