"""Control surface handling for the Lifting Surface Editor."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QTableWidgetItem,
)

from setuav_studio.model.expression import get_expression, set_expression
from setuav_studio.ui.style.theme import tokens
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input

from ...engine.control_surface_geometry import sync_sizing_values
from .host import LiftingSurfaceEditorHost


class ControlSurfacesSectionMixin(LiftingSurfaceEditorHost):
    """Control surface listing, properties, and mutation handling."""

    CONTROL_SURFACE_TYPES = (
        ("aileron", "Aileron"),
        ("flap", "Flap"),
        ("elevator", "Elevator"),
        ("rudder", "Rudder"),
        ("elevon", "Elevon"),
        ("ruddervator", "Ruddervator"),
    )

    SIZING_DRIVER_MODES = (
        ("ratio", "Preserve Ratio (Eta & %c)"),
        ("dimension", "Preserve Dimension (Span & Depth mm)"),
        ("area_chord", "Area + Chord Fraction Driven"),
        ("area_span", "Area + Span Extent Driven"),
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
        layout = self._create_section("Control Surfaces", "geometry_add_control_surface")

        self.control_surfaces_table = self._table(
            [
                "Name",
                "Type",
                "Defl",
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
                ("name", "Name"),
                ("type", "Type"),
                ("sizing_mode", "Sizing Driver Mode"),
                ("area", "Area"),
                ("area_ratio", "Area Ratio"),
                ("span_start", "Span Start"),
                ("span_end", "Span End"),
                ("span_length", "Span Length"),
                ("eta_start", "Eta Start"),
                ("eta_end", "Eta End"),
                ("chord_fraction", "Chord Fraction"),
                ("chord", "Control Chord"),
                ("hinge_sweep", "Hinge Sweep"),
                ("deflection", "Deflection Angle"),
                ("symmetry_mode", "Symmetry Mode"),
            ]
        )
        self.cs_properties_table.cellChanged.connect(self._update_cs_property)
        layout.addWidget(self.cs_properties_table)

    def _surface_span_info(self) -> tuple[float, float, float, float]:
        """Return (semi_span, root_chord, tip_chord, parent_wing_area_dm2) for this lifting surface."""
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
            tip_chord = float(profiles[-1].get("chord", 100.0))
            wing_area_dm2 = (semi_span * (root_chord + tip_chord)) / 10000.0
            return (
                max(semi_span, 1.0),
                max(root_chord, 1.0),
                max(tip_chord, 1.0),
                max(wing_area_dm2, 0.01),
            )
        return 400.0, 150.0, 100.0, 10.0

    def _sync_control_surfaces_with_surface(self) -> None:
        """Synchronize control surface span/chord values according to their span_mode and chord_mode."""
        cs_list = self._control_surfaces()
        if not cs_list:
            return
        semi_span, root_chord, *_ = self._surface_span_info()
        for cs in cs_list:
            sync_sizing_values(self._cs_geom(cs), semi_span, root_chord)

        self._populate_control_surfaces()
        if 0 <= self._control_surface_index < len(cs_list):
            self._load_control_surface(self._control_surface_index)

    # -------------------------------------------------------------------------
    # Control Surface Loading & Populating
    # -------------------------------------------------------------------------

    def _populate_control_surfaces(self) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            cs_list = self._control_surfaces()
            self.control_surfaces_table.setRowCount(len(cs_list))
            for row, cs in enumerate(cs_list):
                for column, value in enumerate(self._cs_table_row_values(row, cs)):
                    item = QTableWidgetItem(value)
                    if column in (1, 2):
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

    def _cs_table_row_values(self, row: int, cs: dict[str, Any]) -> tuple[str, str, str]:
        """Return the (name, type, deflection) cell texts of a control surface list row."""
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        geom = self._cs_geom(cs)
        disp_defl = um.to_display(float(geom.get("deflection", 0.0)), "angle")
        angle_sym = um.get_unit_symbol("angle")
        defl_str = f"{disp_defl:+.1f} {angle_sym}" if abs(disp_defl) > 1e-4 else f"0.0 {angle_sym}"
        name_label = str(cs.get("name") or cs.get("id") or f"CS_{row + 1}")
        cs_type = str(geom.get("type") or "aileron").capitalize()
        return name_label, cs_type, defl_str

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
        semi_span, root_chord, tip_chord, wing_area = self._surface_span_info()

        comp_id = str(self._component.get("id") or "")
        self._api.set_section_selection((comp_id, 1, row))

        was_loading = self._loading
        self._loading = True
        try:
            from ...engine.control_surface_geometry import compute_control_surface_metrics

            metrics = compute_control_surface_metrics(
                geom, semi_span, root_chord, tip_chord, wing_area
            )

            name_val = str(cs.get("name") or cs.get("id") or "")
            cs_type = str(geom.get("type") or "aileron").lower()
            sizing_mode = str(geom.get("sizing_mode", geom.get("span_mode", "ratio"))).lower()

            hinge_sweep = float(geom.get("hinge_sweep", 0.0))
            deflection = float(geom.get("deflection", 0.0))
            sym_mode = str(geom.get("symmetry_mode", "auto")).lower()

            driver_keys = self._get_driver_keys_for_mode(sizing_mode)

            self._set_property_value(self.cs_properties_table, "name", name_val)
            self._set_property_combo(
                self.cs_properties_table,
                "type",
                cs_type,
                self.CONTROL_SURFACE_TYPES,
                lambda val: self._update_cs_choice("type", val),
            )
            self._set_property_combo(
                self.cs_properties_table,
                "sizing_mode",
                sizing_mode,
                self.SIZING_DRIVER_MODES,
                lambda val: self._update_cs_choice("sizing_mode", val),
            )

            self._setup_param(
                "area",
                "Area",
                metrics["area_dm2"],
                get_expression(geom, "area"),
                "dm²",
                3,
                driver_keys,
            )
            self._setup_param(
                "area_ratio", "Area Ratio", metrics["area_ratio"], None, "%", 1, driver_keys
            )
            self._setup_param(
                "span_start",
                "Span start",
                metrics["span_start"],
                get_expression(geom, "span_start"),
                "mm",
                2,
                driver_keys,
            )
            self._setup_param(
                "span_end",
                "Span end",
                metrics["span_end"],
                get_expression(geom, "span_end"),
                "mm",
                2,
                driver_keys,
            )
            self._setup_param(
                "span_length",
                "Span length",
                metrics["span_length"],
                get_expression(geom, "span_length"),
                "mm",
                2,
                driver_keys,
            )
            self._setup_param(
                "eta_start",
                "Span start fraction",
                metrics["eta_start"],
                get_expression(geom, "eta_start"),
                "",
                3,
                driver_keys,
            )
            self._setup_param(
                "eta_end",
                "Span end fraction",
                metrics["eta_end"],
                get_expression(geom, "eta_end"),
                "",
                3,
                driver_keys,
            )
            self._setup_param(
                "chord_fraction",
                "Chord fraction",
                metrics["chord_fraction"],
                get_expression(geom, "chord_fraction"),
                "c",
                3,
                driver_keys,
            )
            self._setup_param(
                "chord",
                "Control chord",
                metrics["chord"],
                get_expression(geom, "chord"),
                "mm",
                2,
                driver_keys,
            )

            hs_val = get_expression(geom, "hinge_sweep") or hinge_sweep
            self._set_property_expression(
                self.cs_properties_table,
                "hinge_sweep",
                hs_val,
                target_data=geom,
                raw_callback=True,
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("hinge_sweep", val),
                api=self._api,
                label="Hinge sweep angle",
                unit="°",
                decimals=2,
            )

            def_val = get_expression(geom, "deflection") or deflection
            self._set_property_expression(
                self.cs_properties_table,
                "deflection",
                def_val,
                target_data=geom,
                raw_callback=True,
                on_changed=lambda val: self._on_cs_prop_spinbox_changed("deflection", val),
                api=self._api,
                label="Deflection angle",
                unit="°",
                decimals=2,
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

    def _on_cs_prop_spinbox_changed(self, key: str, value: Any) -> None:
        if self._loading or self._control_surface_index < 0:
            return
        cs_list = self._control_surfaces()
        if not (0 <= self._control_surface_index < len(cs_list)):
            return
        cs = cs_list[self._control_surface_index]
        geom = self._cs_geom(cs)
        semi_span, root_chord, tip_chord, _wing_area = self._surface_span_info()

        cell = self._property_cell(self.cs_properties_table, key)
        parsed = evaluate_table_cell_input(value, self._api, cell=cell, label=key)
        if parsed is None:
            return
        num_val, expr_to_store = parsed

        def change() -> None:
            set_expression(geom, key, expr_to_store)
            self._apply_cs_spinbox_change(geom, key, num_val, semi_span, root_chord, tip_chord)

        self._edit_control_surface_item(cs, f"Edit control surface {key}", change)
        self._refresh_cs_table_row(self._control_surface_index)
        self._load_control_surface(self._control_surface_index)

    def _apply_cs_spinbox_change(
        self,
        geometry: dict[str, Any],
        key: str,
        value: float,
        semi_span: float,
        root_chord: float,
        tip_chord: float = 100.0,
    ) -> None:
        from ...engine.control_surface_geometry import solve_control_surface_from_area

        if key == "area":
            driver_mode = str(geometry.get("sizing_mode", "area_chord")).lower()
            solve_control_surface_from_area(
                geometry, float(value), semi_span, root_chord, tip_chord, driver_mode
            )
        elif key in {"span_start", "span_end"}:
            geometry[key] = float(value)
            geometry[key.replace("span", "eta")] = round(float(value) / semi_span, 4)
        elif key == "span_length":
            start = float(geometry.get("span_start", 0.0))
            end = min(start + float(value), semi_span)
            geometry["span_end"] = round(end, 1)
            geometry["eta_end"] = round(end / semi_span, 4)
        elif key in {"eta_start", "eta_end"}:
            geometry[key] = float(value)
            geometry[key.replace("eta", "span")] = round(float(value) * semi_span, 1)
        elif key == "chord_fraction":
            geometry[key] = float(value)
            geometry["chord"] = round(float(value) * root_chord, 1)
        elif key == "chord":
            geometry[key] = max(float(value), 1.0)
            geometry["chord_fraction"] = round(float(value) / root_chord, 3)
        elif key in {"hinge_sweep", "deflection"}:
            geometry[key] = float(value)

    # -------------------------------------------------------------------------
    # Control Surface Actions & Mutation
    # -------------------------------------------------------------------------

    def _on_cs_selection_changed(self) -> None:
        if not self._loading:
            row = self.control_surfaces_table.currentRow()
            if row >= 0:
                self._load_control_surface(row)

    @staticmethod
    def _get_driver_keys_for_mode(sizing_mode: str) -> set[str]:
        if sizing_mode == "dimension":
            return {"span_start", "span_end", "chord"}
        if sizing_mode == "area_chord":
            return {"area", "span_start", "eta_start", "chord_fraction"}
        if sizing_mode == "area_span":
            return {"area", "span_start", "span_end", "eta_start", "eta_end"}
        return {"eta_start", "eta_end", "chord_fraction"}

    def _setup_param(
        self,
        key: str,
        label_text: str,
        current_val: float,
        raw_expr: str | None,
        unit: str,
        dec: int,
        driver_keys: set[str],
    ) -> None:
        is_driver = key in driver_keys
        target_row = -1
        for r in range(self.cs_properties_table.rowCount()):
            if self._property_key(self.cs_properties_table, r) == key:
                target_row = r
                break
        if target_row < 0:
            return

        label_item = self.cs_properties_table.item(target_row, 0)
        if label_item:
            font = label_item.font()
            font.setBold(is_driver)
            label_item.setFont(font)
            if is_driver:
                label_item.setForeground(QApplication.palette().text())
            else:
                label_item.setForeground(QColor(tokens()["text_dim"]))

        if is_driver:
            val_to_pass = raw_expr if raw_expr else current_val
            geom = self._cs_geom(self._control_surfaces()[self._control_surface_index])
            self._set_property_expression(
                self.cs_properties_table,
                key,
                val_to_pass,
                target_data=geom,
                raw_callback=True,
                on_changed=lambda val, k=key: self._on_cs_prop_spinbox_changed(k, val),
                api=self._api,
                label=label_text,
                unit=unit,
                decimals=dec,
            )
        else:
            from setuav_studio.ui.widget.table import format_engineering_value
            from setuav_studio.units import get_quantity_for_unit, get_unit_manager

            um = get_unit_manager()
            self.cs_properties_table.removeCellWidget(target_row, 1)

            q_id = get_quantity_for_unit(unit)
            if q_id:
                disp_val = um.to_display(current_val, q_id)
                sym = um.get_unit_symbol(q_id)
            else:
                disp_val = current_val
                sym = unit or ""

            val_str = format_engineering_value(disp_val, dec)
            if sym:
                val_str += f" {sym}"
            val_item = self.cs_properties_table.item(target_row, 1)
            if not val_item:
                val_item = QTableWidgetItem(val_str)
                self.cs_properties_table.setItem(target_row, 1, val_item)
            else:
                val_item.setText(val_str)
            val_item.setForeground(QColor(tokens()["text_dim"]))
            val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

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
                cs["name"] = text_val
            elif column == 1:
                geom["type"] = text_val.lower()

        self._edit_control_surface_item(cs, "Edit control surface", change)
        if row == self._control_surface_index:
            self._load_control_surface(row)

    def _add_control_surface(self) -> None:
        cs_list = self._control_surfaces()
        wing_id = str(self._component.get("id") or "wing")
        new_slug = f"control_{len(cs_list) + 1}"
        new_id = f"{wing_id}-{new_slug}"
        project = self._api.project

        semi_span, root_chord, *_ = self._surface_span_info()
        def_start = round(max(semi_span * 0.4, 20.0), 1)
        def_end = round(max(semi_span * 0.85, def_start + 50.0), 1)
        def_chord = round(max(root_chord * 0.25, 10.0), 1)
        span_len = round(max(def_end - def_start, 20.0), 1)
        span_mid = round((def_start + def_end) / 2.0, 1)

        if project and isinstance(project.data.get("components"), list):
            new_comp = {
                "kind": "component",
                "id": new_id,
                "name": new_slug.replace("_", " ").title(),
                "type": "org.setuav.core:control-surface",
                "attach_to": wing_id,
                "mass": 25.0,
                "transform": {
                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                },
                "envelope": {
                    "shape": "box",
                    "size_mm": {
                        "x": def_chord,
                        "y": span_len,
                        "z": 15.0,
                    },
                    "offset_mm": {
                        "x": round(root_chord * (1.0 - 0.25 / 2.0), 1),
                        "y": span_mid,
                        "z": 0.0,
                    },
                },
                "parameters": {
                    "geometry": {
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

            self._api.edit_project("Add control surface", change)

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
        project = self._api.project

        if project and isinstance(project.data.get("components"), list):
            base_id = str(target.get("id") or "cs")
            target["id"] = f"{base_id}-copy"
            target["name"] = f"{target.get('name', base_id)} (Copy)"

            def change() -> None:
                project.data["components"].append(target)

            self._api.edit_project("Duplicate control surface", change)

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
        project = self._api.project

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

        self._api.edit_project("Move control surface up", change)

        self._populate_control_surfaces()
        self.control_surfaces_table.selectRow(target)
        self._load_control_surface(target)

    def _move_cs_down(self) -> None:
        idx = self._control_surface_index
        cs_list = self._control_surfaces()
        if idx < 0 or idx >= len(cs_list) - 1:
            return
        target = idx + 1
        project = self._api.project

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

        self._api.edit_project("Move control surface down", change)

        self._populate_control_surfaces()
        self.control_surfaces_table.selectRow(target)
        self._load_control_surface(target)

    def _delete_control_surface(self) -> None:
        idx = self._control_surface_index
        cs_list = self._control_surfaces()
        if not (0 <= idx < len(cs_list)):
            return

        self._api.delete_components([str(cs_list[idx]["id"])], "Delete control surface")

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
        values = self._cs_table_row_values(row, cs_list[row])
        was_loading = self._loading
        self._loading = True
        try:
            for column, value in enumerate(values):
                item = self.control_surfaces_table.item(row, column)
                if item is not None:
                    item.setText(value)
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

        def change() -> None:
            if key == "name":
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
        self._load_control_surface(self._control_surface_index)
