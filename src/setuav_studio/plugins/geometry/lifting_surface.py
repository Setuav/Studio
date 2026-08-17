"""Lifting Surface Editor widget for configuring wings, stabilizers, fins, and control surfaces."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QHideEvent
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import StudioAPI
from setuav_studio.plugins.geometry.airfoil import PRESET_AIRFOILS
from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog


class LiftingSurfaceEditor(QWidget):
    """Component property editor for org.setuav.core:lifting-surface."""

    CONTROL_SURFACE_TYPES = [
        ("aileron", "Aileron"),
        ("flap", "Flap"),
        ("elevator", "Elevator"),
        ("rudder", "Rudder"),
    ]

    BLENDING_CONTINUITY = [
        ("G0", "G0 (Positional)"),
        ("G1", "G1 (Tangency)"),
        ("G2", "G2 (Curvature)"),
    ]

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._component = component
        self._profile_index = -1
        self._control_surface_index = -1
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_general_section()
        self._create_attachment_section()
        self._create_planform_metrics_section()
        self._create_profiles_section()
        self._create_profile_properties_section()
        self._create_control_surfaces_section()
        self._create_blending_section()
        self._content_layout.addStretch()

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
            ("parent", "Parent"),
            ("mass", "Mass (g)"),
        ])
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_attachment_section(self) -> None:
        """Component attachment / mount transform on the fuselage or parent."""
        layout = self._create_section("Attachment (Transform)", "mdi6.axis-arrow")

        self.attachment_table = QTableWidget(2, 3)
        self.attachment_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.attachment_table.setVerticalHeaderLabels(["Position (mm)", "Rotation (°)"])
        self.attachment_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.attachment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.attachment_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.attachment_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attachment_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attachment_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.attachment_table.horizontalHeader().setFixedHeight(23)
        self.attachment_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.attachment_table.verticalHeader().setDefaultSectionSize(23)
        self.attachment_table.verticalHeader().setMinimumWidth(82)
        self.attachment_table.setAlternatingRowColors(True)
        self.attachment_table.setFixedHeight(71)
        for row in range(2):
            for column in range(3):
                item = QTableWidgetItem("0.00")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.attachment_table.setItem(row, column, item)
        self.attachment_table.cellChanged.connect(self._update_attachment_transform)
        layout.addWidget(self.attachment_table)

    def _create_planform_metrics_section(self) -> None:
        layout = self._create_section("Planform & Aerodynamics", "fa6s.chart-area")
        self.metrics_table = self._property_table([
            ("wing_area", "Planform Area (S)"),
            ("wingspan", "Total Span (b)"),
            ("aspect_ratio", "Aspect Ratio (AR)"),
            ("mac", "Mean Aerodyn Chord (MAC)"),
            ("taper_ratio", "Taper Ratio (λ)"),
            ("root_chord", "Root Chord (c_root)"),
            ("tip_chord", "Tip Chord (c_tip)"),
        ])
        for r in range(self.metrics_table.rowCount()):
            item = self.metrics_table.item(r, 1)
            if item:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        layout.addWidget(self.metrics_table)

    def _create_profiles_section(self) -> None:
        layout = self._create_section("Wing Profiles (Sections)", "mdi6.vector-polygon")

        self.profiles_table = self._table([
            "#",
            "Airfoil",
            "Span Y (mm)",
            "Chord (mm)",
            "Offset X (mm)",
            "Height Z (mm)",
            "Twist X (°)",
        ])
        self.profiles_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.profiles_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.profiles_table.setColumnWidth(0, 30)
        self.profiles_table.currentCellChanged.connect(self._on_profile_selected)
        self.profiles_table.cellChanged.connect(self._update_profiles_table_cell)
        layout.addWidget(self.profiles_table)

        profile_actions = QHBoxLayout()
        profile_actions.setContentsMargins(0, 2, 0, 2)
        profile_actions.setSpacing(2)
        self.add_profile_button = self._action_button(
            "add", "Add profile station", self._add_profile
        )
        self.duplicate_profile_button = self._action_button(
            "instance", "Duplicate profile station", self._duplicate_profile
        )
        self.move_profile_up_button = self._action_button(
            "fa6s.arrow-up", "Move profile up", self._move_profile_up
        )
        self.move_profile_down_button = self._action_button(
            "fa6s.arrow-down", "Move profile down", self._move_profile_down
        )
        self.delete_profile_button = self._action_button(
            "remove", "Delete profile station", self._delete_profile
        )
        for button in (
            self.add_profile_button,
            self.duplicate_profile_button,
            self.move_profile_up_button,
            self.move_profile_down_button,
            self.delete_profile_button,
        ):
            profile_actions.addWidget(button)
        profile_actions.addStretch()
        layout.addLayout(profile_actions)

    def _create_profile_properties_section(self) -> None:
        layout = self._create_section("Section Properties", "fa6s.sliders")

        self.profile_properties_table = self._property_table([
            ("airfoil", "Airfoil"),
            ("chord", "Chord (mm)"),
        ])
        self.profile_properties_table.cellChanged.connect(self._update_profile_property)
        layout.addWidget(self.profile_properties_table)

        # Airfoil Manager / Selector button
        af_btn_layout = QHBoxLayout()
        af_btn_layout.setContentsMargins(0, 2, 0, 2)
        self.choose_airfoil_btn = QPushButton("Choose / Import Airfoil...")
        self.choose_airfoil_btn.setIcon(get_icon("fa6s.shapes"))
        self.choose_airfoil_btn.clicked.connect(self._open_airfoil_dialog)
        af_btn_layout.addWidget(self.choose_airfoil_btn)
        af_btn_layout.addStretch()
        layout.addLayout(af_btn_layout)

        # Section Local Station Transform Table
        station_header_lbl = QLabel("Station Local Offset & Rotation:")
        station_header_lbl.setStyleSheet("color: #888888; font-size: 11px; margin-top: 4px;")
        layout.addWidget(station_header_lbl)

        self.station_transform_table = QTableWidget(2, 3)
        self.station_transform_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.station_transform_table.setVerticalHeaderLabels(["Offset (mm)", "Rotation (°)"])
        self.station_transform_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.station_transform_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.station_transform_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.station_transform_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.station_transform_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.station_transform_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.station_transform_table.horizontalHeader().setFixedHeight(23)
        self.station_transform_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.station_transform_table.verticalHeader().setDefaultSectionSize(23)
        self.station_transform_table.verticalHeader().setMinimumWidth(82)
        self.station_transform_table.setAlternatingRowColors(True)
        self.station_transform_table.setFixedHeight(71)
        for row in range(2):
            for column in range(3):
                item = QTableWidgetItem("0.00")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.station_transform_table.setItem(row, column, item)
        self.station_transform_table.cellChanged.connect(self._update_station_transform)
        layout.addWidget(self.station_transform_table)

    def _create_control_surfaces_section(self) -> None:
        layout = self._create_section("Control Surfaces", "fa6s.plane")

        self.control_surfaces_table = self._table([
            "Tag",
            "Type",
            "Span Start (mm)",
            "Span End (mm)",
            "Chord (mm)",
        ])
        self.control_surfaces_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.control_surfaces_table.currentCellChanged.connect(self._on_control_surface_selected)
        self.control_surfaces_table.cellChanged.connect(self._update_cs_table_cell)
        layout.addWidget(self.control_surfaces_table)

        cs_actions = QHBoxLayout()
        cs_actions.setContentsMargins(0, 2, 0, 2)
        cs_actions.setSpacing(2)
        self.add_cs_button = self._action_button(
            "add", "Add control surface", self._add_control_surface
        )
        self.duplicate_cs_button = self._action_button(
            "instance", "Duplicate control surface", self._duplicate_control_surface
        )
        self.move_cs_up_button = self._action_button(
            "fa6s.arrow-up", "Move control surface up", self._move_cs_up
        )
        self.move_cs_down_button = self._action_button(
            "fa6s.arrow-down", "Move control surface down", self._move_cs_down
        )
        self.delete_cs_button = self._action_button(
            "remove", "Delete control surface", self._delete_control_surface
        )
        for button in (
            self.add_cs_button,
            self.duplicate_cs_button,
            self.move_cs_up_button,
            self.move_cs_down_button,
            self.delete_cs_button,
        ):
            cs_actions.addWidget(button)
        cs_actions.addStretch()
        layout.addLayout(cs_actions)

        self.cs_properties_table = self._property_table([
            ("tag", "Tag"),
            ("type", "Type"),
            ("span_start", "Span Start (mm)"),
            ("span_end", "Span End (mm)"),
            ("chord", "Control Chord (mm)"),
        ])
        self.cs_properties_table.cellChanged.connect(self._update_cs_property)
        layout.addWidget(self.cs_properties_table)

    def _create_blending_section(self) -> None:
        layout = self._create_section("Loft & Blending", "fa6s.gear")
        self.blending_table = self._property_table([
            ("ruled", "Interpolation"),
            ("continuity", "Continuity"),
            ("max_degree", "Max Degree"),
        ])
        self.blending_table.cellChanged.connect(self._update_blending)
        layout.addWidget(self.blending_table)

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
        layout = QVBoxLayout(section)
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

    @staticmethod
    def _action_button(
        icon_name: str,
        tooltip: str,
        callback: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton()
        button.setIcon(get_icon(icon_name))
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

        # Parent Selection Combo
        current_parent = str(self._component.get("parent") or "")
        parent_options = [("", "(None)")]
        if hasattr(self._api, "project") and self._api.project:
            comp_list = self._api.project.data.get("components")
            if isinstance(comp_list, list):
                for comp in comp_list:
                    if isinstance(comp, dict):
                        cid = str(comp.get("id") or "")
                        if cid and cid != self._component.get("id"):
                            cname = str(comp.get("name") or cid)
                            parent_options.append((cid, f"{cname} ({cid})"))
        self._set_property_combo(
            self.general_table,
            "parent",
            current_parent,
            parent_options,
            lambda val: self._update_parent(val if val else None),
        )

        self._set_property_value(self.general_table, "mass", self._parameters().get("mass") or 0)

        # Attachment / Component Transform
        self._load_attachment_transform()

        # Profiles
        self._populate_profiles()

        # Control Surfaces
        self._populate_control_surfaces()

        # Blending
        blending = self._geometry().get("blending")
        blending = blending if isinstance(blending, dict) else {}
        is_ruled = "true" if blending.get("ruled") is True else "false"
        self._set_property_combo(
            self.blending_table,
            "ruled",
            is_ruled,
            [("false", "Smooth (Spline)"), ("true", "Linear (Ruled)")],
            lambda val: self._update_blending_value("ruled", val == "true"),
        )
        continuity = str(blending.get("continuity") or "G2")
        self._set_property_combo(
            self.blending_table,
            "continuity",
            continuity,
            self.BLENDING_CONTINUITY,
            lambda val: self._update_blending_value("continuity", val),
        )
        self._set_property_value(self.blending_table, "max_degree", blending.get("max_degree") or 3)

        # Planform Metrics
        self._recalculate_planform_metrics()

        self._loading = False

        if self._profiles():
            self.profiles_table.selectRow(0)
            self._load_profile(0)
        else:
            self._update_profile_actions()

        if self._control_surfaces():
            self.control_surfaces_table.selectRow(0)
            self._load_control_surface(0)
        else:
            self._update_cs_actions()

    # -------------------------------------------------------------------------
    # Attachment / Component Transform Handling
    # -------------------------------------------------------------------------

    def _load_attachment_transform(self) -> None:
        transform = self._component.get("transform")
        transform = transform if isinstance(transform, dict) else {}
        pos = transform.get("position")
        pos = pos if isinstance(pos, dict) else {}
        rot = transform.get("rotation")
        rot = rot if isinstance(rot, dict) else {}

        pos_vals = (
            float(pos.get("x", 0.0)),
            float(pos.get("y", 0.0)),
            float(pos.get("z", 0.0)),
        )
        rot_vals = (
            float(rot.get("roll") if "roll" in rot else rot.get("x", 0.0)),
            float(rot.get("pitch") if "pitch" in rot else rot.get("y", 0.0)),
            float(rot.get("yaw") if "yaw" in rot else rot.get("z", 0.0)),
        )

        for row, values in enumerate((pos_vals, rot_vals)):
            for col, val in enumerate(values):
                item = self.attachment_table.item(row, col)
                if item:
                    item.setText(f"{val:.2f}")

    def _update_attachment_transform(self, _row: int, _col: int) -> None:
        if self._loading:
            return
        try:
            pos_x = float(self.attachment_table.item(0, 0).text())
            pos_y = float(self.attachment_table.item(0, 1).text())
            pos_z = float(self.attachment_table.item(0, 2).text())
            rot_r = float(self.attachment_table.item(1, 0).text())
            rot_p = float(self.attachment_table.item(1, 1).text())
            rot_y = float(self.attachment_table.item(1, 2).text())
        except (AttributeError, ValueError):
            return

        def change() -> None:
            tf = self._component.get("transform")
            if not isinstance(tf, dict):
                tf = {}
                self._component["transform"] = tf
            tf["position"] = {"x": pos_x, "y": pos_y, "z": pos_z}
            tf["rotation"] = {"roll": rot_r, "pitch": rot_p, "yaw": rot_y}

        self._edit_component("Edit wing attachment transform", change)

    def _update_parent(self, new_parent: str | None) -> None:
        if self._loading:
            return

        def change() -> None:
            self._component["parent"] = new_parent

        self._edit_component("Change component parent", change)

    # -------------------------------------------------------------------------
    # Profiles Handling
    # -------------------------------------------------------------------------

    def _populate_profiles(self) -> None:
        profiles = self._profiles()
        self.profiles_table.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            pos = profile.get("position") if isinstance(profile.get("position"), dict) else {}
            rot = profile.get("rotation") if isinstance(profile.get("rotation"), dict) else {}
            airfoil = self._format_airfoil_label(profile.get("airfoil"))

            values = (
                str(row + 1),
                airfoil,
                f"{float(pos.get('y', 0.0)):.1f}",
                f"{float(profile.get('chord', 0.0)):.1f}",
                f"{float(pos.get('x', 0.0)):.1f}",
                f"{float(pos.get('z', 0.0)):.1f}",
                f"{float(rot.get('x', 0.0)):.1f}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                elif column == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.profiles_table.setItem(row, column, item)

        self._fit_table_height(self.profiles_table, len(profiles), maximum_visible_rows=8)
        self._update_profile_actions()

    def _populate_control_surfaces(self) -> None:
        cs_list = self._control_surfaces()
        self.control_surfaces_table.setRowCount(len(cs_list))
        for row, cs in enumerate(cs_list):
            values = (
                str(cs.get("tag") or f"CS_{row + 1}"),
                str(cs.get("type") or "aileron").capitalize(),
                f"{float(cs.get('span_start', 0.0)):.1f}",
                f"{float(cs.get('span_end', 0.0)):.1f}",
                f"{float(cs.get('chord', 0.0)):.1f}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column in (0, 1):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.control_surfaces_table.setItem(row, column, item)

        self._fit_table_height(self.control_surfaces_table, len(cs_list), maximum_visible_rows=5)
        self._update_cs_actions()

    def _load_profile(self, row: int) -> None:
        profiles = self._profiles()
        if not (0 <= row < len(profiles)):
            self._profile_index = -1
            self._clear_property_values(self.profile_properties_table)
            self._set_station_transform_values((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            self._update_profile_actions()
            self._publish_section_selection()
            return

        self._profile_index = row
        profile = profiles[row]
        pos = profile.get("position") if isinstance(profile.get("position"), dict) else {}
        rot = profile.get("rotation") if isinstance(profile.get("rotation"), dict) else {}

        self._loading = True

        pos_tuple = (
            float(pos.get("x", 0.0)),
            float(pos.get("y", 0.0)),
            float(pos.get("z", 0.0)),
        )
        rot_tuple = (
            float(rot.get("x", 0.0)),
            float(rot.get("y", 0.0)),
            float(rot.get("z", 0.0)),
        )
        self._set_station_transform_values(pos_tuple, rot_tuple)

        airfoil_val = self._format_airfoil_label(profile.get("airfoil"))
        self._set_property_value(self.profile_properties_table, "airfoil", airfoil_val)
        self._set_property_value(self.profile_properties_table, "chord", float(profile.get("chord", 200.0)))

        self._loading = False
        self._update_profile_actions()
        self._publish_section_selection()

    def _publish_section_selection(self) -> None:
        component_id = self._component.get("id")
        if isinstance(component_id, str) and 0 <= self._profile_index < len(self._profiles()):
            self._api.set_section_selection((component_id, 0, self._profile_index))
        else:
            self._api.set_section_selection(None)

    def _set_station_transform_values(
        self,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float],
    ) -> None:
        for row, values in enumerate((position, rotation)):
            for column, value in enumerate(values):
                item = self.station_transform_table.item(row, column)
                if item is not None:
                    item.setText(f"{value:.2f}")

    def _update_station_transform(self, _row: int, _column: int) -> None:
        if self._loading or self._profile_index < 0:
            return
        try:
            pos_x = float(self.station_transform_table.item(0, 0).text())
            pos_y = float(self.station_transform_table.item(0, 1).text())
            pos_z = float(self.station_transform_table.item(0, 2).text())
            rot_x = float(self.station_transform_table.item(1, 0).text())
            rot_y = float(self.station_transform_table.item(1, 1).text())
            rot_z = float(self.station_transform_table.item(1, 2).text())
        except (AttributeError, ValueError):
            return

        profiles = self._profiles()
        if not (0 <= self._profile_index < len(profiles)):
            return
        prof = profiles[self._profile_index]

        def change() -> None:
            prof["position"] = {"x": pos_x, "y": pos_y, "z": pos_z}
            prof["rotation"] = {"x": rot_x, "y": rot_y, "z": rot_z}

        self._edit_component("Edit station local transform", change)
        self._refresh_profile_table_row(self._profile_index)
        self._recalculate_planform_metrics()

    def _open_airfoil_dialog(self) -> None:
        if self._profile_index < 0:
            return
        profiles = self._profiles()
        if not (0 <= self._profile_index < len(profiles)):
            return
        current_af = profiles[self._profile_index].get("airfoil", "2412")

        dialog = AirfoilDialog(current_af, self)
        if dialog.exec() == AirfoilDialog.DialogCode.Accepted:
            new_af, apply_all = dialog.get_selected_airfoil()
            if apply_all:
                def change() -> None:
                    for p in profiles:
                        p["airfoil"] = deepcopy(new_af)
                self._edit_component("Apply airfoil to all stations", change)
            else:
                def change() -> None:
                    profiles[self._profile_index]["airfoil"] = deepcopy(new_af)
                self._edit_component("Change station airfoil", change)

            self._loading = True
            self._populate_profiles()
            self._loading = False
            self.profiles_table.selectRow(self._profile_index)
            self._load_profile(self._profile_index)

    def _load_control_surface(self, row: int) -> None:
        cs_list = self._control_surfaces()
        if not (0 <= row < len(cs_list)):
            self._control_surface_index = -1
            self._clear_property_values(self.cs_properties_table)
            self._update_cs_actions()
            return

        self._control_surface_index = row
        cs = cs_list[row]

        self._loading = True
        self._set_property_value(self.cs_properties_table, "tag", str(cs.get("tag") or ""))
        self._set_property_combo(
            self.cs_properties_table,
            "type",
            str(cs.get("type") or "aileron"),
            self.CONTROL_SURFACE_TYPES,
            lambda val: self._update_cs_choice("type", val),
        )
        self._set_property_value(self.cs_properties_table, "span_start", float(cs.get("span_start", 0.0)))
        self._set_property_value(self.cs_properties_table, "span_end", float(cs.get("span_end", 0.0)))
        self._set_property_value(self.cs_properties_table, "chord", float(cs.get("chord", 0.0)))
        self._loading = False

        self._update_cs_actions()

    # -------------------------------------------------------------------------
    # Planform Aerodynamics Live Calculation
    # -------------------------------------------------------------------------

    def _recalculate_planform_metrics(self) -> None:
        profiles = self._profiles()
        if len(profiles) < 2:
            for key in ["wing_area", "wingspan", "aspect_ratio", "mac", "taper_ratio", "root_chord", "tip_chord"]:
                self._set_property_value(self.metrics_table, key, "-", editable=False)
            return

        s_semi = 0.0
        mac_num = 0.0
        for i in range(len(profiles) - 1):
            p0, p1 = profiles[i], profiles[i + 1]
            pos0 = p0.get("position", {}) if isinstance(p0.get("position"), dict) else {}
            pos1 = p1.get("position", {}) if isinstance(p1.get("position"), dict) else {}
            dy = abs(float(pos1.get("y", 0.0)) - float(pos0.get("y", 0.0)))
            c0 = max(float(p0.get("chord", 0.0)), 0.0)
            c1 = max(float(p1.get("chord", 0.0)), 0.0)
            s_i = 0.5 * (c0 + c1) * dy
            c_mac_i = (2.0 / 3.0) * (c0 + c1 - (c0 * c1) / max(c0 + c1, 1e-6))
            s_semi += s_i
            mac_num += s_i * c_mac_i

        b_semi = max(
            abs(float(p.get("position", {}).get("y", 0.0)))
            if isinstance(p.get("position"), dict) else 0.0
            for p in profiles
        )
        b_total = 2.0 * b_semi
        s_total = 2.0 * s_semi
        ar = (b_total**2) / max(s_total, 1e-6) if s_total > 0 else 0.0
        mac = mac_num / max(s_semi, 1e-6) if s_semi > 0 else 0.0
        c_root = float(profiles[0].get("chord", 0.0))
        c_tip = float(profiles[-1].get("chord", 0.0))
        taper = c_tip / max(c_root, 1e-6)

        s_m2 = s_total / 1e6
        s_dm2 = s_total / 1e4
        self._set_property_value(self.metrics_table, "wing_area", f"{s_m2:.4f} m² ({s_dm2:.2f} dm²)", editable=False)
        self._set_property_value(self.metrics_table, "wingspan", f"{b_total:.1f} mm", editable=False)
        self._set_property_value(self.metrics_table, "aspect_ratio", f"{ar:.2f}", editable=False)
        self._set_property_value(self.metrics_table, "mac", f"{mac:.1f} mm", editable=False)
        self._set_property_value(self.metrics_table, "taper_ratio", f"{taper:.3f}", editable=False)
        self._set_property_value(self.metrics_table, "root_chord", f"{c_root:.1f} mm", editable=False)
        self._set_property_value(self.metrics_table, "tip_chord", f"{c_tip:.1f} mm", editable=False)

    # -------------------------------------------------------------------------
    # Profile Station Actions & Inline Edits
    # -------------------------------------------------------------------------

    def _on_profile_selected(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if not self._loading:
            self._load_profile(row)

    def _update_profiles_table_cell(self, row: int, column: int) -> None:
        profiles = self._profiles()
        if self._loading or column == 0 or not (0 <= row < len(profiles)):
            return
        item = self.profiles_table.item(row, column)
        if item is None:
            return
        text_val = item.text().strip()
        prof = profiles[row]
        pos = prof.get("position") if isinstance(prof.get("position"), dict) else {}
        if not isinstance(prof.get("position"), dict):
            prof["position"] = pos
        rot = prof.get("rotation") if isinstance(prof.get("rotation"), dict) else {}
        if not isinstance(prof.get("rotation"), dict):
            prof["rotation"] = rot

        def change() -> None:
            if column == 1:  # Airfoil
                prof["airfoil"] = text_val
            elif column == 2:  # Span Y
                pos["y"] = self._parse_number(text_val) or 0.0
            elif column == 3:  # Chord
                prof["chord"] = max(self._parse_number(text_val) or 10.0, 1.0)
            elif column == 4:  # Offset X
                pos["x"] = self._parse_number(text_val) or 0.0
            elif column == 5:  # Height Z
                pos["z"] = self._parse_number(text_val) or 0.0
            elif column == 6:  # Twist X
                rot["x"] = self._parse_number(text_val) or 0.0

        self._edit_component("Edit wing profile station", change)
        if row == self._profile_index:
            self._load_profile(row)
        self._recalculate_planform_metrics()

    def _add_profile(self) -> None:
        profiles = self._profiles()
        insert_at = len(profiles)
        if profiles:
            last_p = profiles[-1]
            last_pos = last_p.get("position", {}) if isinstance(last_p.get("position"), dict) else {}
            last_rot = last_p.get("rotation", {}) if isinstance(last_p.get("rotation"), dict) else {}
            new_profile = {
                "position": {
                    "x": float(last_pos.get("x", 0.0)) + 20.0,
                    "y": float(last_pos.get("y", 0.0)) + 250.0,
                    "z": float(last_pos.get("z", 0.0)),
                },
                "chord": max(float(last_p.get("chord", 200.0)) * 0.8, 50.0),
                "rotation": deepcopy(last_rot),
                "airfoil": deepcopy(last_p.get("airfoil", "2412")),
            }
        else:
            new_profile = {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "chord": 240.0,
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                "airfoil": "2412",
            }

        def change() -> None:
            profiles.insert(insert_at, new_profile)

        self._edit_component("Add wing profile", change)
        self._loading = True
        self._populate_profiles()
        self._loading = False
        self.profiles_table.selectRow(insert_at)
        self._load_profile(insert_at)
        self._recalculate_planform_metrics()

    def _duplicate_profile(self) -> None:
        idx = self._profile_index
        profiles = self._profiles()
        if not (0 <= idx < len(profiles)):
            return
        insert_at = idx + 1
        target = deepcopy(profiles[idx])
        pos = target.get("position", {}) if isinstance(target.get("position"), dict) else {}
        pos["y"] = float(pos.get("y", 0.0)) + 100.0
        target["position"] = pos

        def change() -> None:
            profiles.insert(insert_at, target)

        self._edit_component("Duplicate wing profile", change)
        self._loading = True
        self._populate_profiles()
        self._loading = False
        self.profiles_table.selectRow(insert_at)
        self._load_profile(insert_at)
        self._recalculate_planform_metrics()

    def _move_profile_up(self) -> None:
        idx = self._profile_index
        if idx <= 0:
            return
        profiles = self._profiles()
        target = idx - 1

        def change() -> None:
            profiles.insert(target, profiles.pop(idx))

        self._edit_component("Move wing profile up", change)
        self._loading = True
        self._populate_profiles()
        self._loading = False
        self.profiles_table.selectRow(target)
        self._load_profile(target)
        self._recalculate_planform_metrics()

    def _move_profile_down(self) -> None:
        idx = self._profile_index
        profiles = self._profiles()
        if idx < 0 or idx >= len(profiles) - 1:
            return
        target = idx + 1

        def change() -> None:
            profiles.insert(target, profiles.pop(idx))

        self._edit_component("Move wing profile down", change)
        self._loading = True
        self._populate_profiles()
        self._loading = False
        self.profiles_table.selectRow(target)
        self._load_profile(target)
        self._recalculate_planform_metrics()

    def _delete_profile(self) -> None:
        idx = self._profile_index
        profiles = self._profiles()
        if idx < 0 or len(profiles) <= 2:
            return

        def change() -> None:
            profiles.pop(idx)

        self._edit_component("Delete wing profile", change)
        self._loading = True
        self._populate_profiles()
        self._loading = False
        new_idx = min(idx, len(profiles) - 1)
        self.profiles_table.selectRow(new_idx)
        self._load_profile(new_idx)
        self._recalculate_planform_metrics()

    def _update_profile_actions(self) -> None:
        profiles = self._profiles()
        count = len(profiles)
        idx = self._profile_index
        has_sel = 0 <= idx < count
        self.duplicate_profile_button.setEnabled(has_sel)
        self.move_profile_up_button.setEnabled(has_sel and idx > 0)
        self.move_profile_down_button.setEnabled(has_sel and idx < count - 1)
        self.delete_profile_button.setEnabled(has_sel and count > 2)
        self.choose_airfoil_btn.setEnabled(has_sel)

    # -------------------------------------------------------------------------
    # Profile Properties Mutation
    # -------------------------------------------------------------------------

    def _update_profile_property(self, row: int, column: int) -> None:
        if self._loading or column != 1 or self._profile_index < 0:
            return
        key = self._property_key(self.profile_properties_table, row)
        val_str = self._property_text(self.profile_properties_table, row)

        profiles = self._profiles()
        if not (0 <= self._profile_index < len(profiles)):
            return
        prof = profiles[self._profile_index]

        def change() -> None:
            if key == "airfoil":
                prof["airfoil"] = val_str.strip()
            elif key == "chord":
                prof["chord"] = max(self._parse_number(val_str) or 10.0, 1.0)

        self._edit_component(f"Edit profile {key}", change)
        self._refresh_profile_table_row(self._profile_index)
        self._recalculate_planform_metrics()

    def _refresh_profile_table_row(self, row: int) -> None:
        profiles = self._profiles()
        if not (0 <= row < len(profiles)):
            return
        prof = profiles[row]
        pos = prof.get("position", {}) if isinstance(prof.get("position"), dict) else {}
        rot = prof.get("rotation", {}) if isinstance(prof.get("rotation"), dict) else {}
        airfoil = self._format_airfoil_label(prof.get("airfoil"))

        self._loading = True
        self.profiles_table.item(row, 1).setText(airfoil)
        self.profiles_table.item(row, 2).setText(f"{float(pos.get('y', 0.0)):.1f}")
        self.profiles_table.item(row, 3).setText(f"{float(prof.get('chord', 0.0)):.1f}")
        self.profiles_table.item(row, 4).setText(f"{float(pos.get('x', 0.0)):.1f}")
        self.profiles_table.item(row, 5).setText(f"{float(pos.get('z', 0.0)):.1f}")
        self.profiles_table.item(row, 6).setText(f"{float(rot.get('x', 0.0)):.1f}")
        self._loading = False

    # -------------------------------------------------------------------------
    # Control Surface Actions & Mutation
    # -------------------------------------------------------------------------

    def _on_control_surface_selected(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if not self._loading:
            self._load_control_surface(row)

    def _update_cs_table_cell(self, row: int, column: int) -> None:
        cs_list = self._control_surfaces()
        if self._loading or not (0 <= row < len(cs_list)):
            return
        item = self.control_surfaces_table.item(row, column)
        if item is None:
            return
        text_val = item.text().strip()
        cs = cs_list[row]

        def change() -> None:
            if column == 0:
                cs["tag"] = text_val
            elif column == 1:
                cs["type"] = text_val.lower()
            elif column == 2:
                cs["span_start"] = self._parse_number(text_val) or 0.0
            elif column == 3:
                cs["span_end"] = self._parse_number(text_val) or 0.0
            elif column == 4:
                cs["chord"] = max(self._parse_number(text_val) or 10.0, 1.0)

        self._edit_component("Edit control surface", change)
        if row == self._control_surface_index:
            self._load_control_surface(row)

    def _add_control_surface(self) -> None:
        cs_list = self._control_surfaces()
        new_tag = f"control_{len(cs_list) + 1}"
        new_cs = {
            "tag": new_tag,
            "type": "aileron",
            "span_start": 100.0,
            "span_end": 400.0,
            "chord": 40.0,
        }
        insert_at = len(cs_list)

        def change() -> None:
            cs_list.insert(insert_at, new_cs)

        self._edit_component("Add control surface", change)
        self._loading = True
        self._populate_control_surfaces()
        self._loading = False
        self.control_surfaces_table.selectRow(insert_at)
        self._load_control_surface(insert_at)

    def _duplicate_control_surface(self) -> None:
        idx = self._control_surface_index
        cs_list = self._control_surfaces()
        if not (0 <= idx < len(cs_list)):
            return
        target = deepcopy(cs_list[idx])
        target["tag"] = f"{target.get('tag', 'cs')}_copy"
        insert_at = idx + 1

        def change() -> None:
            cs_list.insert(insert_at, target)

        self._edit_component("Duplicate control surface", change)
        self._loading = True
        self._populate_control_surfaces()
        self._loading = False
        self.control_surfaces_table.selectRow(insert_at)
        self._load_control_surface(insert_at)

    def _move_cs_up(self) -> None:
        idx = self._control_surface_index
        if idx <= 0:
            return
        cs_list = self._control_surfaces()
        target = idx - 1

        def change() -> None:
            cs_list.insert(target, cs_list.pop(idx))

        self._edit_component("Move control surface up", change)
        self._loading = True
        self._populate_control_surfaces()
        self._loading = False
        self.control_surfaces_table.selectRow(target)
        self._load_control_surface(target)

    def _move_cs_down(self) -> None:
        idx = self._control_surface_index
        cs_list = self._control_surfaces()
        if idx < 0 or idx >= len(cs_list) - 1:
            return
        target = idx + 1

        def change() -> None:
            cs_list.insert(target, cs_list.pop(idx))

        self._edit_component("Move control surface down", change)
        self._loading = True
        self._populate_control_surfaces()
        self._loading = False
        self.control_surfaces_table.selectRow(target)
        self._load_control_surface(target)

    def _delete_control_surface(self) -> None:
        idx = self._control_surface_index
        cs_list = self._control_surfaces()
        if not (0 <= idx < len(cs_list)):
            return

        def change() -> None:
            cs_list.pop(idx)

        self._edit_component("Delete control surface", change)
        self._loading = True
        self._populate_control_surfaces()
        self._loading = False
        new_idx = min(idx, len(cs_list) - 1)
        self.control_surfaces_table.selectRow(new_idx)
        self._load_control_surface(new_idx)

    def _update_cs_actions(self) -> None:
        cs_list = self._control_surfaces()
        count = len(cs_list)
        idx = self._control_surface_index
        has_sel = 0 <= idx < count
        self.duplicate_cs_button.setEnabled(has_sel)
        self.move_cs_up_button.setEnabled(has_sel and idx > 0)
        self.move_cs_down_button.setEnabled(has_sel and idx < count - 1)
        self.delete_cs_button.setEnabled(has_sel)

    def _refresh_cs_table_row(self, row: int) -> None:
        cs_list = self._control_surfaces()
        if not (0 <= row < len(cs_list)):
            return
        cs = cs_list[row]
        self._loading = True
        if self.control_surfaces_table.item(row, 0):
            self.control_surfaces_table.item(row, 0).setText(str(cs.get("tag") or f"CS_{row + 1}"))
        if self.control_surfaces_table.item(row, 1):
            self.control_surfaces_table.item(row, 1).setText(str(cs.get("type") or "aileron").capitalize())
        if self.control_surfaces_table.item(row, 2):
            self.control_surfaces_table.item(row, 2).setText(f"{float(cs.get('span_start', 0.0)):.1f}")
        if self.control_surfaces_table.item(row, 3):
            self.control_surfaces_table.item(row, 3).setText(f"{float(cs.get('span_end', 0.0)):.1f}")
        if self.control_surfaces_table.item(row, 4):
            self.control_surfaces_table.item(row, 4).setText(f"{float(cs.get('chord', 0.0)):.1f}")
        self._loading = False

    def _update_cs_property(self, row: int, column: int) -> None:
        if self._loading or column != 1 or self._control_surface_index < 0:
            return
        key = self._property_key(self.cs_properties_table, row)
        val_str = self._property_text(self.cs_properties_table, row)
        cs_list = self._control_surfaces()
        if not (0 <= self._control_surface_index < len(cs_list)):
            return
        cs = cs_list[self._control_surface_index]

        def change() -> None:
            if key == "tag":
                cs["tag"] = val_str.strip()
            elif key == "span_start":
                cs["span_start"] = self._parse_number(val_str) or 0.0
            elif key == "span_end":
                cs["span_end"] = self._parse_number(val_str) or 0.0
            elif key == "chord":
                cs["chord"] = max(self._parse_number(val_str) or 10.0, 1.0)

        self._edit_component(f"Edit control surface {key}", change)
        self._refresh_cs_table_row(self._control_surface_index)

    def _update_cs_choice(self, key: str, value: str) -> None:
        if self._loading or self._control_surface_index < 0:
            return
        cs_list = self._control_surfaces()
        if not (0 <= self._control_surface_index < len(cs_list)):
            return
        cs = cs_list[self._control_surface_index]

        def change() -> None:
            cs[key] = value

        self._edit_component(f"Edit control surface {key}", change)
        self._refresh_cs_table_row(self._control_surface_index)

    # -------------------------------------------------------------------------
    # General & Blending Mutations
    # -------------------------------------------------------------------------

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_str = self._property_text(self.general_table, row)

        def change() -> None:
            if key == "name":
                self._component["name"] = val_str.strip()
            elif key == "mass":
                mass_val = self._parse_number(val_str) or 0.0
                self._parameters()["mass"] = max(mass_val, 0.0)
                self._component["mass"] = max(mass_val, 0.0)

        self._edit_component(f"Edit {key}", change)

    def _update_blending(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.blending_table, row)
        val_str = self._property_text(self.blending_table, row)
        if key == "max_degree":
            deg = int(self._parse_number(val_str) or 3)
            self._update_blending_value("max_degree", max(1, min(deg, 8)))

    def _update_blending_value(self, key: str, value: Any) -> None:
        if self._loading:
            return
        blending = self._geometry().get("blending")
        if not isinstance(blending, dict):
            blending = {}
            self._geometry()["blending"] = blending

        def change() -> None:
            blending[key] = value

        self._edit_component(f"Edit blending {key}", change)

    # -------------------------------------------------------------------------
    # Helpers & Edit Component Transaction
    # -------------------------------------------------------------------------

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

    def _control_surfaces(self) -> list[dict[str, Any]]:
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

    @classmethod
    def _property_table(
        cls,
        definitions: list[tuple[str, str]],
    ) -> QTableWidget:
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
        cls,
        table: QTableWidget,
        definitions: list[tuple[str, str]],
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
            table.setItem(row, 1, QTableWidgetItem())
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
        combo.setFont(QApplication.font())
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        combo.view().setProperty("tableComboPopup", True)
        combo.view().setFont(QApplication.font())
        for option_value, label in options:
            combo.addItem(label, option_value)
        combo.setCurrentIndex(max(combo.findData(value), 0))
        combo.currentIndexChanged.connect(
            lambda _index, editor=combo, callback=on_changed: callback(str(editor.currentData()))
        )
        table.setCellWidget(row, column, combo)

    @staticmethod
    def _set_property_value(
        table: QTableWidget,
        key: str,
        value: object,
        *,
        editable: bool = True,
    ) -> None:
        for row in range(table.rowCount()):
            if LiftingSurfaceEditor._property_key(table, row) != key:
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
    def _clear_property_values(table: QTableWidget) -> None:
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item is not None:
                item.setText("")

    @staticmethod
    def _property_key(table: QTableWidget, row: int) -> str:
        item = table.item(row, 0)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    @staticmethod
    def _property_text(table: QTableWidget, row: int) -> str:
        editor = table.cellWidget(row, 1)
        if isinstance(editor, QComboBox):
            return str(editor.currentData())
        item = table.item(row, 1)
        return item.text() if item is not None else ""

    @staticmethod
    def _parse_number(value: str) -> float | None:
        try:
            return float(value.replace("°", "").replace("mm", "").replace("g", "").strip())
        except ValueError:
            return None

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
        maximum_visible_rows: int = 6,
    ) -> None:
        visible_rows = min(max(row_count, 1), maximum_visible_rows)
        height = (
            table.horizontalHeader().height()
            + table.verticalHeader().defaultSectionSize() * visible_rows
            + 2
        )
        table.setFixedHeight(height)
