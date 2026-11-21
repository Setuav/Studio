"""Propulsor editors: the propulsor itself, and its motor and propeller picked from the catalogs."""

from __future__ import annotations

import weakref
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
from plugins.electrical_propulsion.models.propulsor import (
    PropulsorModel,
    has_motor,
    has_propeller,
)
from setuav_studio.api import ParameterField, StudioAPI
from setuav_studio.model.expression import set_expression
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.button import set_button_role
from setuav_studio.ui.widget.table import PropertyTableMixin

MOTOR_SELECTION_KIND = "propulsor-motor"
PROPELLER_SELECTION_KIND = "propulsor-propeller"

_FIELDS = {field.key: field for field in PropulsorModel.get_scalar_fields()}
_NOT_SELECTED = "Not selected: pick one from the catalog"


class _PropulsorPage(PropertyTableMixin, QWidget):
    """Scrollable page of property sections that edit one propulsor."""

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
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

    def _finish(self) -> None:
        self._content_layout.addStretch()
        self._load()
        self_ref = weakref.ref(self)

        def _on_content_changed(_project: Any = None) -> None:
            editor = self_ref()
            if editor is not None:
                editor._on_project_content_changed()

        self._api.on_project_content_changed(_on_content_changed)
        self.destroyed.connect(
            lambda _obj=None, a=self._api, fn=_on_content_changed: (
                a.remove_project_content_listener(fn)
            )
        )

    def _on_project_content_changed(self, _project: Any = None) -> None:
        if not self._loading:
            self._load()

    def _load(self) -> None:
        raise NotImplementedError

    def _create_section(
        self,
        title: str,
        icon_name: str,
        rows: list[tuple[str, str]],
        on_catalog: Any | None = None,
    ) -> QTableWidget:
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
        layout.addWidget(header)
        if on_catalog is not None:
            button = QPushButton(f" Choose {title} from Catalog…", self)
            set_button_role(button, "primary", "propulsion_component_database")
            button.clicked.connect(on_catalog)
            layout.addWidget(button)
        table = self._property_table(rows)
        layout.addWidget(table)
        self._content_layout.addWidget(section)
        return table

    def _load_number(self, table: QTableWidget, key: str, *, editable: bool) -> None:
        field: ParameterField = _FIELDS[key]
        value = self._component["parameters"][key]
        self._set_property_spinbox(
            table,
            key,
            "" if value is None else value,
            min_val=field.min_value if field.min_value is not None else -1e6,
            max_val=field.max_value if field.max_value is not None else 1e6,
            step=1.0 if field.field_type is int else 0.1,
            decimals=field.decimals,
            quantity=field.quantity,
            unit=field.unit,
            target_data=self._component["parameters"],
            on_changed=lambda v, k=key, t=table: self._on_param_changed(t, k, v),
            read_only=not editable,
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

        self._api.edit_component(self._component, f"Set {key}", apply_edit)


class PropulsorEditor(_PropulsorPage):
    """Name and mass of a propulsor; its motor and propeller have pages of their own."""

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__(api, component)
        self.general_table = self._create_section(
            "General",
            "fa6s.circle-info",
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mass", "Mass [Motor + Propeller]"),
                ("motor", "Motor"),
                ("propeller", "Propeller"),
            ],
        )
        self.general_table.cellChanged.connect(self._update_name)
        self._finish()

    def _load(self) -> None:
        self._loading = True
        try:
            component = self._component
            params = component["parameters"]
            self._set_property_value(self.general_table, "name", str(component.get("name") or ""))
            self._set_property_value(
                self.general_table, "type", str(component["type"]), editable=False
            )
            self._set_property_value(
                self.general_table, "mass", f"{float(component['mass']):.1f}", editable=False
            )
            motor = str(params["motor_model"]) if has_motor(params) else "Not selected"
            propeller = (
                str(params["propeller_catalog_id"]) if has_propeller(params) else "Not selected"
            )
            self._set_property_value(self.general_table, "motor", motor, editable=False)
            self._set_property_value(self.general_table, "propeller", propeller, editable=False)
        finally:
            self._loading = False

    def _update_name(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        if self._property_key(self.general_table, row) != "name":
            return
        name = self._property_text(self.general_table, row)

        def apply_edit() -> None:
            self._component["name"] = name

        self._api.edit_component(self._component, "Edit name", apply_edit)


class PropulsorMotorEditor(_PropulsorPage):
    """The propulsor's motor: picked from the catalog, with an editable mass."""

    _KEYS = (
        "motor_manufacturer",
        "motor_model",
        "motor_kv",
        "motor_resistance",
        "motor_no_load_current",
        "motor_max_current",
        "motor_mass",
    )

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__(api, component)
        self.motor_table = self._create_section(
            "Motor",
            "propulsion_motor",
            [(key, _FIELDS[key].label) for key in self._KEYS],
            self._open_catalog,
        )
        self._finish()

    def _load(self) -> None:
        self._loading = True
        try:
            params = self._component["parameters"]
            picked = has_motor(params)
            self._set_property_value(
                self.motor_table,
                "motor_manufacturer",
                str(params["motor_manufacturer"] or "") if picked else "",
                editable=False,
            )
            self._set_property_value(
                self.motor_table,
                "motor_model",
                str(params["motor_model"]) if picked else _NOT_SELECTED,
                editable=False,
            )
            for key in self._KEYS[2:]:
                self._load_number(self.motor_table, key, editable=picked and key == "motor_mass")
        finally:
            self._loading = False

    def _open_catalog(self) -> None:
        dialog = ComponentCatalogDialog(component_type="motor", parent=self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_motor:
            return
        motor = dialog.selected_motor

        def apply_edit() -> None:
            params = self._component["parameters"]
            for key in self._KEYS:
                set_expression(params, key, None)
            params.update(
                motor_manufacturer=motor.manufacturer or None,
                motor_model=motor.name,
                motor_kv=float(motor.kv),
                motor_resistance=float(motor.resistance),
                motor_no_load_current=float(motor.io),
                motor_max_current=float(motor.max_current),
                motor_mass=float(motor.weight_g),
            )

        self._api.edit_component(self._component, f"Pick motor '{motor.name}'", apply_edit)


class PropulsorPropellerEditor(_PropulsorPage):
    """The propulsor's propeller: picked from the catalog, with a mass entered by hand."""

    _KEYS = (
        "propeller_catalog_id",
        "propeller_diameter",
        "propeller_pitch",
        "propeller_blade_count",
        "propeller_mass",
    )

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__(api, component)
        self.propeller_table = self._create_section(
            "Propeller",
            "propulsion_propeller",
            [(key, _FIELDS[key].label) for key in self._KEYS],
            self._open_catalog,
        )
        self._finish()

    def _load(self) -> None:
        self._loading = True
        try:
            params = self._component["parameters"]
            picked = has_propeller(params)
            self._set_property_value(
                self.propeller_table,
                "propeller_catalog_id",
                str(params["propeller_catalog_id"]) if picked else _NOT_SELECTED,
                editable=False,
            )
            for key in self._KEYS[1:]:
                self._load_number(
                    self.propeller_table, key, editable=picked and key == "propeller_mass"
                )
        finally:
            self._loading = False

    def _open_catalog(self) -> None:
        dialog = ComponentCatalogDialog(component_type="propeller", parent=self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_propeller:
            return
        propeller = dialog.selected_propeller

        def apply_edit() -> None:
            params = self._component["parameters"]
            for key in self._KEYS[:-1]:
                set_expression(params, key, None)
            params.update(
                propeller_catalog_id=propeller.metadata.id,
                propeller_diameter=round(propeller.diameter_m * 1000.0, 1),
                propeller_pitch=round(propeller.pitch_m * 1000.0, 1),
                propeller_blade_count=int(propeller.metadata.blade_count),
            )

        self._api.edit_component(
            self._component, f"Pick propeller '{propeller.metadata.id}'", apply_edit
        )


def propulsor_part_nodes(component: dict[str, Any]) -> tuple[dict[str, str], ...]:
    """Selections of a propulsor's motor and propeller nodes in the project tree.

    The nodes are named after their part; the picked catalog model shows in the editor.
    """
    component_id = str(component["id"])
    return (
        {
            "kind": MOTOR_SELECTION_KIND,
            "id": f"{component_id}:motor",
            "component_id": component_id,
            "name": "Motor",
        },
        {
            "kind": PROPELLER_SELECTION_KIND,
            "id": f"{component_id}:propeller",
            "component_id": component_id,
            "name": "Propeller",
        },
    )


__all__ = [
    "MOTOR_SELECTION_KIND",
    "PROPELLER_SELECTION_KIND",
    "PropulsorEditor",
    "PropulsorMotorEditor",
    "PropulsorPropellerEditor",
    "propulsor_part_nodes",
]
