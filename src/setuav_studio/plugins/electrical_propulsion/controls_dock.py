"""Propulsion Analysis Controls dock widget."""

from __future__ import annotations

import math
from typing import Any, Callable
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import StudioAPI


class PropulsionControlsDock(QWidget):
    """Clean controls and configuration dock for Propulsion Analysis."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._loading = False
        self._current_mode = "airspeed_sweep"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_system_section()
        self._create_mode_section()
        self._create_parameters_section()
        self._create_atmosphere_section()
        self._create_battery_state_section()
        self._create_actions_section()

        self._content_layout.addStretch(1)

        self._api.on_project_changed(lambda _p: self._refresh_assemblies())
        self._api.on_project_content_changed(lambda _p: self._refresh_assemblies())
        self._refresh_assemblies()

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(section)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = QWidget()
        header.setProperty("sectionHeader", True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 4, 0, 2)
        header_layout.setSpacing(6)

        if icon_name:
            icon_label = QLabel()
            pixmap = get_icon(icon_name).pixmap(14, 14)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_system_section(self) -> None:
        layout = self._create_section("Target System", "fa6s.bolt")
        self.system_table = self._property_table([
            ("assembly", "Assembly"),
            ("motor_info", "Motor"),
            ("propeller_info", "Propeller"),
            ("battery_info", "Battery"),
        ])
        layout.addWidget(self.system_table)

    def _create_mode_section(self) -> None:
        layout = self._create_section("Analysis Mode", "fa6s.sliders")
        self.mode_table = self._property_table([
            ("mode", "Mode"),
        ])
        mode_options = [
            ("airspeed_sweep", "Airspeed Sweep (Fixed Throttle)"),
            ("throttle_sweep", "Throttle Sweep (Fixed Airspeed)"),
            ("operating_point", "Single Operating Point"),
        ]
        self._set_property_combo(
            self.mode_table,
            "mode",
            "airspeed_sweep",
            mode_options,
            self._on_mode_changed,
        )
        layout.addWidget(self.mode_table)

    def _create_parameters_section(self) -> None:
        self.params_section_layout = self._create_section("Parameters", "fa6s.list-check")
        self.parameters_table = self._property_table([])
        self.parameters_table.cellChanged.connect(self._on_parameter_cell_changed)
        self.params_section_layout.addWidget(self.parameters_table)
        self._rebuild_parameters_table("airspeed_sweep")

    def _create_atmosphere_section(self) -> None:
        layout = self._create_section("Atmosphere", "fa6s.cloud")
        self.atmosphere_table = self._property_table([
            ("altitude", "Altitude (m)"),
            ("temperature", "Temperature (°C)"),
            ("density", "Air Density (kg/m³)"),
        ])
        self.atmosphere_table.cellChanged.connect(self._on_atmosphere_cell_changed)
        self._set_property_value(self.atmosphere_table, "altitude", "0.0")
        self._set_property_value(self.atmosphere_table, "temperature", "15.0")
        self._set_property_value(self.atmosphere_table, "density", "1.225", editable=False)
        layout.addWidget(self.atmosphere_table)

    def _create_battery_state_section(self) -> None:
        layout = self._create_section("Battery State", "fa6s.battery-half")
        self.battery_state_table = self._property_table([
            ("soc", "State of Charge"),
        ])
        soc_options = [
            ("full", "Full (4.20 V / cell)"),
            ("nominal", "Nominal (3.70 V / cell)"),
            ("discharged", "Discharged (3.50 V / cell)"),
        ]
        self._set_property_combo(
            self.battery_state_table,
            "soc",
            "full",
            soc_options,
            lambda _val: None,
        )
        layout.addWidget(self.battery_state_table)

    def _create_actions_section(self) -> None:
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        actions_layout = QHBoxLayout(container)
        actions_layout.setContentsMargins(0, 8, 0, 2)
        actions_layout.setSpacing(6)

        self.run_button = QPushButton("Run Analysis", self)
        self.run_button.setProperty("accent", True)
        self.run_button.setIcon(get_icon("fa6s.play"))
        self.run_button.setFixedHeight(28)
        actions_layout.addWidget(self.run_button, 2)

        self.reset_button = QPushButton("Reset", self)
        self.reset_button.setIcon(get_icon("fa6s.arrow-rotate-left"))
        self.reset_button.setFixedHeight(28)
        self.reset_button.clicked.connect(self._reset_defaults)
        actions_layout.addWidget(self.reset_button, 1)

        self._content_layout.addWidget(container)

    def _on_mode_changed(self, mode: str) -> None:
        self._current_mode = mode
        self._rebuild_parameters_table(mode)

    def _rebuild_parameters_table(self, mode: str) -> None:
        self._loading = True
        if mode == "airspeed_sweep":
            defs = [
                ("throttle", "Throttle (%)"),
                ("v_min", "Min Airspeed (m/s)"),
                ("v_max", "Max Airspeed (m/s)"),
                ("v_step", "Airspeed Step (m/s)"),
            ]
            self._configure_property_table(self.parameters_table, defs)
            self._set_property_value(self.parameters_table, "throttle", "100")
            self._set_property_value(self.parameters_table, "v_min", "0.0")
            self._set_property_value(self.parameters_table, "v_max", "35.0")
            self._set_property_value(self.parameters_table, "v_step", "1.0")
        elif mode == "throttle_sweep":
            defs = [
                ("airspeed", "Airspeed (m/s)"),
                ("t_min", "Min Throttle (%)"),
                ("t_max", "Max Throttle (%)"),
                ("t_step", "Throttle Step (%)"),
            ]
            self._configure_property_table(self.parameters_table, defs)
            self._set_property_value(self.parameters_table, "airspeed", "0.0")
            self._set_property_value(self.parameters_table, "t_min", "10")
            self._set_property_value(self.parameters_table, "t_max", "100")
            self._set_property_value(self.parameters_table, "t_step", "5")
        elif mode == "operating_point":
            defs = [
                ("airspeed", "Airspeed (m/s)"),
                ("throttle", "Throttle (%)"),
            ]
            self._configure_property_table(self.parameters_table, defs)
            self._set_property_value(self.parameters_table, "airspeed", "18.0")
            self._set_property_value(self.parameters_table, "throttle", "75")
        self._loading = False

    def _on_parameter_cell_changed(self, row: int, col: int) -> None:
        if self._loading or col != 1:
            return

    def _on_atmosphere_cell_changed(self, row: int, col: int) -> None:
        if self._loading or col != 1:
            return
        self._update_isa_density()

    def _update_isa_density(self) -> None:
        try:
            alt_text = self._property_value(self.atmosphere_table, "altitude")
            temp_text = self._property_value(self.atmosphere_table, "temperature")
            alt = float(alt_text) if alt_text else 0.0
            temp_c = float(temp_text) if temp_text else 15.0
        except ValueError:
            return

        # Standard Atmosphere formula
        t_kelvin = temp_c + 273.15
        p0 = 101325.0
        r_air = 287.058
        if alt <= 11000:
            pressure = p0 * ((1 - 0.0065 * alt / 288.15) ** 5.25588)
        else:
            pressure = 22632.0 * math.exp(-9.80665 * (alt - 11000) / (r_air * 216.65))

        density = pressure / (r_air * max(t_kelvin, 1.0))
        self._loading = True
        self._set_property_value(
            self.atmosphere_table, "density", f"{density:.3f}", editable=False
        )
        self._loading = False

    def _reset_defaults(self) -> None:
        self._loading = True
        self._set_property_value(self.atmosphere_table, "altitude", "0.0")
        self._set_property_value(self.atmosphere_table, "temperature", "15.0")
        self._set_property_value(self.atmosphere_table, "density", "1.225", editable=False)
        self._set_table_combo_selection(self.mode_table, "mode", "airspeed_sweep")
        self._set_table_combo_selection(self.battery_state_table, "soc", "full")
        self._rebuild_parameters_table("airspeed_sweep")
        self._loading = False

    def _refresh_assemblies(self) -> None:
        proj = self._api.current_project
        if proj is None:
            self._set_property_value(self.system_table, "assembly", "No Project", editable=False)
            self._set_property_value(self.system_table, "motor_info", "-", editable=False)
            self._set_property_value(self.system_table, "propeller_info", "-", editable=False)
            self._set_property_value(self.system_table, "battery_info", "-", editable=False)
            self.run_button.setEnabled(False)
            return

        assemblies = proj.data.get("assemblies", [])
        prop_assemblies = [
            a for a in assemblies
            if a.get("type") == "org.setuav.core:electric-propulsion-system"
        ]

        if not prop_assemblies:
            self._set_property_value(self.system_table, "assembly", "None", editable=False)
            self._set_property_value(self.system_table, "motor_info", "-", editable=False)
            self._set_property_value(self.system_table, "propeller_info", "-", editable=False)
            self._set_property_value(self.system_table, "battery_info", "-", editable=False)
            self.run_button.setEnabled(False)
            return

        options = [
            (str(a.get("id")), str(a.get("name") or a.get("id")))
            for a in prop_assemblies
        ]
        self._set_property_combo(
            self.system_table,
            "assembly",
            options[0][0],
            options,
            self._on_assembly_selected,
        )
        self._on_assembly_selected(options[0][0])
        self.run_button.setEnabled(True)

    def _on_assembly_selected(self, assembly_id: str) -> None:
        proj = self._api.current_project
        if not proj:
            return

        assemblies = proj.data.get("assemblies", [])
        components = proj.data.get("components", [])
        assembly = next((a for a in assemblies if a.get("id") == assembly_id), None)
        if not assembly:
            return

        members = assembly.get("members", {})
        comp_map = {c.get("id"): c for c in components}

        # Motor Info
        motor_ids = members.get("motors", [])
        motor = comp_map.get(motor_ids[0]) if motor_ids else None
        motor_text = f"{motor.get('name') or motor.get('model') or motor.get('id')}" if motor else "-"
        self._set_property_value(self.system_table, "motor_info", motor_text, editable=False)

        # Propeller Info
        prop_ids = members.get("propulsors", [])
        prop = comp_map.get(prop_ids[0]) if prop_ids else None
        prop_text = f"{prop.get('name') or prop.get('model') or prop.get('id')}" if prop else "-"
        self._set_property_value(self.system_table, "propeller_info", prop_text, editable=False)

        # Battery Info
        bat_id = members.get("battery")
        battery = comp_map.get(bat_id) if bat_id else None
        if battery:
            params = battery.get("parameters", {})
            pack = params.get("pack", {})
            cell = params.get("cell", {})
            s = pack.get("series_count") or params.get("cell_count") or params.get("series_count", 1)
            cap = pack.get("capacity") or params.get("capacity", 0)
            chem = cell.get("chemistry") or params.get("chemistry", "LiPo")
            bat_text = f"{int(s)}S {chem} ({float(cap):.0f} mAh)"
        else:
            bat_text = "-"
        self._set_property_value(self.system_table, "battery_info", bat_text, editable=False)

    def get_configuration(self) -> dict[str, Any]:
        """Collect all configured parameters for the propulsion solver."""
        return {
            "assembly_id": self._get_table_combo_value(self.system_table, "assembly"),
            "mode": self._current_mode,
            "soc": self._get_table_combo_value(self.battery_state_table, "soc"),
            "altitude": float(self._property_value(self.atmosphere_table, "altitude") or 0.0),
            "temperature": float(self._property_value(self.atmosphere_table, "temperature") or 15.0),
            "density": float(self._property_value(self.atmosphere_table, "density") or 1.225),
            "parameters": {
                self._property_key(self.parameters_table, row): self._property_value_by_row(self.parameters_table, row)
                for row in range(self.parameters_table.rowCount())
            },
        }

    # Helper Table Methods
    @classmethod
    def _property_table(cls, definitions: list[tuple[str, str]]) -> QTableWidget:
        table = cls._table(["Property", "Value"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        cls._configure_property_table(table, definitions)
        return table

    @classmethod
    def _configure_property_table(
        cls, table: QTableWidget, definitions: list[tuple[str, str]]
    ) -> None:
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, 1)
            if widget is not None:
                table.removeCellWidget(row, 1)
                widget.deleteLater()
        table.clearContents()
        table.setRowCount(len(definitions))
        for row, (key, label) in enumerate(definitions):
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.ItemDataRole.UserRole, key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, label_item)
            val_item = QTableWidgetItem()
            table.setItem(row, 1, val_item)
        cls._fit_table_height(table, len(definitions))

    def _set_property_combo(
        self,
        table: QTableWidget,
        key: str,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Callable[[str], None],
    ) -> None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            self._set_table_combo(table, row, 1, value, options, on_changed)
            return

    @staticmethod
    def _set_table_combo(
        table: QTableWidget,
        row: int,
        column: int,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Callable[[str], None],
    ) -> None:
        item = table.item(row, column)
        if item is not None:
            item.setText("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        combo = QComboBox(table)
        combo.setProperty("tableEditor", True)
        combo.setFont(QApplication.font())
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        combo.view().setProperty("tableComboPopup", True)
        combo.view().setFont(QApplication.font())
        for option_value, label in options:
            combo.addItem(label, option_value)
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(
            lambda _index, editor=combo, callback=on_changed: callback(
                str(editor.currentData())
            )
        )
        table.setCellWidget(row, column, combo)

    @staticmethod
    def _set_table_combo_selection(table: QTableWidget, key: str, value: str) -> None:
        for row in range(table.rowCount()):
            if PropulsionControlsDock._property_key(table, row) == key:
                combo = table.cellWidget(row, 1)
                if isinstance(combo, QComboBox):
                    idx = combo.findData(value)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                return

    @staticmethod
    def _get_table_combo_value(table: QTableWidget, key: str) -> str:
        for row in range(table.rowCount()):
            if PropulsionControlsDock._property_key(table, row) == key:
                combo = table.cellWidget(row, 1)
                if isinstance(combo, QComboBox):
                    return str(combo.currentData() or "")
                item = table.item(row, 1)
                return item.text() if item else ""
        return ""

    @staticmethod
    def _set_property_value(
        table: QTableWidget,
        key: str,
        value: object,
        *,
        editable: bool = True,
    ) -> None:
        for row in range(table.rowCount()):
            if PropulsionControlsDock._property_key(table, row) != key:
                continue
            item = table.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, 1, item)
            item.setText(str(value))
            if editable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return

    @staticmethod
    def _property_value(table: QTableWidget, key: str) -> str:
        for row in range(table.rowCount()):
            if PropulsionControlsDock._property_key(table, row) == key:
                item = table.item(row, 1)
                return item.text().strip() if item else ""
        return ""

    @staticmethod
    def _property_value_by_row(table: QTableWidget, row: int) -> str:
        item = table.item(row, 1)
        return item.text().strip() if item else ""

    @staticmethod
    def _property_key(table: QTableWidget, row: int) -> str:
        item = table.item(row, 0)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setFixedHeight(23)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        return table

    @staticmethod
    def _fit_table_height(
        table: QTableWidget,
        row_count: int,
        maximum_visible_rows: int = 15,
    ) -> None:
        visible_rows = min(max(row_count, 1), maximum_visible_rows)
        height = (
            table.horizontalHeader().height()
            + table.verticalHeader().defaultSectionSize() * visible_rows
            + 2
        )
        table.setFixedHeight(height)
