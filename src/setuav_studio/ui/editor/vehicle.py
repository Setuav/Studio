"""Summary of the vehicle: its component count, total mass and center of gravity."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import StudioAPI
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio.utilities.mass_balance import resolve_aircraft_mass_properties

_CG_AXES = (("cg_x", "x"), ("cg_y", "y"), ("cg_z", "z"))


class VehicleSummaryEditor(PropertyTableMixin, QWidget):
    """Read-only summary of every component of the project."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 8)
        layout.setSpacing(3)
        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)
        icon_label = QLabel()
        set_label_icon(icon_label, "vehicle")
        icon_label.setFixedSize(14, 14)
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel("Vehicle"))
        header_layout.addStretch()
        layout.addWidget(header)

        self.summary_table = self._property_table(
            [
                ("components", "Components"),
                ("mass", "Total Mass"),
                ("cg_x", "CG X"),
                ("cg_y", "CG Y"),
                ("cg_z", "CG Z"),
            ]
        )
        self.summary_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout.addWidget(self.summary_table)
        layout.addStretch()

        self._load()
        api.on_project_content_changed(self._on_project_content_changed)

    def _on_project_content_changed(self, _project: Any = None) -> None:
        self._load()

    def _load(self) -> None:
        project = self._api.project
        assert project is not None
        components = project.data["components"]
        mass = resolve_aircraft_mass_properties(components)
        self._set_property_value(
            self.summary_table, "components", str(len(components)), editable=False
        )
        self._set_property_spinbox(
            self.summary_table,
            "mass",
            mass.mass_kg * 1000.0,
            decimals=1,
            quantity="mass",
            unit="g",
            read_only=True,
        )
        for key, axis in _CG_AXES:
            self._set_property_spinbox(
                self.summary_table,
                key,
                mass.cg_body_m["xyz".index(axis)] * 1000.0,
                decimals=1,
                quantity="length",
                unit="mm",
                read_only=True,
            )


__all__ = ["VehicleSummaryEditor"]
