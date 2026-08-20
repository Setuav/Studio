"""End caps (tip treatment) handling for the Lifting Surface Editor."""

from __future__ import annotations

from PySide6.QtGui import QBrush, QColor


class TipCapsMixin:
    """End caps / tip treatment configuration handling."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

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