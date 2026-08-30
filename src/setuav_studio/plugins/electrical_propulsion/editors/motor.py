"""Motor component property editor with PyThrust database catalog picker."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from setuav_studio.component_editor import BaseComponentEditor
from setuav_studio.plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from setuav_studio.ui.buttons import set_native_button
from setuav_studio_sdk import ParameterField, StudioAPI


class MotorEditor(BaseComponentEditor):
    """Property editor for brushless and DC motors (org.setuav.core:motor)."""

    FIELDS = (
        ParameterField(
            key="kv",
            label="Velocity Constant (KV)",
            unit="RPM/V",
            field_type=float,
            default=900.0,
            min_value=10.0,
            max_value=20000.0,
            decimals=0,
            tooltip="Motor velocity constant in revolutions per minute per volt.",
        ),
        ParameterField(
            key="resistance",
            label="Internal Resistance (Rm)",
            unit="Ω",
            field_type=float,
            default=0.055,
            min_value=0.0001,
            max_value=10.0,
            decimals=4,
            tooltip="Phase-to-phase internal winding resistance.",
        ),
        ParameterField(
            key="no_load_current",
            label="No-Load Current (I0)",
            unit="A",
            field_type=float,
            default=1.1,
            min_value=0.01,
            max_value=50.0,
            decimals=2,
            tooltip="Idle no-load current at reference test voltage.",
        ),
        ParameterField(
            key="max_current",
            label="Max Current",
            unit="A",
            field_type=float,
            default=40.0,
            min_value=0.1,
            max_value=1000.0,
            decimals=1,
            tooltip="Maximum continuous/peak current rating.",
        ),
        ParameterField(
            key="max_power",
            label="Max Power",
            unit="W",
            field_type=float,
            default=800.0,
            min_value=1.0,
            max_value=100000.0,
            decimals=0,
            tooltip="Maximum electrical power handling limit.",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)

    def _create_general_section(self) -> None:
        catalog_btn = QPushButton("Catalog…", self)
        set_native_button(catalog_btn, "fa6s.database")
        catalog_btn.clicked.connect(self._open_catalog)

        layout = self._create_section("General", "fa6s.circle-info", action_widget=catalog_btn)
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mass", "Mass"),
                ("manufacturer", "Manufacturer"),
                ("model", "Model"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _open_catalog(self) -> None:
        dialog = ComponentCatalogDialog(component_type="motor", parent=self.window())
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_motor:
            m = dialog.selected_motor

            def apply_catalog_motor() -> None:
                self._component["name"] = m.name
                self._component["manufacturer"] = m.manufacturer
                self._component["model"] = m.name
                self._component["mass"] = m.weight_g
                params = self._component.setdefault("parameters", {})
                params["kv"] = float(m.kv)
                params["resistance"] = float(m.resistance)
                params["no_load_current"] = float(m.io)
                params["max_current"] = float(m.max_current)
                if m.max_power:
                    params["max_power"] = float(m.max_power)
                params["mass"] = float(m.weight_g)

            self._api.edit_component(
                self._component,
                f"Apply catalog motor '{m.manufacturer} {m.name}'",
                apply_catalog_motor,
            )
            self._load_component()
