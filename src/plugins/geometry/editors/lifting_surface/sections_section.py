"""Wing sections and their root and tip profiles in the Lifting Surface Editor."""

from __future__ import annotations

import weakref
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QToolButton,
    QWidget,
)

from setuav_studio.model.expression import get_expression, set_expression
from setuav_studio.ui.widget.button import set_native_button
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input, set_table_spinbox
from setuav_studio.ui.widget.table import ExpressionPropertyCell

from ...engine.lifting_surface_layout import (
    append_section,
    delete_section,
    section_root,
    split_section,
)
from .airfoil_dialog import AirfoilDialog
from .host import LiftingSurfaceEditorHost

# The sections table columns after the section number: key, header and quantity.
_SECTION_COLUMNS = (
    ("span", "Span", "length"),
    ("sweep", "Sweep", "angle"),
    ("dihedral", "Dihedral", "angle"),
    ("twist", "Twist", "angle"),
)
_CHORD_ROWS = {"root_chord": "Root Chord", "tip_chord": "Tip Chord"}


class SectionsSectionMixin(LiftingSurfaceEditorHost):
    """The wing's sections and the root and tip profile of the selected section."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_sections_section(self) -> None:
        """Section list table and section action buttons."""
        layout = self._create_section("Sections", "mdi6.vector-polygon")

        self.sections_table = self._table(["#", *(label for _key, label, _q in _SECTION_COLUMNS)])
        self.sections_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sections_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.sections_table.setColumnWidth(0, 30)
        self.sections_table.currentCellChanged.connect(self._on_section_selected)
        self.sections_table.itemSelectionChanged.connect(self._on_sections_selection_changed)
        layout.addWidget(self.sections_table)

        section_actions = QHBoxLayout()
        section_actions.setContentsMargins(0, 2, 0, 2)
        section_actions.setSpacing(4)

        self.split_section_button = self._action_button(
            "split", "Split selected section into two panels", self._split_section
        )
        self.insert_section_button = self._action_button(
            "add", "Insert new connected section at wing tip", self._insert_section
        )
        self.delete_section_button = self._action_button(
            "remove", "Delete selected section", self._delete_section
        )

        for btn in (
            self.split_section_button,
            self.insert_section_button,
            self.delete_section_button,
        ):
            section_actions.addWidget(btn)
        section_actions.addStretch()
        layout.addLayout(section_actions)

    def _create_section_properties_section(self) -> None:
        """Root and tip profile (chord and airfoil) of the selected section."""
        props_layout = self._create_section("Section Profiles", "fa6s.sliders")
        self.section_properties_table = self._property_table(
            [
                ("root_chord", "Root Chord"),
                ("root_airfoil", "Root Airfoil"),
                ("tip_chord", "Tip Chord"),
                ("tip_airfoil", "Tip Airfoil"),
            ]
        )
        self.section_properties_table.cellClicked.connect(self._on_section_property_cell_clicked)
        self.section_properties_table.currentCellChanged.connect(
            self._on_section_property_cell_changed
        )
        self.section_properties_table.itemSelectionChanged.connect(
            self._on_section_property_selection_changed
        )
        props_layout.addWidget(self.section_properties_table)

    def _create_airfoil_shaping_section(self) -> None:
        """Airfoil Shaping: TE blunting, thickness/camber scalers, and dihedral section alignment."""
        layout = self._create_section("Airfoil Shaping", "fa6s.pen-ruler")

        self.airfoil_shaping_table = self._property_table(
            [
                ("section_align", "Section Alignment"),
                ("te_thickness", "TE Thickness"),
                ("thickness_scale", "Thickness Scale"),
                ("camber_scale", "Camber Scale"),
            ]
        )
        layout.addWidget(self.airfoil_shaping_table)

    # -------------------------------------------------------------------------
    # Sections Populating & Loading
    # -------------------------------------------------------------------------

    def _get_sections(self) -> list[dict[str, Any]]:
        return self._geometry()["sections"]

    def _section_cell_changed(self, index: int, key: str) -> Callable[[str], None]:
        editor_ref = weakref.ref(self)

        def on_changed(text: str) -> None:
            editor = editor_ref()
            if editor is not None:
                editor._on_section_value_changed(index, key, text)

        return on_changed

    def _populate_sections(self) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            from setuav_studio.units import get_unit_manager

            um = get_unit_manager()
            sections = self._get_sections()
            self.sections_table.setHorizontalHeaderLabels(
                [
                    "#",
                    *(
                        f"{label} [{um.get_unit_symbol(quantity)}]"
                        for _key, label, quantity in _SECTION_COLUMNS
                    ),
                ]
            )
            self.sections_table.setRowCount(len(sections))

            for row, section in enumerate(sections):
                num_item = QTableWidgetItem(str(row + 1))
                num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.sections_table.setItem(row, 0, num_item)
                for column, (key, label, quantity) in enumerate(_SECTION_COLUMNS, start=1):
                    self.sections_table.setItem(row, column, QTableWidgetItem(""))
                    set_table_spinbox(
                        self.sections_table,
                        row,
                        column,
                        float(section[key]),
                        decimals=1 if quantity == "length" else 2,
                        quantity=quantity,
                        unit=um.get_unit_symbol(quantity),
                        expression=get_expression(section, key),
                        property_key=key,
                        raw_callback=True,
                        on_changed=self._section_cell_changed(row, key),
                        api=self._api,
                        label=f"Section {row + 1} {label}",
                    )

            self._fit_table_height(self.sections_table, len(sections))
            self._update_section_actions()
        finally:
            self._loading = was_loading

    def _update_section_actions(self) -> None:
        self.delete_section_button.setEnabled(len(self._get_sections()) > 1)

    def _on_sections_selection_changed(self) -> None:
        row = self.sections_table.currentRow()
        if row >= 0:
            self._on_section_selected(row, 0)

    def _on_section_selected(
        self, row: int, col: int, prev_row: int = -1, prev_col: int = -1
    ) -> None:
        if row < 0:
            return
        self._section_index = row
        self._load_section(row)
        # Notify 3D renderer about section selection
        comp_id = str(self._component["id"])
        self._api.set_section_selection((comp_id, 0, row))

    def _on_section_property_cell_clicked(self, row: int, _col: int) -> None:
        if not self._loading and row >= 0:
            self._handle_section_property_selection(row)

    def _on_section_property_selection_changed(self) -> None:
        if self._loading:
            return
        row = self.section_properties_table.currentRow()
        if row >= 0:
            self._handle_section_property_selection(row)

    def _on_section_property_cell_changed(
        self, row: int, _col: int, _prev_row: int = -1, _prev_col: int = -1
    ) -> None:
        if self._loading or row < 0:
            return
        self._handle_section_property_selection(row)

    def _handle_section_property_selection(self, row: int) -> None:
        comp_id = str(self._component["id"])
        key = self._property_key(self.section_properties_table, row)
        # The root profile is station i, the tip profile station i + 1.
        station = self._section_index + (1 if key.startswith("tip_") else 0)
        self._api.set_section_selection((comp_id, 0, station))

    def _section_profile(self, index: int, key: str) -> dict[str, Any]:
        """The root or tip profile (chord and airfoil) of section ``index``."""
        geometry = self._geometry()
        if key.startswith("root_"):
            return section_root(geometry["root"], geometry["sections"], index)
        return geometry["sections"][index]["tip"]

    def _load_section(self, idx: int) -> None:
        sections = self._get_sections()
        if not (0 <= idx < len(sections)):
            return

        was_loading = self._loading
        self._loading = True
        try:
            for key, label in _CHORD_ROWS.items():
                profile = self._section_profile(idx, key)
                self._set_property_spinbox(
                    self.section_properties_table,
                    key,
                    float(profile["chord"]),
                    decimals=1,
                    quantity="length",
                    expression=get_expression(profile, "chord"),
                    raw_callback=True,
                    on_changed=self._section_cell_changed(idx, key),
                    api=self._api,
                    label=f"Section {idx + 1} {label}",
                )
            self._setup_airfoil_cell(1, self._section_profile(idx, "root_")["airfoil"], True)
            self._setup_airfoil_cell(3, self._section_profile(idx, "tip_")["airfoil"], False)
        finally:
            self._loading = was_loading

    def _setup_airfoil_cell(self, row: int, airfoil_data: Any, is_root: bool) -> None:
        """Render airfoil name in standard font size with inline choose button."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(6)

        label_str = self._format_airfoil_label(airfoil_data)
        lbl = QLabel(label_str)
        lbl.setToolTip(f"{'Root' if is_root else 'Tip'} Airfoil: {label_str}")

        btn = QToolButton()
        set_native_button(btn, "edit")
        btn.setText("Choose")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setToolTip("Select or import airfoil for this station")

        def on_choose_clicked():
            self.section_properties_table.selectRow(row)
            self._handle_section_property_selection(row)
            self._open_section_airfoil_dialog(is_root)

        btn.clicked.connect(on_choose_clicked)

        def on_mouse_press(_event):
            self.section_properties_table.selectRow(row)
            self._handle_section_property_selection(row)

        container.mousePressEvent = on_mouse_press
        lbl.mousePressEvent = on_mouse_press

        layout.addWidget(lbl, 1)
        layout.addWidget(btn)

        self.section_properties_table.setCellWidget(row, 1, container)

    def _load_airfoil_shaping(self) -> None:
        geom = self._geometry()
        shaping = geom.get("airfoil_shaping")
        if not isinstance(shaping, dict):
            shaping = {}

        self._set_property_combo(
            self.airfoil_shaping_table,
            "section_align",
            str(geom.get("section_align", "xz")).lower(),
            [
                ("xz", "Planform Parallel (XZ)"),
                ("normal", "Dihedral Normal (Perpendicular)"),
            ],
            self._on_section_align_changed,
        )
        self._set_property_spinbox(
            self.airfoil_shaping_table,
            "te_thickness",
            float(shaping.get("te_thickness", 0.0)),
            min_val=0.0,
            max_val=0.05,
            step=0.002,
            decimals=4,
            suffix=" t/c",
            on_changed=lambda val: self._on_airfoil_shaping_spinbox_changed("te_thickness", val),
        )
        self._set_property_spinbox(
            self.airfoil_shaping_table,
            "thickness_scale",
            float(shaping.get("thickness_scale", 1.0)),
            min_val=0.1,
            max_val=3.0,
            step=0.05,
            decimals=3,
            suffix="x",
            on_changed=lambda val: self._on_airfoil_shaping_spinbox_changed("thickness_scale", val),
        )
        self._set_property_spinbox(
            self.airfoil_shaping_table,
            "camber_scale",
            float(shaping.get("camber_scale", 1.0)),
            min_val=0.0,
            max_val=3.0,
            step=0.05,
            decimals=3,
            suffix="x",
            on_changed=lambda val: self._on_airfoil_shaping_spinbox_changed("camber_scale", val),
        )

    # -------------------------------------------------------------------------
    # Section Mutations
    # -------------------------------------------------------------------------

    def _on_section_value_changed(self, index: int, key: str, text: str) -> None:
        """Store a number or formula typed into a section or profile cell."""
        if self._loading:
            return
        if key in _CHORD_ROWS:
            cell = self._property_cell(self.section_properties_table, key)
            label = _CHORD_ROWS[key]
        else:
            column = 1 + [k for k, _label, _q in _SECTION_COLUMNS].index(key)
            widget = self.sections_table.cellWidget(index, column)
            cell = widget if isinstance(widget, ExpressionPropertyCell) else None
            label = _SECTION_COLUMNS[column - 1][1]
        parsed = evaluate_table_cell_input(
            text, self._api, cell=cell, label=f"Section {index + 1} {label}"
        )
        if parsed is None:
            return
        value, expression = parsed

        def change(geometry: dict[str, Any]) -> None:
            if key in _CHORD_ROWS:
                target = (
                    section_root(geometry["root"], geometry["sections"], index)
                    if key == "root_chord"
                    else geometry["sections"][index]["tip"]
                )
                field = "chord"
            else:
                target = geometry["sections"][index]
                field = key
            set_expression(target, field, expression)
            target[field] = value

        self._edit_layout(f"Change section {index + 1} {label.lower()}", change)
        self._refresh_sections(index)

    def _refresh_sections(self, index: int) -> None:
        """Show the sections, the selected section and the planform after an edit."""
        self._populate_sections()
        index = min(index, len(self._get_sections()) - 1)
        self._section_index = index
        self.sections_table.selectRow(index)
        self._load_section(index)
        self._refresh_planform_table()
        self._refresh_control_surfaces()

    def _split_section(self) -> None:
        idx = self._section_index
        if idx < 0:
            return
        self._edit_layout(
            "Split wing section",
            lambda geometry: split_section(geometry["root"], geometry["sections"], idx),
        )
        self._refresh_sections(idx)

    def _insert_section(self) -> None:
        self._edit_layout(
            "Insert wing section", lambda geometry: append_section(geometry["sections"])
        )
        self._refresh_sections(len(self._get_sections()) - 1)

    def _delete_section(self) -> None:
        idx = self._section_index
        if idx < 0:
            return
        self._edit_layout(
            "Delete wing section", lambda geometry: delete_section(geometry["sections"], idx)
        )
        self._refresh_sections(idx)

    def _open_section_airfoil_dialog(self, is_root: bool) -> None:
        idx = self._section_index
        if not (0 <= idx < len(self._get_sections())):
            return

        comp_id = str(self._component["id"])
        station_idx = idx if is_root else idx + 1
        self._api.set_section_selection((comp_id, 0, station_idx))

        key = "root_airfoil" if is_root else "tip_airfoil"
        dialog = AirfoilDialog(self._section_profile(idx, key)["airfoil"], self)
        if dialog.exec() != AirfoilDialog.DialogCode.Accepted:
            return
        new_af, apply_all = dialog.get_selected_airfoil()

        def change(geometry: dict[str, Any]) -> None:
            if apply_all:
                profiles = [geometry["root"], *(s["tip"] for s in geometry["sections"])]
            elif is_root:
                profiles = [section_root(geometry["root"], geometry["sections"], idx)]
            else:
                profiles = [geometry["sections"][idx]["tip"]]
            for profile in profiles:
                profile["airfoil"] = deepcopy(new_af)

        self._edit_layout(f"Apply airfoil to section {idx + 1}", change)
        self._refresh_sections(idx)
        self._api.set_section_selection((comp_id, 0, station_idx))

    def _on_section_align_changed(self, value: str) -> None:
        if self._loading:
            return
        geom = self._geometry()

        def change() -> None:
            geom["section_align"] = value

        self._edit_component("Change section alignment", change)

    def _on_airfoil_shaping_spinbox_changed(self, key: str, value: float) -> None:
        if self._loading:
            return
        geom = self._geometry()
        shaping = geom.setdefault("airfoil_shaping", {})

        def change() -> None:
            shaping[key] = value

        self._edit_component(f"Change {key}", change)
