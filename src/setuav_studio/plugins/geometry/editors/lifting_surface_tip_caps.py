"""End caps (tip treatment) handling for the Lifting Surface Editor."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTableWidgetItem

from ..engine.lifting_surface_geometry import compute_winglet_projected_dimensions


class TipCapsMixin:
    """End caps / tip treatment configuration handling."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_tip_caps_section(self) -> None:
        """End Caps configuration section."""
        layout = self._create_section("End Caps", "fa6s.shapes")

        self.tip_caps_table = self._property_table([("tip_type", "Tip Cap Type")])
        self.tip_caps_table.cellChanged.connect(self._on_tip_cap_cell_edited)
        layout.addWidget(self.tip_caps_table)

    # -------------------------------------------------------------------------
    # End Caps Actions & Mutation
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

        # Determine table rows based on tip_type
        if tip_type == "flat":
            definitions = [("tip_type", "Tip Cap Type")]
        elif tip_type in ("round", "sharp"):
            definitions = [
                ("tip_type", "Tip Cap Type"),
                ("tip_length", "Tip Length (mm)"),
                ("tip_offset_x", "Tip Sweep Offset (mm)"),
            ]
        else:  # winglet
            definitions = [
                ("tip_type", "Tip Cap Type"),
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
            ]

        # Re-initialize property table rows
        was_loading = self._loading
        self._loading = True
        try:
            self.tip_caps_table.setRowCount(len(definitions))
            for r, (key, label) in enumerate(definitions):
                item = QTableWidgetItem(label)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.tip_caps_table.setItem(r, 0, item)

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

            if tip_type in ("round", "sharp"):
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

            if tip_type == "winglet":
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
                    min_val=-85.0,
                    max_val=85.0,
                    step=5.0,
                    decimals=1,
                    suffix="°",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("le_sweep_root", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "le_sweep_tip",
                    le_sweep_tip,
                    min_val=-85.0,
                    max_val=85.0,
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
                    step=5.0,
                    decimals=1,
                    suffix="mm",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("le_curvature", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "te_sweep_root",
                    te_sweep_root,
                    min_val=-85.0,
                    max_val=85.0,
                    step=5.0,
                    decimals=1,
                    suffix="°",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("te_sweep_root", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "te_sweep_tip",
                    te_sweep_tip,
                    min_val=-85.0,
                    max_val=85.0,
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
                    step=5.0,
                    decimals=1,
                    suffix="mm",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("te_curvature", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "toe_root",
                    toe_root,
                    min_val=-45.0,
                    max_val=45.0,
                    step=0.5,
                    decimals=1,
                    suffix="°",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("toe_root", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "toe_tip",
                    toe_tip,
                    min_val=-45.0,
                    max_val=45.0,
                    step=0.5,
                    decimals=1,
                    suffix="°",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("toe_tip", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "root_chord_scale",
                    root_chord_scale,
                    min_val=0.01,
                    max_val=5.0,
                    step=0.05,
                    decimals=2,
                    suffix="x",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("root_chord_scale", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "tip_chord_scale",
                    tip_chord_scale,
                    min_val=0.01,
                    max_val=5.0,
                    step=0.05,
                    decimals=2,
                    suffix="x",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("tip_chord_scale", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "tip_thickness_scale",
                    tip_thickness_scale,
                    min_val=0.01,
                    max_val=5.0,
                    step=0.05,
                    decimals=2,
                    suffix="x",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("tip_thickness_scale", val),
                )
                self._set_property_spinbox(
                    self.tip_caps_table,
                    "taper_curve",
                    taper_curve,
                    min_val=0.1,
                    max_val=10.0,
                    step=0.1,
                    decimals=2,
                    suffix="x",
                    on_changed=lambda val: self._on_tip_cap_spinbox_changed("taper_curve", val),
                )

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

                self._update_winglet_projected_display(tip_treatment)

            self._fit_table_height(self.tip_caps_table, len(definitions))
        finally:
            self._loading = was_loading

    def _update_winglet_projected_display(self, tip_treatment: dict) -> None:
        if not hasattr(self, "metric_height_val") or not hasattr(self, "metric_span_val"):
            return
        winglet_height = float(tip_treatment.get("winglet_height", 130.0))
        cant_tip_default = float(tip_treatment.get("cant_angle", 80.0))
        cant_root = float(tip_treatment.get("cant_root", 0.0))
        cant_tip = float(tip_treatment.get("cant_tip", cant_tip_default))
        blend_radius = float(tip_treatment.get("blend_radius", 45.0 if "blend_radius" in tip_treatment else 0.0))
        h_proj, s_proj = compute_winglet_projected_dimensions(winglet_height, cant_root, cant_tip, blend_radius)
        self.metric_height_val.setText(f"{h_proj:.1f} mm")
        self.metric_span_val.setText(f"{s_proj:.1f} mm")

    def _on_tip_cap_type_changed(self, new_type: str) -> None:
        if self._loading:
            return
        geom = self._geometry()
        tip_treatment = geom.setdefault("tip_treatment", {})

        def change() -> None:
            tip_treatment["type"] = new_type

        self._edit_component(f"Set tip cap to {new_type}", change)
        self._load_tip_caps()

    def _on_match_wing_tangent_changed(self, val_str: str) -> None:
        if self._loading:
            return
        geom = self._geometry()
        tip_treatment = geom.setdefault("tip_treatment", {})
        val_bool = val_str.lower() == "true"

        def change() -> None:
            tip_treatment["match_wing_tangent"] = val_bool

        self._edit_component("Toggle winglet match wing tangent", change)
        self._load_tip_caps()

    def _on_tip_cap_spinbox_changed(self, key: str, value: float) -> None:
        if self._loading:
            return
        geom = self._geometry()
        tip_treatment = geom.setdefault("tip_treatment", {})
        dict_key = "length" if key == "tip_length" else ("offset_x" if key == "tip_offset_x" else key)

        def change() -> None:
            tip_treatment[dict_key] = value

        self._edit_component(f"Change tip cap {dict_key}", change)
        self._update_winglet_projected_display(tip_treatment)

    def _on_tip_cap_cell_edited(self, row: int, column: int) -> None:
        pass