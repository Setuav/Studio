from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import StudioAPI
from setuav_studio.ui.style.icons import get_icon


class PropertiesPanel(QWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 6)
        self._layout.setSpacing(4)
        self._current_widget: QWidget | None = None
        self._current_selection_key: tuple[str, str] | None = None
        self._current_component: dict[str, Any] | None = None
        self._active_component_id: str | None = None
        self._last_component_tab_index: int = 0

        from setuav_studio.ui.shell.native_registrations import register_native_kind_editors

        register_native_kind_editors(api)
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
        if kind in ("", "component") and new_id:
            live_comp = self._resolve_live_component(new_id)
            if (
                live_comp is not None
                and self._current_component is not None
                and self._current_component is not live_comp
            ):
                self._current_selection_key = None
                self.set_selection(live_comp)

    def _on_project_changed(self, _project: Any) -> None:
        self._current_selection_key = None
        self.set_selection(self._api.current_selection)

    def set_selection(self, selection: Any | None) -> None:
        if (
            selection is not None
            and hasattr(selection, "raw_data")
            and isinstance(selection.raw_data, dict)
        ):
            selection = selection.raw_data
        elif not isinstance(selection, dict):
            self._current_selection_key = None
            self._current_component = None
            self._active_component_id = None
            self._clear_selected_cg()
            self._replace_widget(self._message("Select a component, parameter, or constraint"))
            return

        new_id = str(selection.get("id") or "")
        kind = str(selection.get("kind") or "")

        # Handle virtual selections by focusing the parent component on the corresponding tab
        if kind in ("transform", "envelope", "mass-properties"):
            comp_id = str(selection.get("component_id") or selection.get("id") or "")
            if comp_id:
                live_comp = self._resolve_live_component(comp_id)
                if live_comp:
                    if kind == "transform":
                        self._last_component_tab_index = 1
                    elif kind == "envelope":
                        self._last_component_tab_index = 2
                    elif kind == "mass-properties":
                        self._last_component_tab_index = 3
                    self.set_selection(live_comp)
                    return

        new_key = (kind, new_id)

        live_selection = selection
        if kind in ("", "component") and new_id:
            live_comp = self._resolve_live_component(new_id)
            if live_comp is not None:
                live_selection = live_comp

        if (
            self._current_selection_key is not None
            and new_key == self._current_selection_key
            and self._current_widget is not None
        ):
            if (
                self._current_component is not None
                and live_selection is not self._current_component
            ):
                # Component reference changed; fall through to rebuild editor with live component
                pass
            else:
                # Same item and still pointing to the active component
                return

        self._current_selection_key = new_key
        self._current_component = live_selection if kind in ("", "component") else None

        if kind in ("", "component") and new_id:
            self._active_component_id = new_id
            tab_widget = self._build_component_tabs(new_id, live_selection)
            self._replace_widget(tab_widget)
            return

        # Non-component selections (parameter, constraint, analysis, solver)
        self._active_component_id = None
        self._clear_selected_cg()

        editor = self._api.create_component_editor(live_selection)
        if editor is not None:
            self._replace_widget(editor)
            return

        name = str(live_selection.get("name") or "Unnamed component")
        component_type = str(live_selection.get("type") or "Unknown type")
        self._replace_widget(
            self._message(f"{name}\n\nNo properties editor is available for\n{component_type}")
        )

    def _build_component_tabs(
        self,
        comp_id: str,
        component: dict[str, Any],
    ) -> QTabWidget:
        """Construct the fixed 4-tab CAD property editor for a component."""
        from setuav_studio.ui.editor import (
            EnvelopeEditor,
            MassPropertiesEditor,
            TransformEditor,
        )

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.tabBar().setDrawBase(False)

        # Tab 0: Parameters (Primary Component Editor)
        primary_editor = self._api.create_component_editor(component)
        if primary_editor is None:
            name = str(component.get("name") or comp_id)
            ctype = str(component.get("type") or "Unknown")
            primary_editor = self._message(f"{name}\n\nNo primary parameters editor for\n{ctype}")
        tabs.addTab(primary_editor, get_icon("fa6s.sliders"), "Parameters")

        # Tab 1: Transform
        tf_editor = TransformEditor(self._api, component)
        tabs.addTab(tf_editor, get_icon("transform"), "Transform")

        # Tab 2: Envelope
        env_editor = EnvelopeEditor(self._api, component)
        tabs.addTab(env_editor, get_icon("envelope"), "Envelope")

        # Tab 3: Mass
        mass_editor = MassPropertiesEditor(self._api, component)
        tabs.addTab(mass_editor, get_icon("point_mass"), "Mass")

        # Connect tab switching to update viewport CG
        tabs.currentChanged.connect(self._on_component_tab_changed)

        # Restore previous tab index
        target_index = max(0, min(self._last_component_tab_index, tabs.count() - 1))
        tabs.setCurrentIndex(target_index)

        # Trigger corresponding 3D viewport visualization
        if target_index == 2:  # Envelope tab
            self._set_selected_envelope(comp_id)
            self._clear_selected_cg()
        elif target_index == 3:  # Mass tab
            self._set_selected_cg(comp_id)
            self._clear_selected_envelope()
        else:
            self._clear_selected_envelope()
            self._clear_selected_cg()

        return tabs

    def _on_component_tab_changed(self, index: int) -> None:
        self._last_component_tab_index = index
        if index == 2:  # Envelope tab
            self._set_selected_envelope(self._active_component_id)
            self._clear_selected_cg()
        elif index == 3:  # Mass tab
            self._set_selected_cg(self._active_component_id)
            self._clear_selected_envelope()
        else:
            self._clear_selected_envelope()
            self._clear_selected_cg()

    def _set_selected_envelope(self, comp_id: str | None) -> None:
        viewport = getattr(self._api, "viewport", getattr(self._api, "_viewport", None))
        if viewport is not None and hasattr(viewport, "set_selected_envelope"):
            viewport.set_selected_envelope(comp_id)

    def _clear_selected_envelope(self) -> None:
        self._set_selected_envelope(None)

    def _set_selected_cg(self, comp_id: str | None) -> None:
        viewport = getattr(self._api, "viewport", getattr(self._api, "_viewport", None))
        if viewport is not None and hasattr(viewport, "set_selected_cg"):
            viewport.set_selected_cg(comp_id)

    def _clear_selected_cg(self) -> None:
        self._set_selected_cg(None)

    def _replace_widget(self, widget: QWidget | None) -> None:
        if self._current_widget is not None:
            focus_widget = QApplication.focusWidget()
            if focus_widget is not None and self._current_widget.isAncestorOf(focus_widget):
                focus_widget.clearFocus()

            for line_edit in self._current_widget.findChildren(QLineEdit):
                line_edit.editingFinished.emit()

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
            fn = getattr(self._current_widget, "update_theme_style", None)
            if callable(fn):
                fn()
            for child in self._current_widget.findChildren(QWidget):
                child_fn = getattr(child, "update_theme_style", None)
                if callable(child_fn):
                    child_fn()
