"""Electronic Speed Controller (ESC) component property editor."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget
from setuav_studio_sdk import ParameterField, StudioAPI

from setuav_studio.component_editor import BaseComponentEditor


class EscEditor(BaseComponentEditor):
    """Property editor for ESCs and motor controllers (org.setuav.core:esc)."""

    FIELDS = (
        ParameterField(
            key="continuous_current",
            label="Continuous Current",
            unit="A",
            field_type=float,
            default=50.0,
            min_value=1.0,
            max_value=500.0,
            decimals=1,
            tooltip="Rated continuous electrical current limit.",
        ),
        ParameterField(
            key="max_current",
            label="Peak / Burst Current",
            unit="A",
            field_type=float,
            default=60.0,
            min_value=1.0,
            max_value=800.0,
            decimals=1,
            tooltip="Short duration peak/burst current rating.",
        ),
        ParameterField(
            key="max_voltage",
            label="Max Input Voltage",
            unit="V",
            field_type=float,
            default=25.2,  # 6S LiPo max
            min_value=3.0,
            max_value=120.0,
            decimals=1,
            tooltip="Maximum allowable battery input voltage.",
        ),
        ParameterField(
            key="resistance",
            label="Internal Resistance",
            unit="Ω",
            field_type=float,
            default=0.004,
            min_value=0.0001,
            max_value=1.0,
            decimals=4,
            tooltip="Lumped MOSFET and lead wire electrical resistance.",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)
