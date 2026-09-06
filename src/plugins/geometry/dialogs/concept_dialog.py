"""Vehicle Concept Generator Dialog for SetUAV Studio Design Workspace.

Provides clean visual concept presets (Talon Pusher, Conventional Tractor,
Twin-Boom Pusher, Flying Wing) and geometric dimension controls for rapid UAV
airframe instantiation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon, set_label_icon
from setuav_studio.ui.theme import rgba, tokens
from setuav_studio.ui.widget.button import set_button_role
from setuav_studio.ui.widget.spinbox import (
    NumericSpinBox,
)
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio_sdk import StudioAPI

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "concepts"


@dataclass
class ConceptPreset:
    """Definition and default geometric parameters for an aircraft concept preset."""

    id: str
    title: str
    image_filename: str

    # Wing defaults (mm, deg)
    wingspan_mm: float = 1400.0
    wing_root_chord_mm: float = 210.0
    wing_tip_chord_mm: float = 130.0
    wing_sweep_deg: float = 2.0
    wing_dihedral_deg: float = 2.0
    wing_airfoil: str = "NACA 2412"
    wing_position: str = "High-Wing"

    # Fuselage defaults (mm)
    fuselage_length_mm: float = 850.0
    fuselage_diameter_mm: float = 130.0
    nose_length_mm: float = 220.0
    tail_length_mm: float = 450.0
    fuselage_style: str = "Pod & Boom"

    # Tail defaults (mm, deg)
    tail_type: str = "V-Tail"
    tail_span_mm: float = 380.0
    tail_root_chord_mm: float = 120.0
    tail_tip_chord_mm: float = 80.0
    tail_v_angle_deg: float = 110.0
    tail_height_mm: float = 160.0
    tail_arm_mm: float = 520.0
    tail_airfoil: str = "NACA 0012"

    # Propulsion layout
    propulsion_layout: str = "Pusher"


PRESETS: dict[str, ConceptPreset] = {
    "talon_pusher": ConceptPreset(
        id="talon_pusher",
        title="Talon Pusher",
        image_filename="config_pod_boom.jpg",
        wingspan_mm=1400.0,
        wing_root_chord_mm=210.0,
        wing_tip_chord_mm=130.0,
        wing_sweep_deg=2.0,
        wing_dihedral_deg=2.0,
        wing_airfoil="NACA 2412",
        wing_position="High-Wing",
        fuselage_length_mm=850.0,
        fuselage_diameter_mm=130.0,
        nose_length_mm=220.0,
        tail_length_mm=450.0,
        fuselage_style="Pod & Boom",
        tail_type="V-Tail",
        tail_span_mm=380.0,
        tail_root_chord_mm=120.0,
        tail_tip_chord_mm=80.0,
        tail_v_angle_deg=110.0,
        tail_height_mm=160.0,
        tail_arm_mm=520.0,
        tail_airfoil="NACA 0012",
        propulsion_layout="Pusher",
    ),
    "conventional_tractor": ConceptPreset(
        id="conventional_tractor",
        title="Conventional Tractor",
        image_filename="config_conventional.jpg",
        wingspan_mm=1600.0,
        wing_root_chord_mm=220.0,
        wing_tip_chord_mm=150.0,
        wing_sweep_deg=0.0,
        wing_dihedral_deg=3.0,
        wing_airfoil="NACA 2412",
        wing_position="High-Wing",
        fuselage_length_mm=1050.0,
        fuselage_diameter_mm=115.0,
        nose_length_mm=250.0,
        tail_length_mm=550.0,
        fuselage_style="Full Fuselage",
        tail_type="Conventional",
        tail_span_mm=440.0,
        tail_root_chord_mm=130.0,
        tail_tip_chord_mm=90.0,
        tail_v_angle_deg=0.0,
        tail_height_mm=180.0,
        tail_arm_mm=650.0,
        tail_airfoil="NACA 0012",
        propulsion_layout="Tractor",
    ),
    "twin_boom_pusher": ConceptPreset(
        id="twin_boom_pusher",
        title="Twin-Boom Pusher",
        image_filename="config_twin_boom.jpg",
        wingspan_mm=1800.0,
        wing_root_chord_mm=240.0,
        wing_tip_chord_mm=160.0,
        wing_sweep_deg=0.0,
        wing_dihedral_deg=2.0,
        wing_airfoil="Clark Y",
        wing_position="High-Wing",
        fuselage_length_mm=750.0,
        fuselage_diameter_mm=140.0,
        nose_length_mm=220.0,
        tail_length_mm=350.0,
        fuselage_style="Center Pod",
        tail_type="Twin Boom",
        tail_span_mm=520.0,
        tail_root_chord_mm=120.0,
        tail_tip_chord_mm=90.0,
        tail_v_angle_deg=0.0,
        tail_height_mm=170.0,
        tail_arm_mm=620.0,
        tail_airfoil="NACA 0012",
        propulsion_layout="Pusher",
    ),
    "flying_wing": ConceptPreset(
        id="flying_wing",
        title="Flying Wing",
        image_filename="config_flying_wing.jpg",
        wingspan_mm=1200.0,
        wing_root_chord_mm=300.0,
        wing_tip_chord_mm=160.0,
        wing_sweep_deg=18.0,
        wing_dihedral_deg=1.0,
        wing_airfoil="MH 45",
        wing_position="Mid-Wing",
        fuselage_length_mm=350.0,
        fuselage_diameter_mm=120.0,
        nose_length_mm=120.0,
        tail_length_mm=150.0,
        fuselage_style="Blended Center Body",
        tail_type="Winglets Only",
        tail_span_mm=0.0,
        tail_root_chord_mm=140.0,
        tail_tip_chord_mm=80.0,
        tail_v_angle_deg=90.0,
        tail_height_mm=160.0,
        tail_arm_mm=0.0,
        tail_airfoil="NACA 0012",
        propulsion_layout="Pusher",
    ),
}


class ConceptThumbnailCard(QFrame):
    """Compact visual card showing aircraft thumbnail and title."""

    clicked = Signal(str)

    def __init__(
        self,
        preset: ConceptPreset,
        parent: QWidget | None = None,
        image_height: int = 85,
    ) -> None:
        super().__init__(parent)
        self.preset = preset
        self.preset_id = preset.id
        self._selected = False
        self._image_height = image_height

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._init_ui()
        self._update_style()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Image thumbnail
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.img_label.setFixedHeight(self._image_height)

        img_path = ASSETS_DIR / self.preset.image_filename
        if img_path.exists():
            pix = QPixmap(str(img_path))
            scaled = pix.scaled(
                QSize(200, self._image_height),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.img_label.setPixmap(scaled)
        else:
            self.img_label.setText(self.preset.title)

        layout.addWidget(self.img_label)

        # Title label
        self.title_lbl = QLabel(self.preset.title)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(9)
        self.title_lbl.setFont(title_font)
        layout.addWidget(self.title_lbl)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._update_style()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.preset_id)
        super().mousePressEvent(event)

    def _update_style(self) -> None:
        tok = tokens()
        border = tok.get("border", "#3d3d3d")
        accent = tok.get("accent", "#4772b3")
        surface = tok.get("surface", "#282828")
        surface_alt = tok.get("surface_alt", "#323232")
        text_color = tok.get("text", "#ffffff")

        if self._selected:
            self.setStyleSheet(
                f"ConceptThumbnailCard {{"
                f"  background-color: {rgba(accent, 0.12)};"
                f"  border: 2px solid {accent};"
                f"  border-radius: 4px;"
                f"}}"
            )
            self.title_lbl.setStyleSheet(f"color: {accent}; font-weight: bold;")
        else:
            self.setStyleSheet(
                f"ConceptThumbnailCard {{"
                f"  background-color: {surface};"
                f"  border: 1px solid {border};"
                f"  border-radius: 4px;"
                f"}}"
                f"ConceptThumbnailCard:hover {{"
                f"  background-color: {surface_alt};"
                f"  border: 1px solid {accent};"
                f"}}"
            )
            self.title_lbl.setStyleSheet(f"color: {text_color}; font-weight: bold;")


class ConceptGeneratorDialog(QDialog, PropertyTableMixin):
    """Native SetUAV Studio concept-to-geometry wizard dialog for generating 3D airframes."""

    concept_generated = Signal(dict)

    def __init__(
        self,
        api: StudioAPI | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self.setObjectName("geometry.concept_generator_dialog")
        self.setWindowTitle("Airframe Concept Generator — SetUAV Studio")
        self.resize(860, 560)
        self.setMinimumSize(780, 500)

        self._cards: dict[str, ConceptThumbnailCard] = {}
        self._selected_id: str = "talon_pusher"
        self._loading: bool = False

        # Current working parameters
        self.params: dict[str, Any] = {}

        self._init_ui()
        self.select_preset("talon_pusher")

    def _create_section_header(self, title: str, icon_name: str | None = None) -> QWidget:
        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(22)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        if icon_name:
            icon_lbl = QLabel()
            set_label_icon(icon_lbl, icon_name)
            icon_lbl.setFixedSize(14, 14)
            header_layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_font = QFont()
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        return header

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 1. Top Section: Aircraft Architecture Presets
        arch_header = self._create_section_header("Aircraft Architecture Preset", "fa6s.shapes")
        main_layout.addWidget(arch_header)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(8)

        for pid, preset in PRESETS.items():
            card = ConceptThumbnailCard(preset, parent=self)
            card.clicked.connect(self.select_preset)
            cards_row.addWidget(card)
            self._cards[pid] = card

        main_layout.addLayout(cards_row)

        # 2. Middle Section: Geometric Parameters & Metrics
        param_header = self._create_section_header("Geometry Parameters & Configuration", "fa6s.sliders")
        main_layout.addWidget(param_header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Tab 1: Main Wing
        tab_wing = QWidget()
        wing_layout = QVBoxLayout(tab_wing)
        wing_layout.setContentsMargins(4, 6, 4, 4)
        wing_layout.setSpacing(6)

        self.wing_table = self._property_table(
            [
                ("wingspan", "Wingspan (b)"),
                ("root_chord", "Root Chord (c_root)"),
                ("tip_chord", "Tip Chord (c_tip)"),
                ("sweep_angle", "Sweep Angle (deg)"),
                ("dihedral_angle", "Dihedral Angle (deg)"),
                ("airfoil", "Airfoil Profile"),
                ("wing_position", "Fuselage Placement"),
            ]
        )
        wing_layout.addWidget(self.wing_table)
        wing_layout.addStretch()
        self.tabs.addTab(tab_wing, "Main Wing")

        # Tab 2: Fuselage
        tab_fuse = QWidget()
        fuse_layout = QVBoxLayout(tab_fuse)
        fuse_layout.setContentsMargins(4, 6, 4, 4)
        fuse_layout.setSpacing(6)

        self.fuse_table = self._property_table(
            [
                ("fuselage_length", "Total Length (L)"),
                ("fuselage_diameter", "Max Diameter / Width (D)"),
                ("nose_length", "Nose Section Length"),
                ("tail_length", "Tail Boom / Taper Length"),
                ("fuselage_style", "Fuselage Architecture"),
            ]
        )
        fuse_layout.addWidget(self.fuse_table)
        fuse_layout.addStretch()
        self.tabs.addTab(tab_fuse, "Fuselage")

        # Tab 3: Tail (Empennage)
        tab_tail = QWidget()
        tail_layout = QVBoxLayout(tab_tail)
        tail_layout.setContentsMargins(4, 6, 4, 4)
        tail_layout.setSpacing(6)

        self.tail_table = self._property_table(
            [
                ("tail_type", "Tail Configuration"),
                ("tail_span", "Tail Span / Width"),
                ("tail_root_chord", "Tail Root Chord"),
                ("tail_tip_chord", "Tail Tip Chord"),
                ("tail_v_angle", "V-Tail Dihedral Angle"),
                ("tail_height", "Vertical Fin Height"),
                ("tail_arm", "Tail Moment Arm (from Wing)"),
                ("tail_airfoil", "Tail Airfoil Profile"),
            ]
        )
        tail_layout.addWidget(self.tail_table)
        tail_layout.addStretch()
        self.tabs.addTab(tab_tail, "Empennage / Tail")

        # Tab 4: Derived Metrics
        tab_metrics = QWidget()
        met_layout = QVBoxLayout(tab_metrics)
        met_layout.setContentsMargins(4, 6, 4, 4)
        met_layout.setSpacing(6)

        self.metrics_table = self._property_table(
            [
                ("wing_area", "Wing Reference Area (S)"),
                ("aspect_ratio", "Wing Aspect Ratio (AR)"),
                ("mean_chord", "Mean Aerodynamic Chord (MAC)"),
                ("taper_ratio", "Taper Ratio (lambda)"),
                ("tail_area", "Tail Projected Area (S_tail)"),
                ("tail_area_ratio", "Tail / Wing Area Ratio"),
            ]
        )
        met_layout.addWidget(self.metrics_table)
        met_layout.addStretch()
        self.tabs.addTab(tab_metrics, "Planform Metrics")

        main_layout.addWidget(self.tabs, 1)

        # 3. Bottom Action Bar
        action_bar = QWidget()
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 4, 0, 0)
        action_layout.setSpacing(8)

        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.setIcon(get_icon("fa6s.arrow-rotate-left"))
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        action_layout.addWidget(self.btn_reset)

        action_layout.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_cancel)

        self.btn_generate = QPushButton("Generate Aircraft")
        self.btn_generate.setIcon(get_icon("fa6s.wand-magic-sparkles"))
        set_button_role(self.btn_generate, "primary")
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        action_layout.addWidget(self.btn_generate)

        main_layout.addWidget(action_bar)

        # Setup table editors (combos and spinboxes)
        self._setup_table_editors()

    def _setup_table_editors(self) -> None:
        # Wing Combos
        self._set_property_combo(
            self.wing_table,
            "airfoil",
            "NACA 2412",
            [
                ("NACA 2412", "NACA 2412 (Cambered General)"),
                ("NACA 4412", "NACA 4412 (High Lift)"),
                ("Clark Y", "Clark Y (Flat-Bottomed)"),
                ("MH 45", "MH 45 (Reflexed Flying Wing)"),
                ("NACA 0012", "NACA 0012 (Symmetric)"),
            ],
            lambda val: self._update_param("wing_airfoil", val),
        )
        self._set_property_combo(
            self.wing_table,
            "wing_position",
            "High-Wing",
            [
                ("High-Wing", "High-Wing (Shoulder Mounted)"),
                ("Mid-Wing", "Mid-Wing (Aerobatic / Tailless)"),
                ("Low-Wing", "Low-Wing"),
            ],
            lambda val: self._update_param("wing_position", val),
        )

        # Fuselage Combos
        self._set_property_combo(
            self.fuse_table,
            "fuselage_style",
            "Pod & Boom",
            [
                ("Pod & Boom", "Pod & Boom (Talon style)"),
                ("Full Fuselage", "Full Monocoque Fuselage"),
                ("Center Pod", "Center Pod (Twin Boom)"),
                ("Blended Center Body", "Blended Center Body (Tailless)"),
            ],
            lambda val: self._update_param("fuselage_style", val),
        )

        # Tail Combos
        self._set_property_combo(
            self.tail_table,
            "tail_type",
            "V-Tail",
            [
                ("V-Tail", "V-Tail (Dihedral)"),
                ("Inverted V-Tail", "Inverted V-Tail (Anhedral)"),
                ("Conventional", "Conventional (HT + VT)"),
                ("T-Tail", "T-Tail"),
                ("Twin Boom", "Twin Boom Stabilizer"),
                ("Winglets Only", "Winglets Only (Tailless)"),
            ],
            lambda val: self._on_tail_type_changed(val),
        )
        self._set_property_combo(
            self.tail_table,
            "tail_airfoil",
            "NACA 0012",
            [
                ("NACA 0012", "NACA 0012 (Symmetric)"),
                ("NACA 0009", "NACA 0009 (Thin Symmetric)"),
                ("Flat Plate", "Flat Plate / Carbon Strip"),
            ],
            lambda val: self._update_param("tail_airfoil", val),
        )

    def _property_row_index(self, table: QTableWidget, key: str) -> int | None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) == key:
                return row
        return None

    def _find_combo(self, table: QTableWidget, key: str) -> QComboBox | None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) == key:
                widget = table.cellWidget(row, 1)
                if isinstance(widget, QComboBox):
                    return widget
        return None

    def _set_combo_value(self, table: QTableWidget, key: str, value: str) -> None:
        combo = self._find_combo(table, key)
        if combo:
            combo.blockSignals(True)
            idx = combo.findData(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                idx = combo.findText(value)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _set_spin(
        self,
        table: QTableWidget,
        key: str,
        val: float,
        min_v: float,
        max_v: float,
        step: float,
        decimals: int,
        suffix: str,
        on_change,
    ) -> NumericSpinBox | None:
        return self._set_property_spinbox(
            table,
            key,
            val,
            min_val=min_v,
            max_val=max_v,
            step=step,
            decimals=decimals,
            suffix=suffix,
            on_changed=on_change,
        )

    def select_preset(self, preset_id: str) -> None:
        if preset_id not in PRESETS:
            return
        self._selected_id = preset_id

        # Update visual cards
        for pid, card in self._cards.items():
            card.set_selected(pid == preset_id)

        # Load preset parameters
        preset = PRESETS[preset_id]
        self.params = {
            "concept_id": preset.id,
            "concept_title": preset.title,
            "propulsion_layout": preset.propulsion_layout,
            "wingspan_mm": preset.wingspan_mm,
            "wing_root_chord_mm": preset.wing_root_chord_mm,
            "wing_tip_chord_mm": preset.wing_tip_chord_mm,
            "wing_sweep_deg": preset.wing_sweep_deg,
            "wing_dihedral_deg": preset.wing_dihedral_deg,
            "wing_airfoil": preset.wing_airfoil,
            "wing_position": preset.wing_position,
            "fuselage_length_mm": preset.fuselage_length_mm,
            "fuselage_diameter_mm": preset.fuselage_diameter_mm,
            "nose_length_mm": preset.nose_length_mm,
            "tail_length_mm": preset.tail_length_mm,
            "fuselage_style": preset.fuselage_style,
            "tail_type": preset.tail_type,
            "tail_span_mm": preset.tail_span_mm,
            "tail_root_chord_mm": preset.tail_root_chord_mm,
            "tail_tip_chord_mm": preset.tail_tip_chord_mm,
            "tail_v_angle_deg": preset.tail_v_angle_deg,
            "tail_height_mm": preset.tail_height_mm,
            "tail_arm_mm": preset.tail_arm_mm,
            "tail_airfoil": preset.tail_airfoil,
        }

        self._populate_ui_from_params()

    def _populate_ui_from_params(self) -> None:
        self._loading = True
        try:
            # 1. Wing Spinboxes
            self._set_spin(self.wing_table, "wingspan", self.params["wingspan_mm"], 100.0, 10000.0, 10.0, 0, " mm", lambda v: self._update_param("wingspan_mm", v))
            self._set_spin(self.wing_table, "root_chord", self.params["wing_root_chord_mm"], 20.0, 2000.0, 5.0, 0, " mm", lambda v: self._update_param("wing_root_chord_mm", v))
            self._set_spin(self.wing_table, "tip_chord", self.params["wing_tip_chord_mm"], 10.0, 2000.0, 5.0, 0, " mm", lambda v: self._update_param("wing_tip_chord_mm", v))
            self._set_spin(self.wing_table, "sweep_angle", self.params["wing_sweep_deg"], -15.0, 45.0, 0.5, 1, " °", lambda v: self._update_param("wing_sweep_deg", v))
            self._set_spin(self.wing_table, "dihedral_angle", self.params["wing_dihedral_deg"], -15.0, 25.0, 0.5, 1, " °", lambda v: self._update_param("wing_dihedral_deg", v))

            self._set_combo_value(self.wing_table, "airfoil", self.params["wing_airfoil"])
            self._set_combo_value(self.wing_table, "wing_position", self.params["wing_position"])

            # 2. Fuselage Spinboxes
            self._set_spin(self.fuse_table, "fuselage_length", self.params["fuselage_length_mm"], 100.0, 5000.0, 10.0, 0, " mm", lambda v: self._update_param("fuselage_length_mm", v))
            self._set_spin(self.fuse_table, "fuselage_diameter", self.params["fuselage_diameter_mm"], 20.0, 1000.0, 5.0, 0, " mm", lambda v: self._update_param("fuselage_diameter_mm", v))
            self._set_spin(self.fuse_table, "nose_length", self.params["nose_length_mm"], 20.0, 2000.0, 5.0, 0, " mm", lambda v: self._update_param("nose_length_mm", v))
            self._set_spin(self.fuse_table, "tail_length", self.params["tail_length_mm"], 20.0, 3000.0, 5.0, 0, " mm", lambda v: self._update_param("tail_length_mm", v))

            self._set_combo_value(self.fuse_table, "fuselage_style", self.params["fuselage_style"])

            # 3. Tail Spinboxes
            self._set_combo_value(self.tail_table, "tail_type", self.params["tail_type"])
            self._set_spin(self.tail_table, "tail_span", self.params["tail_span_mm"], 0.0, 3000.0, 10.0, 0, " mm", lambda v: self._update_param("tail_span_mm", v))
            self._set_spin(self.tail_table, "tail_root_chord", self.params["tail_root_chord_mm"], 10.0, 1000.0, 5.0, 0, " mm", lambda v: self._update_param("tail_root_chord_mm", v))
            self._set_spin(self.tail_table, "tail_tip_chord", self.params["tail_tip_chord_mm"], 0.0, 1000.0, 5.0, 0, " mm", lambda v: self._update_param("tail_tip_chord_mm", v))
            self._set_spin(self.tail_table, "tail_v_angle", self.params["tail_v_angle_deg"], 0.0, 180.0, 1.0, 0, " °", lambda v: self._update_param("tail_v_angle_deg", v))
            self._set_spin(self.tail_table, "tail_height", self.params["tail_height_mm"], 0.0, 1500.0, 5.0, 0, " mm", lambda v: self._update_param("tail_height_mm", v))
            self._set_spin(self.tail_table, "tail_arm", self.params["tail_arm_mm"], 0.0, 3000.0, 10.0, 0, " mm", lambda v: self._update_param("tail_arm_mm", v))

            self._set_combo_value(self.tail_table, "tail_airfoil", self.params["tail_airfoil"])

            self._update_derived_metrics()
        finally:
            self._loading = False

    def _update_param(self, key: str, value: Any) -> None:
        if self._loading:
            return
        self.params[key] = value
        self._update_derived_metrics()

    def _on_tail_type_changed(self, tail_type: str) -> None:
        self._update_param("tail_type", tail_type)
        is_vtail = tail_type in ("V-Tail", "Inverted V-Tail")

        if is_vtail and self.params["tail_v_angle_deg"] < 45.0:
            self.params["tail_v_angle_deg"] = 110.0
            self._set_spin(self.tail_table, "tail_v_angle", 110.0, 0.0, 180.0, 1.0, 0, " °", lambda v: self._update_param("tail_v_angle_deg", v))
        elif not is_vtail:
            self.params["tail_v_angle_deg"] = 0.0
            self._set_spin(self.tail_table, "tail_v_angle", 0.0, 0.0, 180.0, 1.0, 0, " °", lambda v: self._update_param("tail_v_angle_deg", v))

        self._update_derived_metrics()

    def _update_derived_metrics(self) -> None:
        b_m = self.params.get("wingspan_mm", 1400.0) / 1000.0
        c_root_m = self.params.get("wing_root_chord_mm", 210.0) / 1000.0
        c_tip_m = self.params.get("wing_tip_chord_mm", 130.0) / 1000.0

        # Planform area for linear trapezoid
        s_m2 = b_m * (c_root_m + c_tip_m) / 2.0
        ar = (b_m ** 2) / max(s_m2, 0.001)
        taper = c_tip_m / max(c_root_m, 0.001)
        mac_m = (2.0 / 3.0) * c_root_m * (1.0 + taper + taper ** 2) / max(1.0 + taper, 0.001)

        # Tail area
        tail_b_m = self.params.get("tail_span_mm", 380.0) / 1000.0
        tail_cr_m = self.params.get("tail_root_chord_mm", 120.0) / 1000.0
        tail_ct_m = self.params.get("tail_tip_chord_mm", 80.0) / 1000.0
        s_tail_m2 = tail_b_m * (tail_cr_m + tail_ct_m) / 2.0
        area_ratio = (s_tail_m2 / max(s_m2, 0.001)) * 100.0

        self._set_property_value(self.metrics_table, "wing_area", f"{s_m2:.3f} m² ({s_m2 * 100.0:.1f} dm²)")
        self._set_property_value(self.metrics_table, "aspect_ratio", f"{ar:.2f}")
        self._set_property_value(self.metrics_table, "mean_chord", f"{mac_m * 1000.0:.1f} mm")
        self._set_property_value(self.metrics_table, "taper_ratio", f"{taper:.3f}")
        self._set_property_value(self.metrics_table, "tail_area", f"{s_tail_m2:.3f} m²")
        self._set_property_value(self.metrics_table, "tail_area_ratio", f"{area_ratio:.1f} %")

    def _on_reset_clicked(self) -> None:
        self.select_preset(self._selected_id)

    def _on_generate_clicked(self) -> None:
        self.concept_generated.emit(dict(self.params))
        self.accept()

    def get_configuration(self) -> dict[str, Any]:
        return dict(self.params)


__all__ = ["ConceptGeneratorDialog", "ConceptPreset", "PRESETS"]
