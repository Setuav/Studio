"""Battery pack editor: chemistry, cell capacity and pack configuration."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from plugins.electrical_propulsion.chemistry import CHEMISTRIES
from plugins.electrical_propulsion.models.battery import (
    BATTERY_OVERRIDES,
    BatteryPack,
    battery_pack,
)
from setuav_studio.api import StudioAPI
from setuav_studio.model.expression import set_expression
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin

# Cell properties derived from the chemistry unless overridden:
# (key, label, unit, quantity, decimals, step).
_CELL_PROPERTIES = (
    ("charge_voltage", "Charge Voltage", "V", "voltage", 2, 0.05),
    ("cell_resistance", "Cell Resistance (50% DoD)", "Ω", "resistance", 4, 0.0005),
    ("c_rate", "Continuous C-Rate", "C", None, 1, 1.0),
    ("pack_mass", "Pack Mass", "g", "mass", 1, 10.0),
)
# Read-only pack values: (key, label, unit, quantity, decimals).
_PACK_VALUES = (
    ("capacity", "Pack Capacity", "mAh", "capacity", 0),
    ("nominal_voltage", "Nominal Voltage", "V", "voltage", 1),
    ("full_voltage", "Full-Charge Voltage", "V", "voltage", 2),
    ("cutoff_voltage", "Cut-Off Voltage", "V", "voltage", 2),
    ("internal_resistance", "Internal Resistance (50% DoD)", "Ω", "resistance", 4),
    ("max_current", "Max Continuous Current", "A", "current", 1),
    ("energy", "Energy", "Wh", "energy", 1),
)
_OVERRIDE_TOOLTIP = "Check to override the value derived from the chemistry."


class BatteryEditor(PropertyTableMixin, QWidget):
    """Property editor for a battery pack of one cell chemistry."""

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
        self._create_configuration_section()
        self._create_cell_section()
        self._create_pack_section()

        self._content_layout.addStretch()
        self._load_battery()
        api.on_project_content_changed(self._on_project_content_changed)

    def _on_project_content_changed(self, _project: Any = None) -> None:
        if not self._loading:
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
                ("mass", "Mass [Pack Mass]"),
                ("manufacturer", "Manufacturer"),
                ("model", "Model"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_configuration_section(self) -> None:
        layout = self._create_section("Pack Configuration", "fa6s.battery-full")
        self.config_table = self._property_table(
            [
                ("chemistry", "Chemistry"),
                ("cell_count", "Series Count (S)"),
                ("parallel_count", "Parallel Count (P)"),
                ("cell_capacity", "Cell Capacity"),
            ]
        )
        layout.addWidget(self.config_table)

    def _create_cell_section(self) -> None:
        layout = self._create_section("Cell Properties", "fa6s.microchip")
        self.cell_table = self._property_table(
            [(key, label) for key, label, *_ in _CELL_PROPERTIES]
        )
        for key, *_ in _CELL_PROPERTIES:
            item = self._label_item(self.cell_table, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setToolTip(_OVERRIDE_TOOLTIP)
        self.cell_table.itemChanged.connect(self._on_override_toggled)
        layout.addWidget(self.cell_table)

    def _create_pack_section(self) -> None:
        layout = self._create_section("Pack Performance", "fa6s.bolt")
        self.pack_table = self._property_table([(key, label) for key, label, *_ in _PACK_VALUES])
        layout.addWidget(self.pack_table)

    @staticmethod
    def _label_item(table: QTableWidget, key: str) -> QTableWidgetItem:
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
                return item
        raise KeyError(key)

    def _load_battery(self) -> None:
        self._loading = True
        try:
            params = self._component["parameters"]
            pack = battery_pack(params)
            self._load_general()
            self._load_configuration(params, pack)
            self._load_cell_properties(params, pack)
            self._load_pack_values(pack)
        finally:
            self._loading = False

    def _load_general(self) -> None:
        component = self._component
        self._set_property_value(self.general_table, "name", str(component.get("name") or ""))
        self._set_property_value(
            self.general_table, "type", str(component.get("type") or ""), editable=False
        )
        self._set_property_value(
            self.general_table, "mass", f"{float(component['mass']):.1f}", editable=False
        )
        for key in ("manufacturer", "model"):
            self._set_property_value(self.general_table, key, str(component.get(key) or ""))

    def _load_configuration(self, params: dict[str, Any], pack: BatteryPack) -> None:
        self._set_property_combo(
            self.config_table,
            "chemistry",
            pack.profile.chemistry,
            list(CHEMISTRIES),
            self._on_chemistry_changed,
        )
        for key in ("cell_count", "parallel_count"):
            self._set_property_spinbox(
                self.config_table,
                key,
                int(params[key]),
                min_val=1,
                max_val=100,
                step=1,
                decimals=0,
                target_data=params,
                on_changed=lambda v, k=key: self._on_param_changed(self.config_table, k, v),
            )
        self._set_property_spinbox(
            self.config_table,
            "cell_capacity",
            float(params["cell_capacity"]),
            min_val=100.0,
            max_val=200000.0,
            step=100.0,
            decimals=0,
            quantity="capacity",
            unit="mAh",
            target_data=params,
            on_changed=lambda v: self._on_param_changed(self.config_table, "cell_capacity", v),
        )

    def _load_cell_properties(self, params: dict[str, Any], pack: BatteryPack) -> None:
        profile = pack.profile
        values = {
            "charge_voltage": pack.charge_voltage_v,
            "cell_resistance": pack.cell_resistance_ohm,
            "c_rate": pack.c_rate,
            "pack_mass": pack.mass_g,
        }
        limits = {
            "charge_voltage": (profile.min_charge_voltage_v, profile.max_charge_voltage_v),
            "cell_resistance": (1e-5, 10.0),
            "c_rate": (0.1, 500.0),
            "pack_mass": (1.0, 1e6),
        }
        for key, _label, unit, quantity, decimals, step in _CELL_PROPERTIES:
            overridden = params[key] is not None
            self._label_item(self.cell_table, key).setCheckState(
                Qt.CheckState.Checked if overridden else Qt.CheckState.Unchecked
            )
            min_val, max_val = limits[key]
            self._set_property_spinbox(
                self.cell_table,
                key,
                values[key],
                min_val=min_val,
                max_val=max_val,
                step=step,
                decimals=decimals,
                quantity=quantity,
                unit=unit,
                target_data=params,
                on_changed=lambda v, k=key: self._on_param_changed(self.cell_table, k, v),
                read_only=not overridden,
            )

    def _load_pack_values(self, pack: BatteryPack) -> None:
        values = {
            "capacity": pack.capacity_mah,
            "nominal_voltage": pack.nominal_voltage_v,
            "full_voltage": pack.full_voltage_v,
            "cutoff_voltage": pack.cutoff_voltage_v,
            "internal_resistance": pack.internal_resistance_ohm,
            "max_current": pack.max_current_a,
            "energy": pack.energy_wh,
        }
        for key, _label, unit, quantity, decimals in _PACK_VALUES:
            self._set_property_spinbox(
                self.pack_table,
                key,
                values[key],
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

    def _on_param_changed(self, table: QTableWidget, key: str, value: Any) -> None:
        if self._loading:
            return
        cell = self._property_cell(table, key)
        expr_to_store = cell.stored_expression() if cell is not None else None
        number = float(value)

        def apply_edit() -> None:
            params = self._component["parameters"]
            set_expression(params, key, expr_to_store)
            params[key] = max(1, int(number)) if key in {"cell_count", "parallel_count"} else number

        self._api.edit_component(self._component, f"Set {key}", apply_edit)
        self._load_battery()

    def _on_override_toggled(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 0:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key not in BATTERY_OVERRIDES:
            return
        params = self._component["parameters"]
        overridden = item.checkState() == Qt.CheckState.Checked
        if overridden == (params[key] is not None):
            return
        pack = battery_pack(params)
        current = {
            "charge_voltage": pack.charge_voltage_v,
            "cell_resistance": pack.cell_resistance_ohm,
            "c_rate": pack.c_rate,
            "pack_mass": pack.mass_g,
        }[key]

        def apply_edit() -> None:
            set_expression(params, key, None)
            params[key] = current if overridden else None

        label = "Override" if overridden else "Use default"
        self._api.edit_component(self._component, f"{label} {key}", apply_edit)
        self._load_battery()

    def _on_chemistry_changed(self, chemistry: str) -> None:
        if self._loading:
            return

        def apply_edit() -> None:
            params = self._component["parameters"]
            params["chemistry"] = chemistry
            for key in BATTERY_OVERRIDES:
                set_expression(params, key, None)
                params[key] = None

        self._api.edit_component(
            self._component, f"Set battery chemistry '{chemistry}'", apply_edit
        )
        self._load_battery()
