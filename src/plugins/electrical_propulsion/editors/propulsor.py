"""Propulsor editor: the motor and propeller from the catalogs."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from plugins.electrical_propulsion.models.propulsor import PropulsorModel, propulsor_mass
from setuav_studio.api import ParameterField, StudioAPI
from setuav_studio.model.expression import set_expression
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.button import set_native_button
from setuav_studio.ui.widget.table import PropertyTableMixin

_MOTOR_KEYS = (
    "motor_kv",
    "motor_resistance",
    "motor_no_load_current",
    "motor_max_current",
    "motor_mass",
)
_PROPELLER_KEYS = (
    "propeller_diameter",
    "propeller_pitch",
    "propeller_blade_count",
    "propeller_mass",
)
# Values the catalogs define; the masses stay editable.
_CATALOG_KEYS = frozenset(
    {
        "motor_kv",
        "motor_resistance",
        "motor_no_load_current",
        "motor_max_current",
        "propeller_diameter",
        "propeller_pitch",
        "propeller_blade_count",
    }
)
_FIELDS = {field.key: field for field in PropulsorModel.get_scalar_fields()}


class PropulsorEditor(PropertyTableMixin, QWidget):
    """Property editor for a propulsor: its motor and propeller."""

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._component = component
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_general_section()
        self.motor_table = self._create_parameter_section(
            "Motor", "fa6s.gear", _MOTOR_KEYS, self._open_motor_catalog
        )
        self.propeller_table = self._create_parameter_section(
            "Propeller",
            "fa6s.fan",
            ("propeller_catalog_id", *_PROPELLER_KEYS),
            self._open_propeller_catalog,
        )

        self._content_layout.addStretch()
        self._load()
        api.on_project_content_changed(self._on_project_content_changed)

    def closeEvent(self, event: Any) -> None:
        self._api.remove_project_content_listener(self._on_project_content_changed)
        super().closeEvent(event)

    def _on_project_content_changed(self, _project: Any = None) -> None:
        if not self._loading:
            self._load()

    def _create_section(
        self, title: str, icon_name: str, action: QWidget | None = None
    ) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)
        icon_label = QLabel()
        set_label_icon(icon_label, icon_name)
        icon_label.setFixedSize(14, 14)
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel(title))
        header_layout.addStretch()
        if action is not None:
            header_layout.addWidget(action)
        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mass", "Mass [Motor + Propeller]"),
                ("manufacturer", "Motor Manufacturer"),
                ("model", "Motor Model"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_parameter_section(
        self,
        title: str,
        icon_name: str,
        keys: tuple[str, ...],
        on_catalog: Any | None = None,
    ) -> QTableWidget:
        action = None
        if on_catalog is not None:
            action = QPushButton("Catalog…", self)
            set_native_button(action, "fa6s.database")
            action.clicked.connect(on_catalog)
        layout = self._create_section(title, icon_name, action)
        table = self._property_table([(key, _FIELDS[key].label) for key in keys])
        layout.addWidget(table)
        return table

    def _load(self) -> None:
        self._loading = True
        try:
            component = self._component
            params = component["parameters"]
            self._set_property_value(self.general_table, "name", str(component.get("name") or ""))
            self._set_property_value(
                self.general_table, "type", str(component.get("type") or ""), editable=False
            )
            self._set_property_value(
                self.general_table, "mass", f"{float(component['mass']):.1f}", editable=False
            )
            for key in ("manufacturer", "model"):
                self._set_property_value(
                    self.general_table, key, str(component.get(key) or ""), editable=False
                )
            for table, keys in (
                (self.motor_table, _MOTOR_KEYS),
                (self.propeller_table, _PROPELLER_KEYS),
            ):
                for key in keys:
                    self._load_number(table, key, params[key], read_only=key in _CATALOG_KEYS)
            catalog_id = str(params["propeller_catalog_id"])
            self._set_property_value(
                self.propeller_table,
                "propeller_catalog_id",
                catalog_id or "(select from the catalog)",
                editable=False,
            )
        finally:
            self._loading = False

    def _load_number(self, table: QTableWidget, key: str, value: Any, *, read_only: bool) -> None:
        field: ParameterField = _FIELDS[key]
        self._set_property_spinbox(
            table,
            key,
            value,
            min_val=field.min_value if field.min_value is not None else -1e6,
            max_val=field.max_value if field.max_value is not None else 1e6,
            step=1.0 if field.field_type is int else 0.1,
            decimals=field.decimals,
            quantity=field.quantity,
            unit=field.unit,
            target_data=self._component["parameters"],
            on_changed=lambda v, k=key, t=table: self._on_param_changed(t, k, v),
            read_only=read_only,
        )

    def _on_param_changed(self, table: QTableWidget, key: str, value: Any) -> None:
        if self._loading:
            return
        cell = self._property_cell(table, key)
        expr_to_store = cell.stored_expression() if cell is not None else None
        number = float(value)

        def apply_edit() -> None:
            params = self._component["parameters"]
            set_expression(params, key, expr_to_store)
            params[key] = int(number) if _FIELDS[key].field_type is int else number
            self._component["mass"] = propulsor_mass(params)

        self._api.edit_component(self._component, f"Set {key}", apply_edit)
        self._load()

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        if self._property_key(self.general_table, row) != "name":
            return
        name = self._property_text(self.general_table, row)

        def apply_edit() -> None:
            self._component["name"] = name

        self._api.edit_component(self._component, "Edit name", apply_edit)

    def _open_motor_catalog(self) -> None:
        dialog = ComponentCatalogDialog(component_type="motor", parent=self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_motor:
            return
        motor = dialog.selected_motor

        def apply_edit() -> None:
            params = self._component["parameters"]
            self._component["manufacturer"] = motor.manufacturer or ""
            self._component["model"] = motor.name or ""
            params["motor_kv"] = float(motor.kv)
            params["motor_resistance"] = float(motor.resistance)
            params["motor_no_load_current"] = float(motor.io or 0.0)
            params["motor_max_current"] = float(motor.max_current)
            if motor.weight_g:
                params["motor_mass"] = float(motor.weight_g)
            self._component["mass"] = propulsor_mass(params)

        self._api.edit_component(self._component, f"Apply catalog motor '{motor.name}'", apply_edit)
        self._load()

    def _open_propeller_catalog(self) -> None:
        dialog = ComponentCatalogDialog(component_type="propeller", parent=self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_propeller:
            return
        propeller = dialog.selected_propeller

        def apply_edit() -> None:
            params = self._component["parameters"]
            params["propeller_catalog_id"] = propeller.metadata.id
            params["propeller_diameter"] = round(propeller.diameter_m * 1000.0, 1)
            params["propeller_pitch"] = round(propeller.pitch_m * 1000.0, 1)
            params["propeller_blade_count"] = int(propeller.metadata.blade_count)

        self._api.edit_component(
            self._component, f"Apply catalog propeller '{propeller.metadata.id}'", apply_edit
        )
        self._load()
