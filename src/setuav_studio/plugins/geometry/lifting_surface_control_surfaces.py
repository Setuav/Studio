"""Control surface handling for the Lifting Surface Editor."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QTableWidget, QTableWidgetItem


class ControlSurfacesMixin:
    """Control surface listing, properties, and mutation handling."""

    CONTROL_SURFACE_TYPES = [
        ("aileron", "Aileron"),
        ("flap", "Flap"),
        ("elevator", "Elevator"),
        ("rudder", "Rudder"),
    ]

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

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

        comp_id = str(self._component.get("id") or "")
        self._api.set_section_selection((comp_id, 1, row))

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

    def _on_cs_selection_changed(self) -> None:
        if not self._loading:
            row = self.control_surfaces_table.currentRow()
            if row >= 0:
                self._load_control_surface(row)

    def _on_control_surface_selected(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
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