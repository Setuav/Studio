"""Mission Requirements and Parameter Input Dock for Sizing."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from plugins.sizing.engine.aerodynamics import AeroParameters
from plugins.sizing.engine.battery import BatteryParameters
from plugins.sizing.engine.weight import MissionProfile
from plugins.sizing.presets import PRESETS, SURVEILLANCE_PRESET
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.widget.button import set_button_role
from setuav_studio.ui.widget.spinbox import set_table_spinbox
from setuav_studio.ui.widget.table import ExpressionPropertyCell, PropertyTableMixin
from setuav_studio_sdk import StudioAPI


class SizingRequirementsDock(PropertyTableMixin, QWidget):
    """Configuration dock for sizing requirements using native property tables with fx assistant."""

    requirements_changed = Signal(object, object, object)  # (MissionProfile, AeroParameters, BatteryParameters)

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sizing.requirements_widget")
        self._api = api
        self._updating = False
        self._section_icons: list[tuple[QLabel, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Build sections
        self._create_preset_section()
        self._create_mission_section()
        self._create_field_section()
        self._create_aero_section()
        self._create_powertrain_section()
        self._create_action_section()

        self._content_layout.addStretch(1)

        # Load initial default preset
        self._apply_preset(SURVEILLANCE_PRESET.id)

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        sec_layout = QVBoxLayout(section)
        sec_layout.setContentsMargins(0, 0, 0, 0)
        sec_layout.setSpacing(4)

        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(6)

        if icon_name:
            icon_label = QLabel()
            set_label_icon(icon_label, icon_name)
            self._section_icons.append((icon_label, icon_name))
            h_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        h_layout.addWidget(title_label)
        h_layout.addStretch(1)

        sec_layout.addWidget(header)
        self._content_layout.addWidget(section)
        return sec_layout

    def _create_cell(
        self,
        table: QTableWidget,
        row: int,
        key: str,
        label: str,
        value: float,
        *,
        quantity: str | None = None,
        suffix: str = "",
        min_val: float = -1e6,
        max_val: float = 1e6,
        step: float = 1.0,
        decimals: int = 2,
    ) -> ExpressionPropertyCell:
        """Create an ExpressionPropertyCell with fx assistant and unit badge in table."""
        cell: ExpressionPropertyCell = set_table_spinbox(
            table,
            row,
            1,
            value,
            min_val=min_val,
            max_val=max_val,
            step=step,
            decimals=decimals,
            quantity=quantity,
            suffix=suffix,
            on_changed=lambda _v: self._emit_changes(),
            api=self._api,
            label=label,
        )
        if quantity is None and suffix:
            cell._quantity = None
            cell._suffix = suffix
            cell._refresh_display()
        return cell

    def _create_preset_section(self) -> None:
        sec_layout = self._create_section("Design Preset", "fa6s.layer-group")

        self.preset_combo = QComboBox()
        for preset_id, preset in PRESETS.items():
            self.preset_combo.addItem(preset.name, preset_id)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_combo_changed)
        sec_layout.addWidget(self.preset_combo)

    def _create_mission_section(self) -> None:
        sec_layout = self._create_section("Mission Requirements", "fa6s.crosshairs")

        self.mission_table = self._property_table(
            [
                ("payload", "Payload Mass"),
                ("range", "Target Range"),
                ("endurance", "Flight Endurance"),
                ("v_cruise", "Cruise Speed"),
                ("v_stall", "Max Stall Speed"),
                ("v_climb", "Climb Speed"),
                ("roc", "Rate of Climb"),
            ]
        )

        self.cell_payload = self._create_cell(
            self.mission_table,
            0,
            "payload",
            "Payload Mass",
            500.0,
            quantity="mass",
            min_val=10.0,
            max_val=100000.0,
            step=50.0,
            decimals=1,
        )
        self.cell_range = self._create_cell(
            self.mission_table,
            1,
            "range",
            "Target Range",
            40.0,
            suffix="km",
            min_val=1.0,
            max_val=1000.0,
            step=5.0,
            decimals=1,
        )
        self.cell_endurance = self._create_cell(
            self.mission_table,
            2,
            "endurance",
            "Flight Endurance",
            45.0,
            suffix="min",
            min_val=1.0,
            max_val=1000.0,
            step=5.0,
            decimals=1,
        )
        self.cell_v_cruise = self._create_cell(
            self.mission_table,
            3,
            "v_cruise",
            "Cruise Speed",
            18.0,
            quantity="velocity",
            min_val=5.0,
            max_val=100.0,
            step=1.0,
            decimals=1,
        )
        self.cell_v_stall = self._create_cell(
            self.mission_table,
            4,
            "v_stall",
            "Max Stall Speed",
            11.0,
            quantity="velocity",
            min_val=3.0,
            max_val=50.0,
            step=0.5,
            decimals=1,
        )
        self.cell_v_climb = self._create_cell(
            self.mission_table,
            5,
            "v_climb",
            "Climb Speed",
            14.0,
            quantity="velocity",
            min_val=4.0,
            max_val=60.0,
            step=0.5,
            decimals=1,
        )
        self.cell_roc = self._create_cell(
            self.mission_table,
            6,
            "roc",
            "Rate of Climb",
            3.5,
            quantity="velocity",
            min_val=0.5,
            max_val=25.0,
            step=0.5,
            decimals=1,
        )

        sec_layout.addWidget(self.mission_table)

    def _create_field_section(self) -> None:
        sec_layout = self._create_section("Operating Conditions", "fa6s.mountain-sun")

        self.field_table = self._property_table(
            [
                ("altitude", "Cruise Altitude"),
                ("takeoff_run", "Takeoff Ground Roll"),
                ("landing_run", "Landing Ground Roll"),
                ("load_factor", "Turn Load Factor (n)"),
            ]
        )

        self.cell_altitude = self._create_cell(
            self.field_table,
            0,
            "altitude",
            "Cruise Altitude",
            500.0,
            suffix="m",
            min_val=0.0,
            max_val=10000.0,
            step=100.0,
            decimals=0,
        )
        self.cell_takeoff_run = self._create_cell(
            self.field_table,
            1,
            "takeoff_run",
            "Takeoff Ground Roll",
            25.0,
            suffix="m",
            min_val=2.0,
            max_val=500.0,
            step=5.0,
            decimals=1,
        )
        self.cell_landing_run = self._create_cell(
            self.field_table,
            2,
            "landing_run",
            "Landing Ground Roll",
            30.0,
            suffix="m",
            min_val=2.0,
            max_val=500.0,
            step=5.0,
            decimals=1,
        )
        self.cell_load_factor = self._create_cell(
            self.field_table,
            3,
            "load_factor",
            "Turn Load Factor (n)",
            1.41,
            min_val=1.0,
            max_val=5.0,
            step=0.1,
            decimals=2,
        )

        sec_layout.addWidget(self.field_table)

    def _create_aero_section(self) -> None:
        sec_layout = self._create_section("Aerodynamics & Wing", "fa6s.wind")

        self.aero_table = self._property_table(
            [
                ("cd0", "Zero-Lift Drag (CD0)"),
                ("ar", "Aspect Ratio (AR)"),
                ("oswald_e", "Oswald Efficiency (e)"),
                ("cl_max_clean", "CLmax (Clean)"),
                ("cl_max_takeoff", "CLmax (Takeoff)"),
                ("cl_max_landing", "CLmax (Landing)"),
            ]
        )

        self.cell_cd0 = self._create_cell(
            self.aero_table,
            0,
            "cd0",
            "Zero-Lift Drag (CD0)",
            0.025,
            min_val=0.010,
            max_val=0.080,
            step=0.002,
            decimals=4,
        )
        self.cell_ar = self._create_cell(
            self.aero_table,
            1,
            "ar",
            "Aspect Ratio (AR)",
            10.0,
            min_val=3.0,
            max_val=30.0,
            step=0.5,
            decimals=1,
        )
        self.cell_oswald_e = self._create_cell(
            self.aero_table,
            2,
            "oswald_e",
            "Oswald Efficiency (e)",
            0.80,
            min_val=0.50,
            max_val=0.98,
            step=0.02,
            decimals=2,
        )
        self.cell_cl_clean = self._create_cell(
            self.aero_table,
            3,
            "cl_max_clean",
            "CLmax (Clean)",
            1.40,
            min_val=0.8,
            max_val=2.5,
            step=0.05,
            decimals=2,
        )
        self.cell_cl_to = self._create_cell(
            self.aero_table,
            4,
            "cl_max_takeoff",
            "CLmax (Takeoff)",
            1.60,
            min_val=1.0,
            max_val=3.0,
            step=0.05,
            decimals=2,
        )
        self.cell_cl_land = self._create_cell(
            self.aero_table,
            5,
            "cl_max_landing",
            "CLmax (Landing)",
            1.80,
            min_val=1.0,
            max_val=3.5,
            step=0.05,
            decimals=2,
        )

        sec_layout.addWidget(self.aero_table)

    def _create_powertrain_section(self) -> None:
        sec_layout = self._create_section("Powertrain Technology", "fa6s.battery-three-quarters")

        self.powertrain_table = self._property_table(
            [
                ("specific_energy", "Battery Energy Density"),
                ("max_dod", "Max Depth of Discharge"),
                ("elec_efficiency", "Electrical Efficiency"),
                ("prop_efficiency", "Propeller Efficiency (Cruise)"),
                ("avionics_mass", "Avionics & Electronics Mass"),
            ]
        )

        self.cell_specific_energy = self._create_cell(
            self.powertrain_table,
            0,
            "specific_energy",
            "Battery Energy Density",
            180.0,
            quantity="specific_energy",
            suffix="Wh/kg",
            min_val=100.0,
            max_val=400.0,
            step=10.0,
            decimals=1,
        )
        self.cell_dod = self._create_cell(
            self.powertrain_table,
            1,
            "max_dod",
            "Max Depth of Discharge",
            80.0,
            suffix="%",
            min_val=50.0,
            max_val=95.0,
            step=5.0,
            decimals=1,
        )
        self.cell_elec_eff = self._create_cell(
            self.powertrain_table,
            2,
            "elec_efficiency",
            "Electrical Efficiency",
            85.0,
            suffix="%",
            min_val=60.0,
            max_val=98.0,
            step=1.0,
            decimals=1,
        )
        self.cell_prop_eff = self._create_cell(
            self.powertrain_table,
            3,
            "prop_efficiency",
            "Propeller Efficiency (Cruise)",
            80.0,
            suffix="%",
            min_val=40.0,
            max_val=92.0,
            step=1.0,
            decimals=1,
        )
        self.cell_avionics_mass = self._create_cell(
            self.powertrain_table,
            4,
            "avionics_mass",
            "Avionics & Electronics Mass",
            250.0,
            quantity="mass",
            min_val=10.0,
            max_val=10000.0,
            step=10.0,
            decimals=1,
        )

        sec_layout.addWidget(self.powertrain_table)

    def _create_action_section(self) -> None:
        btn_calc = QPushButton("Recalculate Constraints")
        set_button_role(btn_calc, "primary")
        btn_calc.clicked.connect(self._emit_changes)
        self._content_layout.addWidget(btn_calc)

    def _on_preset_combo_changed(self, index: int) -> None:
        preset_id = self.preset_combo.itemData(index)
        if isinstance(preset_id, str):
            self._apply_preset(preset_id)

    def _apply_preset(self, preset_id: str) -> None:
        preset = PRESETS.get(preset_id)
        if not preset:
            return

        self._updating = True
        try:
            m = preset.mission
            self.cell_payload.setValue(m.payload_mass_kg * 1000.0)
            self.cell_range.setValue(m.range_km)
            self.cell_endurance.setValue(m.endurance_min)
            self.cell_v_cruise.setValue(m.v_cruise_mps)
            self.cell_v_stall.setValue(m.v_stall_mps)
            self.cell_v_climb.setValue(m.v_climb_mps)
            self.cell_roc.setValue(m.roc_mps)
            self.cell_altitude.setValue(m.cruise_altitude_m)
            self.cell_takeoff_run.setValue(m.ground_roll_takeoff_m)
            self.cell_landing_run.setValue(m.ground_roll_landing_m)
            self.cell_load_factor.setValue(m.turn_load_factor_n)
            self.cell_avionics_mass.setValue(m.avionics_mass_kg * 1000.0)

            a = preset.aero
            self.cell_cd0.setValue(a.cd0)
            self.cell_ar.setValue(a.aspect_ratio)
            self.cell_oswald_e.setValue(a.oswald_e)
            self.cell_cl_clean.setValue(a.cl_max_clean)
            self.cell_cl_to.setValue(a.cl_max_takeoff)
            self.cell_cl_land.setValue(a.cl_max_landing)

            b = preset.battery
            self.cell_specific_energy.setValue(b.specific_energy_wh_kg)
            self.cell_dod.setValue(b.max_dod * 100.0)
            self.cell_elec_eff.setValue(b.powertrain_efficiency * 100.0)
            self.cell_prop_eff.setValue(80.0)
        finally:
            self._updating = False

        self._emit_changes()

    def get_current_configuration(self) -> tuple[MissionProfile, AeroParameters, BatteryParameters]:
        """Extract typed parameters from table inputs."""
        mission = MissionProfile(
            payload_mass_kg=self.cell_payload.value() / 1000.0,
            range_km=self.cell_range.value(),
            endurance_min=self.cell_endurance.value(),
            v_cruise_mps=self.cell_v_cruise.value(),
            v_stall_mps=self.cell_v_stall.value(),
            v_climb_mps=self.cell_v_climb.value(),
            roc_mps=self.cell_roc.value(),
            cruise_altitude_m=self.cell_altitude.value(),
            ground_roll_takeoff_m=self.cell_takeoff_run.value(),
            ground_roll_landing_m=self.cell_landing_run.value(),
            turn_load_factor_n=self.cell_load_factor.value(),
            avionics_mass_kg=self.cell_avionics_mass.value() / 1000.0,
        )
        aero = AeroParameters.create(
            cd0=self.cell_cd0.value(),
            aspect_ratio=self.cell_ar.value(),
            oswald_e=self.cell_oswald_e.value(),
            cl_max_clean=self.cell_cl_clean.value(),
            cl_max_takeoff=self.cell_cl_to.value(),
            cl_max_landing=self.cell_cl_land.value(),
        )
        battery = BatteryParameters(
            specific_energy_wh_kg=self.cell_specific_energy.value(),
            max_dod=self.cell_dod.value() / 100.0,
            powertrain_efficiency=self.cell_elec_eff.value() / 100.0,
        )
        return mission, aero, battery

    def _emit_changes(self) -> None:
        if self._updating:
            return
        mission, aero, battery = self.get_current_configuration()
        self.requirements_changed.emit(mission, aero, battery)


__all__ = ["SizingRequirementsDock"]
