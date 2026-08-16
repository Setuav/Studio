"""Base reusable property editor and parameter descriptors for Setuav components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.plugin_system import StudioAPI


@dataclass(frozen=True)
class ParameterField:
    """Descriptor for a component parameter field in the property editor."""

    key: str
    label: str
    unit: str = ""
    field_type: type = float
    default: Any = 0.0
    min_value: float | None = None
    max_value: float | None = None
    decimals: int = 2
    tooltip: str = ""
    options: tuple[str, ...] | None = None


class BaseComponentEditor(QWidget):
    """Reusable base property editor for Setuav project components with Undo/Redo support."""

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        parameter_fields: Sequence[ParameterField] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._component = component
        self._fields = list(parameter_fields)
        self._loading = False

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(10)

        scroll.setWidget(self._content)
        main_layout.addWidget(scroll)

        # Build sections
        self._build_header_section()
        self._build_general_section()
        if self._fields:
            self._build_parameters_section()

        self._content_layout.addStretch()
        self._load_values()

    def create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        """Create a standard styled section container with a title bar."""
        section = QFrame(self._content)
        section.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 6px;
            }
        """)
        sec_layout = QVBoxLayout(section)
        sec_layout.setContentsMargins(8, 8, 8, 8)
        sec_layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        if icon_name:
            icon_lbl = QLabel(section)
            icon_lbl.setPixmap(get_icon(icon_name).pixmap(14, 14))
            header.addWidget(icon_lbl)

        title_lbl = QLabel(title, section)
        title_lbl.setStyleSheet("font-weight: 700; font-size: 8.5pt; color: #abb2bf;")
        header.addWidget(title_lbl)
        header.addStretch()
        sec_layout.addLayout(header)

        self._content_layout.addWidget(section)
        return sec_layout

    def _build_header_section(self) -> None:
        comp_type = self._component.get("type", "component")
        comp_id = self._component.get("id", "")

        header = QFrame(self._content)
        header.setStyleSheet("""
            QFrame {
                background-color: rgba(127, 196, 209, 0.08);
                border: 1px solid rgba(127, 196, 209, 0.25);
                border-radius: 6px;
                padding: 6px 8px;
            }
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(6)

        id_lbl = QLabel(f"<b>ID:</b> <span style='color:#7fc4d1;'>{comp_id}</span>", header)
        id_lbl.setStyleSheet("font-size: 8.5pt;")
        h_layout.addWidget(id_lbl)
        h_layout.addStretch()

        type_badge = QLabel(comp_type.split(":")[-1].upper(), header)
        type_badge.setStyleSheet(
            "background-color: #2c313a; color: #abb2bf; font-size: 7.5pt; font-weight: 700; "
            "padding: 2px 6px; border-radius: 4px;"
        )
        h_layout.addWidget(type_badge)

        self._content_layout.addWidget(header)

    def _build_general_section(self) -> None:
        layout = self.create_section("General Info", "fa6s.circle-info")
        form = QFormLayout()
        form.setSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_general_edited)
        form.addRow("Name:", self._name_edit)

        self._manufacturer_edit = QLineEdit()
        self._manufacturer_edit.textChanged.connect(self._on_general_edited)
        form.addRow("Manufacturer:", self._manufacturer_edit)

        self._model_edit = QLineEdit()
        self._model_edit.textChanged.connect(self._on_general_edited)
        form.addRow("Model / Part #:", self._model_edit)

        self._mass_spin = QDoubleSpinBox()
        self._mass_spin.setRange(0.0, 500000.0)
        self._mass_spin.setDecimals(1)
        self._mass_spin.setSuffix(" g")
        self._mass_spin.valueChanged.connect(self._on_general_edited)
        form.addRow("Mass:", self._mass_spin)

        layout.addLayout(form)

    def _build_parameters_section(self) -> None:
        layout = self.create_section("Parameters & Specs", "fa6s.sliders")
        form = QFormLayout()
        form.setSpacing(6)

        self._param_widgets: dict[str, QWidget] = {}

        for field in self._fields:
            if field.options:
                combo = QComboBox()
                combo.addItems(field.options)
                combo.currentTextChanged.connect(
                    lambda _text, k=field.key: self._on_param_edited(k)
                )
                if field.tooltip:
                    combo.setToolTip(field.tooltip)
                form.addRow(f"{field.label}:", combo)
                self._param_widgets[field.key] = combo
            elif field.field_type is int:
                spin = QSpinBox()
                spin.setRange(
                    int(field.min_value if field.min_value is not None else 0),
                    int(field.max_value if field.max_value is not None else 100000),
                )
                if field.unit:
                    spin.setSuffix(f" {field.unit}")
                if field.tooltip:
                    spin.setToolTip(field.tooltip)
                spin.valueChanged.connect(lambda _val, k=field.key: self._on_param_edited(k))
                form.addRow(f"{field.label}:", spin)
                self._param_widgets[field.key] = spin
            elif field.field_type is float:
                dspin = QDoubleSpinBox()
                dspin.setRange(
                    float(field.min_value if field.min_value is not None else 0.0),
                    float(field.max_value if field.max_value is not None else 1000000.0),
                )
                dspin.setDecimals(field.decimals)
                if field.unit:
                    dspin.setSuffix(f" {field.unit}")
                if field.tooltip:
                    dspin.setToolTip(field.tooltip)
                dspin.valueChanged.connect(lambda _val, k=field.key: self._on_param_edited(k))
                form.addRow(f"{field.label}:", dspin)
                self._param_widgets[field.key] = dspin
            else:
                edit = QLineEdit()
                edit.textChanged.connect(lambda _text, k=field.key: self._on_param_edited(k))
                if field.tooltip:
                    edit.setToolTip(field.tooltip)
                form.addRow(f"{field.label}:", edit)
                self._param_widgets[field.key] = edit

        layout.addLayout(form)

    def _load_values(self) -> None:
        self._loading = True
        try:
            self._name_edit.setText(str(self._component.get("name", "")))
            self._manufacturer_edit.setText(str(self._component.get("manufacturer", "")))
            self._model_edit.setText(str(self._component.get("model", "")))
            self._mass_spin.setValue(float(self._component.get("mass", self._component.get("mass_g", 0.0))))

            params = self._component.get("parameters", {})
            for field in self._fields:
                widget = self._param_widgets.get(field.key)
                if widget is None:
                    continue
                val = params.get(field.key, field.default)
                if isinstance(widget, QComboBox):
                    widget.setCurrentText(str(val))
                elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                    widget.setValue(float(val) if isinstance(widget, QDoubleSpinBox) else int(val))
                elif isinstance(widget, QLineEdit):
                    widget.setText(str(val))
        finally:
            self._loading = False

    def _on_general_edited(self) -> None:
        if self._loading:
            return

        name = self._name_edit.text()
        manufacturer = self._manufacturer_edit.text()
        model = self._model_edit.text()
        mass = self._mass_spin.value()

        def apply_changes() -> None:
            self._component["name"] = name
            if manufacturer:
                self._component["manufacturer"] = manufacturer
            elif "manufacturer" in self._component:
                self._component.pop("manufacturer")

            if model:
                self._component["model"] = model
            elif "model" in self._component:
                self._component.pop("model")

            self._component["mass"] = mass

        self._api.edit_component(self._component, f"Edit {self._component.get('name', 'component')}", apply_changes)

    def _on_param_edited(self, key: str) -> None:
        if self._loading:
            return

        widget = self._param_widgets.get(key)
        if widget is None:
            return

        if isinstance(widget, QComboBox):
            val: Any = widget.currentText()
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            val = widget.value()
        elif isinstance(widget, QLineEdit):
            val = widget.text()
        else:
            return

        def apply_param() -> None:
            params = self._component.setdefault("parameters", {})
            params[key] = val

        self._api.edit_component(
            self._component,
            f"Set {key} of {self._component.get('name', 'component')}",
            apply_param,
        )
