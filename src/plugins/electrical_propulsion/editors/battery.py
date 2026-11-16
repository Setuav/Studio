"""Battery pack editor: catalogue cell selection and pack configuration."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from plugins.electrical_propulsion.cells import (
    CHEMISTRIES,
    DEFAULT_CELLS,
    cell_spec,
    chemistry_cells,
)
from plugins.electrical_propulsion.models.battery import battery_pack
from setuav_studio.api import StudioAPI
from setuav_studio.model.expression import set_expression
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin

# Read-only pack and cell values: (key, label, unit, quantity, decimals).
_PACK_VALUES = (
    ("capacity", "Pack Capacity", "mAh", "capacity", 0),
    ("nominal_voltage", "Nominal Voltage", "V", "voltage", 1),
    ("charge_voltage", "Charge Voltage", "V", "voltage", 2),
    ("cutoff_voltage", "Cut-Off Voltage", "V", "voltage", 2),
    ("internal_resistance", "Internal Resistance (50% DoD)", "Ω", "resistance", 4),
    ("max_current", "Max Continuous Current", "A", "current", 1),
    ("energy", "Nominal Energy", "Wh", "energy", 1),
)
_CELL_VALUES = (
    ("cell_capacity", "Capacity", "mAh", "capacity", 0),
    ("cell_nominal_voltage", "Nominal Voltage", "V", "voltage", 2),
    ("cell_charge_voltage", "Charge Voltage", "V", "voltage", 2),
    ("cell_cutoff_voltage", "Cut-Off Voltage", "V", "voltage", 2),
    ("cell_resistance", "Resistance (50% DoD)", "Ω", "resistance", 4),
    ("cell_max_current", "Max Continuous Current", "A", "current", 1),
    ("cell_mass", "Mass", "g", "mass", 1),
)


class BatteryEditor(PropertyTableMixin, QWidget):
    """Property editor for a battery pack built from a catalogue cell."""

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
        self._create_pack_section()
        self._create_cell_section()

        self._content_layout.addStretch()
        self._load_battery()

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
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

        if icon_name:
            icon_label = QLabel()
            set_label_icon(icon_label, icon_name)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mass", "Total Pack Mass [Calculated]"),
                ("manufacturer", "Manufacturer"),
                ("model", "Model"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_pack_section(self) -> None:
        layout = self._create_section("Pack Configuration", "fa6s.battery-full")
        self.pack_table = self._property_table(
            [
                ("cell_count", "Series Count (S)"),
                ("parallel_count", "Parallel Count (P)"),
                ("packaging_mass", "Packaging & Wiring Mass"),
                *((key, label) for key, label, *_ in _PACK_VALUES),
            ]
        )
        layout.addWidget(self.pack_table)

    def _create_cell_section(self) -> None:
        layout = self._create_section("Cell", "fa6s.microchip")
        self.cell_table = self._property_table(
            [
                ("chemistry", "Chemistry"),
                ("cell_id", "Cell"),
                *((key, label) for key, label, *_ in _CELL_VALUES),
                ("cell_source", "Data Source"),
            ]
        )
        layout.addWidget(self.cell_table)

    def _load_battery(self) -> None:
        self._loading = True
        try:
            params = self._component["parameters"]
            pack = battery_pack(params)
            cell = pack.cell

            self._set_property_value(
                self.general_table, "name", str(self._component.get("name") or "")
            )
            self._set_property_value(
                self.general_table, "type", str(self._component.get("type") or ""), editable=False
            )
            self._set_property_value(
                self.general_table, "mass", f"{float(self._component['mass']):.1f}", editable=False
            )
            self._set_property_value(
                self.general_table, "manufacturer", str(self._component.get("manufacturer") or "")
            )
            self._set_property_value(
                self.general_table, "model", str(self._component.get("model") or "")
            )

            for key in ("cell_count", "parallel_count"):
                self._set_property_spinbox(
                    self.pack_table,
                    key,
                    int(params[key]),
                    min_val=1,
                    max_val=100,
                    step=1,
                    decimals=0,
                    target_data=params,
                    on_changed=lambda v, k=key: self._on_pack_param_changed(k, v),
                )
            self._set_property_spinbox(
                self.pack_table,
                "packaging_mass",
                float(params["packaging_mass"]),
                min_val=0,
                max_val=1e5,
                step=1.0,
                decimals=1,
                quantity="mass",
                unit="g",
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("packaging_mass", v),
            )
            pack_values = {
                "capacity": pack.capacity_mah,
                "nominal_voltage": pack.nominal_voltage_v,
                "charge_voltage": pack.charge_voltage_v,
                "cutoff_voltage": pack.cutoff_voltage_v,
                "internal_resistance": pack.internal_resistance_ohm,
                "max_current": pack.max_current_a,
                "energy": pack.energy_wh,
            }
            for key, _label, unit, quantity, decimals in _PACK_VALUES:
                self._set_read_only_value(
                    self.pack_table, key, pack_values[key], unit, quantity, decimals
                )

            self._set_property_combo(
                self.cell_table,
                "chemistry",
                cell.chemistry,
                list(CHEMISTRIES),
                self._on_chemistry_changed,
            )
            self._set_property_combo(
                self.cell_table,
                "cell_id",
                cell.id,
                [(spec.id, spec.name) for spec in chemistry_cells(cell.chemistry)],
                self._on_cell_changed,
            )
            cell_values = {
                "cell_capacity": cell.capacity_ah * 1000.0,
                "cell_nominal_voltage": cell.nominal_voltage_v,
                "cell_charge_voltage": cell.charge_voltage_v,
                "cell_cutoff_voltage": cell.cutoff_voltage_v,
                "cell_resistance": cell.mid_discharge_resistance_ohm,
                "cell_max_current": cell.max_current_a,
                "cell_mass": cell.mass_g,
            }
            for key, _label, unit, quantity, decimals in _CELL_VALUES:
                self._set_read_only_value(
                    self.cell_table, key, cell_values[key], unit, quantity, decimals
                )
            self._set_property_value(self.cell_table, "cell_source", cell.source, editable=False)
        finally:
            self._loading = False

    def _set_read_only_value(
        self,
        table: Any,
        key: str,
        value: float,
        unit: str,
        quantity: str,
        decimals: int,
    ) -> None:
        self._set_property_spinbox(
            table,
            key,
            value,
            decimals=decimals,
            quantity=quantity,
            unit=unit,
            read_only=True,
        )

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_text = self._property_text(self.general_table, row)

        def apply_edit() -> None:
            if key == "name":
                self._component["name"] = val_text
            elif key in {"manufacturer", "model"}:
                if val_text:
                    self._component[key] = val_text
                elif key in self._component:
                    self._component.pop(key)

        self._api.edit_component(self._component, f"Edit {key}", apply_edit)

    def _on_pack_param_changed(self, key: str, value: Any) -> None:
        if self._loading:
            return
        cell = self._property_cell(self.pack_table, key)
        expr_to_store = cell.stored_expression() if cell is not None else None

        def apply_edit() -> None:
            params = self._component["parameters"]
            set_expression(params, key, expr_to_store)
            params[key] = max(1, int(float(value))) if key != "packaging_mass" else float(value)
            self._component["mass"] = battery_pack(params).mass_g

        self._api.edit_component(self._component, f"Set {key}", apply_edit)
        self._load_battery()

    def _on_chemistry_changed(self, chemistry: str) -> None:
        if self._loading:
            return
        self._set_cell(DEFAULT_CELLS[chemistry], f"Set battery chemistry '{chemistry}'")

    def _on_cell_changed(self, cell_id: str) -> None:
        if self._loading:
            return
        self._set_cell(cell_id, f"Set battery cell '{cell_spec(cell_id).name}'")

    def _set_cell(self, cell_id: str, label: str) -> None:
        def apply_edit() -> None:
            params = self._component["parameters"]
            params["cell_id"] = cell_id
            self._component["mass"] = battery_pack(params).mass_g

        self._api.edit_component(self._component, label, apply_edit)
        self._load_battery()
