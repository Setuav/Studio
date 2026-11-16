"""Battery pack and cell property editor styled after Fuselage/Wing standards."""

from __future__ import annotations

from typing import Any, ClassVar

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from plugins.electrical_propulsion.models.battery import battery_pack_mass
from setuav_studio.api import StudioAPI
from setuav_studio.model.expression import set_expression
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin


class BatteryEditor(PropertyTableMixin, QWidget):
    """Property editor separating battery cell specifications from pack configuration."""

    # Typical cell specifications per chemistry, keyed by battery parameter. They
    # apply when the chemistry is chosen.
    CHEMISTRY_DEFAULTS: ClassVar[dict[str, dict[str, float]]] = {
        "LiPo": {
            "cell_nominal_voltage": 3.7,
            "cell_max_voltage": 4.2,
            "cell_min_voltage": 3.0,
            "max_discharge": 35.0,
            "burst_discharge": 70.0,
            "cell_mass": 130.0,
            "cell_capacity": 6000.0,
            "cell_resistance": 0.0025,
        },
        "Li-Ion (18650/21700)": {
            "cell_nominal_voltage": 3.6,
            "cell_max_voltage": 4.2,
            "cell_min_voltage": 2.5,
            "max_discharge": 10.0,
            "burst_discharge": 20.0,
            "cell_mass": 70.0,
            "cell_capacity": 4500.0,
            "cell_resistance": 0.015,
        },
        "LiFePO4": {
            "cell_nominal_voltage": 3.2,
            "cell_max_voltage": 3.65,
            "cell_min_voltage": 2.5,
            "max_discharge": 25.0,
            "burst_discharge": 50.0,
            "cell_mass": 140.0,
            "cell_capacity": 5000.0,
            "cell_resistance": 0.004,
        },
        "Solid-State": {
            "cell_nominal_voltage": 3.8,
            "cell_max_voltage": 4.35,
            "cell_min_voltage": 3.0,
            "max_discharge": 15.0,
            "burst_discharge": 30.0,
            "cell_mass": 100.0,
            "cell_capacity": 6500.0,
            "cell_resistance": 0.002,
        },
        "NiMH": {
            "cell_nominal_voltage": 1.2,
            "cell_max_voltage": 1.45,
            "cell_min_voltage": 1.0,
            "max_discharge": 5.0,
            "burst_discharge": 10.0,
            "cell_mass": 55.0,
            "cell_capacity": 2500.0,
            "cell_resistance": 0.02,
        },
    }

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
                ("capacity", "Pack Capacity"),
                ("nominal_voltage", "Pack Nominal Voltage"),
                ("internal_resistance", "Pack Internal Resistance"),
                ("packaging_mass", "Packaging & Wiring Mass"),
                ("max_discharge", "Continuous Discharge (C)"),
                ("burst_discharge", "Burst Discharge (C)"),
            ]
        )
        layout.addWidget(self.pack_table)

    def _create_cell_section(self) -> None:
        layout = self._create_section("Cell Properties", "fa6s.microchip")
        self.cell_table = self._property_table(
            [
                ("chemistry", "Cell Chemistry"),
                ("cell_capacity", "Cell Capacity"),
                ("cell_nominal_voltage", "Cell Nominal Voltage"),
                ("cell_max_voltage", "Cell Max Voltage"),
                ("cell_min_voltage", "Cell Cut-Off Voltage"),
                ("cell_resistance", "Cell Resistance"),
                ("cell_mass", "Cell Mass"),
            ]
        )
        layout.addWidget(self.cell_table)

    def _load_battery(self) -> None:
        self._loading = True
        try:
            params = self._component["parameters"]

            s = int(params["cell_count"])
            p = int(params["parallel_count"])
            chem = str(params["chemistry"])
            pack_cap = float(params["capacity"])
            v_nom = float(params["nominal_voltage"])
            r_pack = float(params["internal_resistance"])
            packaging_mass = float(params["packaging_mass"])
            c_cont = float(params["max_discharge"])
            c_burst = float(params["burst_discharge"])

            cell_cap = float(params["cell_capacity"])
            cell_v_nom = float(params["cell_nominal_voltage"])
            cell_v_max = float(params["cell_max_voltage"])
            cell_v_min = float(params["cell_min_voltage"])
            cell_res = float(params["cell_resistance"])
            cell_mass = float(params["cell_mass"])
            total_mass = float(self._component["mass"])

            # General
            self._set_property_value(
                self.general_table, "name", str(self._component.get("name") or "")
            )
            self._set_property_value(
                self.general_table, "type", str(self._component.get("type") or ""), editable=False
            )
            self._set_property_value(
                self.general_table, "mass", f"{total_mass:.1f}", editable=False
            )
            self._set_property_value(
                self.general_table, "manufacturer", str(self._component.get("manufacturer") or "")
            )
            self._set_property_value(
                self.general_table, "model", str(self._component.get("model") or "")
            )

            # Pack table
            self._set_property_spinbox(
                self.pack_table,
                "cell_count",
                s,
                min_val=1,
                max_val=100,
                step=1,
                decimals=0,
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("cell_count", v),
            )
            self._set_property_spinbox(
                self.pack_table,
                "parallel_count",
                p,
                min_val=1,
                max_val=100,
                step=1,
                decimals=0,
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("parallel_count", v),
            )
            self._set_property_spinbox(
                self.pack_table,
                "capacity",
                pack_cap,
                min_val=0,
                max_val=1e6,
                step=100,
                decimals=0,
                suffix="mAh",
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("capacity", v),
            )
            self._set_property_spinbox(
                self.pack_table,
                "nominal_voltage",
                v_nom,
                min_val=0,
                max_val=1000,
                step=0.1,
                decimals=1,
                suffix="V",
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("nominal_voltage", v),
            )
            self._set_property_spinbox(
                self.pack_table,
                "internal_resistance",
                r_pack,
                min_val=0,
                max_val=100,
                step=0.001,
                decimals=4,
                suffix="Ω",
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("internal_resistance", v),
            )
            self._set_property_spinbox(
                self.pack_table,
                "packaging_mass",
                packaging_mass,
                min_val=0,
                max_val=1e5,
                step=1.0,
                decimals=1,
                suffix="g",
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("packaging_mass", v),
            )
            self._set_property_spinbox(
                self.pack_table,
                "max_discharge",
                c_cont,
                min_val=0,
                max_val=500,
                step=1,
                decimals=0,
                suffix="C",
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("max_discharge", v),
            )
            self._set_property_spinbox(
                self.pack_table,
                "burst_discharge",
                c_burst,
                min_val=0,
                max_val=500,
                step=1,
                decimals=0,
                suffix="C",
                target_data=params,
                on_changed=lambda v: self._on_pack_param_changed("burst_discharge", v),
            )

            # Cell table
            chem_options = [
                ("LiPo", "LiPo (3.7V)"),
                ("Li-Ion (18650/21700)", "Li-Ion (3.6V)"),
                ("LiFePO4", "LiFePO4 (3.2V)"),
                ("Solid-State", "Solid-State (3.8V)"),
                ("NiMH", "NiMH (1.2V)"),
            ]
            self._set_property_combo(
                self.cell_table,
                "chemistry",
                chem,
                chem_options,
                self._on_chemistry_changed,
            )
            self._set_property_spinbox(
                self.cell_table,
                "cell_capacity",
                cell_cap,
                min_val=0,
                max_val=1e6,
                step=100,
                decimals=0,
                suffix="mAh",
                target_data=params,
                on_changed=lambda v: self._on_cell_param_changed("cell_capacity", v),
            )
            self._set_property_spinbox(
                self.cell_table,
                "cell_nominal_voltage",
                cell_v_nom,
                min_val=0,
                max_val=100,
                step=0.05,
                decimals=2,
                suffix="V",
                target_data=params,
                on_changed=lambda v: self._on_cell_param_changed("cell_nominal_voltage", v),
            )
            self._set_property_spinbox(
                self.cell_table,
                "cell_max_voltage",
                cell_v_max,
                min_val=0,
                max_val=100,
                step=0.05,
                decimals=2,
                suffix="V",
                target_data=params,
                on_changed=lambda v: self._on_cell_param_changed("cell_max_voltage", v),
            )
            self._set_property_spinbox(
                self.cell_table,
                "cell_min_voltage",
                cell_v_min,
                min_val=0,
                max_val=100,
                step=0.05,
                decimals=2,
                suffix="V",
                target_data=params,
                on_changed=lambda v: self._on_cell_param_changed("cell_min_voltage", v),
            )
            self._set_property_spinbox(
                self.cell_table,
                "cell_resistance",
                cell_res,
                min_val=0,
                max_val=10,
                step=0.0005,
                decimals=4,
                suffix="Ω",
                target_data=params,
                on_changed=lambda v: self._on_cell_param_changed("cell_resistance", v),
            )
            self._set_property_spinbox(
                self.cell_table,
                "cell_mass",
                cell_mass,
                min_val=0,
                max_val=10000,
                step=1.0,
                decimals=1,
                suffix="g",
                target_data=params,
                on_changed=lambda v: self._on_cell_param_changed("cell_mass", v),
            )

        finally:
            self._loading = False

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
        try:
            num = float(value)
        except (ValueError, TypeError):
            return
        cell = self._property_cell(self.pack_table, key)
        expr_to_store = cell.stored_expression() if cell is not None else None

        def apply_edit() -> None:
            p = self._component["parameters"]
            set_expression(p, key, expr_to_store)
            if key in {"cell_count", "parallel_count"}:
                p[key] = max(1, int(num))
            else:
                p[key] = float(num)

            self._component["mass"] = battery_pack_mass(p)

            if key == "cell_count":
                p["nominal_voltage"] = p["cell_count"] * float(p["cell_nominal_voltage"])
            elif key == "parallel_count":
                p["capacity"] = p["parallel_count"] * float(p["cell_capacity"])

        self._api.edit_component(self._component, f"Set {key}", apply_edit)
        self._load_battery()

    def _on_cell_param_changed(self, key: str, value: Any) -> None:
        if self._loading:
            return
        try:
            num = float(value)
        except (ValueError, TypeError):
            return
        cell = self._property_cell(self.cell_table, key)
        expr_to_store = cell.stored_expression() if cell is not None else None

        def apply_edit() -> None:
            p = self._component["parameters"]
            set_expression(p, key, expr_to_store)
            p[key] = float(num)

            self._component["mass"] = battery_pack_mass(p)

            s = int(p["cell_count"])
            par = int(p["parallel_count"])
            if key == "cell_capacity":
                p["capacity"] = par * float(num)
            elif key == "cell_nominal_voltage":
                p["nominal_voltage"] = s * float(num)
            elif key == "cell_resistance":
                p["internal_resistance"] = (s / par) * float(num)

        self._api.edit_component(self._component, f"Set {key}", apply_edit)
        self._load_battery()

    def _on_chemistry_changed(self, new_chem: str) -> None:
        if self._loading:
            return

        preset = self.CHEMISTRY_DEFAULTS[new_chem]

        def apply_chem() -> None:
            p = self._component["parameters"]
            p["chemistry"] = new_chem
            p.update(preset)

            s = int(p["cell_count"])
            par = int(p["parallel_count"])
            p["nominal_voltage"] = s * preset["cell_nominal_voltage"]
            p["capacity"] = par * preset["cell_capacity"]
            p["internal_resistance"] = (s / par) * preset["cell_resistance"]

            self._component["mass"] = battery_pack_mass(p)

        self._api.edit_component(self._component, f"Set battery chemistry '{new_chem}'", apply_chem)
        self._load_battery()
