"""End caps (tip treatment) handling for the Lifting Surface Editor."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from .lifting_surface_geometry import compute_winglet_projected_dimensions


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
            ("match_wing_tangent", "Match Wing Tangent"),
            ("winglet_height", "Winglet Arc Span (mm)"),
            ("winglet_projected_metrics", "Height / Span"),
            ("cant_root", "Cant Root (°)"),
            ("cant_tip", "Cant Tip (°)"),
            ("blend_radius", "Blend Radius (mm)"),
            ("le_sweep_root", "LE Sweep Root (°)"),
            ("le_sweep_tip", "LE Sweep Tip (°)"),
            ("le_curvature", "LE Curvature (mm)"),
            ("te_sweep_root", "TE Sweep Root (°)"),
            ("te_sweep_tip", "TE Sweep Tip (°)"),
            ("te_curvature", "TE Curvature (mm)"),
            ("toe_root", "Toe Root (°)"),
            ("toe_tip", "Toe Tip (°)"),
            ("root_chord_scale", "Root Chord Scale"),
            ("tip_chord_scale", "Tip Chord Scale"),
            ("tip_thickness_scale", "Tip Thickness Scale"),
            ("taper_curve", "Taper Exponent"),
        ])
        self.tip_caps_table.cellChanged.connect(self._on_tip_cap_cell_edited)

        # 4-cell live metric widget: | Height | height_value | Span | span_value |
        metrics_row = -1
        for r in range(self.tip_caps_table.rowCount()):
            if self._property_key(self.tip_caps_table, r) == "winglet_projected_metrics":
                metrics_row = r
                break

        if metrics_row >= 0:
            self.tip_caps_table.setSpan(metrics_row, 0, 1, 2)
            self.winglet_metrics_widget = QFrame()
            self.winglet_metrics_widget.setStyleSheet(
                "QFrame { background: #161616; border: 1px solid #2d2d2d; border-radius: 3px; }"
                "QLabel { font-size: 11px; padding: 2px 4px; }"
            )
            m_layout = QHBoxLayout(self.winglet_metrics_widget)
            m_layout.setContentsMargins(0, 0, 0, 0)
            m_layout.setSpacing(0)

            self.lbl_metric_h_tag = QLabel("Height")
            self.lbl_metric_h_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_metric_h_tag.setStyleSheet("background: #222222; color: #888888; font-weight: bold; border-right: 1px solid #2d2d2d;")

            self.metric_height_val = QLabel("0.0 mm")
            self.metric_height_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.metric_height_val.setStyleSheet("background: #181818; color: #ffffff; font-weight: bold; border-right: 1px solid #2d2d2d;")

            self.lbl_metric_span_tag = QLabel("Span")
            self.lbl_metric_span_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_metric_span_tag.setStyleSheet("background: #222222; color: #888888; font-weight: bold; border-right: 1px solid #2d2d2d;")

            self.metric_span_val = QLabel("0.0 mm")
            self.metric_span_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.metric_span_val.setStyleSheet("background: #181818; color: #ffffff; font-weight: bold;")

            m_layout.addWidget(self.lbl_metric_h_tag, 1)
            m_layout.addWidget(self.metric_height_val, 1)
            m_layout.addWidget(self.lbl_metric_span_tag, 1)
            m_layout.addWidget(self.metric_span_val, 1)

            self.tip_caps_table.setCellWidget(metrics_row, 0, self.winglet_metrics_widget)

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
        match_tangent = bool(tip_treatment.get("match_wing_tangent", True))
        winglet_height = float(tip_treatment.get("winglet_height", 130.0))

        # Cant
        cant_tip_default = float(tip_treatment.get("cant_angle", 80.0))
        cant_root = float(tip_treatment.get("cant_root", 0.0))
        cant_tip = float(tip_treatment.get("cant_tip", cant_tip_default))
        blend_radius = float(tip_treatment.get("blend_radius", 45.0 if "blend_radius" in tip_treatment else 0.0))

        # LE Sweep & Curvature
        sweep_default = float(tip_treatment.get("winglet_sweep", 20.0))
        le_sweep_root = float(tip_treatment.get("le_sweep_root", tip_treatment.get("sweep_root", sweep_default)))
        le_sweep_tip = float(tip_treatment.get("le_sweep_tip", tip_treatment.get("sweep_tip", 48.0)))
        le_curvature = float(tip_treatment.get("le_curvature", tip_treatment.get("scimitar_offset", 0.0)))

        # TE Sweep & Curvature
        te_sweep_root = float(tip_treatment.get("te_sweep_root", 15.0))
        te_sweep_tip = float(tip_treatment.get("te_sweep_tip", 25.0))
        te_curvature = float(tip_treatment.get("te_curvature", 0.0))

        # Toe
        toe_default = float(tip_treatment.get("toe_angle", 0.0))
        toe_root = float(tip_treatment.get("toe_root", toe_default))
        toe_tip = float(tip_treatment.get("toe_tip", -1.5 if "toe_tip" not in tip_treatment else toe_default))

        # Chords, Thickness & Taper
        root_chord_scale = float(tip_treatment.get("root_chord_scale", 1.0))
        tip_chord_scale = float(tip_treatment.get("tip_chord_scale", 0.45))
        tip_thickness_scale = float(tip_treatment.get("tip_thickness_scale", 0.7))
        taper_curve = float(tip_treatment.get("taper_curve", 1.0))

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
        self._set_property_combo(
            self.tip_caps_table,
            "match_wing_tangent",
            "true" if match_tangent else "false",
            [
                ("true", "Yes (Continuous Tangent)"),
                ("false", "No (Manual Angle)"),
            ],
            self._on_match_wing_tangent_changed,
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
            "cant_root",
            cant_root,
            min_val=-90.0,
            max_val=90.0,
            step=5.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("cant_root", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "cant_tip",
            cant_tip,
            min_val=-90.0,
            max_val=90.0,
            step=5.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("cant_tip", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "blend_radius",
            blend_radius,
            min_val=0.0,
            max_val=1000.0,
            step=5.0,
            decimals=1,
            suffix="mm",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("blend_radius", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "le_sweep_root",
            le_sweep_root,
            min_val=-80.0,
            max_val=80.0,
            step=5.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("le_sweep_root", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "le_sweep_tip",
            le_sweep_tip,
            min_val=-80.0,
            max_val=80.0,
            step=5.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("le_sweep_tip", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "le_curvature",
            le_curvature,
            min_val=-500.0,
            max_val=500.0,
            step=2.0,
            decimals=1,
            suffix="mm",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("le_curvature", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "te_sweep_root",
            te_sweep_root,
            min_val=-80.0,
            max_val=80.0,
            step=5.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("te_sweep_root", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "te_sweep_tip",
            te_sweep_tip,
            min_val=-80.0,
            max_val=80.0,
            step=5.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("te_sweep_tip", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "te_curvature",
            te_curvature,
            min_val=-500.0,
            max_val=500.0,
            step=2.0,
            decimals=1,
            suffix="mm",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("te_curvature", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "toe_root",
            toe_root,
            min_val=-30.0,
            max_val=30.0,
            step=0.5,
            decimals=2,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("toe_root", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "toe_tip",
            toe_tip,
            min_val=-30.0,
            max_val=30.0,
            step=0.5,
            decimals=2,
            suffix="°",
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("toe_tip", val),
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
        self._set_property_spinbox(
            self.tip_caps_table,
            "tip_thickness_scale",
            tip_thickness_scale,
            min_val=0.1,
            max_val=3.0,
            step=0.05,
            decimals=2,
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("tip_thickness_scale", val),
        )
        self._set_property_spinbox(
            self.tip_caps_table,
            "taper_curve",
            taper_curve,
            min_val=0.1,
            max_val=5.0,
            step=0.1,
            decimals=2,
            on_changed=lambda val: self._on_tip_cap_spinbox_changed("taper_curve", val),
        )
        self._refresh_winglet_projected_metrics()
        self._update_tip_caps_interactivity(tip_type)

    def _refresh_winglet_projected_metrics(self) -> None:
        geom = self._geometry()
        tip_treatment = geom.get("tip_treatment")
        tt = tip_treatment if isinstance(tip_treatment, dict) else {}
        w_h = float(tt.get("winglet_height", 130.0))
        c_tip = float(tt.get("cant_tip", tt.get("cant_angle", 80.0)))
        c_root = float(tt.get("cant_root", 0.0))
        blend_r = float(tt.get("blend_radius", 45.0 if "blend_radius" in tt else 0.0))

        dz, dy = compute_winglet_projected_dimensions(w_h, c_root, c_tip, blend_r)
        if hasattr(self, "metric_height_val") and hasattr(self, "metric_span_val"):
            self.metric_height_val.setText(f"{dz:.1f} mm")
            self.metric_span_val.setText(f"{dy:.1f} mm")
        self._set_property_value(
            self.tip_caps_table,
            "winglet_projected_metrics",
            f"Height: {dz:.1f} mm  |  Span: {dy:.1f} mm",
            editable=False,
        )

    def _update_tip_caps_interactivity(self, tip_type: str) -> None:
        is_cap = tip_type in ("round", "sharp")
        is_winglet = tip_type == "winglet"
        cap_keys = {"tip_length", "tip_offset_x"}
        winglet_keys = {
            "match_wing_tangent",
            "winglet_height",
            "winglet_projected_metrics",
            "cant_root",
            "cant_tip",
            "blend_radius",
            "le_sweep_root",
            "le_sweep_tip",
            "le_curvature",
            "te_sweep_root",
            "te_sweep_tip",
            "te_curvature",
            "toe_root",
            "toe_tip",
            "root_chord_scale",
            "tip_chord_scale",
            "tip_thickness_scale",
            "taper_curve",
        }
        for row in range(self.tip_caps_table.rowCount()):
            key = self._property_key(self.tip_caps_table, row)
            w = self.tip_caps_table.cellWidget(row, 1) or self.tip_caps_table.cellWidget(row, 0)
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
        if new_type == "winglet":
            self._refresh_winglet_projected_metrics()

    def _on_match_wing_tangent_changed(self, val: str) -> None:
        if self._loading:
            return

        def change() -> None:
            geom = self._geometry()
            tt = geom.setdefault("tip_treatment", {})
            tt["match_wing_tangent"] = (val == "true")

        self._edit_component("Update winglet tangent matching", change)

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
            elif key == "cant_root":
                tt["cant_root"] = min(max(float(value), -90.0), 90.0)
            elif key == "cant_tip":
                tt["cant_tip"] = min(max(float(value), -90.0), 90.0)
                tt["cant_angle"] = tt["cant_tip"]
            elif key == "blend_radius":
                tt["blend_radius"] = max(float(value), 0.0)
            elif key == "le_sweep_root":
                tt["le_sweep_root"] = float(value)
                tt["sweep_root"] = float(value)
                tt["winglet_sweep"] = float(value)
            elif key == "le_sweep_tip":
                tt["le_sweep_tip"] = float(value)
                tt["sweep_tip"] = float(value)
            elif key == "le_curvature":
                tt["le_curvature"] = float(value)
                tt["scimitar_offset"] = float(value)
            elif key == "te_sweep_root":
                tt["te_sweep_root"] = float(value)
            elif key == "te_sweep_tip":
                tt["te_sweep_tip"] = float(value)
            elif key == "te_curvature":
                tt["te_curvature"] = float(value)
            elif key == "toe_root":
                tt["toe_root"] = float(value)
                tt["toe_angle"] = float(value)
            elif key == "toe_tip":
                tt["toe_tip"] = float(value)
            elif key == "root_chord_scale":
                tt["root_chord_scale"] = max(float(value), 0.1)
            elif key == "tip_chord_scale":
                tt["tip_chord_scale"] = max(float(value), 0.0)
            elif key == "tip_thickness_scale":
                tt["tip_thickness_scale"] = max(float(value), 0.05)
            elif key == "taper_curve":
                tt["taper_curve"] = max(float(value), 0.1)

        self._edit_component(f"Update wingtip {key}", change)
        if key in ("winglet_height", "cant_root", "cant_tip", "blend_radius"):
            self._refresh_winglet_projected_metrics()

    def _on_tip_cap_cell_edited(self, row: int, column: int) -> None:
        pass