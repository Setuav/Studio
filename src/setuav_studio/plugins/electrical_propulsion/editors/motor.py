"""Motor component property editor."""

from __future__ import annotations

from typing import Any
from PySide6.QtWidgets import QWidget

from setuav_studio.plugin_system import BaseComponentEditor, ParameterField, StudioAPI


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

    def __init__(self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)
