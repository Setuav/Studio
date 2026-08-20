"""Lifting Surface Editor widget for configuring wings, stabilizers, fins, and control surfaces."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QFont, QHideEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.numeric_spinbox import (
    NoWheelComboBox,
    NumericSpinBox,
    set_table_spinbox,
)
from setuav_studio.ui.property_tables import PropertyTableMixin
from setuav_studio.plugins.geometry.airfoil import PRESET_AIRFOILS
from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog
from setuav_studio.plugins.geometry.wing_planform_engine import (
    DRIVER_MODES,
    SWEEP_LOCATIONS,
    TWIST_LOCATIONS,
    compute_planform_metrics,
    get_driver_inputs_for_mode,
    solve_wing_planform,
)


class LiftingSurfaceEditor(PropertyTableMixin, QWidget):
    """Component property editor for org.setuav.core:lifting-surface."""

    table_combo_cls = NoWheelComboBox
    table_scroll_policy_off = True
    table_max_visible_rows = None
    table_property_text_spinbox = True

    CONTROL_SURFACE_TYPES = [
        ("aileron", "Aileron"),
        ("flap", "Flap"),
        ("elevator", "Elevator"),
        ("rudder", "Rudder"),
    ]

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._component = component
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
        self._create_driver_groups_section()
        self._create_planform_sizing_section()
        self._create_profiles_section()
        self._create_profile_properties_section()
        self._create_airfoil_shaping_section()
        self._create_tip_caps_section()
        self._create_control_surfaces_section()
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

        self.attachment_options_table = self._property_table([
            ("mirror", "Symmetry / Mirror"),
        ])
        layout.addWidget(self.attachment_options_table)

    def _create_driver_groups_section(self) -> None:
        """Driver Groups configuration table section."""
        layout = self._create_section("Driver Group", "fa6s.arrows-left-right-to-line")

        self.driver_groups_table = self._property_table([
            ("driver_mode", "Driver Mode"),
            ("sweep_loc", "Sweep Reference"),
            ("twist_axis", "Twist Axis"),
        ])
        layout.addWidget(self.driver_groups_table)

    def _create_planform_sizing_section(self) -> None:
        """Parametric Planform Sizing table section."""
        layout = self._create_section("Planform Sizing", "fa6s.ruler-combined")

        # Planform Parameters Table
        self.planform_table = self._property_table([
            ("area", "Planform Area (S)"),
            ("span", "Total Wingspan (b)"),
            ("aspect_ratio", "Aspect Ratio (AR)"),
            ("taper_ratio", "Taper Ratio (λ)"),
            ("root_chord", "Root Chord (c_root)"),
            ("tip_chord", "Tip Chord (c_tip)"),
            ("sweep", "Sweep Angle (Λ)"),
            ("washout", "Tip Twist / Washout (ε)"),
            ("mac", "Mean Aerodyn Chord (MAC)"),
        ])
        self.planform_table.cellChanged.connect(self._on_planform_parameter_edited)
        layout.addWidget(self.planform_table)

    def _create_profiles_section(self) -> None:
        layout = self._create_section("Wing Profiles (Sections)", "mdi6.vector-polygon")

        self.profiles_table = self._table([
            "#",
            "Airfoil",
            "Span Y (mm)",
            "Chord (mm)",
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
            ("twist", "Twist Angle (°)"),
            ("span_y", "Span Y (mm)"),
            ("offset_x", "Offset X (mm)"),
            ("height_z", "Height Z (mm)"),
            ("dihedral", "Dihedral / Roll (°)"),
            ("yaw", "Yaw Angle (°)"),
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

    def _create_airfoil_shaping_section(self) -> None:
        """Airfoil Shaping: TE blunting, thickness/camber scalers, and dihedral section alignment."""
        layout = self._create_section("Airfoil Shaping", "fa6s.pen-ruler")

        self.airfoil_shaping_table = self._property_table([
            ("section_align", "Section Alignment"),
            ("te_thickness", "TE Blunting (% chord)"),
            ("thickness_scale", "Thickness Scale"),
            ("camber_scale", "Camber Scale"),
        ])
        layout.addWidget(self.airfoil_shaping_table)

    def _create_tip_caps_section(self) -> None:
        """End Caps (Tip Treatment) configuration section."""
        layout = self._create_section("End Caps (Tip Treatment)", "fa6s.shapes")

        self.tip_caps_table = self._property_table([
            ("tip_type", "Tip Cap Type"),
            ("tip_length", "Tip Length (mm)"),
            ("tip_offset_x", "Tip Sweep Offset (mm)"),
            ("winglet_height", "Winglet Height (mm)"),
            ("cant_angle", "Cant Angle (°)"),
            ("winglet_sweep", "Winglet Sweep (°)"),
            ("toe_angle", "Toe Angle (°)"),
            ("root_chord_scale", "Root Chord Scale"),
            ("tip_chord_scale", "Tip Chord Scale"),
        ])
        self.tip_caps_table.cellChanged.connect(self._on_tip_cap_cell_edited)
        layout.addWidget(self.tip_caps_table)

    def _create_control_surfaces_section(self) -> None:
        layout = self._create_section("Control Surfaces", "fa6s.sliders")

        self.control_surfaces_table = self._table([
            "Tag",
            "Type",
            "Span (mm)",
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
            ("hinge_sweep", "Hinge Sweep (°)"),
            ("deflection", "Deflection Angle (°)"),
        ])
        self.cs_properties_table.cellChanged.connect(self._update_cs_property)
        layout.addWidget(self.cs_properties_table)

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
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

        # Parent Selection Combo (Only fuselage and lifting surfaces)
        current_parent = str(self._component.get("parent") or "")
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
            "parent",
            current_parent,
            parent_options,
            lambda val: self._update_parent(val if val else None),
        )

        mass_val = float(self._parameters().get("mass") or 0.0)
        self._set_property_spinbox(
            self.general_table,
            "mass",
            mass_val,
            min_val=0.0,
            step=10.0,
            decimals=1,
            suffix="g",
            on_changed=lambda _v: self._update_general(1, 1),
        )

        # Attachment / Component Transform
        self._load_attachment_transform()

        # Profiles
        self._populate_profiles()

        # Planform Sizing & Driver Group Initial Setup
        self._sync_driver_mode_from_project()
        self._load_driver_groups_table()
        self._refresh_planform_table()

        # End Caps (Tip Treatment)
        self._load_tip_caps()

        # Airfoil Shaping
        self._load_airfoil_shaping()

        # Control Surfaces
        self._populate_control_surfaces()

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

        for col, val in enumerate(pos_vals):
            set_table_spinbox(
                self.attachment_table,
                0,
                col,
                val,
                step=5.0,
                decimals=2,
                suffix="mm",
                on_changed=lambda _v: self._on_attachment_spinbox_changed(),
            )
        for col, val in enumerate(rot_vals):
            set_table_spinbox(
                self.attachment_table,
                1,
                col,
                val,
                min_val=-360.0,
                max_val=360.0,
                step=1.0,
                decimals=2,
                suffix="°",
                on_changed=lambda _v: self._on_attachment_spinbox_changed(),
            )

        # Symmetry / Mirror
        is_mirror = "true" if self._geometry().get("mirror") is True else "false"
        self._set_property_combo(
            self.attachment_options_table,
            "mirror",
            is_mirror,
            [("false", "Single (No Mirror)"), ("true", "Bilateral (Mirror XZ)")],
            lambda val: self._update_mirror(val == "true"),
        )

    def _update_mirror(self, is_mirrored: bool) -> None:
        if self._loading:
            return

        def change() -> None:
            if is_mirrored:
                self._geometry()["mirror"] = True
            else:
                self._geometry().pop("mirror", None)

        self._edit_component("Toggle bilateral wing mirror", change)

    def _on_attachment_spinbox_changed(self) -> None:
        if self._loading:
            return
        vals_pos = []
        for col in range(3):
            w = self.attachment_table.cellWidget(0, col)
            vals_pos.append(float(w.value()) if isinstance(w, QDoubleSpinBox) else 0.0)
        vals_rot = []
        for col in range(3):
            w = self.attachment_table.cellWidget(1, col)
            vals_rot.append(float(w.value()) if isinstance(w, QDoubleSpinBox) else 0.0)

        def change() -> None:
            tf = self._component.get("transform")
            if not isinstance(tf, dict):
                tf = {}
                self._component["transform"] = tf
            tf["position"] = {"x": vals_pos[0], "y": vals_pos[1], "z": vals_pos[2]}
            tf["rotation"] = {"roll": vals_rot[0], "pitch": vals_rot[1], "yaw": vals_rot[2]}

        self._edit_component("Edit wing attachment transform", change)
        self._refresh_planform_table()

    def _update_attachment_transform(self, _row: int, _col: int) -> None:
        pass

    def _update_parent(self, new_parent: str | None) -> None:
        if self._loading:
            return

        def change() -> None:
            self._component["parent"] = new_parent

        self._edit_component("Change component parent", change)

    # -------------------------------------------------------------------------
    # Planform Sizing & Driver Group Logic
    # -------------------------------------------------------------------------

    def _sync_driver_mode_from_project(self) -> None:
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if project and isinstance(project.data.get("driver_groups"), list):
            for dg in project.data["driver_groups"]:
                if isinstance(dg, dict) and dg.get("id") in ("wing-drivers", f"{self._component.get('id')}-drivers"):
                    self._driver_mode = "area_ar_taper"
                    break

    def _load_driver_groups_table(self) -> None:
        # Driver Mode
        self._set_property_combo(
            self.driver_groups_table,
            "driver_mode",
            self._driver_mode,
            DRIVER_MODES,
            self._on_driver_mode_changed,
        )

        # Sweep Reference
        self._set_property_combo(
            self.driver_groups_table,
            "sweep_loc",
            str(self._sweep_loc),
            [(str(val), label) for val, label in SWEEP_LOCATIONS],
            self._on_sweep_loc_changed,
        )

        # Twist Axis Location
        twist_loc = float(self._geometry().get("twist_location", 0.25))
        self._set_property_combo(
            self.driver_groups_table,
            "twist_axis",
            str(twist_loc),
            [(str(val), label) for val, label in TWIST_LOCATIONS],
            self._on_twist_loc_changed,
        )

    def _on_driver_mode_changed(self, mode_val: str) -> None:
        if self._loading:
            return
        self._driver_mode = str(mode_val or "manual")
        self._refresh_planform_table()
        self._update_profile_actions()
        self._update_profiles_table_interactivity()
        if 0 <= self._profile_index < len(self._profiles()):
            self._load_profile(self._profile_index)

    def _on_sweep_loc_changed(self, loc_val_str: str) -> None:
        if self._loading:
            return
        try:
            self._sweep_loc = float(loc_val_str)
        except ValueError:
            self._sweep_loc = 0.25
        self._refresh_planform_table()

    def _on_twist_loc_changed(self, twist_val_str: str) -> None:
        if self._loading:
            return
        try:
            twist_loc = float(twist_val_str)
        except ValueError:
            twist_loc = 0.25

        def change() -> None:
            self._geometry()["twist_location"] = twist_loc

        self._edit_component("Change wing twist axis location", change)

    def _is_symmetric(self) -> bool:
        geom = self._geometry()
        return bool(geom.get("symmetric", True))

    def _y_offset(self) -> float:
        tf = self._component.get("transform")
        if isinstance(tf, dict):
            pos = tf.get("position")
            if isinstance(pos, dict):
                return float(pos.get("y", 0.0))
        return 0.0

    def _refresh_planform_table(self) -> None:
        profiles = self._profiles()
        metrics = compute_planform_metrics(
            profiles,
            self._sweep_loc,
            symmetric=self._is_symmetric(),
            y_offset=self._y_offset(),
        )
        active_driver_keys = [k for k, _l, _u in get_driver_inputs_for_mode(self._driver_mode)]

        was_loading = self._loading
        self._loading = True
        try:
            s_total = metrics["area"]
            s_m2 = s_total / 1e6
            s_dm2 = s_total / 1e4
            if "area" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "area",
                    s_total,
                    min_val=100.0,
                    step=1000.0,
                    decimals=1,
                    suffix="mm²",
                    on_changed=lambda val: self._on_planform_spinbox_changed("area", val),
                )
            else:
                self._set_planform_cell("area", f"{s_m2:.4f} m² ({s_dm2:.2f} dm²)", editable=False)

            if "span" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "span",
                    metrics["span"],
                    min_val=10.0,
                    step=50.0,
                    decimals=1,
                    suffix="mm",
                    on_changed=lambda val: self._on_planform_spinbox_changed("span", val),
                )
            else:
                self._set_planform_cell("span", f"{metrics['span']:.1f} mm", editable=False)

            if "aspect_ratio" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "aspect_ratio",
                    metrics["aspect_ratio"],
                    min_val=0.5,
                    max_val=50.0,
                    step=0.1,
                    decimals=2,
                    on_changed=lambda val: self._on_planform_spinbox_changed("aspect_ratio", val),
                )
            else:
                self._set_planform_cell("aspect_ratio", f"{metrics['aspect_ratio']:.2f}", editable=False)

            if "taper_ratio" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "taper_ratio",
                    metrics["taper_ratio"],
                    min_val=0.01,
                    max_val=5.0,
                    step=0.05,
                    decimals=3,
                    on_changed=lambda val: self._on_planform_spinbox_changed("taper_ratio", val),
                )
            else:
                self._set_planform_cell("taper_ratio", f"{metrics['taper_ratio']:.3f}", editable=False)

            if "root_chord" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "root_chord",
                    metrics["root_chord"],
                    min_val=5.0,
                    step=10.0,
                    decimals=1,
                    suffix="mm",
                    on_changed=lambda val: self._on_planform_spinbox_changed("root_chord", val),
                )
            else:
                self._set_planform_cell("root_chord", f"{metrics['root_chord']:.1f} mm", editable=False)

            if "tip_chord" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "tip_chord",
                    metrics["tip_chord"],
                    min_val=5.0,
                    step=10.0,
                    decimals=1,
                    suffix="mm",
                    on_changed=lambda val: self._on_planform_spinbox_changed("tip_chord", val),
                )
            else:
                self._set_planform_cell("tip_chord", f"{metrics['tip_chord']:.1f} mm", editable=False)

            if "sweep" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "sweep",
                    metrics["sweep"],
                    min_val=-80.0,
                    max_val=80.0,
                    step=1.0,
                    decimals=1,
                    suffix="°",
                    on_changed=lambda val: self._on_planform_spinbox_changed("sweep", val),
                )
            else:
                self._set_planform_cell("sweep", f"{metrics['sweep']:.1f}°", editable=False)

            if "washout" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "washout",
                    metrics["washout"],
                    min_val=-45.0,
                    max_val=45.0,
                    step=0.5,
                    decimals=1,
                    suffix="°",
                    on_changed=lambda val: self._on_planform_spinbox_changed("washout", val),
                )
            else:
                self._set_planform_cell("washout", f"{metrics['washout']:.1f}°", editable=False)

            self._set_planform_cell("mac", f"{metrics['mac']:.1f} mm", editable=False)

            self._update_profiles_table_interactivity()
        finally:
            self._loading = was_loading

    def _set_planform_cell(self, key: str, value: str, *, editable: bool) -> None:
        """Set property value with distinct visual styling for active drivers vs computed values."""
        for row in range(self.planform_table.rowCount()):
            if self._property_key(self.planform_table, row) != key:
                continue
            if self.planform_table.cellWidget(row, 1) is not None:
                self.planform_table.removeCellWidget(row, 1)
            item = self.planform_table.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                self.planform_table.setItem(row, 1, item)
            item.setText(value)
            label_item = self.planform_table.item(row, 0)
            if editable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setForeground(QBrush(QColor("#ffffff")))
                if label_item:
                    label_item.setForeground(QBrush(QColor("#ffffff")))
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setForeground(QBrush(QColor("#777777")))
                if label_item:
                    label_item.setForeground(QBrush(QColor("#999999")))
            return

    def _on_planform_spinbox_changed(self, key: str, val_num: float) -> None:
        if self._loading:
            return
        if key not in ("sweep", "washout") and val_num <= 0:
            return

        profiles = self._profiles()
        is_sym = self._is_symmetric()
        y_off = self._y_offset()
        current_metrics = compute_planform_metrics(
            profiles,
            self._sweep_loc,
            symmetric=is_sym,
            y_offset=y_off,
        )
        inputs: dict[str, float] = {
            "area": current_metrics["area"],
            "span": current_metrics["span"],
            "aspect_ratio": current_metrics["aspect_ratio"],
            "taper_ratio": current_metrics["taper_ratio"],
            "root_chord": current_metrics["root_chord"],
            "tip_chord": current_metrics["tip_chord"],
            "sweep": current_metrics["sweep"],
            "washout": current_metrics["washout"],
        }
        inputs[key] = float(val_num)

        new_profiles, calculated_metrics = solve_wing_planform(
            self._driver_mode,
            inputs,
            profiles,
            self._sweep_loc,
            symmetric=is_sym,
            y_offset=y_off,
        )

        def change() -> None:
            profiles.clear()
            profiles.extend(deepcopy(new_profiles))
            self._sync_project_parameters(inputs, key)

        self._edit_component(f"Parametric wing resize ({key})", change)

        self._populate_profiles()
        self._refresh_planform_table()
        if 0 <= self._profile_index < len(profiles):
            self._load_profile(self._profile_index)

    def _on_planform_parameter_edited(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.planform_table, row)
        val_str = self._property_text(self.planform_table, row)
        val_num = self._parse_number(val_str)
        if val_num is not None:
            self._on_planform_spinbox_changed(key, val_num)

    def _sync_project_parameters(self, inputs: dict[str, float], edited_key: str) -> None:
        """Sync updated macro parameters to project.data['parameters'] if present."""
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if not project or not isinstance(project.data.get("parameters"), dict):
            return
        params = project.data["parameters"]
        if "wing_area" in params and isinstance(params["wing_area"], dict):
            params["wing_area"]["value"] = inputs.get("area", 218700.0)
        if "wing_aspect_ratio" in params and isinstance(params["wing_aspect_ratio"], dict):
            params["wing_aspect_ratio"]["value"] = inputs.get("aspect_ratio", 5.33)

    def _update_profiles_table_interactivity(self) -> None:
        """Lock or unlock profiles table columns depending on driver mode."""
        is_manual = self._driver_mode == "manual"
        # Columns: 0=#, 1=Airfoil, 2=Span Y, 3=Chord
        for r in range(self.profiles_table.rowCount()):
            # Airfoil is always editable
            af_item = self.profiles_table.item(r, 1)
            if af_item:
                af_item.setFlags(af_item.flags() | Qt.ItemFlag.ItemIsEditable)
                af_item.setForeground(QBrush(QColor("#ffffff")))
            # Span Y and Chord depend on driver mode
            for c in (2, 3):
                item = self.profiles_table.item(r, c)
                if not item:
                    continue
                if is_manual:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setForeground(QBrush(QColor("#ffffff")))
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setForeground(QBrush(QColor("#777777")))

        # In section properties: chord, span_y, offset_x are locked when macro driver is active
        locked_keys = {"chord", "span_y", "offset_x"}
        for row in range(self.profile_properties_table.rowCount()):
            key = self._property_key(self.profile_properties_table, row)
            widget = self.profile_properties_table.cellWidget(row, 1)
            val_item = self.profile_properties_table.item(row, 1)
            lbl_item = self.profile_properties_table.item(row, 0)
            is_locked = (key in locked_keys) and not is_manual
            if widget is not None:
                widget.setEnabled(not is_locked)
            if val_item is not None:
                if is_locked:
                    val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    val_item.setForeground(QBrush(QColor("#777777")))
                else:
                    val_item.setFlags(val_item.flags() | Qt.ItemFlag.ItemIsEditable)
                    val_item.setForeground(QBrush(QColor("#ffffff")))
            if lbl_item is not None:
                lbl_item.setForeground(QBrush(QColor("#777777" if is_locked else "#ffffff")))

    # -------------------------------------------------------------------------
    # Profiles Handling
    # -------------------------------------------------------------------------

    def _populate_profiles(self) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            profiles = self._profiles()
            self.profiles_table.setRowCount(len(profiles))
            for row, profile in enumerate(profiles):
                pos = profile.get("position") if isinstance(profile.get("position"), dict) else {}
                airfoil = self._format_airfoil_label(profile.get("airfoil"))
                values = (
                    str(row + 1),
                    airfoil,
                    f"{float(pos.get('y', 0.0)):.1f}",
                    f"{float(profile.get('chord', 0.0)):.1f}",
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
            self._update_profiles_table_interactivity()
        finally:
            self._loading = was_loading

    def _populate_control_surfaces(self) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            cs_list = self._control_surfaces()
            self.control_surfaces_table.setRowCount(len(cs_list))
            for row, cs in enumerate(cs_list):
                geom = self._cs_geom(cs)
                s_start = float(geom.get("span_start", 0.0))
                s_end = float(geom.get("span_end", 0.0))
                tag_label = str(geom.get("tag") or cs.get("name") or cs.get("id") or f"CS_{row + 1}")
                cs_type = str(geom.get("type") or "aileron").capitalize()
                values = (
                    tag_label,
                    cs_type,
                    f"{s_start:.1f} - {s_end:.1f}",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 2:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    else:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.control_surfaces_table.setItem(row, column, item)

            self._fit_table_height(self.control_surfaces_table, len(cs_list), maximum_visible_rows=5)
            self._update_cs_actions()
        finally:
            self._loading = was_loading

    def _load_profile(self, row: int) -> None:
        profiles = self._profiles()
        if not (0 <= row < len(profiles)):
            self._profile_index = -1
            self._clear_property_values(self.profile_properties_table)
            self._update_profile_actions()
            self._publish_section_selection()
            return

        self._profile_index = row
        profile = profiles[row]
        pos = profile.get("position") if isinstance(profile.get("position"), dict) else {}
        rot = profile.get("rotation") if isinstance(profile.get("rotation"), dict) else {}

        was_loading = self._loading
        self._loading = True
        try:
            airfoil_val = self._format_airfoil_label(profile.get("airfoil"))
            self._set_property_value(self.profile_properties_table, "airfoil", airfoil_val)
            self._set_property_spinbox(
                self.profile_properties_table,
                "chord",
                float(profile.get("chord", 200.0)),
                min_val=1.0,
                step=5.0,
                decimals=1,
                suffix="mm",
                on_changed=lambda val: self._on_profile_prop_spinbox_changed("chord", val),
            )
            self._set_property_spinbox(
                self.profile_properties_table,
                "twist",
                float(rot.get("y", 0.0)),
                min_val=-45.0,
                max_val=45.0,
                step=0.5,
                decimals=2,
                suffix="°",
                on_changed=lambda val: self._on_profile_prop_spinbox_changed("twist", val),
            )
            self._set_property_spinbox(
                self.profile_properties_table,
                "span_y",
                float(pos.get("y", 0.0)),
                step=5.0,
                decimals=1,
                suffix="mm",
                on_changed=lambda val: self._on_profile_prop_spinbox_changed("span_y", val),
            )
            self._set_property_spinbox(
                self.profile_properties_table,
                "offset_x",
                float(pos.get("x", 0.0)),
                step=5.0,
                decimals=1,
                suffix="mm",
                on_changed=lambda val: self._on_profile_prop_spinbox_changed("offset_x", val),
            )
            self._set_property_spinbox(
                self.profile_properties_table,
                "height_z",
                float(pos.get("z", 0.0)),
                step=5.0,
                decimals=1,
                suffix="mm",
                on_changed=lambda val: self._on_profile_prop_spinbox_changed("height_z", val),
            )
            self._set_property_spinbox(
                self.profile_properties_table,
                "dihedral",
                float(rot.get("x", 0.0)),
                min_val=-90.0,
                max_val=90.0,
                step=1.0,
                decimals=2,
                suffix="°",
                on_changed=lambda val: self._on_profile_prop_spinbox_changed("dihedral", val),
            )
            self._set_property_spinbox(
                self.profile_properties_table,
                "yaw",
                float(rot.get("z", 0.0)),
                min_val=-90.0,
                max_val=90.0,
                step=1.0,
                decimals=2,
                suffix="°",
                on_changed=lambda val: self._on_profile_prop_spinbox_changed("yaw", val),
            )
            self._update_profile_actions()
            self._update_profiles_table_interactivity()
        finally:
            self._loading = was_loading

        self._publish_section_selection()

    def _publish_section_selection(self) -> None:
        component_id = self._component.get("id")
        if isinstance(component_id, str) and 0 <= self._profile_index < len(self._profiles()):
            self._api.set_section_selection((component_id, 0, self._profile_index))
        else:
            self._api.set_section_selection(None)

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

            self._populate_profiles()
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
        geom = self._cs_geom(cs)

        was_loading = self._loading
        self._loading = True
        try:
            self._set_property_value(self.cs_properties_table, "tag", str(geom.get("tag") or cs.get("name") or cs.get("id") or ""))
            self._set_property_combo(
                self.cs_properties_table,
                "type",
                str(geom.get("type") or "aileron"),
                self.CONTROL_SURFACE_TYPES,
                lambda val: self._update_cs_choice("type", val),
            )
            self._set_property_spinbox(
                self.cs_properties_table,
                "span_start",
                float(geom.get("span_start", 0.0)),
                min_val=0.0,
                step=5.0,
                decimals=1,
                suffix="mm",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("span_start", val),
            )
            self._set_property_spinbox(
                self.cs_properties_table,
                "span_end",
                float(geom.get("span_end", 0.0)),
                min_val=0.0,
                step=5.0,
                decimals=1,
                suffix="mm",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("span_end", val),
            )
            self._set_property_spinbox(
                self.cs_properties_table,
                "chord",
                float(geom.get("chord", 0.0)),
                min_val=1.0,
                step=2.0,
                decimals=1,
                suffix="mm",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("chord", val),
            )
            self._set_property_spinbox(
                self.cs_properties_table,
                "hinge_sweep",
                float(geom.get("hinge_sweep", 0.0)),
                min_val=-80.0,
                max_val=80.0,
                step=1.0,
                decimals=1,
                suffix="°",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("hinge_sweep", val),
            )
            self._set_property_spinbox(
                self.cs_properties_table,
                "deflection",
                float(geom.get("deflection", 0.0)),
                min_val=-90.0,
                max_val=90.0,
                step=1.0,
                decimals=1,
                suffix="°",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("deflection", val),
            )
            self._update_cs_actions()
        finally:
            self._loading = was_loading

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
        if self._driver_mode != "manual" and column in (2, 3):
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

        self._edit_component("Edit wing profile station", change)
        if row == self._profile_index:
            self._load_profile(row)
        self._refresh_planform_table()

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
        self._populate_profiles()
        self.profiles_table.selectRow(insert_at)
        self._load_profile(insert_at)
        self._refresh_planform_table()

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
        self._populate_profiles()
        self.profiles_table.selectRow(insert_at)
        self._load_profile(insert_at)
        self._refresh_planform_table()

    def _move_profile_up(self) -> None:
        idx = self._profile_index
        if idx <= 0:
            return
        profiles = self._profiles()
        target = idx - 1

        def change() -> None:
            profiles.insert(target, profiles.pop(idx))

        self._edit_component("Move wing profile up", change)
        self._populate_profiles()
        self.profiles_table.selectRow(target)
        self._load_profile(target)
        self._refresh_planform_table()

    def _move_profile_down(self) -> None:
        idx = self._profile_index
        profiles = self._profiles()
        if idx < 0 or idx >= len(profiles) - 1:
            return
        target = idx + 1

        def change() -> None:
            profiles.insert(target, profiles.pop(idx))

        self._edit_component("Move wing profile down", change)
        self._populate_profiles()
        self.profiles_table.selectRow(target)
        self._load_profile(target)
        self._refresh_planform_table()

    def _delete_profile(self) -> None:
        idx = self._profile_index
        profiles = self._profiles()
        if idx < 0 or len(profiles) <= 2:
            return

        def change() -> None:
            profiles.pop(idx)

        self._edit_component("Delete wing profile", change)
        self._populate_profiles()
        new_idx = min(idx, len(profiles) - 1)
        self.profiles_table.selectRow(new_idx)
        self._load_profile(new_idx)
        self._refresh_planform_table()

    def _update_profile_actions(self) -> None:
        profiles = self._profiles()
        count = len(profiles)
        idx = self._profile_index
        has_sel = 0 <= idx < count
        is_manual = self._driver_mode == "manual"
        self.add_profile_button.setEnabled(is_manual)
        self.duplicate_profile_button.setEnabled(has_sel and is_manual)
        self.move_profile_up_button.setEnabled(has_sel and idx > 0 and is_manual)
        self.move_profile_down_button.setEnabled(has_sel and idx < count - 1 and is_manual)
        self.delete_profile_button.setEnabled(has_sel and count > 2 and is_manual)
        self.choose_airfoil_btn.setEnabled(has_sel)

    # -------------------------------------------------------------------------
    # Profile Properties Mutation
    # -------------------------------------------------------------------------

    def _on_profile_prop_spinbox_changed(self, key: str, value: float) -> None:
        if self._loading or self._profile_index < 0:
            return
        if self._driver_mode != "manual" and key in ("chord", "span_y", "offset_x"):
            return
        profiles = self._profiles()
        if not (0 <= self._profile_index < len(profiles)):
            return
        prof = profiles[self._profile_index]
        pos = prof.get("position") if isinstance(prof.get("position"), dict) else {}
        if not isinstance(prof.get("position"), dict):
            prof["position"] = pos
        rot = prof.get("rotation") if isinstance(prof.get("rotation"), dict) else {}
        if not isinstance(prof.get("rotation"), dict):
            prof["rotation"] = rot

        def change() -> None:
            if key == "chord":
                prof["chord"] = max(float(value), 1.0)
            elif key == "twist":
                rot["y"] = float(value)
            elif key == "span_y":
                pos["y"] = float(value)
            elif key == "offset_x":
                pos["x"] = float(value)
            elif key == "height_z":
                pos["z"] = float(value)
            elif key == "dihedral":
                rot["x"] = float(value)
            elif key == "yaw":
                rot["z"] = float(value)

        self._edit_component(f"Edit profile {key}", change)
        self._refresh_profile_table_row(self._profile_index)
        self._refresh_planform_table()

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

        self._edit_component(f"Edit profile {key}", change)
        self._refresh_profile_table_row(self._profile_index)
        self._refresh_planform_table()

    def _refresh_profile_table_row(self, row: int) -> None:
        profiles = self._profiles()
        if not (0 <= row < len(profiles)):
            return
        prof = profiles[row]
        pos = prof.get("position", {}) if isinstance(prof.get("position"), dict) else {}
        airfoil = self._format_airfoil_label(prof.get("airfoil"))

        was_loading = self._loading
        self._loading = True
        try:
            self.profiles_table.item(row, 1).setText(airfoil)
            self.profiles_table.item(row, 2).setText(f"{float(pos.get('y', 0.0)):.1f}")
            self.profiles_table.item(row, 3).setText(f"{float(prof.get('chord', 0.0)):.1f}")
            self._update_profiles_table_interactivity()
        finally:
            self._loading = was_loading

    # -------------------------------------------------------------------------
    # End Caps (Tip Treatment) Actions & Mutation
    # -------------------------------------------------------------------------

    def _load_tip_caps(self) -> None:
        geom = self._geometry()
        tip_treatment = geom.get("tip_treatment")
        tip_treatment = tip_treatment if isinstance(tip_treatment, dict) else {}
        tip_type = str(tip_treatment.get("type", "flat")).lower()
        tip_length = float(tip_treatment.get("length", 20.0))
        tip_offset_x = float(tip_treatment.get("offset_x", 0.0))
        winglet_height = float(tip_treatment.get("winglet_height", 100.0))
        cant_angle = float(tip_treatment.get("cant_angle", 75.0))
        winglet_sweep = float(tip_treatment.get("winglet_sweep", 30.0))
        toe_angle = float(tip_treatment.get("toe_angle", 0.0))
        root_chord_scale = float(tip_treatment.get("root_chord_scale", 1.0))
        tip_chord_scale = float(tip_treatment.get("tip_chord_scale", 0.5))

        self._set_property_combo(
            self.tip_caps_table,
            "tip_type",
            tip_type,
            [
                ("flat", "Flat"),
                ("round", "Round (Dome)"),
                ("sharp", "Sharp (Bevel)"),
                ("winglet", "Winglet"),
            ],
            self._on_tip_cap_type_changed,
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "tip_length",
            tip_length,
            min_val=0.0,
            step=2.0,
            decimals=1,
            suffix="mm",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("tip_length", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "tip_offset_x",
            tip_offset_x,
            step=2.0,
            decimals=1,
            suffix="mm",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("tip_offset_x", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "winglet_height",
            winglet_height,
            min_val=0.0,
            max_val=5000.0,
            step=10.0,
            decimals=1,
            suffix="mm",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("winglet_height", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "cant_angle",
            cant_angle,
            min_val=0.0,
            max_val=90.0,
            step=5.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("cant_angle", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "winglet_sweep",
            winglet_sweep,
            min_val=-80.0,
            max_val=80.0,
            step=5.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("winglet_sweep", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "toe_angle",
            toe_angle,
            min_val=-30.0,
            max_val=30.0,
            step=0.5,
            decimals=2,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("toe_angle", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "root_chord_scale",
            root_chord_scale,
            min_val=0.1,
            max_val=3.0,
            step=0.05,
            decimals=3,
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("root_chord_scale", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "tip_chord_scale",
            tip_chord_scale,
            min_val=0.0,
            max_val=3.0,
            step=0.05,
            decimals=3,
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("tip_chord_scale", val),
        )
        self._update_tip_caps_interactivity(tip_type)

    def _update_tip_caps_interactivity(self, tip_type: str) -> None:
        is_cap = tip_type in ("round", "sharp")
        is_winglet = tip_type == "winglet"
        cap_keys = {"tip_length", "tip_offset_x"}
        winglet_keys = {"winglet_height", "cant_angle", "winglet_sweep", "toe_angle", "root_chord_scale", "tip_chord_scale"}
        for row in range(self.tip_caps_table.rowCount()):
            key = self._property_key(self.tip_caps_table, row)
            w = self.tip_caps_table.cellWidget(row, 1)
            lbl_item = self.tip_caps_table.item(row, 0)
            if key in cap_keys:
                active = is_cap
            elif key in winglet_keys:
                active = is_winglet
            else:
                continue
            if w is not None:
                w.setEnabled(active)
            if lbl_item:
                lbl_item.setForeground(QBrush(QColor("#ffffff" if active else "#999999")))

    def _on_tip_cap_type_changed(self, new_type: str) -> None:
        if self._loading:
            return

        def change() -> None:
            geom = self._geometry()
            tt = geom.setdefault("tip_treatment", {})
            tt["type"] = new_type

        self._edit_component("Change wingtip cap type", change)
        self._update_tip_caps_interactivity(new_type)

    def _on_tip_cap_spinbox_changed(self, key: str, value: float) -> None:
        if self._loading:
            return

        def change() -> None:
            geom = self._geometry()
            tt = geom.setdefault("tip_treatment", {})
            if key == "tip_length":
                tt["length"] = max(float(value), 0.0)
            elif key == "tip_offset_x":
                tt["offset_x"] = float(value)
            elif key == "winglet_height":
                tt["winglet_height"] = max(float(value), 0.0)
            elif key == "cant_angle":
                tt["cant_angle"] = min(max(float(value), 0.0), 90.0)
            elif key == "winglet_sweep":
                tt["winglet_sweep"] = float(value)
            elif key == "toe_angle":
                tt["toe_angle"] = float(value)
            elif key == "root_chord_scale":
                tt["root_chord_scale"] = max(float(value), 0.1)
            elif key == "tip_chord_scale":
                tt["tip_chord_scale"] = max(float(value), 0.0)

        self._edit_component(f"Update wingtip {key}", change)

    def _on_tip_cap_cell_edited(self, row: int, column: int) -> None:
        pass

    # -------------------------------------------------------------------------
    # Airfoil Shaping (TE Blunting, Thickness/Camber Scale, Section Alignment)
    # -------------------------------------------------------------------------

    def _load_airfoil_shaping(self) -> None:
        geom = self._geometry()
        shaping = geom.get("airfoil_shaping")
        shaping = shaping if isinstance(shaping, dict) else {}
        te_pct = float(shaping.get("te_thickness", 0.0)) * 100.0  # stored as fraction, shown as %
        thickness_scale = float(shaping.get("thickness_scale", 1.0))
        camber_scale = float(shaping.get("camber_scale", 1.0))
        section_align = str(geom.get("section_align", "xz")).lower()

        self._set_property_combo(
            self.airfoil_shaping_table,
            "section_align",
            section_align,
            [
                ("xz", "XZ Plane (default)"),
                ("normal", "Normal to Span (dihedral-correct)"),
            ],
            self._on_section_align_changed,
        )
        self._set_property_spinbox(
            self.airfoil_shaping_table,
            "te_thickness",
            te_pct,
            min_val=0.0,
            max_val=5.0,
            step=0.05,
            decimals=3,
            suffix="%",
            on_changed=lambda val: self._on_airfoil_shaping_spinbox_changed("te_thickness", val),
        )
        self._set_property_spinbox(
            self.airfoil_shaping_table,
            "thickness_scale",
            thickness_scale,
            min_val=0.1,
            max_val=5.0,
            step=0.05,
            decimals=3,
            on_changed=lambda val: self._on_airfoil_shaping_spinbox_changed("thickness_scale", val),
        )
        self._set_property_spinbox(
            self.airfoil_shaping_table,
            "camber_scale",
            camber_scale,
            min_val=0.0,
            max_val=5.0,
            step=0.05,
            decimals=3,
            on_changed=lambda val: self._on_airfoil_shaping_spinbox_changed("camber_scale", val),
        )

    def _on_section_align_changed(self, value: str) -> None:
        if self._loading:
            return

        def change() -> None:
            self._geometry()["section_align"] = str(value)

        self._edit_component("Change section alignment", change)

    def _on_airfoil_shaping_spinbox_changed(self, key: str, value: float) -> None:
        if self._loading:
            return

        def change() -> None:
            geom = self._geometry()
            sh = geom.setdefault("airfoil_shaping", {})
            if key == "te_thickness":
                sh["te_thickness"] = max(float(value) / 100.0, 0.0)  # convert % -> fraction
            elif key == "thickness_scale":
                sh["thickness_scale"] = max(float(value), 0.1)
            elif key == "camber_scale":
                sh["camber_scale"] = max(float(value), 0.0)

        self._edit_component(f"Update airfoil shaping ({key})", change)

    def _on_cs_prop_spinbox_changed(self, key: str, value: float) -> None:
        if self._loading or self._control_surface_index < 0:
            return
        cs_list = self._control_surfaces()
        if not (0 <= self._control_surface_index < len(cs_list)):
            return
        cs = cs_list[self._control_surface_index]
        geom = self._cs_geom(cs)

        def change() -> None:
            if key == "span_start":
                geom["span_start"] = float(value)
            elif key == "span_end":
                geom["span_end"] = float(value)
            elif key == "chord":
                geom["chord"] = max(float(value), 1.0)
            elif key == "hinge_sweep":
                geom["hinge_sweep"] = float(value)
            elif key == "deflection":
                geom["deflection"] = float(value)

        self._edit_control_surface_item(cs, f"Edit control surface {key}", change)
        self._refresh_cs_table_row(self._control_surface_index)

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
        geom = self._cs_geom(cs)

        def change() -> None:
            if column == 0:
                geom["tag"] = text_val
                if "name" in cs:
                    cs["name"] = text_val
            elif column == 1:
                geom["type"] = text_val.lower()

        self._edit_control_surface_item(cs, "Edit control surface", change)
        if row == self._control_surface_index:
            self._load_control_surface(row)

    def _add_control_surface(self) -> None:
        cs_list = self._control_surfaces()
        wing_id = str(self._component.get("id") or "wing")
        new_tag = f"control_{len(cs_list) + 1}"
        new_id = f"{wing_id}-{new_tag}"
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)

        profiles = self._profiles()
        span_values = [float(p.get("position", {}).get("y", 0.0)) for p in profiles if isinstance(p.get("position"), dict)]
        root_chord = float(profiles[0].get("chord", 150.0)) if profiles else 150.0
        semi_span = max(span_values) - min(span_values) if len(span_values) >= 2 else 400.0
        def_start = round(max(semi_span * 0.4, 20.0), 1)
        def_end = round(max(semi_span * 0.85, def_start + 50.0), 1)
        def_chord = round(max(root_chord * 0.25, 10.0), 1)

        if project and isinstance(project.data.get("components"), list):
            new_comp = {
                "kind": "component",
                "id": new_id,
                "name": new_tag.replace("_", " ").title(),
                "type": "org.setuav.core:control-surface",
                "parent": wing_id,
                "parameters": {
                    "mass": 15.0,
                    "geometry": {
                        "tag": new_tag,
                        "type": "aileron",
                        "span_start": def_start,
                        "span_end": def_end,
                        "chord": def_chord,
                        "hinge_sweep": 0.0,
                        "deflection": 0.0,
                    },
                },
            }

            def change() -> None:
                project.data["components"].append(new_comp)

            if hasattr(self._api, "edit_project"):
                self._api.edit_project("Add control surface", change)
            else:
                change()
        else:
            new_cs = {
                "tag": new_tag,
                "type": "aileron",
                "span_start": def_start,
                "span_end": def_end,
                "chord": def_chord,
                "hinge_sweep": 0.0,
                "deflection": 0.0,
            }

            def change() -> None:
                self._geometry().setdefault("control_surfaces", []).append(new_cs)

            self._edit_component("Add control surface", change)

        self._populate_control_surfaces()
        insert_at = len(self._control_surfaces()) - 1
        if insert_at >= 0:
            self.control_surfaces_table.selectRow(insert_at)
            self._load_control_surface(insert_at)

    def _duplicate_control_surface(self) -> None:
        idx = self._control_surface_index
        cs_list = self._control_surfaces()
        if not (0 <= idx < len(cs_list)):
            return
        target = deepcopy(cs_list[idx])
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)

        if project and isinstance(project.data.get("components"), list) and "parameters" in target:
            base_id = str(target.get("id") or "cs")
            target["id"] = f"{base_id}-copy"
            target["name"] = f"{target.get('name', base_id)} (Copy)"
            geom = target.setdefault("parameters", {}).setdefault("geometry", {})
            geom["tag"] = f"{geom.get('tag', base_id)}_copy"

            def change() -> None:
                project.data["components"].append(target)

            if hasattr(self._api, "edit_project"):
                self._api.edit_project("Duplicate control surface", change)
            else:
                change()
        else:
            target["tag"] = f"{target.get('tag', 'cs')}_copy"

            def change() -> None:
                self._geometry().setdefault("control_surfaces", []).insert(idx + 1, target)

            self._edit_component("Duplicate control surface", change)

        self._populate_control_surfaces()
        insert_at = len(self._control_surfaces()) - 1
        if insert_at >= 0:
            self.control_surfaces_table.selectRow(insert_at)
            self._load_control_surface(insert_at)

    def _move_cs_up(self) -> None:
        idx = self._control_surface_index
        if idx <= 0:
            return
        cs_list = self._control_surfaces()
        target = idx - 1
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)

        def change() -> None:
            if project and isinstance(project.data.get("components"), list) and cs_list[idx] in project.data["components"]:
                comps = project.data["components"]
                i1 = comps.index(cs_list[idx])
                i2 = comps.index(cs_list[target])
                comps[i1], comps[i2] = comps[i2], comps[i1]
            elif "control_surfaces" in self._geometry():
                cs_arr = self._geometry()["control_surfaces"]
                cs_arr.insert(target, cs_arr.pop(idx))

        if project and isinstance(project.data.get("components"), list) and cs_list[idx] in project.data["components"] and hasattr(self._api, "edit_project"):
            self._api.edit_project("Move control surface up", change)
        else:
            self._edit_component("Move control surface up", change)

        self._populate_control_surfaces()
        self.control_surfaces_table.selectRow(target)
        self._load_control_surface(target)

    def _move_cs_down(self) -> None:
        idx = self._control_surface_index
        cs_list = self._control_surfaces()
        if idx < 0 or idx >= len(cs_list) - 1:
            return
        target = idx + 1
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)

        def change() -> None:
            if project and isinstance(project.data.get("components"), list) and cs_list[idx] in project.data["components"]:
                comps = project.data["components"]
                i1 = comps.index(cs_list[idx])
                i2 = comps.index(cs_list[target])
                comps[i1], comps[i2] = comps[i2], comps[i1]
            elif "control_surfaces" in self._geometry():
                cs_arr = self._geometry()["control_surfaces"]
                cs_arr.insert(target, cs_arr.pop(idx))

        if project and isinstance(project.data.get("components"), list) and cs_list[idx] in project.data["components"] and hasattr(self._api, "edit_project"):
            self._api.edit_project("Move control surface down", change)
        else:
            self._edit_component("Move control surface down", change)

        self._populate_control_surfaces()
        self.control_surfaces_table.selectRow(target)
        self._load_control_surface(target)

    def _delete_control_surface(self) -> None:
        idx = self._control_surface_index
        cs_list = self._control_surfaces()
        if not (0 <= idx < len(cs_list)):
            return

        target_item = cs_list[idx]
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)

        def change() -> None:
            if project and isinstance(project.data.get("components"), list) and target_item in project.data["components"]:
                project.data["components"].remove(target_item)
            elif "control_surfaces" in self._geometry():
                cs_arr = self._geometry()["control_surfaces"]
                if target_item in cs_arr:
                    cs_arr.remove(target_item)
                elif 0 <= idx < len(cs_arr):
                    cs_arr.pop(idx)

        if project and isinstance(project.data.get("components"), list) and target_item in project.data["components"] and hasattr(self._api, "edit_project"):
            self._api.edit_project("Delete control surface", change)
        else:
            self._edit_component("Delete control surface", change)

        self._populate_control_surfaces()
        new_idx = min(idx, len(self._control_surfaces()) - 1)
        if new_idx >= 0:
            self.control_surfaces_table.selectRow(new_idx)
            self._load_control_surface(new_idx)
        else:
            self._load_control_surface(-1)

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
        geom = self._cs_geom(cs)
        s_start = float(geom.get("span_start", 0.0))
        s_end = float(geom.get("span_end", 0.0))
        was_loading = self._loading
        self._loading = True
        try:
            if self.control_surfaces_table.item(row, 0):
                tag_label = str(geom.get("tag") or cs.get("name") or cs.get("id") or f"CS_{row + 1}")
                self.control_surfaces_table.item(row, 0).setText(tag_label)
            if self.control_surfaces_table.item(row, 1):
                self.control_surfaces_table.item(row, 1).setText(str(geom.get("type") or "aileron").capitalize())
            if self.control_surfaces_table.item(row, 2):
                self.control_surfaces_table.item(row, 2).setText(f"{s_start:.1f} - {s_end:.1f}")
        finally:
            self._loading = was_loading

    def _update_cs_property(self, row: int, column: int) -> None:
        if self._loading or column != 1 or self._control_surface_index < 0:
            return
        key = self._property_key(self.cs_properties_table, row)
        val_str = self._property_text(self.cs_properties_table, row)
        cs_list = self._control_surfaces()
        if not (0 <= self._control_surface_index < len(cs_list)):
            return
        cs = cs_list[self._control_surface_index]
        geom = self._cs_geom(cs)

        def change() -> None:
            if key == "tag":
                geom["tag"] = val_str.strip()
                if "name" in cs:
                    cs["name"] = val_str.strip()
            elif key == "span_start":
                geom["span_start"] = self._parse_number(val_str) or 0.0
            elif key == "span_end":
                geom["span_end"] = self._parse_number(val_str) or 0.0
            elif key == "chord":
                geom["chord"] = max(self._parse_number(val_str) or 10.0, 1.0)
            elif key == "hinge_sweep":
                geom["hinge_sweep"] = self._parse_number(val_str) or 0.0
            elif key == "deflection":
                geom["deflection"] = self._parse_number(val_str) or 0.0

        self._edit_control_surface_item(cs, f"Edit control surface {key}", change)
        self._refresh_cs_table_row(self._control_surface_index)

    def _update_cs_choice(self, key: str, value: str) -> None:
        if self._loading or self._control_surface_index < 0:
            return
        cs_list = self._control_surfaces()
        if not (0 <= self._control_surface_index < len(cs_list)):
            return
        cs = cs_list[self._control_surface_index]
        geom = self._cs_geom(cs)

        def change() -> None:
            geom[key] = value

        self._edit_control_surface_item(cs, f"Edit control surface {key}", change)
        self._refresh_cs_table_row(self._control_surface_index)

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
            elif key == "mass":
                mass_val = self._parse_number(val_str) or 0.0
                self._parameters()["mass"] = max(mass_val, 0.0)
                self._component["mass"] = max(mass_val, 0.0)

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
                    and comp.get("parent") == wing_id
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

