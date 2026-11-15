"""Lifting Surface Editor widget for configuring wings, stabilizers, fins, and control surfaces."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtGui import QCloseEvent, QHideEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import StudioAPI
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.button import set_native_button
from setuav_studio.ui.widget.spinbox import (
    NoWheelComboBox,
)
from setuav_studio.ui.widget.table import PropertyTableMixin

from ...engine.airfoil import PRESET_AIRFOILS
from .control_surfaces_section import ControlSurfacesSectionMixin
from .general_section import GeneralSectionMixin
from .planform_section import PlanformSectionMixin
from .sections_section import SectionsSectionMixin
from .tip_caps_section import TipCapsSectionMixin


class LiftingSurfaceEditor(
    GeneralSectionMixin,
    PlanformSectionMixin,
    SectionsSectionMixin,
    TipCapsSectionMixin,
    ControlSurfacesSectionMixin,
    PropertyTableMixin,
    QWidget,
):
    """Component property editor for org.setuav.core:lifting-surface."""

    table_combo_cls = NoWheelComboBox
    table_scroll_policy_off = True
    table_max_visible_rows = None
    table_property_text_spinbox = True

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._component = component
        self._section_index = -1
        self._control_surface_index = -1
        self._driver_mode = "area_ar_taper"
        self._sweep_loc = float(self._geometry().get("sweep_location", 0.25))
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
        self._create_planform_section()
        self._create_angles_section()
        self._create_sections_section()
        self._create_section_properties_section()
        self._create_tip_caps_section()
        self._create_control_surfaces_section()
        self._create_airfoil_shaping_section()
        self._content_layout.addStretch()

        from setuav_studio.units import get_unit_manager

        get_unit_manager().units_changed.connect(self._on_units_changed)

        self._load_component()

    def _on_units_changed(self) -> None:
        self._populate_sections()
        self._populate_control_surfaces()
        if self._control_surface_index >= 0:
            self._load_control_surface(self._control_surface_index)
        if self._section_index >= 0:
            self._load_section(self._section_index)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._api.set_section_selection(None)
        super().closeEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self._api.set_section_selection(None)
        super().hideEvent(event)

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

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

    @staticmethod
    def _action_button(
        icon_name: str,
        tooltip: str,
        callback: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton()
        set_native_button(button, icon_name)
        button.setToolTip(tooltip)
        button.setFixedSize(24, 24)
        button.setAutoRaise(True)
        button.clicked.connect(callback)
        return button

    # -------------------------------------------------------------------------
    # Loading & Populating Data
    # -------------------------------------------------------------------------

    def _load_component(self) -> None:
        self._loading = True

        # General
        self._load_general()

        # Sections (Panels)
        self._populate_sections()

        # Planform Sizing Initial Setup
        self._sync_driver_mode_from_project()
        self._refresh_planform_table()

        # End Caps (Tip Treatment)
        self._load_tip_caps()

        # Control Surfaces
        self._populate_control_surfaces()

        # Airfoil Shaping
        self._load_airfoil_shaping()

        self._loading = False

        if self._get_sections():
            self.sections_table.selectRow(0)
            self._load_section(0)
        else:
            self._update_section_actions()

        if self._control_surfaces():
            self.control_surfaces_table.selectRow(0)
            self._load_control_surface(0)
        else:
            self._update_cs_actions()

    # -------------------------------------------------------------------------
    # Helpers & Edit Component Transaction
    # -------------------------------------------------------------------------

    def _edit_control_surface_item(
        self, cs: dict[str, Any], description: str, change_fn: Callable[[], None]
    ) -> None:
        def wrapped_cs_change() -> None:
            change_fn()
            from ...engine.envelope import sync_component_envelope

            sync_component_envelope(cs, self._component)

        self._api.edit_component(cs, description, wrapped_cs_change)

    def _edit_component(self, description: str, change_fn: Callable[[], None]) -> None:
        def wrapped_change() -> None:
            change_fn()
            from ...engine.envelope import sync_component_envelope

            sync_component_envelope(self._component)

        self._api.edit_component(self._component, description, wrapped_change)

    def _parameters(self) -> dict[str, Any]:
        params = self._component.get("parameters")
        if not isinstance(params, dict):
            params = {}
            self._component["parameters"] = params
        return params

    def _geometry(self) -> dict[str, Any]:
        geom = self._parameters().get("geometry")
        if not isinstance(geom, dict):
            geom = {}
            self._parameters()["geometry"] = geom
        return geom

    def _profiles(self) -> list[dict[str, Any]]:
        profs = self._geometry().get("profiles")
        if not isinstance(profs, list):
            profs = []
            self._geometry()["profiles"] = profs
        return profs

    def _cs_geom(self, cs: dict[str, Any]) -> dict[str, Any]:
        params = cs.setdefault("parameters", {})
        return params.setdefault("geometry", {})

    def _control_surfaces(self) -> list[dict[str, Any]]:
        project = self._api.project
        if not project or not isinstance(project.data.get("components"), list):
            return []
        wing_id = self._component.get("id")
        return [
            comp
            for comp in project.data["components"]
            if isinstance(comp, dict)
            and comp.get("type") == "org.setuav.core:control-surface"
            and comp.get("parent") == wing_id
        ]

    @staticmethod
    def _format_airfoil_label(value: object) -> str:
        if isinstance(value, str):
            for name, preset in PRESET_AIRFOILS.items():
                if name.lower() == value.lower() or preset.get("code") == value:
                    return name
            return value
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("code") or "")
            if name:
                return name
            if value.get("type") == "coordinates":
                return f"Custom ({len(value.get('points') or [])} pts)"
            if value.get("type") == "file":
                return f"File: {Path(str(value.get('path') or '')).name}"
        return "NACA 2412"

    @staticmethod
    def _clear_property_values(table: QTableWidget) -> None:
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item is not None:
                item.setText("")

    @staticmethod
    def _parse_number(value: str) -> float | None:
        try:
            return float(
                value.replace("°", "")
                .replace("mm²", "")
                .replace("m²", "")
                .replace("dm²", "")
                .replace("mm", "")
                .replace("g", "")
                .split("(")[0]
                .strip()
            )
        except ValueError:
            return None
