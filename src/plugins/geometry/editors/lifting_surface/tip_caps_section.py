"""End caps (tip treatment) handling for the Lifting Surface Editor."""

from __future__ import annotations

from dataclasses import asdict
from typing import NamedTuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTableWidgetItem
from shiboken6 import isValid

from setuav_studio.model.expression import set_expression
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input

from ...engine.lifting_surface_tips import (
    WingletParameters,
    compute_winglet_projected_dimensions,
    new_tip_treatment,
    tip_cap_parameters,
    tip_treatment_type,
    winglet_parameters,
)
from .host import LiftingSurfaceEditorHost


class _SpinField(NamedTuple):
    key: str
    label: str
    min_val: float
    max_val: float
    step: float
    decimals: int
    suffix: str


_TIP_CAP_FIELDS = (
    _SpinField("length", "Tip Length", 0.0, 1e6, 2.0, 1, "mm"),
    _SpinField("offset_x", "Tip Sweep Offset", -1e6, 1e6, 2.0, 1, "mm"),
)

_WINGLET_FIELDS = (
    _SpinField("winglet_height", "Arc Span", 0.0, 5000.0, 10.0, 1, "mm"),
    _SpinField("cant_root", "Cant Root", -90.0, 90.0, 5.0, 1, "°"),
    _SpinField("cant_tip", "Cant Tip", -90.0, 90.0, 5.0, 1, "°"),
    _SpinField("blend_radius", "Blend Radius", 0.0, 1000.0, 5.0, 1, "mm"),
    _SpinField("le_sweep_root", "LE Sweep Root", -85.0, 85.0, 5.0, 1, "°"),
    _SpinField("le_sweep_tip", "LE Sweep Tip", -85.0, 85.0, 5.0, 1, "°"),
    _SpinField("le_curvature", "LE Curvature", -500.0, 500.0, 5.0, 1, "mm"),
    _SpinField("te_sweep_root", "TE Sweep Root", -85.0, 85.0, 5.0, 1, "°"),
    _SpinField("te_sweep_tip", "TE Sweep Tip", -85.0, 85.0, 5.0, 1, "°"),
    _SpinField("te_curvature", "TE Curvature", -500.0, 500.0, 5.0, 1, "mm"),
    _SpinField("toe_root", "Toe Root", -45.0, 45.0, 0.5, 1, "°"),
    _SpinField("toe_tip", "Toe Tip", -45.0, 45.0, 0.5, 1, "°"),
    _SpinField("root_chord_scale", "Root Chord Scale", 0.01, 5.0, 0.05, 2, "x"),
    _SpinField("tip_chord_scale", "Tip Chord Scale", 0.01, 5.0, 0.05, 2, "x"),
    _SpinField("tip_thickness_scale", "Tip Thickness Scale", 0.01, 5.0, 0.05, 2, "x"),
)

# Root sweeps a winglet takes from the wing edges while it matches the wing tangent.
_TANGENT_ROOT_SWEEPS = frozenset({"le_sweep_root", "te_sweep_root"})

_TIP_TYPE_OPTIONS = [
    ("flat", "Flat"),
    ("round", "Round (Dome)"),
    ("sharp", "Sharp (Bevel)"),
    ("winglet", "Winglet"),
]


_SPIN_FIELDS = {field.key: field for field in (*_TIP_CAP_FIELDS, *_WINGLET_FIELDS)}


