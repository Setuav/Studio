"""Propeller and rotor component property editor."""

from __future__ import annotations

from typing import Any
from PySide6.QtWidgets import QWidget

from setuav_studio.plugin_system import BaseComponentEditor, ParameterField, StudioAPI


class PropellerEditor(BaseComponentEditor):
    """Property editor for propellers and rotors (org.setuav.core:propeller, org.setuav.core:rotor)."""

    FIELDS = (
        ParameterField(
            key="diameter",
            label="Prop Diameter",
            unit="mm",
            field_type=float,
            default=330.2,  # 13 in
            min_value=10.0,
            max_value=3000.0,
            decimals=1,
            tooltip="Propeller tip-to-tip diameter in millimeters.",
        ),
        ParameterField(
            key="pitch",
            label="Prop Pitch",
            unit="mm",
            field_type=float,
            default=152.4,  # 6 in
            min_value=5.0,
            max_value=2000.0,
            decimals=1,
            tooltip="Geometric pitch distance advanced per single revolution.",
        ),
        ParameterField(
            key="blade_count",
            label="Blade Count",
            field_type=int,
            default=2,
            min_value=1,
            max_value=12,
            tooltip="Number of propeller blades.",
        ),
        ParameterField(
            key="hub_diameter",
            label="Hub Diameter",
            unit="mm",
            field_type=float,
            default=32.0,
            min_value=2.0,
            max_value=200.0,
            decimals=1,
        ),
        ParameterField(
            key="rotation_direction",
            label="Rotation Direction",
            field_type=str,
            default="ccw",
            options=("ccw", "cw"),
            tooltip="Standard rotation orientation (CCW: Tractor / CW: Pusher).",
        ),
    )

    def __init__(self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)
