from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox, set_table_spinbox
from setuav_studio.ui.property_tables import PropertyTableMixin

CONTROL_SURFACE_TYPES = [
    ("aileron", "Aileron"),
    ("flap", "Flap"),
    ("elevator", "Elevator"),
    ("rudder", "Rudder"),
    ("elevon", "Elevon"),
    ("ruddervator", "Ruddervator"),
]

SPAN_SIZING_MODES = [
    ("ratio", "Preserve Ratio (Eta)"),
    ("dimension", "Preserve Length (mm)"),
]

CHORD_SIZING_MODES = [
    ("ratio", "Preserve Ratio (% Chord)"),
    ("dimension", "Preserve Depth (mm)"),
]

SYMMETRY_MODES = [
    ("auto", "Auto (By Type)"),
    ("antisymmetric", "Antisymmetric (Differential)"),
    ("symmetric", "Symmetric"),
    ("none", "None (Single)"),
]


class ControlSurfaceEditor(PropertyTableMixin, QWidget):
    table_scroll_policy_off = True
    table_max_visible_rows = None

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._component = component
        self._loading = False
        self._cs_spinboxes: dict[str, NumericSpinBox] = {}

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        self._create_general_section()
        self._create_properties_section()
        self._content_layout.addStretch(1)

        scroll.setWidget(content)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll)

        self.load_component(component)

    def load_component(self, component: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._component = component
            self._load_general()
            self._load_properties()
        finally:
            self._loading = False

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

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("parent", "Parent Wing"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_properties_section(self) -> None:
        layout = self._create_section("Control Surface Geometry", "fa6s.sliders")
        self.properties_table = self._property_table(
            [
                ("tag", "Tag / Label"),
                ("type", "Type"),
                ("span_mode", "Span Sizing"),
                ("span_start", "Span Start (mm)"),
                ("span_end", "Span End (mm)"),
                ("eta_start", "Eta Start (0 - 1)"),
                ("eta_end", "Eta End (0 - 1)"),
                ("chord_mode", "Chord Sizing"),
                ("chord_fraction", "Chord Fraction (c_f / c)"),
                ("chord", "Control Chord (mm)"),
                ("hinge_sweep", "Hinge Sweep (°)"),
                ("deflection", "Deflection Angle (°)"),
                ("symmetry_mode", "Symmetry Mode"),
            ]
        )
        self.properties_table.cellChanged.connect(self._update_property_cell)
        layout.addWidget(self.properties_table)

    def _parent_wing_info(self) -> tuple[float, float]:
        """Return (semi_span, root_chord) for the parent lifting surface."""
        parent_id = str(self._component.get("parent") or self._component.get("attach_to") or "")
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if project and isinstance(project.data.get("components"), list):
            for c in project.data["components"]:
                if isinstance(c, dict) and str(c.get("id") or "") == parent_id:
                    params = c.get("parameters", {})
                    geom = params.get("geometry", {})
                    profs = geom.get("profiles", [])
                    if isinstance(profs, list) and profs:
                        span_values = [
                            float(p.get("position", {}).get("y", 0.0))
                            for p in profs
                            if isinstance(p.get("position"), dict)
                        ]
                        y0 = span_values[0] if span_values else 0.0
                        y1 = span_values[-1] if span_values else 0.0
                        semi_span = abs(y1 - y0) if len(span_values) >= 2 else 400.0
                        root_chord = float(profs[0].get("chord", 150.0))
                        return max(semi_span, 1.0), max(root_chord, 1.0)
        return 400.0, 150.0

    def _load_general(self) -> None:
        name = str(self._component.get("name") or self._component.get("id") or "")
        comp_type = str(self._component.get("type") or "org.setuav.core:control-surface")
        parent = str(self._component.get("parent") or self._component.get("attach_to") or "")

        self._set_property_value(self.general_table, "name", name)
        self._set_property_value(self.general_table, "type", comp_type, editable=False)

        # Parent combo (find all lifting surface components)
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        options: list[tuple[str, str]] = [("", "-- None --")]
        if project and isinstance(project.data.get("components"), list):
            for c in project.data["components"]:
                if isinstance(c, dict) and c.get("type") == "org.setuav.core:lifting-surface":
                    cid = str(c.get("id") or "")
                    cname = str(c.get("name") or cid)
                    options.append((cid, cname))

        self._set_property_combo(
            self.general_table,
            "parent",
            parent,
            options,
            self._update_parent,
        )

    def _load_properties(self) -> None:
        geom = self._geometry()
        semi_span, root_chord = self._parent_wing_info()
        self._cs_spinboxes = {}

        tag_val = str(
            geom.get("tag") or self._component.get("name") or self._component.get("id") or ""
        )
        cs_type = str(geom.get("type") or "aileron").lower()
        span_mode = str(geom.get("span_mode", "ratio")).lower()
        chord_mode = str(geom.get("chord_mode", "ratio")).lower()

        # Resolve span and eta
        if "span_start" in geom:
            span_start = float(geom.get("span_start", 0.0))
            eta_start = float(geom.get("eta_start", round(span_start / semi_span, 4)))
        elif "eta_start" in geom:
            eta_start = float(geom.get("eta_start", 0.0))
            span_start = round(eta_start * semi_span, 1)
            geom["span_start"] = span_start
        else:
            span_start = round(semi_span * 0.4, 1)
            eta_start = 0.4
            geom["span_start"] = span_start
            geom["eta_start"] = eta_start

        if "span_end" in geom:
            span_end = float(geom.get("span_end", 0.0))
            eta_end = float(geom.get("eta_end", round(span_end / semi_span, 4)))
        elif "eta_end" in geom:
            eta_end = float(geom.get("eta_end", 0.0))
            span_end = round(eta_end * semi_span, 1)
            geom["span_end"] = span_end
        else:
            span_end = round(semi_span * 0.85, 1)
            eta_end = 0.85
            geom["span_end"] = span_end
            geom["eta_end"] = eta_end

        # Resolve chord and chord fraction
        if "chord_fraction" in geom and geom.get("chord_fraction") is not None:
            chord_fraction = float(geom.get("chord_fraction", 0.25))
            chord = float(geom.get("chord", round(chord_fraction * root_chord, 1)))
        elif "chord" in geom:
            chord = float(geom.get("chord", 40.0))
            chord_fraction = round(chord / root_chord, 3)
            geom["chord_fraction"] = chord_fraction
        else:
            chord_fraction = 0.25
            chord = round(root_chord * 0.25, 1)
            geom["chord"] = chord
            geom["chord_fraction"] = chord_fraction

        hinge_sweep = float(geom.get("hinge_sweep", 0.0))
        deflection = float(geom.get("deflection", 0.0))
        sym_mode = str(geom.get("symmetry_mode", "auto")).lower()

        self._set_property_value(self.properties_table, "tag", tag_val)
        self._set_property_combo(
            self.properties_table,
            "type",
            cs_type,
            CONTROL_SURFACE_TYPES,
            lambda val: self._on_prop_combo_changed("type", val),
        )
        self._set_property_combo(
            self.properties_table,
            "span_mode",
            span_mode,
            SPAN_SIZING_MODES,
            lambda val: self._on_prop_combo_changed("span_mode", val),
        )
        sb_ss = self._set_property_spinbox(
            self.properties_table,
            "span_start",
            span_start,
            min_val=0.0,
            max_val=20000.0,
            step=5.0,
            decimals=1,
            suffix=" mm",
            on_changed=lambda val: self._on_prop_spinbox_changed("span_start", val),
        )
        if sb_ss:
            self._cs_spinboxes["span_start"] = sb_ss

        sb_se = self._set_property_spinbox(
            self.properties_table,
            "span_end",
            span_end,
            min_val=0.0,
            max_val=20000.0,
            step=5.0,
            decimals=1,
            suffix=" mm",
            on_changed=lambda val: self._on_prop_spinbox_changed("span_end", val),
        )
        if sb_se:
            self._cs_spinboxes["span_end"] = sb_se

        sb_es = self._set_property_spinbox(
            self.properties_table,
            "eta_start",
            eta_start,
            min_val=0.0,
            max_val=1.0,
            step=0.01,
            decimals=3,
            on_changed=lambda val: self._on_prop_spinbox_changed("eta_start", val),
        )
        if sb_es:
            self._cs_spinboxes["eta_start"] = sb_es

        sb_ee = self._set_property_spinbox(
            self.properties_table,
            "eta_end",
            eta_end,
            min_val=0.0,
            max_val=1.0,
            step=0.01,
            decimals=3,
            on_changed=lambda val: self._on_prop_spinbox_changed("eta_end", val),
        )
        if sb_ee:
            self._cs_spinboxes["eta_end"] = sb_ee

        self._set_property_combo(
            self.properties_table,
            "chord_mode",
            chord_mode,
            CHORD_SIZING_MODES,
            lambda val: self._on_prop_combo_changed("chord_mode", val),
        )
        sb_cf = self._set_property_spinbox(
            self.properties_table,
            "chord_fraction",
            chord_fraction,
            min_val=0.02,
            max_val=0.95,
            step=0.01,
            decimals=3,
            suffix=" c",
            on_changed=lambda val: self._on_prop_spinbox_changed("chord_fraction", val),
        )
        if sb_cf:
            self._cs_spinboxes["chord_fraction"] = sb_cf

        sb_c = self._set_property_spinbox(
            self.properties_table,
            "chord",
            chord,
            min_val=1.0,
            max_val=5000.0,
            step=1.0,
            decimals=1,
            suffix=" mm",
            on_changed=lambda val: self._on_prop_spinbox_changed("chord", val),
        )
        if sb_c:
            self._cs_spinboxes["chord"] = sb_c

        self._set_property_spinbox(
            self.properties_table,
            "hinge_sweep",
            hinge_sweep,
            min_val=-85.0,
            max_val=85.0,
            step=0.5,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_prop_spinbox_changed("hinge_sweep", val),
        )
        self._set_property_spinbox(
            self.properties_table,
            "deflection",
            deflection,
            min_val=-90.0,
            max_val=90.0,
            step=1.0,
            decimals=1,
            suffix="°",
            on_changed=lambda val: self._on_prop_spinbox_changed("deflection", val),
        )
        self._set_property_combo(
            self.properties_table,
            "symmetry_mode",
            sym_mode,
            SYMMETRY_MODES,
            lambda val: self._on_prop_combo_changed("symmetry_mode", val),
        )

    def _on_prop_spinbox_changed(self, key: str, value: float) -> None:
        if self._loading:
            return
        geom = self._geometry()
        semi_span, root_chord = self._parent_wing_info()

        def change() -> None:
            if key == "span_start":
                geom["span_start"] = float(value)
                new_eta = round(float(value) / semi_span, 4)
                geom["eta_start"] = new_eta
                if hasattr(self, "_cs_spinboxes") and "eta_start" in self._cs_spinboxes:
                    self._cs_spinboxes["eta_start"].blockSignals(True)
                    self._cs_spinboxes["eta_start"].setValue(new_eta)
                    self._cs_spinboxes["eta_start"].blockSignals(False)

            elif key == "span_end":
                geom["span_end"] = float(value)
                new_eta = round(float(value) / semi_span, 4)
                geom["eta_end"] = new_eta
                if hasattr(self, "_cs_spinboxes") and "eta_end" in self._cs_spinboxes:
                    self._cs_spinboxes["eta_end"].blockSignals(True)
                    self._cs_spinboxes["eta_end"].setValue(new_eta)
                    self._cs_spinboxes["eta_end"].blockSignals(False)

            elif key == "eta_start":
                geom["eta_start"] = float(value)
                new_span = round(float(value) * semi_span, 1)
                geom["span_start"] = new_span
                if hasattr(self, "_cs_spinboxes") and "span_start" in self._cs_spinboxes:
                    self._cs_spinboxes["span_start"].blockSignals(True)
                    self._cs_spinboxes["span_start"].setValue(new_span)
                    self._cs_spinboxes["span_start"].blockSignals(False)

            elif key == "eta_end":
                geom["eta_end"] = float(value)
                new_span = round(float(value) * semi_span, 1)
                geom["span_end"] = new_span
                if hasattr(self, "_cs_spinboxes") and "span_end" in self._cs_spinboxes:
                    self._cs_spinboxes["span_end"].blockSignals(True)
                    self._cs_spinboxes["span_end"].setValue(new_span)
                    self._cs_spinboxes["span_end"].blockSignals(False)

            elif key == "chord_fraction":
                geom["chord_fraction"] = float(value)
                new_c = round(float(value) * root_chord, 1)
                geom["chord"] = new_c
                if hasattr(self, "_cs_spinboxes") and "chord" in self._cs_spinboxes:
                    self._cs_spinboxes["chord"].blockSignals(True)
                    self._cs_spinboxes["chord"].setValue(new_c)
                    self._cs_spinboxes["chord"].blockSignals(False)

            elif key == "chord":
                geom["chord"] = max(float(value), 1.0)
                new_cf = round(float(value) / root_chord, 3)
                geom["chord_fraction"] = new_cf
                if hasattr(self, "_cs_spinboxes") and "chord_fraction" in self._cs_spinboxes:
                    self._cs_spinboxes["chord_fraction"].blockSignals(True)
                    self._cs_spinboxes["chord_fraction"].setValue(new_cf)
                    self._cs_spinboxes["chord_fraction"].blockSignals(False)

            elif key == "hinge_sweep":
                geom["hinge_sweep"] = float(value)
            elif key == "deflection":
                geom["deflection"] = float(value)

        self._edit_component(f"Edit control surface {key}", change)

    def _on_prop_combo_changed(self, key: str, value: str) -> None:
        if self._loading:
            return
        geom = self._geometry()

        def change() -> None:
            geom[key] = value

        self._edit_component(f"Edit control surface {key}", change)

    def _update_property_cell(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.properties_table, row)
        val_str = self._property_text(self.properties_table, row).strip()
        if key == "tag":
            geom = self._geometry()

            def change() -> None:
                geom["tag"] = val_str
                self._component["name"] = val_str

            self._edit_component("Rename control surface tag", change)

    def _geometry(self) -> dict[str, Any]:
        params = self._component.get("parameters")
        if not isinstance(params, dict):
            params = {}
            self._component["parameters"] = params
        geom = params.get("geometry")
        if not isinstance(geom, dict):
            geom = {}
            params["geometry"] = geom
        return geom

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_str = self._property_text(self.general_table, row).strip()
        if key == "name":

            def change() -> None:
                self._component["name"] = val_str
                self._geometry()["tag"] = val_str

            self._edit_component("Rename control surface", change)

    def _update_parent(self, new_parent: str | None) -> None:
        if self._loading:
            return

        def change() -> None:
            self._component["parent"] = new_parent if new_parent else None
            self._component["attach_to"] = new_parent if new_parent else None

        self._edit_component("Change control surface parent wing", change)

    def _edit_component(self, action_name: str, mutation: Callable[[], None]) -> None:
        if hasattr(self._api, "edit_component"):
            self._api.edit_component(self._component, action_name, mutation)
        else:
            mutation()

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
            item = table.item(row, 1)
            if item is not None:
                item.setText("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            combo = QComboBox(table)
            combo.setFont(QApplication.font())
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            for opt_val, opt_label in options:
                combo.addItem(opt_label, opt_val)
            idx = combo.findData(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(
                lambda _i, combo=combo: on_changed(str(combo.currentData()))
            )
            table.setCellWidget(row, 1, combo)
            return
