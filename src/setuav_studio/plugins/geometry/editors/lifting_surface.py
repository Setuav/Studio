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

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.buttons import set_native_button
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import (
    NoWheelComboBox,
    NumericSpinBox,
    set_table_spinbox,
)
from setuav_studio.ui.property_tables import PropertyTableMixin

from ..engine.airfoil import PRESET_AIRFOILS
from .lifting_surface_attachment import AttachmentMixin
from .lifting_surface_control_surfaces import ControlSurfacesMixin
from .lifting_surface_planform import PlanformMixin
from .lifting_surface_sections import SectionsMixin
from .lifting_surface_tip_caps import TipCapsMixin


class LiftingSurfaceEditor(
    PropertyTableMixin,
    AttachmentMixin,
    PlanformMixin,
    SectionsMixin,
    TipCapsMixin,
    ControlSurfacesMixin,
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
        self._profile_index = -1
        self._control_surface_index = -1
        self._driver_mode = "area_ar_taper"
        self._sweep_loc = 0.25
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
        self._create_attachment_section()
        self._create_planform_sizing_section()
        self._create_wing_angles_section()
        self._create_sections_section()
        self._create_section_properties_section()
        self._create_tip_caps_section()
        self._create_control_surfaces_section()
        self._create_airfoil_shaping_section()
        self._content_layout.addStretch()

        # Aliases for backward compatibility
        self.profiles_table = self.sections_table
        self.profile_properties_table = self.section_properties_table
        self.add_profile_button = self.insert_section_button
        self.duplicate_profile_button = self.split_section_button
        self.delete_profile_button = self.delete_section_button

        self._load_component()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._api.set_section_selection(None)
        super().closeEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self._api.set_section_selection(None)
        super().hideEvent(event)

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table([
            ("name", "Name"),
            ("type", "Type"),
            ("attach_to", "Attach to"),
        ])
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

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
        self._set_property_value(self.general_table, "name", str(self._component.get("name") or ""))
        self._set_property_value(self.general_table, "type", str(self._component.get("type") or ""), editable=False)

        # Parent Selection Combo (Only fuselage and lifting surfaces)
        current_attach = str(self._component.get("attach_to") or self._component.get("parent") or "")
        parent_options = [("", "(None)")]
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if project and isinstance(project.data.get("components"), list):
            for comp in project.data["components"]:
                if (
                    isinstance(comp, dict)
                    and comp.get("type") in ("org.setuav.core:fuselage", "org.setuav.core:lifting-surface")
                ):
                    cid = str(comp.get("id") or "")
                    if cid and cid != self._component.get("id"):
                        cname = str(comp.get("name") or cid)
                        parent_options.append((cid, f"{cname} ({cid})"))
        self._set_property_combo(
            self.general_table,
            "attach_to",
            current_attach,
            parent_options,
            lambda val: self._update_attach_to(val if val else None),
        )

        # Attachment / Component Transform
        self._load_attachment_transform()

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
    # General Mutations
    # -------------------------------------------------------------------------

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_str = self._property_text(self.general_table, row)

        def change() -> None:
            if key == "name":
                self._component["name"] = val_str.strip()

        self._edit_component(f"Edit {key}", change)

    # -------------------------------------------------------------------------
    # Helpers & Edit Component Transaction
    # -------------------------------------------------------------------------

    def _edit_control_surface_item(self, cs: dict[str, Any], description: str, change_fn: Callable[[], None]) -> None:
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if project and isinstance(project.data.get("components"), list) and cs in project.data["components"]:
            if hasattr(self._api, "edit_component"):
                self._api.edit_component(cs, description, change_fn)
            elif hasattr(self._api, "edit_project"):
                self._api.edit_project(description, change_fn)
            else:
                change_fn()
        else:
            self._edit_component(description, change_fn)

    def _edit_component(self, description: str, change_fn: Callable[[], None]) -> None:
        if hasattr(self._api, "edit_component"):
            self._api.edit_component(self._component, description, change_fn)
        else:
            change_fn()

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
        if "parameters" in cs and isinstance(cs["parameters"], dict):
            geom = cs["parameters"].get("geometry")
            if isinstance(geom, dict):
                return geom
        return cs

    def _control_surfaces(self) -> list[dict[str, Any]]:
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        child_cs: list[dict[str, Any]] = []
        if project and isinstance(project.data.get("components"), list):
            wing_id = self._component.get("id")
            for comp in project.data["components"]:
                if (
                    isinstance(comp, dict)
                    and comp.get("type") == "org.setuav.core:control-surface"
                    and (comp.get("attach_to") or comp.get("parent")) == wing_id
                ):
                    child_cs.append(comp)

        if child_cs:
            return child_cs

        cs = self._geometry().get("control_surfaces")
        if not isinstance(cs, list):
            cs = []
            self._geometry()["control_surfaces"] = cs
        return cs

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
                return f"File: {Path(str(value.get('path') or value.get('file') or '')).name}"
        return "NACA 2412"

    def _set_property_spinbox(
        self,
        table: QTableWidget,
        key: str,
        value: float,
        *,
        min_val: float = -1e6,
        max_val: float = 1e6,
        step: float = 1.0,
        decimals: int = 2,
        suffix: str = "",
        on_changed: Callable[[float], None] | None = None,
    ) -> NumericSpinBox | None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            return set_table_spinbox(
                table,
                row,
                1,
                value,
                min_val=min_val,
                max_val=max_val,
                step=step,
                decimals=decimals,
                suffix=suffix,
                on_changed=on_changed,
            )
        return None

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
