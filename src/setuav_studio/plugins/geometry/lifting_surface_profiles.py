"""Profile stations and airfoil shaping handling for the Lifting Surface Editor."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from setuav_studio.icons import get_icon
from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog


class ProfilesMixin:
    """Wing profile stations, section properties, and airfoil shaping handling."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

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