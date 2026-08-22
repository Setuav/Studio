"""Wing Sections and Section Properties handling for the Lifting Surface Editor."""

from __future__ import annotations

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

from setuav_studio.ui.icons import get_icon
from setuav_studio.plugins.geometry.airfoil_dialog import AirfoilDialog
from setuav_studio.plugins.geometry.wing_driver_solver import compute_all_8_parameters
from setuav_studio.plugins.geometry.wing_driver_table import DriverPlanformTable
from setuav_studio.plugins.geometry.wing_planform_engine import SWEEP_LOCATIONS
from setuav_studio.plugins.geometry.wing_sections_engine import (
    delete_section,
    insert_section,
    profiles_to_sections,
    sections_to_profiles,
    split_section,
)


class SectionsMixin:
    """Parametric wing sections, section-level driver sizing, and section properties."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_sections_section(self) -> None:
        """Section panel list table and panel action buttons."""
        layout = self._create_section("Wing Sections", "mdi6.vector-polygon")

        self.sections_table = self._table([
            "#",
            "Span (mm)",
            "Root C (mm)",
            "Tip C (mm)",
            "Sweep (°)",
            "Dihedral (°)",
            "Twist (°)",
        ])
        self.sections_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.sections_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.sections_table.setColumnWidth(0, 30)
        self.sections_table.currentCellChanged.connect(self._on_section_selected)
        self.sections_table.itemSelectionChanged.connect(self._on_sections_selection_changed)
        self.sections_table.cellChanged.connect(self._update_sections_table_cell)
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
        """Section Planform (8 parameters with 3-driver checkboxes) and Section Properties table."""
        # 1. Section Planform
        planform_layout = self._create_section("Section Planform", "fa6s.ruler-combined")
        self.section_planform_table = DriverPlanformTable(
            default_drivers=["span", "root_chord", "tip_chord"],
            on_values_changed=self._on_section_planform_changed,
        )
        planform_layout.addWidget(self.section_planform_table)

        # 2. Section Properties (Sweep, Sweep Location, Dihedral, Twist, Root Airfoil, Tip Airfoil)
        props_layout = self._create_section("Section Properties", "fa6s.sliders")
        self.section_properties_table = self._property_table([
            ("sweep", "Sweep Angle (°)"),
            ("sweep_loc", "Sweep Location"),
            ("dihedral", "Dihedral Angle (°)"),
            ("twist", "Twist Angle (°)"),
            ("root_airfoil", "Root Airfoil"),
            ("tip_airfoil", "Tip Airfoil"),
        ])
        self.section_properties_table.cellClicked.connect(self._on_section_property_cell_clicked)
        self.section_properties_table.currentCellChanged.connect(self._on_section_property_cell_changed)
        self.section_properties_table.itemSelectionChanged.connect(self._on_section_property_selection_changed)
        props_layout.addWidget(self.section_properties_table)

        # Backward compatibility aliases
        self.section_angles_table = self.section_properties_table
        self.section_airfoils_table = self.section_properties_table

    def _create_airfoil_shaping_section(self) -> None:
        """Airfoil Shaping: TE blunting, thickness/camber scalers, and dihedral section alignment."""
        layout = self._create_section("Airfoil Shaping", "fa6s.pen-ruler")

        self.airfoil_shaping_table = self._property_table([
            ("section_align", "Section Alignment"),
            ("te_thickness", "TE Thickness (t/c)"),
            ("thickness_scale", "Thickness Scale"),
            ("camber_scale", "Camber Scale"),
        ])
        layout.addWidget(self.airfoil_shaping_table)

    # -------------------------------------------------------------------------
    # Sections Populating & Loading
    # -------------------------------------------------------------------------

    def _get_sections(self) -> list[dict[str, Any]]:
        profiles = self._profiles()
        sw_loc = getattr(self, "_sweep_loc", 0.25)
        return profiles_to_sections(profiles, sw_loc)

    def _populate_sections(self) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            sections = self._get_sections()
            self.sections_table.setRowCount(len(sections))

            for r, sec in enumerate(sections):
                num_item = QTableWidgetItem(str(r + 1))
                num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.sections_table.setItem(r, 0, num_item)

                span_item = QTableWidgetItem(f"{sec['span']:.1f}")
                span_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.sections_table.setItem(r, 1, span_item)

                rc_item = QTableWidgetItem(f"{sec['root_chord']:.1f}")
                rc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if r > 0:
                    rc_item.setFlags(rc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    rc_item.setToolTip("Shared with preceding section tip chord")
                self.sections_table.setItem(r, 2, rc_item)

                tc_item = QTableWidgetItem(f"{sec['tip_chord']:.1f}")
                tc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.sections_table.setItem(r, 3, tc_item)

                sw_item = QTableWidgetItem(f"{sec['sweep']:.1f}")
                sw_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.sections_table.setItem(r, 4, sw_item)

                dih_item = QTableWidgetItem(f"{sec['dihedral']:.1f}")
                dih_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.sections_table.setItem(r, 5, dih_item)

                tw_item = QTableWidgetItem(f"{sec['twist']:.1f}")
                tw_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.sections_table.setItem(r, 6, tw_item)

            self._fit_table_height(self.sections_table, len(sections))

            # Enable/disable buttons based on section count
            can_delete = len(sections) > 1
            self.delete_section_button.setEnabled(can_delete)
        finally:
            self._loading = was_loading

    def _on_sections_selection_changed(self) -> None:
        row = self.sections_table.currentRow()
        if row >= 0:
            self._on_section_selected(row, 0)

    def _on_section_selected(self, row: int, col: int, prev_row: int = -1, prev_col: int = -1) -> None:
        if row < 0:
            return
        self._section_index = row
        self._load_section(row)
        # Notify 3D renderer about section selection
        comp_id = str(self._component.get("id") or "")
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

    def _on_section_property_cell_changed(self, row: int, _col: int, _prev_row: int = -1, _prev_col: int = -1) -> None:
        if self._loading or row < 0:
            return
        self._handle_section_property_selection(row)

    def _handle_section_property_selection(self, row: int) -> None:
        comp_id = str(self._component.get("id") or "")
        key = self._property_key(self.section_properties_table, row)
        idx = getattr(self, "_section_index", 0)
        if key == "root_airfoil":
            # Highlight specifically the Root Airfoil Station (Station i)
            self._api.set_section_selection((comp_id, 2, idx))
        elif key == "tip_airfoil":
            # Highlight specifically the Tip Airfoil Station (Station i + 1)
            self._api.set_section_selection((comp_id, 2, idx + 1))
        else:
            # Highlight the full panel
            self._api.set_section_selection((comp_id, 0, idx))

    def _load_section(self, idx: int) -> None:
        sections = self._get_sections()
        if not (0 <= idx < len(sections)):
            return

        sec = sections[idx]
        was_loading = self._loading
        self._loading = True
        try:
            # 1. Section Planform Sizing (8 parameters)
            sec_all_8 = compute_all_8_parameters(
                sec["span"],
                sec["root_chord"],
                sec["tip_chord"],
                is_symmetric=False,
                y_offset=0.0,
            )
            self.section_planform_table.set_parameters(
                sec_all_8,
                is_symmetric=False,
                y_offset=0.0,
            )

            # 2. Section Properties (Sweep, Sweep Location, Dihedral, Twist, Airfoils)
            self._set_property_spinbox(
                self.section_properties_table,
                "sweep",
                float(sec.get("sweep", 0.0)),
                min_val=-85.0,
                max_val=85.0,
                step=0.5,
                decimals=2,
                suffix="°",
                on_changed=lambda val: self._on_section_angle_changed("sweep", val),
            )
            self._set_property_combo(
                self.section_properties_table,
                "sweep_loc",
                str(sec.get("sweep_loc", getattr(self, "_sweep_loc", 0.25))),
                [(str(val), label) for val, label in SWEEP_LOCATIONS],
                self._on_section_sweep_loc_changed,
            )
            self._set_property_spinbox(
                self.section_properties_table,
                "dihedral",
                float(sec.get("dihedral", 0.0)),
                min_val=-85.0,
                max_val=85.0,
                step=0.5,
                decimals=2,
                suffix="°",
                on_changed=lambda val: self._on_section_angle_changed("dihedral", val),
            )
            self._set_property_spinbox(
                self.section_properties_table,
                "twist",
                float(sec.get("twist", 0.0)),
                min_val=-45.0,
                max_val=45.0,
                step=0.5,
                decimals=2,
                suffix="°",
                on_changed=lambda val: self._on_section_angle_changed("twist", val),
            )

            # Setup Root and Tip Airfoil rows with normal font size and inline choose button
            self._setup_airfoil_cell(4, sec.get("root_airfoil", "2412"), is_root=True)
            self._setup_airfoil_cell(5, sec.get("tip_airfoil", "2412"), is_root=False)

        finally:
            self._loading = was_loading

    def _setup_airfoil_cell(self, row: int, airfoil_data: Any, is_root: bool) -> None:
        """Render airfoil name in standard font size with inline choose button."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(6)

        label_str = self._format_airfoil_label(airfoil_data) if hasattr(self, "_format_airfoil_label") else str(airfoil_data)
        lbl = QLabel(label_str)
        lbl.setStyleSheet("color: #e0e0e0; font-weight: 500;")
        lbl.setToolTip(f"{'Root' if is_root else 'Tip'} Airfoil: {label_str}")

        btn = QToolButton()
        btn.setIcon(get_icon("edit"))
        btn.setText("Choose")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setToolTip("Select or import airfoil for this station")
        btn.setStyleSheet(
            "QToolButton { background: #2a2a2a; border: 1px solid #3d3d3d; border-radius: 3px; padding: 2px 6px; color: #ffffff; font-size: 11px; }"
            "QToolButton:hover { background: #383838; border-color: #555555; }"
            "QToolButton:pressed { background: #444444; }"
        )

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
        shaping = geom.get("airfoil_shaping") if isinstance(geom.get("airfoil_shaping"), dict) else {}

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
    # Section Mutations & Table Cell Editing
    # -------------------------------------------------------------------------

    def _update_sections_table_cell(self, row: int, column: int) -> None:
        """Apply direct table cell edits to the underlying wing section."""
        if self._loading:
            return
        item = self.sections_table.item(row, column)
        if not item:
            return
        val = self._parse_number(item.text())
        if val is None:
            return
        sections = self._get_sections()
        if not (0 <= row < len(sections)):
            return

        sec = sections[row]
        if column == 1:
            sec["span"] = max(val, 1.0)
        elif column == 2 and row == 0:
            sec["root_chord"] = max(val, 1.0)
        elif column == 3:
            sec["tip_chord"] = max(val, 1.0)
            if row + 1 < len(sections):
                sections[row + 1]["root_chord"] = sec["tip_chord"]
        elif column == 4:
            sec["sweep"] = float(val)
        elif column == 5:
            sec["dihedral"] = float(val)
        elif column == 6:
            sec["twist"] = float(val)
        else:
            return

        sw_loc = getattr(self, "_sweep_loc", 0.25)
        new_profiles = sections_to_profiles(sections, self._profiles()[0], sw_loc)

        def change() -> None:
            self._component["parameters"]["geometry"]["profiles"] = new_profiles

        self._edit_component(f"Edit section {row + 1} table cell", change)
        self._populate_sections()
        self.sections_table.selectRow(row)
        self._refresh_planform_table()
        self._load_section(row)

    def _on_section_planform_changed(self, new_metrics: dict[str, float]) -> None:
        if self._loading:
            return
        idx = getattr(self, "_section_index", -1)
        if idx < 0:
            return
        sections = self._get_sections()
        if not (0 <= idx < len(sections)):
            return

        sec = sections[idx]
        sec["span"] = new_metrics["span"]
        sec["root_chord"] = new_metrics["root_chord"]
        sec["tip_chord"] = new_metrics["tip_chord"]

        if idx + 1 < len(sections):
            sections[idx + 1]["root_chord"] = sec["tip_chord"]
        if idx > 0:
            sections[idx - 1]["tip_chord"] = sec["root_chord"]

        sw_loc = getattr(self, "_sweep_loc", 0.25)
        new_profiles = sections_to_profiles(sections, self._profiles()[0], sw_loc)

        def change() -> None:
            self._component["parameters"]["geometry"]["profiles"] = new_profiles

        self._edit_component(f"Resize section {idx + 1}", change)
        self._populate_sections()
        self.sections_table.selectRow(idx)
        self._refresh_planform_table()
        if hasattr(self, "_sync_control_surfaces_with_wing"):
            self._sync_control_surfaces_with_wing()

    def _on_section_angle_changed(self, key: str, value: float) -> None:
        if self._loading:
            return
        idx = getattr(self, "_section_index", -1)
        if idx < 0:
            return
        sections = self._get_sections()
        if not (0 <= idx < len(sections)):
            return

        sections[idx][key] = value
        sw_loc = getattr(self, "_sweep_loc", 0.25)
        new_profiles = sections_to_profiles(sections, self._profiles()[0], sw_loc)

        def change() -> None:
            self._component["parameters"]["geometry"]["profiles"] = new_profiles

        self._edit_component(f"Change section {idx + 1} {key}", change)
        self._populate_sections()
        self.sections_table.selectRow(idx)
        self._refresh_planform_table()

    def _on_section_sweep_loc_changed(self, val_str: str) -> None:
        if self._loading:
            return
        idx = getattr(self, "_section_index", -1)
        if idx < 0:
            return
        sections = self._get_sections()
        if not (0 <= idx < len(sections)):
            return

        try:
            sections[idx]["sweep_loc"] = float(val_str)
        except ValueError:
            sections[idx]["sweep_loc"] = 0.25

        sw_loc = getattr(self, "_sweep_loc", 0.25)
        new_profiles = sections_to_profiles(sections, self._profiles()[0], sw_loc)

        def change() -> None:
            self._component["parameters"]["geometry"]["profiles"] = new_profiles

        self._edit_component(f"Change section {idx + 1} sweep location", change)
        self._populate_sections()
        self.sections_table.selectRow(idx)
        self._refresh_planform_table()

    def _split_section(self) -> None:
        idx = getattr(self, "_section_index", -1)
        if idx < 0:
            return
        profiles = self._profiles()
        sw_loc = getattr(self, "_sweep_loc", 0.25)
        new_profiles = split_section(profiles, idx, sw_loc)

        def change() -> None:
            self._component["parameters"]["geometry"]["profiles"] = new_profiles

        self._edit_component("Split wing section", change)
        self._populate_sections()
        self.sections_table.selectRow(idx)
        self._load_section(idx)
        self._refresh_planform_table()

    def _insert_section(self) -> None:
        profiles = self._profiles()
        sw_loc = getattr(self, "_sweep_loc", 0.25)
        new_profiles = insert_section(profiles, sw_loc)
        insert_idx = len(new_profiles) - 2

        def change() -> None:
            self._component["parameters"]["geometry"]["profiles"] = new_profiles

        self._edit_component("Insert wing section", change)
        self._populate_sections()
        self.sections_table.selectRow(insert_idx)
        self._load_section(insert_idx)
        self._refresh_planform_table()

    def _delete_section(self) -> None:
        idx = getattr(self, "_section_index", -1)
        if idx < 0:
            return
        profiles = self._profiles()
        sw_loc = getattr(self, "_sweep_loc", 0.25)
        new_profiles = delete_section(profiles, idx, sw_loc)
        new_idx = max(0, min(idx, len(new_profiles) - 2))

        def change() -> None:
            self._component["parameters"]["geometry"]["profiles"] = new_profiles

        self._edit_component("Delete wing section", change)
        self._populate_sections()
        self.sections_table.selectRow(new_idx)
        self._load_section(new_idx)
        self._refresh_planform_table()

    def _open_section_airfoil_dialog(self, is_root: bool) -> None:
        idx = getattr(self, "_section_index", -1)
        if idx < 0:
            return
        sections = self._get_sections()
        if not (0 <= idx < len(sections)):
            return

        comp_id = str(self._component.get("id") or "")
        station_idx = idx if is_root else idx + 1
        self._api.set_section_selection((comp_id, 2, station_idx))

        key = "root_airfoil" if is_root else "tip_airfoil"
        curr_af = sections[idx].get(key, "2412")

        dialog = AirfoilDialog(curr_af, self)
        if dialog.exec() == AirfoilDialog.DialogCode.Accepted:
            new_af, apply_all = dialog.get_selected_airfoil()
            if apply_all:
                for s in sections:
                    s["root_airfoil"] = deepcopy(new_af)
                    s["tip_airfoil"] = deepcopy(new_af)
            else:
                sections[idx][key] = deepcopy(new_af)
                if key == "tip_airfoil" and idx + 1 < len(sections):
                    sections[idx + 1]["root_airfoil"] = deepcopy(new_af)
                elif key == "root_airfoil" and idx > 0:
                    sections[idx - 1]["tip_airfoil"] = deepcopy(new_af)

            sw_loc = getattr(self, "_sweep_loc", 0.25)
            new_profiles = sections_to_profiles(sections, self._profiles()[0], sw_loc)

            def change() -> None:
                self._component["parameters"]["geometry"]["profiles"] = new_profiles

            self._edit_component(f"Apply airfoil to section {idx + 1}", change)
            self._populate_sections()
            self.sections_table.selectRow(idx)
            self._load_section(idx)
            self._api.set_section_selection((comp_id, 2, station_idx))

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
