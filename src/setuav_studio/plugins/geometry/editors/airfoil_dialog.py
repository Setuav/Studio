"""Interactive Airfoil Manager and 2D Cross-Section Preview Dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.buttons import set_button_role, set_native_button
from setuav_studio.ui.theme import tokens
from ..engine.airfoil import (
    PRESET_AIRFOILS,
    compute_airfoil_metrics,
    naca4,
    naca5,
    parse_airfoil_dat,
)


class AirfoilCanvasWidget(QWidget):
    """2D interactive canvas for previewing airfoil cross-section geometry."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens()
        self._points: tuple[tuple[float, float], ...] = ()
        self._airfoil_name: str = "NACA 2412"
        self._metrics: dict[str, float] = {}
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_airfoil(self, name: str, points: tuple[tuple[float, float], ...]) -> None:
        self._airfoil_name = name
        self._points = points
        self._metrics = compute_airfoil_metrics(points)
        self.update()

    def paintEvent(self, _event: Any) -> None:
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        bg_color = QColor(tok.get("elevated", "#ffffff" if is_light else "#1a1a1c"))
        grid_color = QColor(tok.get("grid", "#e2e4e8" if is_light else "#2d2d35"))
        chord_color = QColor(tok.get("border_strong", "#b0b4bc" if is_light else "#484852"))
        text_color = QColor(tok.get("text", "#202020" if is_light else "#e0e0e0"))
        dim_text = QColor(tok.get("text_dim", "#666666" if is_light else "#888888"))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # Background
        painter.fillRect(0, 0, width, height, bg_color)

        # Plot margins
        margin_x = 40
        margin_y = 35
        plot_w = max(width - 2 * margin_x, 100)
        plot_h = max(height - 2 * margin_y, 80)

        center_y = margin_y + plot_h / 2.0
        scale = plot_w

        # Draw grid lines
        grid_pen = QPen(grid_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        for step in (0.0, 0.25, 0.5, 0.75, 1.0):
            gx = margin_x + step * scale
            painter.drawLine(int(gx), margin_y, int(gx), margin_y + plot_h)
            # Label
            painter.setPen(dim_text)
            painter.setFont(QFont("sans-serif", 8))
            painter.drawText(int(gx) - 10, margin_y + plot_h + 14, f"{int(step * 100)}%")
            painter.setPen(grid_pen)

        # Chord line (z = 0)
        chord_pen = QPen(chord_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(chord_pen)
        painter.drawLine(margin_x, int(center_y), margin_x + plot_w, int(center_y))

        if not self._points:
            return

        # Build airfoil polygon path
        path = QPainterPath()
        poly = QPolygonF()
        for i, (x, z) in enumerate(self._points):
            px = margin_x + x * scale
            py = center_y - z * scale
            poly.append(QPointF(px, py))
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()

        # Fill & Stroke Airfoil
        from setuav_studio.ui.theme import chart_color

        series_color = QColor(chart_color("blue"))
        fill_color = QColor(series_color)
        fill_color.setAlpha(35)
        painter.fillPath(path, QBrush(fill_color))

        stroke_pen = QPen(series_color, 2.0, Qt.PenStyle.SolidLine)
        painter.strokePath(path, stroke_pen)

        # Draw Leading Edge Marker
        painter.setBrush(series_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(margin_x, center_y), 3.5, 3.5)

        # Draw Title & Quick stats
        painter.setPen(text_color)
        painter.setFont(QFont("sans-serif", 10, QFont.Weight.Bold))
        painter.drawText(margin_x, margin_y - 12, self._airfoil_name)

        if self._metrics:
            tc = self._metrics.get("max_thickness", 0.12) * 100.0
            yc = self._metrics.get("max_camber", 0.0) * 100.0
            stat_text = f"t/c: {tc:.1f}%   camber: {yc:.1f}%"
            painter.setFont(QFont("sans-serif", 8))
            painter.setPen(dim_text)
            painter.drawText(width - margin_x - 140, margin_y - 12, stat_text)


class AirfoilDialog(QDialog):
    """Dialog for choosing, generating, and previewing airfoils."""

    def __init__(
        self,
        current_airfoil: object,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens()
        self.setWindowTitle("Airfoil Selector & Manager")
        self.setMinimumSize(780, 520)
        self.resize(840, 560)

        self._selected_airfoil_data: dict[str, Any] | str = "2412"
        self._apply_all: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Main splitter (Left: Selection Tabs, Right: 2D Canvas & Metrics)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---------------------------------------------------------------------
        # Left: Tabs for Library, NACA, File Import
        # ---------------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.tabs = QTabWidget()

        # Tab 1: Library Presets
        lib_tab = QWidget()
        lib_layout = QVBoxLayout(lib_tab)
        lib_layout.setContentsMargins(8, 8, 8, 8)
        lib_layout.setSpacing(6)

        cat_layout = QHBoxLayout()
        cat_layout.addWidget(QLabel("Category:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItems([
            "All Categories",
            "General Aviation",
            "High Lift UAV",
            "Tailless & Flying Wing",
            "Symmetric & Tail",
        ])
        self.cat_combo.currentTextChanged.connect(self._filter_presets)
        cat_layout.addWidget(self.cat_combo)
        lib_layout.addLayout(cat_layout)

        self.preset_list = QListWidget()
        self.preset_list.currentItemChanged.connect(self._on_preset_selected)
        lib_layout.addWidget(self.preset_list)

        self.tabs.addTab(lib_tab, "Preset Library")

        # Tab 2: NACA Generator
        naca_tab = QWidget()
        naca_layout = QVBoxLayout(naca_tab)
        naca_layout.setContentsMargins(8, 8, 8, 8)
        naca_layout.setSpacing(8)

        naca_type_box = QGroupBox("NACA Series")
        naca_type_layout = QHBoxLayout(naca_type_box)
        self.naca4_radio = QRadioButton("4-Digit (e.g. 2412, 4415, 0012)")
        self.naca5_radio = QRadioButton("5-Digit (e.g. 23012, 24012)")
        self.naca4_radio.setChecked(True)
        self.naca4_radio.toggled.connect(self._on_naca_radio_toggled)
        naca_type_layout.addWidget(self.naca4_radio)
        naca_type_layout.addWidget(self.naca5_radio)
        naca_layout.addWidget(naca_type_box)

        code_layout = QHBoxLayout()
        code_layout.addWidget(QLabel("Airfoil Code:"))
        self.naca_code_input = QLineEdit("2412")
        self.naca_code_input.textChanged.connect(self._on_naca_code_changed)
        code_layout.addWidget(self.naca_code_input)
        naca_layout.addLayout(code_layout)

        self.naca_desc_label = QLabel("Standard 4-digit: 2% camber at 40% chord, 12% thickness.")
        self.naca_desc_label.setWordWrap(True)
        naca_layout.addWidget(self.naca_desc_label)
        naca_layout.addStretch()

        self.tabs.addTab(naca_tab, "NACA Generator")

        # Tab 3: File Import
        file_tab = QWidget()
        file_layout = QVBoxLayout(file_tab)
        file_layout.setContentsMargins(8, 8, 8, 8)
        file_layout.setSpacing(8)

        browse_btn = QPushButton("Browse .DAT File...")
        set_native_button(browse_btn, "fa6s.folder-open")
        browse_btn.clicked.connect(self._browse_dat_file)
        file_layout.addWidget(browse_btn)

        self.file_path_label = QLabel("No file loaded")
        self.file_path_label.setWordWrap(True)
        file_layout.addWidget(self.file_path_label)

        self.coord_table = QTableWidget(0, 2)
        self.coord_table.setHorizontalHeaderLabels(["X", "Z"])
        self.coord_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        file_layout.addWidget(self.coord_table)

        self.tabs.addTab(file_tab, "Import File (.dat)")

        left_layout.addWidget(self.tabs)
        splitter.addWidget(left_widget)

        # ---------------------------------------------------------------------
        # Right: 2D Canvas and Metrics Panel
        # ---------------------------------------------------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.canvas = AirfoilCanvasWidget()
        right_layout.addWidget(self.canvas)

        # Metrics Card
        metrics_box = QGroupBox("Airfoil Properties")
        m_layout = QVBoxLayout(metrics_box)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setSpacing(4)

        self.max_thick_label = QLabel("Max Thickness: 12.0% at 30.0% chord")
        self.max_camber_label = QLabel("Max Camber: 2.0% at 40.0% chord")
        self.te_gap_label = QLabel("Trailing Edge Gap: 0.0%")
        self.pts_count_label = QLabel("Points: 128")

        for lbl in (self.max_thick_label, self.max_camber_label, self.te_gap_label, self.pts_count_label):
            m_layout.addWidget(lbl)

        right_layout.addWidget(metrics_box)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        layout.addWidget(splitter)

        # ---------------------------------------------------------------------
        # Bottom Buttons
        # ---------------------------------------------------------------------
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.apply_all_btn = QPushButton("Apply to All Stations")
        set_native_button(self.apply_all_btn, "fa6s.check-double")
        self.apply_all_btn.clicked.connect(self._on_apply_all)
        btn_layout.addWidget(self.apply_all_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.apply_btn = QPushButton("Apply to Section")
        set_button_role(self.apply_btn, "primary", "fa6s.check")
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.apply_btn)

        layout.addLayout(btn_layout)

        # Initial populate
        self._populate_presets()
        self._set_initial_selection(current_airfoil)

    def _populate_presets(self, category: str = "All Categories") -> None:
        self.preset_list.clear()
        for name, data in PRESET_AIRFOILS.items():
            if category != "All Categories" and data.get("category") != category:
                continue
            item = QListWidgetItem(f"{name} — {data.get('category')}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.preset_list.addItem(item)

    def _filter_presets(self, category: str) -> None:
        self._populate_presets(category)
        if self.preset_list.count() > 0:
            self.preset_list.setCurrentRow(0)

    def _set_initial_selection(self, current: object) -> None:
        name_str = "2412"
        if isinstance(current, str):
            name_str = current
        elif isinstance(current, dict):
            name_str = str(current.get("code") or current.get("name") or "2412")

        # Try finding in presets
        for i in range(self.preset_list.count()):
            item = self.preset_list.item(i)
            preset_name = str(item.data(Qt.ItemDataRole.UserRole))
            if preset_name.lower() == name_str.lower() or preset_name.replace(" ", "").lower() == name_str.replace(" ", "").lower():
                self.preset_list.setCurrentRow(i)
                return

        # Default to NACA tab if code
        self.tabs.setCurrentIndex(1)
        self.naca_code_input.setText(name_str)

    def _on_preset_selected(self, current: QListWidgetItem | None, _prev: Any = None) -> None:
        if not current:
            return
        name = str(current.data(Qt.ItemDataRole.UserRole))
        preset = PRESET_AIRFOILS.get(name)
        if not preset:
            return
        pts = preset["generator"]()
        self.canvas.set_airfoil(name, pts)
        self._update_metrics_display(pts)

        if preset["type"] == "naca":
            self._selected_airfoil_data = preset["code"]
        else:
            self._selected_airfoil_data = {
                "type": "coordinates",
                "name": name,
                "points": [list(p) for p in pts],
            }

    def _on_naca_radio_toggled(self) -> None:
        if self.naca4_radio.isChecked():
            if len(self.naca_code_input.text().strip()) == 5:
                self.naca_code_input.setText("2412")
        else:
            if len(self.naca_code_input.text().strip()) == 4:
                self.naca_code_input.setText("23012")
        self._on_naca_code_changed(self.naca_code_input.text())

    def _on_naca_code_changed(self, text: str) -> None:
        code = text.strip()
        if self.naca5_radio.isChecked():
            if len(code) >= 5:
                pts = naca5(code)
                name = f"NACA {code}"
                self.canvas.set_airfoil(name, pts)
                self._update_metrics_display(pts)
                self._selected_airfoil_data = code
                self.naca_desc_label.setText(f"NACA 5-digit: {code} low pitching moment airfoil.")
        else:
            if len(code) >= 4:
                pts = naca4(code)
                name = f"NACA {code}"
                self.canvas.set_airfoil(name, pts)
                self._update_metrics_display(pts)
                self._selected_airfoil_data = code
                self.naca_desc_label.setText(
                    f"NACA 4-digit: {code[0]}% camber at {int(code[1])*10}% chord, {code[2:4]}% thickness."
                )

    def _browse_dat_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Airfoil Coordinates (.dat / .txt)", "", "Airfoil Files (*.dat *.txt *.cor *.af);;All Files (*)"
        )
        if not file_path:
            return
        path = Path(file_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        name, pts = parse_airfoil_dat(content)

        self.file_path_label.setText(f"{path.name} ({len(pts)} points)")
        self.canvas.set_airfoil(name or path.stem, pts)
        self._update_metrics_display(pts)

        # Populate coordinates table
        self.coord_table.setRowCount(len(pts))
        for r, (x, z) in enumerate(pts):
            self.coord_table.setItem(r, 0, QTableWidgetItem(f"{x:.6f}"))
            self.coord_table.setItem(r, 1, QTableWidgetItem(f"{z:.6f}"))

        self._selected_airfoil_data = {
            "type": "coordinates",
            "name": name or path.stem,
            "points": [list(p) for p in pts],
        }

    def _update_metrics_display(self, points: tuple[tuple[float, float], ...]) -> None:
        metrics = compute_airfoil_metrics(points)
        tc = metrics.get("max_thickness", 0.12) * 100.0
        tc_x = metrics.get("thickness_x", 0.3) * 100.0
        yc = metrics.get("max_camber", 0.0) * 100.0
        yc_x = metrics.get("camber_x", 0.4) * 100.0
        te = metrics.get("te_gap", 0.0) * 100.0

        self.max_thick_label.setText(f"Max Thickness: {tc:.1f}% at {tc_x:.0f}% chord")
        self.max_camber_label.setText(f"Max Camber: {yc:.1f}% at {yc_x:.0f}% chord")
        self.te_gap_label.setText(f"Trailing Edge Gap: {te:.2f}%")
        self.pts_count_label.setText(f"Points: {len(points)}")

    def _on_apply(self) -> None:
        self._apply_all = False
        self.accept()

    def _on_apply_all(self) -> None:
        self._apply_all = True
        self.accept()

    def get_selected_airfoil(self) -> tuple[dict[str, Any] | str, bool]:
        """Return (airfoil_spec, apply_to_all)."""
        return self._selected_airfoil_data, self._apply_all
