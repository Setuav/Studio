"""Propeller and rotor component property editor with PyThrust APC database picker."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from setuav_studio.component_editor import BaseComponentEditor
from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from setuav_studio.ui.buttons import set_native_button
from setuav_studio_sdk import ParameterField, StudioAPI


class PropellerEditor(BaseComponentEditor):
    """Property editor for propellers and rotors (org.setuav.core:propeller / rotor)."""

    FIELDS = (
        ParameterField(
            key="diameter",
            label="Diameter",
            unit="mm",
            field_type=float,
            default=330.0,
            min_value=10.0,
            max_value=3000.0,
            decimals=1,
            tooltip="Propeller overall tip-to-tip diameter in millimeters.",
        ),
        ParameterField(
            key="pitch",
            label="Pitch",
            unit="mm",
            field_type=float,
            default=165.0,
            min_value=5.0,
            max_value=2000.0,
            decimals=1,
            tooltip="Geometric pitch advance per revolution in millimeters.",
        ),
        ParameterField(
            key="blade_count",
            label="Blade Count",
            unit="",
            field_type=int,
            default=2,
            min_value=1,
            max_value=8,
            tooltip="Number of propeller blades.",
        ),
        ParameterField(
            key="hub_diameter",
            label="Hub Diameter",
            unit="mm",
            field_type=float,
            default=25.0,
            min_value=0.0,
            max_value=300.0,
            decimals=1,
            tooltip="Propeller central hub diameter.",
        ),
        ParameterField(
            key="rotation_direction",
            label="Rotation Direction",
            unit="",
            field_type=str,
            default="ccw",
            options=["ccw", "cw"],
            tooltip="Direction of rotation viewed from front/top (CCW or CW).",
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
        dialog = ComponentCatalogDialog(component_type="propeller", parent=self.window())
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_propeller:
            p = dialog.selected_propeller

            def apply_catalog_propeller() -> None:
                self._component["name"] = f"APC {p.metadata.model}"
                self._component["manufacturer"] = p.metadata.manufacturer
                self._component["model"] = p.metadata.model
                params = self._component.setdefault("parameters", {})
                params["diameter"] = round(p.diameter_m * 1000.0, 1)
                params["pitch"] = round(p.pitch_m * 1000.0, 1)
                params["blade_count"] = int(p.metadata.blade_count)

            self._api.edit_component(
                self._component,
                f"Apply catalog propeller '{p.metadata.id}'",
                apply_catalog_propeller,
            )
            self._load_component()
