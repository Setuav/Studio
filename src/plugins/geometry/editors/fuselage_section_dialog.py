"""Interactive 2D Fuselage Cross-Section Inspector and Profile Editor Dialog."""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.widget.button import set_button_role, set_native_button
from setuav_studio.ui.widget.spinbox import (
    NoWheelComboBox,
    set_table_spinbox,
)
from setuav_studio.ui.widget.table import ExpressionPropertyCell
from setuav_studio_sdk import StudioAPI

from ..settings import _EDITOR_AUTO_FIT_KEY, _EDITOR_GRID_KEY, _as_bool, editor_setting
from .fuselage_canvas import FuselageCanvasWidget
from .fuselage_commands import (
    AddVertexCommand,
    ChangeProfileTypeCommand,
    ChangePropertyCommand,
    DeleteVertexCommand,
    MoveVertexCommand,
)


class FuselageSectionDialog(QDialog):
    """Detailed 2D cross-section inspector and interactive profile editor dialog with Undo/Redo."""

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        segment_index: int = 0,
        section_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._component = component
        self._original_component = copy.deepcopy(component)
        self._segment_index = segment_index
        self._section_index = section_index
        self._loading = False
        self._auto_fit_sections = _as_bool(
            editor_setting(_EDITOR_AUTO_FIT_KEY, True),
            True,
        )

        # Dedicated QUndoStack for interactive 2D editing
        self.undo_stack = QUndoStack(self)

        self.setWindowTitle(f"Fuselage Section Inspector — {component.get('name', 'Fuselage')}")
        self.setMinimumSize(900, 600)
        self.resize(980, 650)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Top Section Navigator Bar
        nav_bar = QWidget()
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)

        nav_layout.addWidget(QLabel("Segment:"))
        self.segment_combo = NoWheelComboBox()
        self.segment_combo.currentIndexChanged.connect(self._on_segment_combo_changed)
        nav_layout.addWidget(self.segment_combo)

        nav_layout.addSpacing(16)

        self.prev_btn = QToolButton()
        self.prev_btn.setIcon(get_icon("fa6s.chevron-left"))
        self.prev_btn.setToolTip("Previous Section")
        self.prev_btn.clicked.connect(self._on_prev_section)
        nav_layout.addWidget(self.prev_btn)

        self.section_label = QLabel("Section 1 of 1")
        nav_layout.addWidget(self.section_label)

        self.next_btn = QToolButton()
        self.next_btn.setIcon(get_icon("fa6s.chevron-right"))
        self.next_btn.setToolTip("Next Section")
        self.next_btn.clicked.connect(self._on_next_section)
        nav_layout.addWidget(self.next_btn)

        nav_layout.addStretch()
        main_layout.addWidget(nav_bar)

        # 2. Main Horizontal Splitter (Left: Controls, Right: Canvas)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 8, 0)
        self._scroll_layout.setSpacing(10)

        # Group A: Profile Definition
        prof_box = QGroupBox("Profile Definition")
        prof_layout = QVBoxLayout(prof_box)
        prof_layout.setSpacing(6)

        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Profile Type:"))
        self.profile_type_combo = NoWheelComboBox()
        self.profile_type_combo.addItems(
            [
                "circle",
                "ellipse",
                "rectangle",
                "trapezoid",
                "triangle",
                "polygon",
            ]
        )
        self.profile_type_combo.currentTextChanged.connect(self._on_profile_type_changed)
        type_layout.addWidget(self.profile_type_combo)
        prof_layout.addLayout(type_layout)

        self.props_table = QTableWidget(0, 2)
        self.props_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.props_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.props_table.cellChanged.connect(self._on_prop_table_cell_changed)
        prof_layout.addWidget(self.props_table)

        # Polygon vertices table
        self.poly_box = QWidget()
        poly_layout = QVBoxLayout(self.poly_box)
        poly_layout.setContentsMargins(0, 0, 0, 0)
        poly_layout.setSpacing(4)
        poly_layout.addWidget(QLabel("Polygon Vertices (Interactive on Canvas):"))

        self.vertices_table = QTableWidget(0, 3)
        self.vertices_table.setHorizontalHeaderLabels(["Y", "Z", "Radius"])
        self.vertices_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.vertices_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.vertices_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.vertices_table.cellChanged.connect(self._on_vertices_cell_changed)
        self.vertices_table.currentCellChanged.connect(self._on_vertices_row_selected)
        poly_layout.addWidget(self.vertices_table)

        v_actions = QHBoxLayout()
        self.add_v_btn = QToolButton()
        set_native_button(self.add_v_btn, "add")
        self.add_v_btn.setToolTip("Add Vertex")
        self.add_v_btn.clicked.connect(self._add_polygon_vertex)
        self.del_v_btn = QToolButton()
        set_native_button(self.del_v_btn, "remove")
        self.del_v_btn.setToolTip("Delete Vertex (Delete key)")
        self.del_v_btn.clicked.connect(self._delete_polygon_vertex)
        v_actions.addWidget(self.add_v_btn)
        v_actions.addWidget(self.del_v_btn)
        v_actions.addStretch()
        poly_layout.addLayout(v_actions)

        prof_layout.addWidget(self.poly_box)
        self._scroll_layout.addWidget(prof_box)

        # Group B: Transform
        trans_box = QGroupBox("Section Transform")
        trans_layout = QVBoxLayout(trans_box)
        self.trans_table = QTableWidget(2, 3)
        self.trans_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.trans_table.setVerticalHeaderLabels(["Position", "Rotation"])
        self.trans_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trans_table.verticalHeader().setDefaultSectionSize(24)
        self.trans_table.setFixedHeight(75)
        for r in range(2):
            for c in range(3):
                item = QTableWidgetItem("0.0")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.trans_table.setItem(r, c, item)
        self.trans_table.cellChanged.connect(self._on_transform_cell_changed)
        trans_layout.addWidget(self.trans_table)
        self._scroll_layout.addWidget(trans_box)

        # Group C: Display Options
        disp_box = QGroupBox("Display Options")
        disp_layout = QVBoxLayout(disp_box)
        disp_layout.setSpacing(4)

        self.cb_prev = QCheckBox("Show Previous Section (Ghost)")
        self.cb_prev.setChecked(True)
        self.cb_prev.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_prev)

        self.cb_next = QCheckBox("Show Next Section (Ghost)")
        self.cb_next.setChecked(True)
        self.cb_next.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_next)

        self.cb_dims = QCheckBox("Show Dimension Annotations")
        self.cb_dims.setChecked(True)
        self.cb_dims.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_dims)

        self.cb_cg = QCheckBox("Show Centroid (CG)")
        self.cb_cg.setChecked(True)
        self.cb_cg.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_cg)

        self.cb_grid = QCheckBox("Show Grid & Coordinate Axes")
        self.cb_grid.setChecked(_as_bool(editor_setting(_EDITOR_GRID_KEY, True), True))
        self.cb_grid.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_grid)

        self.cb_radial = QCheckBox("Show 128 Radial Sample Points")
        self.cb_radial.setChecked(False)
        self.cb_radial.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_radial)

        self._scroll_layout.addWidget(disp_box)
        self._scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        splitter.addWidget(left_widget)

        # Right Panel (2D Canvas + Metrics Panel)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Canvas Toolbar (Undo, Redo, Zoom, Pan controls)
        canvas_bar = QWidget()
        c_layout = QHBoxLayout(canvas_bar)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(4)

        # Undo Action & Button
        self.undo_btn = QToolButton()
        self.undo_btn.setIcon(get_icon("fa6s.rotate-left"))
        self.undo_btn.setToolTip("Undo (Ctrl+Z)")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo_stack.undo)
        c_layout.addWidget(self.undo_btn)

        # Redo Action & Button
        self.redo_btn = QToolButton()
        self.redo_btn.setIcon(get_icon("fa6s.rotate-right"))
        self.redo_btn.setToolTip("Redo (Ctrl+Y)")
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.undo_stack.redo)
        c_layout.addWidget(self.redo_btn)

        self.undo_stack.canUndoChanged.connect(self.undo_btn.setEnabled)
        self.undo_stack.canRedoChanged.connect(self.redo_btn.setEnabled)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        c_layout.addWidget(sep1)

        fit_btn = QToolButton()
        fit_btn.setIcon(get_icon("fit"))
        fit_btn.setToolTip("Fit View (Reset Camera)")
        fit_btn.clicked.connect(self._on_fit_view)
        c_layout.addWidget(fit_btn)

        zin_btn = QToolButton()
        zin_btn.setIcon(get_icon("fa6s.magnifying-glass-plus"))
        zin_btn.setToolTip("Zoom In")
        zin_btn.clicked.connect(self._on_zoom_in)
        c_layout.addWidget(zin_btn)

        zout_btn = QToolButton()
        zout_btn.setIcon(get_icon("fa6s.magnifying-glass-minus"))
        zout_btn.setToolTip("Zoom Out")
        zout_btn.clicked.connect(self._on_zoom_out)
        c_layout.addWidget(zout_btn)

        c_layout.addStretch()
        right_layout.addWidget(canvas_bar)

        self.canvas = FuselageCanvasWidget()
        self.canvas.vertexSelected.connect(self._on_canvas_vertex_selected)
        self.canvas.vertexMoved.connect(self._on_canvas_vertex_moved)
        self.canvas.vertexDragFinished.connect(self._on_canvas_vertex_drag_finished)
        self.canvas.vertexInserted.connect(self._on_canvas_vertex_inserted)
        self.canvas.vertexDeleteRequested.connect(self._delete_polygon_vertex)
        self.canvas.undoRequested.connect(self.undo_stack.undo)
        self.canvas.redoRequested.connect(self.undo_stack.redo)

        right_layout.addWidget(self.canvas, 1)

        # Metrics Card
        metrics_box = QGroupBox("Section Properties & Engineering Metrics")
        m_layout = QGridLayout(metrics_box)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setHorizontalSpacing(20)
        m_layout.setVerticalSpacing(4)

        self.lbl_area = QLabel("Area: 0.0 mm²")
        self.lbl_perim = QLabel("Perimeter: 0.0 mm")
        self.lbl_dims = QLabel("Dimensions (W × H): 0.0 × 0.0 mm")
        self.lbl_aspect = QLabel("Aspect Ratio (W/H): 0.00")
        self.lbl_cg = QLabel("Centroid (Y, Z): (0.0, 0.0) mm")
        self.lbl_dh = QLabel("Hydraulic Diameter (Dh): 0.0 mm")

        m_layout.addWidget(self.lbl_area, 0, 0)
        m_layout.addWidget(self.lbl_perim, 0, 1)
        m_layout.addWidget(self.lbl_dims, 1, 0)
        m_layout.addWidget(self.lbl_aspect, 1, 1)
        m_layout.addWidget(self.lbl_cg, 2, 0)
        m_layout.addWidget(self.lbl_dh, 2, 1)

        right_layout.addWidget(metrics_box)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        main_layout.addWidget(splitter, 1)

        # 3. Bottom Action Buttons
        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)

        btn_layout.addStretch()

        self.apply_btn = QPushButton("Apply")
        set_native_button(self.apply_btn, "fa6s.check")
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.apply_btn)

        self.ok_btn = QPushButton("Save & Close")
        set_button_role(self.ok_btn, "primary", "fa6s.floppy-disk")
        self.ok_btn.clicked.connect(self._on_ok_clicked)
        btn_layout.addWidget(self.ok_btn)

        self.close_btn = QPushButton("Cancel")
        self.close_btn.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.close_btn)

        main_layout.addWidget(btn_bar)

        self._populate_segments()
        self._load_section(auto_fit=self._auto_fit_sections)

    # -------------------------------------------------------------------------
    # Population & Section Loading
    # -------------------------------------------------------------------------
    def _segments(self) -> list[dict[str, Any]]:
        params = self._component.get("parameters")
        params = params if isinstance(params, dict) else {}
        geom = params.get("geometry")
        geom = geom if isinstance(geom, dict) else {}
        segs = geom.get("segments")
        if not isinstance(segs, list):
            segs = []
            geom["segments"] = segs
            params["geometry"] = geom
            self._component["parameters"] = params
        return [s for s in segs if isinstance(s, dict)]

    def _current_segment(self) -> dict[str, Any] | None:
        segs = self._segments()
        if 0 <= self._segment_index < len(segs):
            return segs[self._segment_index]
        return None

    def _sections(self) -> list[dict[str, Any]]:
        seg = self._current_segment()
        if not seg:
            return []
        secs = seg.get("sections")
        if not isinstance(secs, list):
            secs = []
            seg["sections"] = secs
        return [s for s in secs if isinstance(s, dict)]

    def _current_section(self) -> dict[str, Any] | None:
        secs = self._sections()
        if 0 <= self._section_index < len(secs):
            return secs[self._section_index]
        return None

    def _populate_segments(self) -> None:
        self._loading = True
        self.segment_combo.clear()
        segs = self._segments()
        for idx, seg in enumerate(segs):
            tag = str(seg.get("tag") or f"Segment {idx + 1}")
            self.segment_combo.addItem(f"{idx + 1}: {tag}")
        if 0 <= self._segment_index < len(segs):
            self.segment_combo.setCurrentIndex(self._segment_index)
        self._loading = False

    def _load_section(self, auto_fit: bool = False) -> None:
        self._loading = True
        secs = self._sections()
        num_secs = len(secs)

        if num_secs == 0:
            self.section_label.setText("No Sections")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self._loading = False
            return

        self._section_index = max(0, min(self._section_index, num_secs - 1))
        sec = secs[self._section_index]

        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        pos = sec.get("position", {}) if isinstance(sec.get("position"), dict) else {}
        x_val = float(pos.get("x", 0.0))
        disp_x = um.to_display(x_val, "length")
        l_sym = um.get_unit_symbol("length")
        self.section_label.setText(
            f"Section {self._section_index + 1} of {num_secs} (X = {disp_x:.1f} {l_sym})"
        )

        self.prev_btn.setEnabled(self._section_index > 0)
        self.next_btn.setEnabled(self._section_index < num_secs - 1)

        prof = sec.get("profile", {}) if isinstance(sec.get("profile"), dict) else {}
        prof_type = str(prof.get("type", "circle")).lower()

        idx = self.profile_type_combo.findText(prof_type)
        if idx >= 0:
            self.profile_type_combo.setCurrentIndex(idx)

        self._populate_props_table(prof)
        self._populate_transform_table(sec)

        prev_prof = (
            secs[self._section_index - 1].get("profile") if self._section_index > 0 else None
        )
        next_prof = (
            secs[self._section_index + 1].get("profile")
            if self._section_index < num_secs - 1
            else None
        )

        title_str = f"Sec {self._section_index + 1} / {num_secs}"
        self.canvas.set_section_data(
            prof, prev_prof, next_prof, title_info=title_str, auto_fit=auto_fit
        )
        self._update_metrics_labels()
        self._loading = False

    def _populate_props_table(self, profile: dict[str, Any]) -> None:
        prof_type = str(profile.get("type", "circle")).lower()
        self.props_table.setRowCount(0)

        is_polygon = prof_type == "polygon"
        self.poly_box.setVisible(is_polygon)
        self.props_table.setVisible(not is_polygon)

        if prof_type == "circle":
            self._add_prop_row("Diameter", profile.get("diameter", 100.0), "diameter")
        elif prof_type == "ellipse":
            self._add_prop_row("Width", profile.get("width", 120.0), "width")
            self._add_prop_row("Height", profile.get("height", 80.0), "height")
        elif prof_type == "rectangle":
            self._add_prop_row("Width", profile.get("width", 120.0), "width")
            self._add_prop_row("Height", profile.get("height", 80.0), "height")
            self._add_prop_row("Corner Radius", profile.get("corner_radius", 10.0), "corner_radius")
        elif prof_type == "trapezoid":
            self._add_prop_row("Top Width", profile.get("top_width", 80.0), "top_width")
            self._add_prop_row("Bottom Width", profile.get("bottom_width", 120.0), "bottom_width")
            self._add_prop_row("Height", profile.get("height", 80.0), "height")
            self._add_prop_row("Corner Radius", profile.get("corner_radius", 5.0), "corner_radius")
        elif prof_type == "triangle":
            self._add_prop_row("Base Width", profile.get("base_width", 100.0), "base_width")
            self._add_prop_row("Height", profile.get("height", 80.0), "height")
            self._add_prop_row("Corner Radius", profile.get("corner_radius", 5.0), "corner_radius")
            self._add_prop_row("Orientation", profile.get("orientation", "up"), "orientation")
        elif prof_type == "polygon":
            self._populate_vertices_table(profile)

    def _add_prop_row(self, label: str, value: Any, key: str) -> None:
        row = self.props_table.rowCount()
        self.props_table.insertRow(row)

        lbl_item = QTableWidgetItem(label)
        lbl_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        lbl_item.setData(Qt.ItemDataRole.UserRole, key)
        self.props_table.setItem(row, 0, lbl_item)

        if key == "orientation":
            combo = NoWheelComboBox(self.props_table)
            combo.addItems(["up", "down"])
            combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(lambda txt, k=key: self._on_prop_spin_changed(k, txt))
            self.props_table.setCellWidget(row, 1, combo)
        else:
            try:
                num_val = float(value)
            except (ValueError, TypeError):
                num_val = 0.0
            step_val = (
                5.0 if any(sub in key for sub in ("width", "height", "diameter", "radius")) else 1.0
            )
            set_table_spinbox(
                self.props_table,
                row,
                1,
                num_val,
                min_val=0.0,
                step=step_val,
                decimals=2,
                quantity="length",
                suffix="mm",
                on_changed=lambda _v, k=key: self._on_prop_spin_changed(k, _v),
            )

    def _on_prop_spin_changed(self, key: str, new_val: Any) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict):
            return
        old_val = prof.get(key)
        if old_val == new_val:
            return
        cmd = ChangePropertyCommand(self, key, old_val, new_val)
        self.undo_stack.push(cmd)

    def _populate_vertices_table(self, profile: dict[str, Any]) -> None:
        self.vertices_table.setRowCount(0)
        raw_v = profile.get("vertices")
        if not isinstance(raw_v, list):
            return

        for _r, v in enumerate(raw_v):
            if not isinstance(v, dict):
                continue
            row = self.vertices_table.rowCount()
            self.vertices_table.insertRow(row)

            set_table_spinbox(
                self.vertices_table,
                row,
                0,
                float(v.get("y", 0.0)),
                step=1.0,
                decimals=2,
                quantity="length",
                suffix="mm",
                on_changed=lambda val, row_idx=row: self._on_vertex_cell_spin_changed(
                    row_idx, "y", val
                ),
            )
            set_table_spinbox(
                self.vertices_table,
                row,
                1,
                float(v.get("z", 0.0)),
                step=1.0,
                decimals=2,
                quantity="length",
                suffix="mm",
                on_changed=lambda val, row_idx=row: self._on_vertex_cell_spin_changed(
                    row_idx, "z", val
                ),
            )
            set_table_spinbox(
                self.vertices_table,
                row,
                2,
                float(v.get("radius", 0.0)),
                min_val=0.0,
                step=0.5,
                decimals=2,
                quantity="length",
                suffix="mm",
                on_changed=lambda val, row_idx=row: self._on_vertex_cell_spin_changed(
                    row_idx, "radius", val
                ),
            )

        # Restore row selection if any
        if (
            self.canvas.selected_vertex_index is not None
            and 0 <= self.canvas.selected_vertex_index < len(raw_v)
        ):
            self.vertices_table.selectRow(self.canvas.selected_vertex_index)

    def _on_vertex_cell_spin_changed(self, row: int, key: str, value: float) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list) or not (0 <= row < len(verts)):
            return
        old_val = float(verts[row].get(key, 0.0))
        if abs(value - old_val) < 1e-4:
            return
        verts[row][key] = float(value)
        self._refresh_canvas_and_metrics()

    def _populate_transform_table(self, section: dict[str, Any]) -> None:
        pos = section.get("position", {}) if isinstance(section.get("position"), dict) else {}
        rot = section.get("rotation", {}) if isinstance(section.get("rotation"), dict) else {}

        rotation_aliases = {"x": "roll", "y": "pitch", "z": "yaw"}
        for col, axis in enumerate(("x", "y", "z")):
            set_table_spinbox(
                self.trans_table,
                0,
                col,
                float(pos.get(axis, 0.0)),
                step=5.0,
                decimals=2,
                quantity="length",
                suffix="mm",
                on_changed=lambda _v: self._on_transform_spinbox_changed(),
            )
            set_table_spinbox(
                self.trans_table,
                1,
                col,
                float(rot.get(axis, rot.get(rotation_aliases[axis], 0.0))),
                min_val=-360.0,
                max_val=360.0,
                step=1.0,
                decimals=2,
                quantity="angle",
                suffix="°",
                on_changed=lambda _v: self._on_transform_spinbox_changed(),
            )

    def _on_transform_spinbox_changed(self) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        pos = sec.get("position") if isinstance(sec.get("position"), dict) else {}
        rotation: dict[str, float] = {}

        for col, axis in enumerate(("x", "y", "z")):
            w_pos = self.trans_table.cellWidget(0, col)
            if isinstance(w_pos, (QDoubleSpinBox, ExpressionPropertyCell)):
                pos[axis] = float(w_pos.value())
            w_rot = self.trans_table.cellWidget(1, col)
            if isinstance(w_rot, (QDoubleSpinBox, ExpressionPropertyCell)):
                rotation[axis] = float(w_rot.value())
        sec["position"] = pos
        sec["rotation"] = rotation
        self._refresh_canvas_and_metrics()

    def _update_metrics_labels(self) -> None:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        l_sym = um.get_unit_symbol("length")
        a_sym = um.get_unit_symbol("area")

        m = self.canvas._metrics
        if not m or m.get("area", 0) <= 0:
            self.lbl_area.setText(f"Area: 0.0 {a_sym}")
            self.lbl_perim.setText(f"Perimeter: 0.0 {l_sym}")
            self.lbl_dims.setText(f"Dimensions (W × H): 0.0 × 0.0 {l_sym}")
            self.lbl_aspect.setText("Aspect Ratio (W/H): 0.00")
            self.lbl_cg.setText(f"Centroid (Y, Z): (0.0, 0.0) {l_sym}")
            self.lbl_dh.setText(f"Hydraulic Diameter (Dh): 0.0 {l_sym}")
            return

        area_mm2 = m["area"]
        area_dm2 = area_mm2 / 10000.0
        disp_area = um.to_display(area_dm2, "area")
        disp_perim = um.to_display(m["perimeter"], "length")
        disp_w = um.to_display(m["width"], "length")
        disp_h = um.to_display(m["height"], "length")
        disp_ycg = um.to_display(m["y_cg"], "length")
        disp_zcg = um.to_display(m["z_cg"], "length")
        disp_dh = um.to_display(m["hydraulic_diam"], "length")

        self.lbl_area.setText(f"Area: {disp_area:,.3f} {a_sym}")
        self.lbl_perim.setText(f"Perimeter: {disp_perim:,.1f} {l_sym}")
        self.lbl_dims.setText(f"Dimensions (W × H): {disp_w:.1f} × {disp_h:.1f} {l_sym}")
        self.lbl_aspect.setText(f"Aspect Ratio (W/H): {m['aspect_ratio']:.2f}")
        self.lbl_cg.setText(f"Centroid (Y, Z): ({disp_ycg:.1f}, {disp_zcg:.1f}) {l_sym}")
        self.lbl_dh.setText(f"Hydraulic Diameter (Dh): {disp_dh:.1f} {l_sym}")

    # -------------------------------------------------------------------------
    # Undo / Redo Internal Application Methods
    # -------------------------------------------------------------------------
    def _apply_vertex_pos(self, vertex_idx: int, y: float, z: float) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if isinstance(verts, list) and 0 <= vertex_idx < len(verts):
            verts[vertex_idx]["y"] = y
            verts[vertex_idx]["z"] = z
            self._loading = True
            if vertex_idx < self.vertices_table.rowCount():
                wy = self.vertices_table.cellWidget(vertex_idx, 0)
                if isinstance(wy, (QDoubleSpinBox, ExpressionPropertyCell)):
                    wy.setValue(y)
                wz = self.vertices_table.cellWidget(vertex_idx, 1)
                if isinstance(wz, (QDoubleSpinBox, ExpressionPropertyCell)):
                    wz.setValue(z)
            self._loading = False
            self._refresh_canvas_and_metrics()

    def _insert_vertex_internal(self, insert_idx: int, vertex_data: dict[str, float]) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list):
            verts = []
            prof["vertices"] = verts
        insert_idx = max(0, min(insert_idx, len(verts)))
        verts.insert(insert_idx, copy.deepcopy(vertex_data))
        self.canvas.selected_vertex_index = insert_idx
        self._populate_vertices_table(prof)
        self._refresh_canvas_and_metrics()

    def _remove_vertex_internal(self, delete_idx: int) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if isinstance(verts, list) and 0 <= delete_idx < len(verts):
            verts.pop(delete_idx)
            self.canvas.selected_vertex_index = min(delete_idx, len(verts) - 1) if verts else None
            self._populate_vertices_table(prof)
            self._refresh_canvas_and_metrics()

    def _apply_profile_property(self, key: str, value: Any) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict):
            return
        prof[key] = value
        self._populate_props_table(prof)
        self._refresh_canvas_and_metrics()

    def _apply_full_profile(self, profile: dict[str, Any]) -> None:
        sec = self._current_section()
        if not sec:
            return
        sec["profile"] = copy.deepcopy(profile)
        prof_type = str(profile.get("type", "circle")).lower()
        idx = self.profile_type_combo.findText(prof_type)
        self._loading = True
        if idx >= 0:
            self.profile_type_combo.setCurrentIndex(idx)
        self._populate_props_table(profile)
        self._loading = False
        self._refresh_canvas_and_metrics()

    # -------------------------------------------------------------------------
    # Interactive Canvas Signals
    # -------------------------------------------------------------------------
    def _on_canvas_vertex_selected(self, index: int) -> None:
        if 0 <= index < self.vertices_table.rowCount():
            self._loading = True
            self.vertices_table.selectRow(index)
            self._loading = False

    def _on_canvas_vertex_moved(self, index: int, y: float, z: float) -> None:
        if 0 <= index < self.vertices_table.rowCount():
            self._loading = True
            wy = self.vertices_table.cellWidget(index, 0)
            if isinstance(wy, (QDoubleSpinBox, ExpressionPropertyCell)):
                wy.setValue(y)
            wz = self.vertices_table.cellWidget(index, 1)
            if isinstance(wz, (QDoubleSpinBox, ExpressionPropertyCell)):
                wz.setValue(z)
            self._loading = False
            self._update_metrics_labels()

    def _on_canvas_vertex_drag_finished(
        self, index: int, old_y: float, old_z: float, new_y: float, new_z: float
    ) -> None:
        cmd = MoveVertexCommand(self, index, (old_y, old_z), (new_y, new_z))
        self.undo_stack.push(cmd)

    def _on_canvas_vertex_inserted(self, insert_idx: int, y: float, z: float) -> None:
        v_data = {"y": y, "z": z, "radius": 0.0}
        cmd = AddVertexCommand(self, insert_idx, v_data)
        self.undo_stack.push(cmd)

    def _on_vertices_row_selected(self, row: int, _column: int, *_previous: int) -> None:
        if self._loading:
            return
        self.canvas.set_selected_vertex(row if row >= 0 else None)

    # -------------------------------------------------------------------------
    # Navigation & Table Change Handlers
    # -------------------------------------------------------------------------
    def _on_segment_combo_changed(self, index: int) -> None:
        if self._loading:
            return
        self._segment_index = index
        self._section_index = 0
        self._load_section(auto_fit=self._auto_fit_sections)

    def _on_prev_section(self) -> None:
        if self._section_index > 0:
            self._section_index -= 1
            self._load_section(auto_fit=False)

    def _on_next_section(self) -> None:
        if self._section_index < len(self._sections()) - 1:
            self._section_index += 1
            self._load_section(auto_fit=False)

    def _on_profile_type_changed(self, new_type: str) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        old_prof = copy.deepcopy(sec.get("profile", {}))
        new_prof = copy.deepcopy(old_prof)
        new_prof["type"] = new_type

        if new_type == "circle" and "diameter" not in new_prof:
            new_prof["diameter"] = 100.0
        elif new_type in ("ellipse", "rectangle") and (
            "width" not in new_prof or "height" not in new_prof
        ):
            new_prof["width"] = 120.0
            new_prof["height"] = 80.0
            if new_type == "rectangle":
                new_prof["corner_radius"] = 10.0
        elif new_type == "trapezoid" and "top_width" not in new_prof:
            new_prof["top_width"] = 80.0
            new_prof["bottom_width"] = 120.0
            new_prof["height"] = 80.0
            new_prof["corner_radius"] = 5.0
        elif new_type == "triangle" and "base_width" not in new_prof:
            new_prof["base_width"] = 100.0
            new_prof["height"] = 80.0
            new_prof["corner_radius"] = 5.0
            new_prof["orientation"] = "up"
        elif new_type == "polygon" and "vertices" not in new_prof:
            new_prof["vertices"] = [
                {"y": -50.0, "z": -40.0, "radius": 10.0},
                {"y": 50.0, "z": -40.0, "radius": 10.0},
                {"y": 60.0, "z": 40.0, "radius": 15.0},
                {"y": -60.0, "z": 40.0, "radius": 15.0},
            ]

        cmd = ChangeProfileTypeCommand(self, old_prof, new_prof)
        self.undo_stack.push(cmd)

    def _on_prop_table_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict):
            return

        key_item = self.props_table.item(row, 0)
        val_item = self.props_table.item(row, 1)
        if not key_item or not val_item:
            return

        key = key_item.data(Qt.ItemDataRole.UserRole)
        val_text = val_item.text().strip()
        old_val = prof.get(key)

        try:
            new_val = float(val_text)
        except ValueError:
            new_val = val_text

        if old_val == new_val:
            return

        cmd = ChangePropertyCommand(self, key, old_val, new_val)
        self.undo_stack.push(cmd)

    def _on_vertices_cell_changed(self, row: int, column: int) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list) or not (0 <= row < len(verts)):
            return

        item = self.vertices_table.item(row, column)
        if not item:
            return

        try:
            val = float(item.text())
        except ValueError:
            val = 0.0

        key = ["y", "z", "radius"][column]
        old_val = verts[row].get(key, 0.0)
        if abs(val - old_val) < 1e-4:
            return

        verts[row][key] = val
        self._refresh_canvas_and_metrics()

    def _add_polygon_vertex(self) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list):
            verts = []
            prof["vertices"] = verts

        # If a vertex is selected, insert after it, else append
        curr_row = self.vertices_table.currentRow()
        insert_idx = (curr_row + 1) if 0 <= curr_row < len(verts) else len(verts)

        # Default position: offset from previous or (0, 0)
        if verts and 0 <= curr_row < len(verts):
            ref_y = float(verts[curr_row].get("y", 0.0))
            ref_z = float(verts[curr_row].get("z", 0.0))
            v_data = {"y": round(ref_y + 10.0, 1), "z": round(ref_z + 10.0, 1), "radius": 0.0}
        else:
            v_data = {"y": 0.0, "z": 0.0, "radius": 0.0}

        cmd = AddVertexCommand(self, insert_idx, v_data)
        self.undo_stack.push(cmd)

    def _delete_polygon_vertex(self, delete_idx: int | None = None) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list) or len(verts) <= 3:
            return

        if delete_idx is None or not (0 <= delete_idx < len(verts)):
            curr_row = self.vertices_table.currentRow()
            delete_idx = curr_row if 0 <= curr_row < len(verts) else (len(verts) - 1)

        v_data = verts[delete_idx]
        cmd = DeleteVertexCommand(self, delete_idx, v_data)
        self.undo_stack.push(cmd)

    def _on_transform_cell_changed(self, row: int, column: int) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        item = self.trans_table.item(row, column)
        if not item:
            return

        try:
            val = float(item.text().strip())
        except ValueError:
            val = 0.0

        key_axis = ["x", "y", "z"][column]
        if row == 0:
            pos = sec.get("position")
            if not isinstance(pos, dict):
                pos = {}
                sec["position"] = pos
            pos[key_axis] = val
        else:
            rot = sec.get("rotation")
            if not isinstance(rot, dict):
                rot = {}
            canonical_rotation = {
                "x": float(rot.get("x", rot.get("roll", 0.0))),
                "y": float(rot.get("y", rot.get("pitch", 0.0))),
                "z": float(rot.get("z", rot.get("yaw", 0.0))),
            }
            canonical_rotation[key_axis] = val
            sec["rotation"] = canonical_rotation

    def _on_display_option_toggled(self) -> None:
        self.canvas.show_previous = self.cb_prev.isChecked()
        self.canvas.show_next = self.cb_next.isChecked()
        self.canvas.show_dimensions = self.cb_dims.isChecked()
        self.canvas.show_centroid = self.cb_cg.isChecked()
        self.canvas.show_grid = self.cb_grid.isChecked()
        self.canvas.show_radial_samples = self.cb_radial.isChecked()
        self.canvas.update()

    def _on_fit_view(self) -> None:
        self.canvas.fit_view()

    def _on_zoom_in(self) -> None:
        self.canvas.zoom_in()

    def _on_zoom_out(self) -> None:
        self.canvas.zoom_out()

    def _refresh_canvas_and_metrics(self) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile", {}) if isinstance(sec.get("profile"), dict) else {}
        secs = self._sections()
        prev_prof = (
            secs[self._section_index - 1].get("profile") if self._section_index > 0 else None
        )
        next_prof = (
            secs[self._section_index + 1].get("profile")
            if self._section_index < len(secs) - 1
            else None
        )

        title_str = f"Sec {self._section_index + 1} / {len(secs)}"
        self.canvas.set_section_data(
            prof, prev_prof, next_prof, title_info=title_str, auto_fit=False
        )
        self._update_metrics_labels()

    def _on_apply_clicked(self) -> None:
        """Trigger project mutation to update 3D scene while keeping dialog open."""
        after_data = copy.deepcopy(self._component)
        self._component.clear()
        self._component.update(self._original_component)
        self._api.edit_component(
            self._component,
            f"Edit fuselage section {self._section_index + 1}",
            lambda: self._component.update(after_data),
        )
        self._original_component = copy.deepcopy(self._component)

    def _on_ok_clicked(self) -> None:
        """Apply changes and close dialog."""
        after_data = copy.deepcopy(self._component)
        self._component.clear()
        self._component.update(self._original_component)
        self._api.edit_component(
            self._component,
            f"Edit fuselage section {self._section_index + 1}",
            lambda: self._component.update(after_data),
        )
        self.accept()

    def _on_cancel_clicked(self) -> None:
        """Discard changes and restore original component state."""
        self._component.clear()
        self._component.update(self._original_component)
        if self._api.current_project:
            self._api.edit_component(
                self._component,
                "Cancel fuselage section edit",
                lambda: None,
            )
        self.reject()
