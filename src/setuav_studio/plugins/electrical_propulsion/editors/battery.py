"""Battery pack and cell property editor styled after Fuselage/Wing standards."""

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

from setuav_studio.ui.icons import set_label_icon
from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.property_tables import PropertyTableMixin


class BatteryEditor(PropertyTableMixin, QWidget):
    """Property editor separating battery cell specifications from pack configuration."""

    CHEMISTRY_DEFAULTS = {
        "LiPo": {"nominal_v": 3.7, "max_v": 4.2, "min_v": 3.0, "c_rate": 35.0, "burst_c": 70.0, "cell_mass": 130.0, "cell_cap": 6000.0, "cell_r": 0.0025},
        "Li-Ion (18650/21700)": {"nominal_v": 3.6, "max_v": 4.2, "min_v": 2.5, "c_rate": 10.0, "burst_c": 20.0, "cell_mass": 70.0, "cell_cap": 4500.0, "cell_r": 0.015},
        "LiFePO4": {"nominal_v": 3.2, "max_v": 3.65, "min_v": 2.5, "c_rate": 25.0, "burst_c": 50.0, "cell_mass": 140.0, "cell_cap": 5000.0, "cell_r": 0.004},
        "Solid-State": {"nominal_v": 3.8, "max_v": 4.35, "min_v": 3.0, "c_rate": 15.0, "burst_c": 30.0, "cell_mass": 100.0, "cell_cap": 6500.0, "cell_r": 0.002},
        "NiMH": {"nominal_v": 1.2, "max_v": 1.45, "min_v": 1.0, "c_rate": 5.0, "burst_c": 10.0, "cell_mass": 55.0, "cell_cap": 2500.0, "cell_r": 0.02},
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
                ("mass", "Total Pack Mass (g) [Calculated]"),
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
                ("capacity", "Pack Capacity (mAh)"),
                ("nominal_voltage", "Pack Nominal Voltage (V)"),
                ("internal_resistance", "Pack Internal Resistance (Ω)"),
                ("packaging_mass", "Packaging & Wiring Mass (g)"),
                ("max_discharge", "Continuous Discharge (C)"),
                ("burst_discharge", "Burst Discharge (C)"),
            ]
        )
        self.pack_table.cellChanged.connect(self._update_pack_cell)
        layout.addWidget(self.pack_table)

    def _create_cell_section(self) -> None:
        layout = self._create_section("Cell Properties", "fa6s.microchip")
        self.cell_table = self._property_table(
            [
                ("chemistry", "Cell Chemistry"),
                ("cell_capacity", "Cell Capacity (mAh)"),
                ("cell_nominal_voltage", "Cell Nominal Voltage (V)"),
                ("cell_max_voltage", "Cell Max Voltage (V)"),
                ("cell_min_voltage", "Cell Cut-Off Voltage (V)"),
                ("cell_resistance", "Cell Resistance (Ω)"),
                ("cell_mass", "Cell Mass (g)"),
            ]
        )
        self.cell_table.cellChanged.connect(self._update_cell_param)
        layout.addWidget(self.cell_table)

    def _load_battery(self) -> None:
        self._loading = True
        try:
            params = self._component.get("parameters", {})

            # Pack S/P
            s = int(params.get("cell_count", params.get("series_count", 6)))
            p = int(params.get("parallel_count", 1))

            # Cell specs
            chem = str(params.get("chemistry", "LiPo"))
            defaults = self.CHEMISTRY_DEFAULTS.get(chem, self.CHEMISTRY_DEFAULTS["LiPo"])

            cell_cap = float(params.get("cell_capacity", params.get("capacity", 6000.0) / max(1, p)))
            cell_v_nom = float(params.get("cell_nominal_voltage", defaults["nominal_v"]))
            cell_v_max = float(params.get("cell_max_voltage", defaults["max_v"]))
            cell_v_min = float(params.get("cell_min_voltage", defaults["min_v"]))
            cell_res = float(params.get("cell_resistance", defaults["cell_r"]))
            cell_mass = float(params.get("cell_mass", defaults["cell_mass"]))

            packaging_mass = float(params.get("packaging_mass", 40.0))

            # Calculated Pack Values
            pack_cap = float(params.get("capacity", s * p * cell_cap / max(1, s)))
            v_nom = float(params.get("nominal_voltage", s * cell_v_nom))
            r_pack = float(params.get("internal_resistance", (s / max(1, p)) * cell_res))
            c_cont = float(params.get("max_discharge", defaults["c_rate"]))
            c_burst = float(params.get("burst_discharge", defaults["burst_c"]))

            # Calculated Total Pack Mass = (S * P * cell_mass) + packaging_mass
            total_mass = (s * p * cell_mass) + packaging_mass
            self._component["mass"] = total_mass
            params["mass"] = total_mass

            # General
            self._set_property_value(self.general_table, "name", str(self._component.get("name") or ""))
            self._set_property_value(self.general_table, "type", str(self._component.get("type") or ""), editable=False)
            self._set_property_value(self.general_table, "mass", f"{total_mass:.1f}", editable=False)
            self._set_property_value(self.general_table, "manufacturer", str(self._component.get("manufacturer") or ""))
            self._set_property_value(self.general_table, "model", str(self._component.get("model") or ""))

            # Pack table
            self._set_property_value(self.pack_table, "cell_count", str(s))
            self._set_property_value(self.pack_table, "parallel_count", str(p))
            self._set_property_value(self.pack_table, "capacity", f"{pack_cap:.0f}")
            self._set_property_value(self.pack_table, "nominal_voltage", f"{v_nom:.1f}")
            self._set_property_value(self.pack_table, "internal_resistance", f"{r_pack:.4f}")
            self._set_property_value(self.pack_table, "packaging_mass", f"{packaging_mass:.1f}")
            self._set_property_value(self.pack_table, "max_discharge", f"{c_cont:.0f}")
            self._set_property_value(self.pack_table, "burst_discharge", f"{c_burst:.0f}")

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
            self._set_property_value(self.cell_table, "cell_capacity", f"{cell_cap:.0f}")
            self._set_property_value(self.cell_table, "cell_nominal_voltage", f"{cell_v_nom:.2f}")
            self._set_property_value(self.cell_table, "cell_max_voltage", f"{cell_v_max:.2f}")
            self._set_property_value(self.cell_table, "cell_min_voltage", f"{cell_v_min:.2f}")
            self._set_property_value(self.cell_table, "cell_resistance", f"{cell_res:.4f}")
            self._set_property_value(self.cell_table, "cell_mass", f"{cell_mass:.1f}")

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

    def _update_pack_cell(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.pack_table, row)
        val_text = self._property_text(self.pack_table, row)
        num = self._parse_number(val_text) or 0.0

        def apply_edit() -> None:
            p = self._component.setdefault("parameters", {})
            if key in {"cell_count", "parallel_count"}:
                p[key] = max(1, int(num))
            else:
                p[key] = float(num)

            # Recalculate derived totals
            s = int(p.get("cell_count", 6))
            par = int(p.get("parallel_count", 1))
            cell_m = float(p.get("cell_mass", 130.0))
            pkg_m = float(p.get("packaging_mass", 40.0))
            total_m = (s * par * cell_m) + pkg_m

            self._component["mass"] = total_m
            p["mass"] = total_m

            if key == "cell_count":
                cell_v = float(p.get("cell_nominal_voltage", 3.7))
                p["nominal_voltage"] = s * cell_v
            elif key == "parallel_count":
                cell_c = float(p.get("cell_capacity", 6000.0))
                p["capacity"] = par * cell_c

        self._api.edit_component(self._component, f"Set {key}", apply_edit)
        self._load_battery()

    def _update_cell_param(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.cell_table, row)
        val_text = self._property_text(self.cell_table, row)
        num = self._parse_number(val_text) or 0.0

        def apply_edit() -> None:
            p = self._component.setdefault("parameters", {})
            p[key] = float(num)

            # Recalculate derived totals
            s = int(p.get("cell_count", 6))
            par = int(p.get("parallel_count", 1))
            cell_m = float(p.get("cell_mass", 130.0))
            pkg_m = float(p.get("packaging_mass", 40.0))
            total_m = (s * par * cell_m) + pkg_m

            self._component["mass"] = total_m
            p["mass"] = total_m

            if key == "cell_capacity":
                p["capacity"] = par * float(num)
            elif key == "cell_nominal_voltage":
                p["nominal_voltage"] = s * float(num)
            elif key == "cell_resistance":
                p["internal_resistance"] = (s / max(1, par)) * float(num)

        self._api.edit_component(self._component, f"Set {key}", apply_edit)
        self._load_battery()

    def _on_chemistry_changed(self, new_chem: str) -> None:
        if self._loading:
            return

        defaults = self.CHEMISTRY_DEFAULTS.get(new_chem, self.CHEMISTRY_DEFAULTS["LiPo"])

        def apply_chem() -> None:
            p = self._component.setdefault("parameters", {})
            p["chemistry"] = new_chem
            p["cell_nominal_voltage"] = defaults["nominal_v"]
            p["cell_max_voltage"] = defaults["max_v"]
            p["cell_min_voltage"] = defaults["min_v"]
            p["cell_mass"] = defaults["cell_mass"]
            p["cell_capacity"] = defaults["cell_cap"]
            p["cell_resistance"] = defaults["cell_r"]
            p["max_discharge"] = defaults["c_rate"]
            p["burst_discharge"] = defaults["burst_c"]

            s = int(p.get("cell_count", 6))
            par = int(p.get("parallel_count", 1))
            pkg_m = float(p.get("packaging_mass", 40.0))

            p["nominal_voltage"] = s * defaults["nominal_v"]
            p["capacity"] = par * defaults["cell_cap"]
            p["internal_resistance"] = (s / max(1, par)) * defaults["cell_r"]

            total_m = (s * par * defaults["cell_mass"]) + pkg_m
            self._component["mass"] = total_m
            p["mass"] = total_m