class TipCapsSectionMixin(LiftingSurfaceEditorHost):
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
        # The metrics cell widget is recreated whenever the tip type changes.
        # Clear stale references before Qt deletes the old table widgets.
        self.metric_height_val = None
        self.metric_span_val = None
        geom = self._geometry()
        tip_type = tip_treatment_type(geom)

        winglet: WingletParameters | None = None
        values: dict[str, float] = {}
        spin_fields: tuple[_SpinField, ...] = ()
        if tip_type in ("round", "sharp"):
            values = asdict(tip_cap_parameters(geom))
            spin_fields = _TIP_CAP_FIELDS
        elif tip_type == "winglet":
            winglet = winglet_parameters(geom)
            values = asdict(winglet)
            spin_fields = tuple(
                field
                for field in _WINGLET_FIELDS
                if not (winglet.match_wing_tangent and field.key in _TANGENT_ROOT_SWEEPS)
            )

        definitions = [("tip_type", "Tip Cap Type")]
        if winglet is not None:
            definitions.append(("match_wing_tangent", "Match Tangent"))
        for field in spin_fields:
            definitions.append((field.key, field.label))
            if field.key == "winglet_height":
                definitions.append(("winglet_projected_metrics", ""))

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
                _TIP_TYPE_OPTIONS,
                self._on_tip_cap_type_changed,
            )

            for field in spin_fields:
                self._set_property_spinbox(
                    self.tip_caps_table,
                    field.key,
                    values[field.key],
                    min_val=field.min_val,
                    max_val=field.max_val,
                    step=field.step,
                    decimals=field.decimals,
                    suffix=field.suffix,
                    target_data=geom.get("tip_treatment"),
                    raw_callback=True,
                    api=self._api,
                    on_changed=lambda text, key=field.key: self._on_tip_cap_spinbox_changed(
                        key, text
                    ),
                )

            if winglet is not None:
                self._set_property_combo(
                    self.tip_caps_table,
                    "match_wing_tangent",
                    "true" if winglet.match_wing_tangent else "false",
                    [
                        ("true", "Yes (Continuous Tangent)"),
                        ("false", "No (Manual Angle)"),
                    ],
                    self._on_match_wing_tangent_changed,
                )
                self._create_winglet_metrics_row()
                self._update_winglet_projected_display(winglet)

            self._fit_table_height(self.tip_caps_table, len(definitions))
        finally:
            self._loading = was_loading

    def _create_winglet_metrics_row(self) -> None:
        """Place the two-column live metric widgets: | Height: h_val | Span: s_val |."""
        metrics_row = -1
        for r in range(self.tip_caps_table.rowCount()):
            if self._property_key(self.tip_caps_table, r) == "winglet_projected_metrics":
                metrics_row = r
                break
        if metrics_row < 0:
            return

        self.metric_height_widget = QFrame()
        h_layout = QHBoxLayout(self.metric_height_widget)
        h_layout.setContentsMargins(6, 0, 6, 0)
        h_layout.setSpacing(6)

        self.lbl_metric_h_tag = QLabel("Height:")
        self.metric_height_val = QLabel("0.0 mm")
        h_layout.addWidget(self.lbl_metric_h_tag)
        h_layout.addWidget(self.metric_height_val)
        h_layout.addStretch()

        self.metric_span_widget = QFrame()
        s_layout = QHBoxLayout(self.metric_span_widget)
        s_layout.setContentsMargins(6, 0, 6, 0)
        s_layout.setSpacing(6)

        self.lbl_metric_span_tag = QLabel("Span:")
        self.metric_span_val = QLabel("0.0 mm")
        s_layout.addWidget(self.lbl_metric_span_tag)
        s_layout.addWidget(self.metric_span_val)
        s_layout.addStretch()

        val_item = QTableWidgetItem("")
        val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.tip_caps_table.setItem(metrics_row, 1, val_item)

        self.tip_caps_table.setCellWidget(metrics_row, 0, self.metric_height_widget)
        self.tip_caps_table.setCellWidget(metrics_row, 1, self.metric_span_widget)

    def _update_winglet_projected_display(self, winglet: WingletParameters) -> None:
        height_label = getattr(self, "metric_height_val", None)
        span_label = getattr(self, "metric_span_val", None)
        if (
            height_label is None
            or span_label is None
            or not isValid(height_label)
            or not isValid(span_label)
        ):
            return
        h_proj, s_proj = compute_winglet_projected_dimensions(winglet)
        height_label.setText(f"{h_proj:.1f} mm")
        span_label.setText(f"{s_proj:.1f} mm")

    def _on_tip_cap_type_changed(self, new_type: str) -> None:
        if self._loading:
            return
        geom = self._geometry()
        current = geom.get("tip_treatment")

        def change() -> None:
            geom["tip_treatment"] = new_tip_treatment(new_type, current)

        self._edit_component(f"Set tip cap to {new_type}", change)
        self._load_tip_caps()

    def _on_match_wing_tangent_changed(self, val_str: str) -> None:
        if self._loading:
            return
        tip_treatment = self._geometry()["tip_treatment"]
        val_bool = val_str.lower() == "true"

        def change() -> None:
            tip_treatment["match_wing_tangent"] = val_bool

        self._edit_component("Toggle winglet match wing tangent", change)
        self._load_tip_caps()

    def _on_tip_cap_spinbox_changed(self, key: str, text: object) -> None:
        if self._loading:
            return
        field = _SPIN_FIELDS[key]
        parsed = evaluate_table_cell_input(
            text,
            self._api,
            cell=self._property_cell(self.tip_caps_table, key),
            label=field.label,
            min_val=field.min_val,
            max_val=field.max_val,
        )
        if parsed is None:
            return
        value, expression = parsed
        geom = self._geometry()
        tip_treatment = geom["tip_treatment"]

        def change() -> None:
            tip_treatment[key] = value
            set_expression(tip_treatment, key, expression)

        self._edit_component(f"Change tip cap {key}", change)
        if tip_treatment_type(geom) == "winglet":
            self._update_winglet_projected_display(winglet_parameters(geom))

    def _on_tip_cap_cell_edited(self, row: int, column: int) -> None:
        pass
