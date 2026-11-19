"""Station sections management for the Fuselage Editor."""

from __future__ import annotations

import weakref
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from setuav_studio.model.expression import get_expression, set_expression
from setuav_studio.ui.widget.button import set_native_button
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input, set_table_spinbox
from setuav_studio.ui.widget.table import ExpressionPropertyCell

from ...engine.fuselage_geometry import (
    create_default_section,
    get_default_profile,
)
from .host import FuselageEditorHost
from .profile_editor import (
    PROFILE_FIELDS,
    format_profile_size,
)
from .section_dialog import FuselageSectionDialog


class SectionsSectionMixin(FuselageEditorHost):
    """Manages fuselage cross-section stations, transforms, and profiles."""

    def _create_sections_section(self) -> None:
        layout = self._create_section("Sections", "mdi6.vector-polygon")

        self.sections_table = self._table(["#", "Profile", "X", "Size"])
        self.sections_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.sections_table.setColumnWidth(0, 32)
        self.sections_table.currentCellChanged.connect(self._on_section_selected)
        self.sections_table.doubleClicked.connect(self._on_section_double_clicked)
        layout.addWidget(self.sections_table)

        section_actions = QHBoxLayout()
        section_actions.setContentsMargins(0, 2, 0, 2)
        section_actions.setSpacing(2)
        self.inspect_section_button = self._action_button(
            "mdi6.eye-outline", "Inspect & Edit 2D Cross-Section...", self._inspect_section
        )
        set_native_button(self.inspect_section_button, "mdi6.eye-outline")
        self.add_section_button = self._action_button("add", "Add section", self._add_section)
        self.duplicate_section_button = self._action_button(
            "instance", "Duplicate section", self._duplicate_section
        )
        self.move_section_up_button = self._action_button(
            "fa6s.arrow-up", "Move section up", self._move_section_up
        )
        self.move_section_down_button = self._action_button(
            "fa6s.arrow-down", "Move section down", self._move_section_down
        )
        self.delete_section_button = self._action_button(
            "remove", "Delete section", self._delete_section
        )
        for button in (
            self.inspect_section_button,
            self.add_section_button,
            self.duplicate_section_button,
            self.move_section_up_button,
            self.move_section_down_button,
            self.delete_section_button,
        ):
            section_actions.addWidget(button)
        section_actions.addStretch()
        layout.addLayout(section_actions)

        transform_layout = self._create_section("Transform", "mdi6.axis-arrow")
        self.transform_table = QTableWidget(2, 3)
        self.transform_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.transform_table.setVerticalHeaderLabels(["Position", "Rotation"])
        self.transform_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.transform_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.transform_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.transform_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transform_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transform_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.transform_table.horizontalHeader().setFixedHeight(23)
        self.transform_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.transform_table.verticalHeader().setDefaultSectionSize(23)
        self.transform_table.verticalHeader().setMinimumWidth(82)
        self.transform_table.setFixedHeight(71)
        for row in range(2):
            for column in range(3):
                item = QTableWidgetItem("0.00")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.transform_table.setItem(row, column, item)
        self.transform_table.cellChanged.connect(self._update_section)
        transform_layout.addWidget(self.transform_table)

        properties_layout = self._create_section("Section Properties", "fa6s.sliders")

        self.inspect_2d_button = QPushButton("Inspect & Edit 2D Section...")
        set_native_button(self.inspect_2d_button, "mdi6.vector-polygon")
        self.inspect_2d_button.setToolTip("Open interactive 2D cross-section inspector & metrics")
        self.inspect_2d_button.clicked.connect(self._inspect_section)
        properties_layout.addWidget(self.inspect_2d_button)

        self.section_properties_table = self._property_table([])
        self.section_properties_table.cellChanged.connect(self._update_section_property)
        properties_layout.addWidget(self.section_properties_table)

        self.vertices_table = self._table(["Y", "Z", "Radius"])
        self.vertices_table.cellChanged.connect(self._update_vertices)
        self.vertices_table.setVisible(False)
        properties_layout.addWidget(self.vertices_table)

    def _populate_sections(self) -> None:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        length_sym = um.get_unit_symbol("length")
        sections = self._sections()
        self.sections_table.setRowCount(len(sections))
        for row, section in enumerate(sections):
            profile = section.get("profile")
            if not isinstance(profile, dict):
                profile = {}
            position = section.get("position")
            if not isinstance(position, dict):
                position = {}
            x_raw = float(position.get("x") or 0.0)
            disp_x = um.to_display(x_raw, "length")
            disp_x_str = (
                f"{disp_x:.1f} {length_sym}"
                if abs(disp_x - round(disp_x)) > 1e-4
                else f"{disp_x:.0f} {length_sym}"
            )
            values = (
                str(row + 1),
                str(profile.get("type") or ""),
                disp_x_str,
                self._profile_size(profile),
            )
            for column, value in enumerate(values):
                self.sections_table.setItem(row, column, QTableWidgetItem(value))
        self._fit_table_height(self.sections_table, len(sections))

    def _load_section(self, index: int) -> None:
        sections = self._sections()
        if not 0 <= index < len(sections):
            self._section_index = -1
            self.vertices_table.setVisible(False)
            return

        self._loading = True
        self._section_index = index
        section = sections[index]
        position = self._object(section, "position")
        rotation = self._object(section, "rotation")
        profile = self._object(section, "profile")

        self._set_transform_values(
            position,
            rotation,
        )
        self._populate_section_properties(profile)
        self._populate_vertices(profile)
        self._loading = False

    def _on_section_selected(self, row: int, _column: int, *_previous: int) -> None:
        if self._loading:
            return
        if row >= 0:
            self._load_section(row)
        else:
            self._section_index = -1
        self._update_section_actions()
        self._publish_section_selection()

    def _publish_section_selection(self) -> None:
        component_id = self._component.get("id")
        if isinstance(component_id, str) and self._segment_index >= 0 and self._section_index >= 0:
            self._api.set_section_selection(
                (component_id, self._segment_index, self._section_index)
            )
        else:
            self._api.set_section_selection(None)

    def _add_section(self) -> None:
        segment = self._current_segment()
        if segment is None:
            self._add_segment()
            segment = self._current_segment()
            if segment is None:
                return
        sections = self._sections()
        insert_at = (
            self._section_index + 1 if 0 <= self._section_index < len(sections) else len(sections)
        )
        new_section = self._new_section(sections, insert_at)
        self._edit_component(
            "Add fuselage section",
            lambda: sections.insert(insert_at, new_section),
        )
        self._reload_sections(insert_at)
        self._update_segment_sections_cell()

    def _duplicate_section(self) -> None:
        sections = self._sections()
        index = self._section_index
        if not 0 <= index < len(sections):
            return
        insert_at = index + 1
        duplicate = deepcopy(sections[index])
        self._edit_component(
            "Duplicate fuselage section",
            lambda: sections.insert(insert_at, duplicate),
        )
        self._reload_sections(insert_at)
        self._update_segment_sections_cell()

    def _move_section_up(self) -> None:
        self._move_section(-1)

    def _move_section_down(self) -> None:
        self._move_section(1)

    def _move_section(self, offset: int) -> None:
        sections = self._sections()
        source = self._section_index
        target = source + offset
        if not 0 <= source < len(sections) or not 0 <= target < len(sections):
            return

        def change() -> None:
            sections.insert(target, sections.pop(source))

        self._edit_component(
            "Move fuselage section",
            change,
        )
        self._reload_sections(target)

    def _delete_section(self) -> None:
        sections = self._sections()
        index = self._section_index
        if len(sections) <= 2 or not 0 <= index < len(sections):
            return
        self._edit_component(
            "Delete fuselage section",
            lambda: sections.pop(index),
        )
        self._reload_sections(min(index, len(sections) - 1))
        self._update_segment_sections_cell()

    def _reload_sections(self, selected_index: int) -> None:
        self._loading = True
        self._populate_sections()
        sections = self._sections()
        if sections:
            selected_index = min(max(selected_index, 0), len(sections) - 1)
            self.sections_table.selectRow(selected_index)
        else:
            selected_index = -1
        self._loading = False
        if selected_index >= 0:
            self._load_section(selected_index)
        else:
            self._section_index = -1
        self._update_section_actions()
        self._publish_section_selection()

    def _update_section_actions(self) -> None:
        sections = self._sections()
        index = self._section_index
        has_segment = self._current_segment() is not None
        has_section = 0 <= index < len(sections)
        self.inspect_section_button.setEnabled(has_section)
        self.inspect_2d_button.setEnabled(has_section)
        self.add_section_button.setEnabled(has_segment)
        self.duplicate_section_button.setEnabled(has_section)
        self.move_section_up_button.setEnabled(has_section and index > 0)
        self.move_section_down_button.setEnabled(has_section and index < len(sections) - 1)
        self.delete_section_button.setEnabled(has_section and len(sections) > 2)

    def _on_section_double_clicked(self, _index: Any = None) -> None:
        self._inspect_section()

    def _inspect_section(self) -> None:
        if self._segment_index < 0 or self._section_index < 0:
            return
        segs = self._segments()
        if not (0 <= self._segment_index < len(segs)):
            return
        secs = self._sections()
        if not (0 <= self._section_index < len(secs)):
            return

        dlg = FuselageSectionDialog(
            self._api,
            self._component,
            segment_index=self._segment_index,
            section_index=self._section_index,
            parent=self,
        )
        if dlg.exec():
            self._load_component()

    @classmethod
    def _new_section(
        cls,
        sections: list[dict[str, Any]],
        insert_at: int,
    ) -> dict[str, Any]:
        x = cls._new_section_x(sections, insert_at)
        return cls._default_section(x)

    @classmethod
    def _default_section(cls, x: float) -> dict[str, Any]:
        section = create_default_section(x, "circle")
        section["rotation"] = {"x": 0.0, "y": 0.0, "z": 0.0}
        section["skin"] = {"continuity": "curvature", "symmetry": "all"}
        return section

    @staticmethod
    def _new_section_x(sections: list[dict[str, Any]], insert_at: int) -> float:
        def x_at(index: int) -> float:
            position = sections[index].get("position")
            if not isinstance(position, dict):
                return 0.0
            try:
                return float(position.get("x") or 0)
            except (TypeError, ValueError):
                return 0.0

        has_previous = insert_at > 0
        has_next = insert_at < len(sections)
        if has_previous and has_next:
            return (x_at(insert_at - 1) + x_at(insert_at)) / 2
        if has_previous:
            return x_at(insert_at - 1) + 100.0
        if has_next:
            return x_at(insert_at) - 100.0
        return 0.0

    def _change_profile_type(self, profile_type: str) -> None:
        section = self._current_section()
        if self._loading or section is None:
            return

        self._edit_component(
            "Change fuselage profile",
            lambda: section.__setitem__("profile", self._default_profile(profile_type)),
        )
        self._load_section(self._section_index)
        self._populate_sections()
        self.sections_table.selectRow(self._section_index)

    def _update_section(self, *_args: object) -> None:
        section = self._current_section()
        if self._loading or section is None:
            return

        transform_values = self._transform_values()
        if transform_values is None:
            self._load_section(self._section_index)
            return
        position_values, rotation_values = transform_values

        def change() -> None:
            pos = section.setdefault("position", {})
            pos["x"] = position_values[0]
            pos["y"] = position_values[1]
            pos["z"] = position_values[2]
            rot = section.setdefault("rotation", {})
            rot["x"] = rotation_values[0]
            rot["y"] = rotation_values[1]
            rot["z"] = rotation_values[2]

        self._edit_component("Edit section transform", change)
        self._refresh_section_row()

    def _on_transform_expression_changed(self, transform_type: str, axis: str, value: Any) -> None:
        if self._loading:
            return
        section = self._current_section()
        if section is None:
            return
        target = self._object(section, transform_type)

        row = 0 if transform_type == "position" else 1
        col = ("x", "y", "z").index(axis)
        widget = self.transform_table.cellWidget(row, col)
        cell = widget if isinstance(widget, ExpressionPropertyCell) else None
        raw_input: Any = value
        if (raw_input is None or raw_input == "") and cell is not None:
            raw_input = cell.text().strip()

        parsed = evaluate_table_cell_input(
            raw_input,
            self._api,
            cell=cell,
            label=f"section {transform_type} {axis}",
        )
        if parsed is None:
            return
        num_val, expr_to_store = parsed

        def change() -> None:
            set_expression(target, axis, expr_to_store)
            target[axis] = num_val

        self._edit_component(f"Change fuselage section {transform_type} {axis}", change)
        self._refresh_section_row()

    def _update_section_property(self, row: int, column: int) -> None:
        section = self._current_section()
        if self._loading or section is None or column != 1:
            return
        key = self._property_key(self.section_properties_table, row)
        value = self._property_text(self.section_properties_table, row).strip()
        profile = self._object(section, "profile")

        if key == "type":
            if value not in self.PROFILE_TYPES:
                self._load_section(self._section_index)
                return
            self._change_profile_type(value)
            return
        if key == "orientation":
            if value not in {"up", "down"}:
                self._load_section(self._section_index)
                return
            converted: str | float = value
        elif key == "vertices":
            return
        else:
            number = self._parse_number(value)
            if number is None or number < 0:
                self._load_section(self._section_index)
                return
            converted = number

        self._edit_component(
            "Edit section profile",
            lambda: profile.__setitem__(key, converted),
        )
        self._refresh_section_row()

    def _update_section_choice(self, key: str, value: str) -> None:
        if self._loading:
            return
        if key == "type":
            if value in self.PROFILE_TYPES:
                self._change_profile_type(value)
            return
        if key != "orientation" or value not in {"up", "down"}:
            return

        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        self._edit_component(
            "Edit section profile",
            lambda: profile.__setitem__(key, value),
        )
        self._refresh_section_row()

    def _set_transform_values(
        self,
        position: dict[str, Any] | tuple[float, float, float],
        rotation: dict[str, Any] | tuple[float, float, float],
    ) -> None:
        self_ref = weakref.ref(self)

        def transform_callback(transform_type: str, axis: str) -> Callable[[Any], None]:
            def on_changed(value: Any) -> None:
                editor = self_ref()
                if editor is not None:
                    editor._on_transform_expression_changed(transform_type, axis, value)

            return on_changed

        pos_dict = (
            position
            if isinstance(position, dict)
            else {"x": position[0], "y": position[1], "z": position[2]}
        )
        rot_dict = (
            rotation
            if isinstance(rotation, dict)
            else {"x": rotation[0], "y": rotation[1], "z": rotation[2]}
        )
        axes = ("x", "y", "z")
        for column, axis in enumerate(axes):
            raw_val = get_expression(pos_dict, axis) or pos_dict.get(axis, 0.0)
            set_table_spinbox(
                self.transform_table,
                0,
                column,
                raw_val,
                step=5.0,
                decimals=2,
                quantity="length",
                suffix="mm",
                api=self._api,
                label=f"Position {axis.upper()}",
                property_key=axis,
                raw_callback=True,
                on_changed=transform_callback("position", axis),
            )
        for column, axis in enumerate(axes):
            raw_val = get_expression(rot_dict, axis) or rot_dict.get(axis, 0.0)
            set_table_spinbox(
                self.transform_table,
                1,
                column,
                raw_val,
                min_val=-360.0,
                max_val=360.0,
                step=1.0,
                decimals=2,
                quantity="angle",
                suffix="°",
                api=self._api,
                label=f"Rotation {axis.upper()}",
                property_key=axis,
                raw_callback=True,
                on_changed=transform_callback("rotation", axis),
            )

    def _transform_values(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        rows: list[tuple[float, float, float]] = []
        for row in range(2):
            vals: list[float] = []
            for column in range(3):
                w = self.transform_table.cellWidget(row, column)
                if isinstance(w, (QDoubleSpinBox, ExpressionPropertyCell)):
                    vals.append(float(w.value()))
                else:
                    item = self.transform_table.item(row, column)
                    try:
                        vals.append(float(item.text()) if item is not None else 0.0)
                    except (AttributeError, ValueError):
                        return None
            if len(vals) == 3:
                rows.append((vals[0], vals[1], vals[2]))
        if len(rows) == 2:
            return rows[0], rows[1]
        return None

    def _update_vertices(self, row: int, column: int) -> None:
        if self._loading:
            return
        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        vertices = profile.get("vertices")
        if not isinstance(vertices, list) or not 0 <= row < len(vertices):
            return
        w = self.vertices_table.cellWidget(row, column)
        if isinstance(w, (QDoubleSpinBox, ExpressionPropertyCell)):
            value = float(w.value())
        else:
            item = self.vertices_table.item(row, column)
            try:
                value = float(item.text()) if item is not None else 0.0
            except ValueError:
                return
        key = ("y", "z", "radius")[column]
        if isinstance(vertices[row], dict):
            self._edit_component(
                "Edit polygon vertex",
                lambda: vertices[row].__setitem__(key, value),
            )

    def _populate_section_properties(self, profile: dict[str, Any]) -> None:
        profile_type = str(profile.get("type") or "circle")
        definitions = [("type", "Profile"), *PROFILE_FIELDS.get(profile_type, [])]
        self._configure_property_table(self.section_properties_table, definitions)
        self.vertices_table.setVisible(profile_type == "polygon")
        for key, _label in definitions:
            if key == "type":
                continue
            elif key == "vertices":
                value = len(profile.get("vertices") or [])
                self._set_property_value(
                    self.section_properties_table,
                    key,
                    str(value),
                    editable=False,
                )
            elif key in (
                "diameter",
                "width",
                "height",
                "top_width",
                "bottom_width",
                "base_width",
                "corner_radius",
                "fillet_radius",
            ):
                raw_val = get_expression(profile, key) or profile.get(key, 0.0)
                self._set_property_expression(
                    self.section_properties_table,
                    key,
                    raw_val,
                    target_data=profile,
                    raw_callback=True,
                    on_changed=lambda v, k=key: self._on_property_expression_changed(k, v),
                    api=self._api,
                    label=_label,
                    unit="mm",
                )
            else:
                self._set_property_value(
                    self.section_properties_table,
                    key,
                    profile.get(key, 0),
                )
        self._set_property_combo(
            self.section_properties_table,
            "type",
            profile_type,
            [(value, value.replace("_", " ").title()) for value in self.PROFILE_TYPES],
            lambda value: self._update_section_choice("type", value),
        )
        if profile_type == "triangle":
            self._set_property_combo(
                self.section_properties_table,
                "orientation",
                str(profile.get("orientation") or "up"),
                [("up", "Up"), ("down", "Down")],
                lambda value: self._update_section_choice("orientation", value),
            )

    def _on_property_expression_changed(self, key: str, value: Any) -> None:
        if self._loading:
            return
        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        cell = self._property_cell(self.section_properties_table, key)
        parsed = evaluate_table_cell_input(value, self._api, cell=cell, label=key)
        if parsed is None:
            return
        num_val, expr_to_store = parsed
        if num_val < 0:
            msg = f"Invalid {key}: value must be non-negative"
            if cell is not None:
                cell.set_error(msg)
            if self._api is not None:
                self._api.show_status(msg, "error")
            return

        def change() -> None:
            set_expression(profile, key, expr_to_store)
            profile[key] = num_val

        self._edit_component(
            f"Change fuselage section {key}",
            change,
        )
        self._refresh_section_row()
        self.vertices_table.setVisible(profile.get("type") == "polygon")

    def _populate_vertices(self, profile: dict[str, Any]) -> None:
        is_polygon = profile.get("type") == "polygon"
        self.vertices_table.setVisible(is_polygon)
        if not is_polygon:
            self.vertices_table.setRowCount(0)
            return
        self_ref = weakref.ref(self)

        def vertex_callback(row: int, column: int) -> Callable[[Any], None]:
            def on_changed(value: Any) -> None:
                editor = self_ref()
                if editor is not None:
                    editor._on_vertex_spin_changed(row, column, value)

            return on_changed

        vertices = profile.get("vertices")
        if not isinstance(vertices, list):
            vertices = []
        self.vertices_table.setRowCount(len(vertices))
        for row, vertex in enumerate(vertices):
            if not isinstance(vertex, dict):
                continue
            set_table_spinbox(
                self.vertices_table,
                row,
                0,
                float(vertex.get("y") or 0.0),
                step=1.0,
                decimals=2,
                suffix="mm",
                on_changed=vertex_callback(row, 0),
                api=self._api,
            )
            set_table_spinbox(
                self.vertices_table,
                row,
                1,
                float(vertex.get("z") or 0.0),
                step=1.0,
                decimals=2,
                suffix="mm",
                on_changed=vertex_callback(row, 1),
                api=self._api,
            )
            set_table_spinbox(
                self.vertices_table,
                row,
                2,
                float(vertex.get("radius") or 0.0),
                min_val=0.0,
                step=0.5,
                decimals=2,
                suffix="mm",
                on_changed=vertex_callback(row, 2),
                api=self._api,
            )
        self._fit_table_height(self.vertices_table, len(vertices))

    def _on_vertex_spin_changed(self, row: int, column: int, value: float) -> None:
        if self._loading:
            return
        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        vertices = profile.get("vertices")
        if not isinstance(vertices, list) or not 0 <= row < len(vertices):
            return
        key = ("y", "z", "radius")[column]
        if isinstance(vertices[row], dict):
            self._edit_component(
                "Edit polygon vertex",
                lambda: vertices[row].__setitem__(key, float(value)),
            )

    def _refresh_section_row(self) -> None:
        section = self._current_section()
        if section is None:
            return
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        length_sym = um.get_unit_symbol("length")
        position = section.get("position")
        if not isinstance(position, dict):
            position = {}
        profile = section.get("profile")
        if not isinstance(profile, dict):
            profile = {}
        row = self._section_index
        if not hasattr(self, "sections_table") or row < 0 or row >= self.sections_table.rowCount():
            return
        x_raw = float(position.get("x") or 0.0)
        disp_x = um.to_display(x_raw, "length")
        disp_x_str = (
            f"{disp_x:.1f} {length_sym}"
            if abs(disp_x - round(disp_x)) > 1e-4
            else f"{disp_x:.0f} {length_sym}"
        )
        item1 = self.sections_table.item(row, 1)
        if item1 is not None:
            item1.setText(str(profile.get("type") or ""))
        item2 = self.sections_table.item(row, 2)
        if item2 is not None:
            item2.setText(disp_x_str)
        item3 = self.sections_table.item(row, 3)
        if item3 is not None:
            item3.setText(self._profile_size(profile))

    def _sections(self) -> list[dict[str, Any]]:
        segment = self._current_segment()
        if segment is None:
            return []
        sections = segment.get("sections")
        if not isinstance(sections, list):
            sections = []
            segment["sections"] = sections
        return sections

    def _current_section(self) -> dict[str, Any] | None:
        sections = self._sections()
        if 0 <= self._section_index < len(sections):
            return sections[self._section_index]
        return None

    @staticmethod
    def _profile_size(profile: dict[str, Any]) -> str:
        return format_profile_size(profile)

    @staticmethod
    def _default_profile(profile_type: str) -> dict[str, Any]:
        return get_default_profile(profile_type)
