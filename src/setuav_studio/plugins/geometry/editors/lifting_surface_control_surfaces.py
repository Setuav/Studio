"""Control surface handling for the Lifting Surface Editor."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QTableWidgetItem,
)

from setuav_studio.ui.numeric_spinbox import NumericSpinBox


class ControlSurfacesMixin:
    """Control surface listing, properties, and mutation handling."""

    CONTROL_SURFACE_TYPES = (
        ("aileron", "Aileron"),
        ("flap", "Flap"),
        ("elevator", "Elevator"),
        ("rudder", "Rudder"),
        ("elevon", "Elevon"),
        ("ruddervator", "Ruddervator"),
    )

    SPAN_SIZING_MODES = (
        ("ratio", "Preserve Ratio (Eta)"),
        ("dimension", "Preserve Length (mm)"),
    )

    CHORD_SIZING_MODES = (
        ("ratio", "Preserve Ratio (% Chord)"),
        ("dimension", "Preserve Depth (mm)"),
    )

    SYMMETRY_MODES = (
        ("auto", "Auto (By Type)"),
        ("antisymmetric", "Antisymmetric (Differential)"),
        ("symmetric", "Symmetric"),
        ("none", "None (Single)"),
    )

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_control_surfaces_section(self) -> None:
        layout = self._create_section("Control Surfaces", "fa6s.sliders")

        self.control_surfaces_table = self._table(
            [
                "Tag",
                "Type",
                "Span (mm)",
                "Eta",
                "Chord",
                "Defl (°)",
            ]
        )
        self.control_surfaces_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.control_surfaces_table.currentCellChanged.connect(self._on_control_surface_selected)
        self.control_surfaces_table.itemSelectionChanged.connect(self._on_cs_selection_changed)
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

        self.cs_properties_table = self._property_table(
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
        self.cs_properties_table.cellChanged.connect(self._update_cs_property)
        layout.addWidget(self.cs_properties_table)

    def _wing_span_info(self) -> tuple[float, float]:
        """Return (semi_span, root_chord) for this lifting surface."""
        profiles = self._profiles()
        if profiles:
            span_values = [
                float(p.get("position", {}).get("y", 0.0))
                for p in profiles
                if isinstance(p.get("position"), dict)
            ]
            y0 = span_values[0] if span_values else 0.0
            y1 = span_values[-1] if span_values else 0.0
            semi_span = abs(y1 - y0) if len(span_values) >= 2 else 400.0
            root_chord = float(profiles[0].get("chord", 150.0))
            return max(semi_span, 1.0), max(root_chord, 1.0)
        return 400.0, 150.0

    def _sync_control_surfaces_with_wing(self) -> None:
        """Synchronize control surface span/chord values according to their span_mode and chord_mode."""
        cs_list = self._control_surfaces()
        if not cs_list:
            return
        semi_span, root_chord = self._wing_span_info()
        for cs in cs_list:
            geom = self._cs_geom(cs)
            span_mode = str(geom.get("span_mode", "ratio")).lower()
            chord_mode = str(geom.get("chord_mode", "ratio")).lower()

            if span_mode == "ratio":
                if "eta_start" in geom:
                    eta_s = float(geom["eta_start"])
                elif "span_start" in geom:
                    eta_s = round(float(geom["span_start"]) / semi_span, 4)
                    geom["eta_start"] = eta_s
                else:
                    eta_s = 0.4
                    geom["eta_start"] = eta_s

                if "eta_end" in geom:
                    eta_e = float(geom["eta_end"])
                elif "span_end" in geom:
                    eta_e = round(float(geom["span_end"]) / semi_span, 4)
                    geom["eta_end"] = eta_e
                else:
                    eta_e = 0.85
                    geom["eta_end"] = eta_e

                geom["span_start"] = round(eta_s * semi_span, 1)
                geom["span_end"] = round(eta_e * semi_span, 1)
            else:
                s_s = float(geom.get("span_start", 0.0))
                s_e = float(geom.get("span_end", 0.0))
                geom["eta_start"] = round(s_s / semi_span, 4)
                geom["eta_end"] = round(s_e / semi_span, 4)

            if chord_mode == "ratio":
                if "chord_fraction" in geom and geom["chord_fraction"] is not None:
                    c_frac = float(geom["chord_fraction"])
                elif "chord" in geom:
                    c_frac = round(float(geom["chord"]) / root_chord, 3)
                    geom["chord_fraction"] = c_frac
                else:
                    c_frac = 0.25
                    geom["chord_fraction"] = c_frac

                geom["chord"] = round(c_frac * root_chord, 1)
            else:
                c_mm = float(geom.get("chord", 40.0))
                geom["chord_fraction"] = round(c_mm / root_chord, 3)

        self._populate_control_surfaces()
        if 0 <= getattr(self, "_control_surface_index", -1) < len(cs_list):
            self._load_control_surface(self._control_surface_index)

    # -------------------------------------------------------------------------
    # Control Surface Loading & Populating
    # -------------------------------------------------------------------------

    def _populate_control_surfaces(self) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            cs_list = self._control_surfaces()
            semi_span, root_chord = self._wing_span_info()
            self.control_surfaces_table.setRowCount(len(cs_list))
            for row, cs in enumerate(cs_list):
                geom = self._cs_geom(cs)
                s_start = float(geom.get("span_start", 0.0))
                s_end = float(geom.get("span_end", 0.0))
                eta_start = float(geom.get("eta_start", round(s_start / semi_span, 3)))
                eta_end = float(geom.get("eta_end", round(s_end / semi_span, 3)))
                chord = float(geom.get("chord", 40.0))
                chord_frac = float(geom.get("chord_fraction", round(chord / root_chord, 2)))
                defl = float(geom.get("deflection", 0.0))
                tag_label = str(
                    geom.get("tag") or cs.get("name") or cs.get("id") or f"CS_{row + 1}"
                )
                cs_type = str(geom.get("type") or "aileron").capitalize()

                values = (
                    tag_label,
                    cs_type,
                    f"{s_start:.1f} - {s_end:.1f}",
                    f"{eta_start:.2f} - {eta_end:.2f}",
                    f"{chord_frac * 100:.0f}% ({chord:.1f} mm)",
                    f"{defl:+.1f}°" if defl != 0.0 else "0.0°",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column in (2, 3, 4, 5):
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    else:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.control_surfaces_table.setItem(row, column, item)

            self._fit_table_height(
                self.control_surfaces_table, len(cs_list), maximum_visible_rows=5
            )
            self._update_cs_actions()
        finally:
            self._loading = was_loading

    def _load_control_surface(self, row: int) -> None:
        cs_list = self._control_surfaces()
        if not (0 <= row < len(cs_list)):
            self._control_surface_index = -1
            self._clear_property_values(self.cs_properties_table)
            self._update_cs_actions()
            self._api.set_section_selection(None)
            return

        self._control_surface_index = row
        cs = cs_list[row]
        geom = self._cs_geom(cs)
        semi_span, root_chord = self._wing_span_info()

        comp_id = str(self._component.get("id") or "")
        self._api.set_section_selection((comp_id, 1, row))

        was_loading = self._loading
        self._loading = True
        try:
            self._cs_spinboxes: dict[str, NumericSpinBox] = {}

            tag_val = str(geom.get("tag") or cs.get("name") or cs.get("id") or "")
            cs_type = str(geom.get("type") or "aileron").lower()
            span_mode = str(geom.get("span_mode", "ratio")).lower()
            chord_mode = str(geom.get("chord_mode", "ratio")).lower()

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

            self._set_property_value(self.cs_properties_table, "tag", tag_val)
            self._set_property_combo(
                self.cs_properties_table,
                "type",
                cs_type,
                self.CONTROL_SURFACE_TYPES,
                lambda val: self._update_cs_choice("type", val),
            )
            self._set_property_combo(
                self.cs_properties_table,
                "span_mode",
                span_mode,
                self.SPAN_SIZING_MODES,
                lambda val: self._update_cs_choice("span_mode", val),
            )
            sb_ss = self._set_property_spinbox(
                self.cs_properties_table,
                "span_start",
                span_start,
                min_val=0.0,
                max_val=20000.0,
                step=5.0,
                decimals=1,
                suffix=" mm",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("span_start", val),
            )
            if sb_ss:
                self._cs_spinboxes["span_start"] = sb_ss

            sb_se = self._set_property_spinbox(
                self.cs_properties_table,
                "span_end",
                span_end,
                min_val=0.0,
                max_val=20000.0,
                step=5.0,
                decimals=1,
                suffix=" mm",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("span_end", val),
            )
            if sb_se:
                self._cs_spinboxes["span_end"] = sb_se

            sb_es = self._set_property_spinbox(
                self.cs_properties_table,
                "eta_start",
                eta_start,
                min_val=0.0,
                max_val=1.0,
                step=0.01,
                decimals=3,
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("eta_start", val),
            )
            if sb_es:
                self._cs_spinboxes["eta_start"] = sb_es

            sb_ee = self._set_property_spinbox(
                self.cs_properties_table,
                "eta_end",
                eta_end,
                min_val=0.0,
                max_val=1.0,
                step=0.01,
                decimals=3,
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("eta_end", val),
            )
            if sb_ee:
                self._cs_spinboxes["eta_end"] = sb_ee

            self._set_property_combo(
                self.cs_properties_table,
                "chord_mode",
                chord_mode,
                self.CHORD_SIZING_MODES,
                lambda val: self._update_cs_choice("chord_mode", val),
            )
            sb_cf = self._set_property_spinbox(
                self.cs_properties_table,
                "chord_fraction",
                chord_fraction,
                min_val=0.02,
                max_val=0.95,
                step=0.01,
                decimals=3,
                suffix=" c",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("chord_fraction", val),
            )
            if sb_cf:
                self._cs_spinboxes["chord_fraction"] = sb_cf

            sb_c = self._set_property_spinbox(
                self.cs_properties_table,
                "chord",
                chord,
                min_val=1.0,
                max_val=5000.0,
                step=1.0,
                decimals=1,
                suffix=" mm",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("chord", val),
            )
            if sb_c:
                self._cs_spinboxes["chord"] = sb_c

            self._set_property_spinbox(
                self.cs_properties_table,
                "hinge_sweep",
                hinge_sweep,
                min_val=-85.0,
                max_val=85.0,
                step=0.5,
                decimals=1,
                suffix="°",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("hinge_sweep", val),
            )
            self._set_property_spinbox(
                self.cs_properties_table,
                "deflection",
                deflection,
                min_val=-90.0,
                max_val=90.0,
                step=1.0,
                decimals=1,
                suffix="°",
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("deflection", val),
            )
            self._set_property_combo(
                self.cs_properties_table,
                "symmetry_mode",
                sym_mode,
                self.SYMMETRY_MODES,
                lambda val: self._update_cs_choice("symmetry_mode", val),
            )
            self._update_cs_actions()
        finally:
            self._loading = was_loading

    def _on_cs_prop_spinbox_changed(self, key: str, value: float) -> None:
        if self._loading or self._control_surface_index < 0:
            return
        cs_list = self._control_surfaces()
        if not (0 <= self._control_surface_index < len(cs_list)):
            return
        cs = cs_list[self._control_surface_index]
        geom = self._cs_geom(cs)
        semi_span, root_chord = self._wing_span_info()

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

        self._edit_control_surface_item(cs, f"Edit control surface {key}", change)
        self._refresh_cs_table_row(self._control_surface_index)

    # -------------------------------------------------------------------------
    # Control Surface Actions & Mutation
    # -------------------------------------------------------------------------

    def _on_cs_selection_changed(self) -> None:
        if not self._loading:
            row = self.control_surfaces_table.currentRow()
            if row >= 0:
                self._load_control_surface(row)

    def _on_control_surface_selected(
        self, row: int, _col: int, _prev_row: int = -1, _prev_col: int = -1
    ) -> None:
        if not self._loading and row >= 0:
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

        semi_span, root_chord = self._wing_span_info()
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
                    "geometry": {
                        "tag": new_tag,
                        "type": "aileron",
                        "span_mode": "ratio",
                        "span_start": def_start,
                        "span_end": def_end,
                        "eta_start": round(def_start / semi_span, 3),
                        "eta_end": round(def_end / semi_span, 3),
                        "chord_mode": "ratio",
                        "chord_fraction": 0.25,
                        "chord": def_chord,
                        "hinge_sweep": 0.0,
                        "deflection": 0.0,
                        "symmetry_mode": "auto",
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
                "span_mode": "ratio",
                "span_start": def_start,
                "span_end": def_end,
                "eta_start": round(def_start / semi_span, 3),
                "eta_end": round(def_end / semi_span, 3),
                "chord_mode": "ratio",
                "chord_fraction": 0.25,
                "chord": def_chord,
                "hinge_sweep": 0.0,
                "deflection": 0.0,
                "symmetry_mode": "auto",
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
            if (
                project
                and isinstance(project.data.get("components"), list)
                and cs_list[idx] in project.data["components"]
            ):
                comps = project.data["components"]
                i1 = comps.index(cs_list[idx])
                i2 = comps.index(cs_list[target])
                comps[i1], comps[i2] = comps[i2], comps[i1]
            elif "control_surfaces" in self._geometry():
                cs_arr = self._geometry()["control_surfaces"]
                cs_arr.insert(target, cs_arr.pop(idx))

        if (
            project
            and isinstance(project.data.get("components"), list)
            and cs_list[idx] in project.data["components"]
            and hasattr(self._api, "edit_project")
        ):
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
            if (
                project
                and isinstance(project.data.get("components"), list)
                and cs_list[idx] in project.data["components"]
            ):
                comps = project.data["components"]
                i1 = comps.index(cs_list[idx])
                i2 = comps.index(cs_list[target])
                comps[i1], comps[i2] = comps[i2], comps[i1]
            elif "control_surfaces" in self._geometry():
                cs_arr = self._geometry()["control_surfaces"]
                cs_arr.insert(target, cs_arr.pop(idx))

        if (
            project
            and isinstance(project.data.get("components"), list)
            and cs_list[idx] in project.data["components"]
            and hasattr(self._api, "edit_project")
        ):
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
            if (
                project
                and isinstance(project.data.get("components"), list)
                and target_item in project.data["components"]
            ):
                project.data["components"].remove(target_item)
            elif "control_surfaces" in self._geometry():
                cs_arr = self._geometry()["control_surfaces"]
                if target_item in cs_arr:
                    cs_arr.remove(target_item)
                elif 0 <= idx < len(cs_arr):
                    cs_arr.pop(idx)

        if (
            project
            and isinstance(project.data.get("components"), list)
            and target_item in project.data["components"]
            and hasattr(self._api, "edit_project")
        ):
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
        semi_span, root_chord = self._wing_span_info()
        s_start = float(geom.get("span_start", 0.0))
        s_end = float(geom.get("span_end", 0.0))
        eta_start = float(geom.get("eta_start", round(s_start / semi_span, 3)))
        eta_end = float(geom.get("eta_end", round(s_end / semi_span, 3)))
        chord = float(geom.get("chord", 40.0))
        chord_frac = float(geom.get("chord_fraction", round(chord / root_chord, 2)))
        defl = float(geom.get("deflection", 0.0))
        was_loading = self._loading
        self._loading = True
        try:
            if self.control_surfaces_table.item(row, 0):
                tag_label = str(
                    geom.get("tag") or cs.get("name") or cs.get("id") or f"CS_{row + 1}"
                )
                self.control_surfaces_table.item(row, 0).setText(tag_label)
            if self.control_surfaces_table.item(row, 1):
                self.control_surfaces_table.item(row, 1).setText(
                    str(geom.get("type") or "aileron").capitalize()
                )
            if self.control_surfaces_table.item(row, 2):
                self.control_surfaces_table.item(row, 2).setText(f"{s_start:.1f} - {s_end:.1f}")
            if self.control_surfaces_table.item(row, 3):
                self.control_surfaces_table.item(row, 3).setText(f"{eta_start:.2f} - {eta_end:.2f}")
            if self.control_surfaces_table.item(row, 4):
                self.control_surfaces_table.item(row, 4).setText(
                    f"{chord_frac * 100:.0f}% ({chord:.1f} mm)"
                )
            if self.control_surfaces_table.item(row, 5):
                self.control_surfaces_table.item(row, 5).setText(
                    f"{defl:+.1f}°" if defl != 0.0 else "0.0°"
                )
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
