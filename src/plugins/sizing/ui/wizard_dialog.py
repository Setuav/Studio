"""Preliminary Sizing Wizard Dialog for SetUAV Studio.

Provides an interactive multi-step visual wizard that guides the engineer
through high-level mission and architectural decisions:
1. Mission & Performance Requirements
2. Aircraft Architecture (Configuration)
3. Wing Vertical Placement
4. Wing Planform Geometry
5. Tail Configuration
6. Propulsion Architecture
7. Battery Technology
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.theme import rgba, tokens
from setuav_studio.ui.widget.button import set_button_role
from setuav_studio.ui.widget.table import ExpressionPropertyCell, PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "wizard"


@dataclass
class WizardOption:
    """Definition of a selectable visual card in the wizard."""

    id: str
    title: str
    subtitle: str
    image_filename: str | None = None
    badge: str | None = None
    details: list[str] | None = None


class WizardOptionCard(QFrame):
    """Interactive visual option card with thumbnail, title, badge, and pros/cons."""

    clicked = Signal(str)  # option_id

    def __init__(
        self,
        option: WizardOption,
        parent: QWidget | None = None,
        image_height: int = 140,
    ) -> None:
        super().__init__(parent)
        self.option = option
        self._selected = False
        self._image_height = image_height

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(200)

        tok = tokens()
        accent = tok.get("accent", "#4772b3")
        text = tok.get("text", "#ffffff")
        text_muted = tok.get("text_muted", "#b9b9b9")
        text_dim = tok.get("text_dim", "#848484")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(6)

        # Image thumbnail container
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.img_label.setFixedHeight(self._image_height)

        if option.image_filename:
            img_path = ASSETS_DIR / option.image_filename
            if img_path.exists():
                pix = QPixmap(str(img_path))
                scaled = pix.scaled(
                    QSize(280, self._image_height),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.img_label.setPixmap(scaled)
            else:
                self.img_label.setText(option.title)
        else:
            self.img_label.setText(option.badge or option.title)

        layout.addWidget(self.img_label)

        # Header row (Title + Badge)
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        title_lbl = QLabel(option.title)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet(f"color: {text};")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header_row.addWidget(title_lbl)

        if option.badge:
            badge_lbl = QLabel(f" {option.badge} ")
            badge_font = QFont()
            badge_font.setPointSize(8)
            badge_font.setBold(True)
            badge_lbl.setFont(badge_font)
            badge_lbl.setStyleSheet(
                f"background-color: {rgba(accent, 0.18)}; "
                f"color: {accent}; "
                f"border: 1px solid {rgba(accent, 0.35)}; "
                f"border-radius: 3px; "
                f"padding: 1px 5px;"
            )
            header_row.addWidget(badge_lbl)

        layout.addLayout(header_row)

        # Subtitle
        sub_lbl = QLabel(option.subtitle)
        sub_lbl.setWordWrap(True)
        sub_font = QFont()
        sub_font.setPointSize(9)
        sub_lbl.setFont(sub_font)
        sub_lbl.setStyleSheet(f"color: {text_muted};")
        layout.addWidget(sub_lbl)

        # Details / bullets
        if option.details:
            details_text = "\n".join(f"•  {d}" for d in option.details)
            det_lbl = QLabel(details_text)
            det_lbl.setWordWrap(True)
            det_font = QFont()
            det_font.setPointSize(8)
            det_lbl.setFont(det_font)
            det_lbl.setStyleSheet(f"color: {text_dim}; margin-top: 2px;")
            layout.addWidget(det_lbl)

        layout.addStretch(1)
        self._update_style()

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self._update_style()

    def is_selected(self) -> bool:
        return self._selected

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.option.id)
        super().mousePressEvent(event)

    def _update_style(self) -> None:
        tok = tokens()
        surface = tok.get("surface", "#282828")
        surface_alt = tok.get("surface_alt", "#3d3d3d")
        accent = tok.get("accent", "#4772b3")
        border_strong = tok.get("border_strong", "#6c6c6c")

        if self._selected:
            self.setStyleSheet(
                f"WizardOptionCard {{"
                f"  background-color: {surface};"
                f"  border: 2px solid {accent};"
                f"  border-radius: 6px;"
                f"}}"
            )
        else:
            self.setStyleSheet(
                f"WizardOptionCard {{"
                f"  background-color: {surface};"
                f"  border: 1px solid {border_strong};"
                f"  border-radius: 6px;"
                f"}}"
                f"WizardOptionCard:hover {{"
                f"  background-color: {surface_alt};"
                f"  border: 1px solid {accent};"
                f"}}"
            )


class WizardCardGrid(QWidget):
    """Grid container for selectable visual cards with single selection."""

    selection_changed = Signal(str)

    def __init__(
        self,
        options: list[WizardOption],
        columns: int = 2,
        parent: QWidget | None = None,
        image_height: int = 140,
    ) -> None:
        super().__init__(parent)
        self._cards: dict[str, WizardOptionCard] = {}
        self._selected_id: str | None = None

        layout = QGridLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        for i, opt in enumerate(options):
            card = WizardOptionCard(opt, parent=self, image_height=image_height)
            card.clicked.connect(self._on_card_clicked)
            row = i // columns
            col = i % columns
            layout.addWidget(card, row, col)
            self._cards[opt.id] = card

        if options:
            self.select(options[0].id)

    def select(self, option_id: str) -> None:
        if option_id not in self._cards:
            return
        self._selected_id = option_id
        for cid, card in self._cards.items():
            card.set_selected(cid == option_id)
        self.selection_changed.emit(option_id)

    def selected_id(self) -> str | None:
        return self._selected_id

    def _on_card_clicked(self, option_id: str) -> None:
        self.select(option_id)


class ConceptWizardDialog(QDialog, PropertyTableMixin):
    """Interactive multi-step visual concept wizard for UAV design."""

    def __init__(
        self,
        parent: QWidget | None = None,
        api: StudioAPI | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self.setObjectName("sizing.concept_wizard_dialog")
        self.setWindowTitle("UAV Concept Wizard — SetUAV Studio")
        self.resize(1080, 720)
        self.setMinimumSize(900, 600)

        # Wizard state dictionary
        self.state: dict[str, Any] = {
            "payload_kg": 0.5,
            "endurance_min": 45.0,
            "cruise_speed_ms": 18.0,
            "cruise_alt_m": 100.0,
            "stall_speed_ms": 12.0,
            "takeoff_run_m": 25.0,
            "climb_rate_ms": 3.0,
            "config_type": "conventional",
            "wing_location": "high",
            "wing_planform": "tapered",
            "tail_type": "conventional",
            "propulsion_layout": "tractor",
            "battery_chemistry": "li_ion_21700",
        }

        self._init_ui()

    def _init_ui(self) -> None:
        tok = tokens()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Header Banner & Step Title
        header_frame = QFrame()
        header_frame.setObjectName("wizard_header")
        header_frame.setStyleSheet(
            f"QFrame#wizard_header {{"
            f"  background-color: {tok.get('surface', '#282828')};"
            f"  border: 1px solid {tok.get('border', '#3d3d3d')};"
            f"  border-radius: 6px;"
            f"  padding: 8px 12px;"
            f"}}"
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 6, 8, 6)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        self.step_counter_lbl = QLabel("STEP 1 OF 7")
        self.step_counter_lbl.setStyleSheet(
            f"color: {tok.get('accent', '#4772b3')}; font-size: 11px; font-weight: bold;"
        )
        title_vbox.addWidget(self.step_counter_lbl)

        self.step_title_lbl = QLabel("Mission & Performance Requirements")
        step_title_font = QFont()
        step_title_font.setPointSize(13)
        step_title_font.setBold(True)
        self.step_title_lbl.setFont(step_title_font)
        self.step_title_lbl.setStyleSheet(f"color: {tok.get('text', '#ffffff')};")
        title_vbox.addWidget(self.step_title_lbl)

        self.step_desc_lbl = QLabel(
            "Define payload capacity and primary mission flight envelope requirements."
        )
        self.step_desc_lbl.setStyleSheet(
            f"color: {tok.get('text_muted', '#b9b9b9')}; font-size: 11px;"
        )
        title_vbox.addWidget(self.step_desc_lbl)

        header_layout.addLayout(title_vbox, 1)

        # Quick breadcrumbs / step tabs
        self.step_pill_layout = QHBoxLayout()
        self.step_pill_layout.setSpacing(4)
        self._step_buttons: list[QPushButton] = []
        step_short_names = [
            "1. Mission",
            "2. Architecture",
            "3. Wing Pos",
            "4. Planform",
            "5. Tail",
            "6. Propulsion",
            "7. Battery",
        ]
        for idx, name in enumerate(step_short_names):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {tok.get('surface', '#282828')};"
                f"  color: {tok.get('text_muted', '#b9b9b9')};"
                f"  border: 1px solid {tok.get('border', '#3d3d3d')};"
                f"  border-radius: 4px;"
                f"  padding: 3px 8px;"
                f"  font-size: 11px;"
                f"}}"
                f"QPushButton:checked {{"
                f"  background-color: {tok.get('accent', '#4772b3')};"
                f"  color: {tok.get('accent_text', '#ffffff')};"
                f"  border: 1px solid {tok.get('accent', '#4772b3')};"
                f"  font-weight: bold;"
                f"}}"
                f"QPushButton:hover {{"
                f"  border: 1px solid {tok.get('accent', '#4772b3')};"
                f"}}"
            )
            btn.clicked.connect(lambda _c, i=idx: self.go_to_step(i))
            self.step_pill_layout.addWidget(btn)
            self._step_buttons.append(btn)

        header_layout.addLayout(self.step_pill_layout)
        main_layout.addWidget(header_frame)

        # 2. Central Split (Step Content on left, Live Summary on right)
        central_layout = QHBoxLayout()
        central_layout.setSpacing(12)

        # Stacked Pages with Scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self.stack = QStackedWidget()
        self._build_pages()
        scroll.setWidget(self.stack)
        central_layout.addWidget(scroll, 3)

        # Live Summary Sidebar
        sidebar = self._build_summary_sidebar()
        central_layout.addWidget(sidebar, 1)

        main_layout.addLayout(central_layout, 1)

        # 3. Bottom Navigation Bar
        nav_frame = QFrame()
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(4, 4, 4, 4)

        self.btn_cancel = QPushButton("Cancel")
        set_button_role(self.btn_cancel, "neutral")
        self.btn_cancel.clicked.connect(self.reject)
        nav_layout.addWidget(self.btn_cancel)

        nav_layout.addStretch(1)

        self.btn_back = QPushButton("Back")
        self.btn_back.setIcon(get_icon("fa6s.chevron-left"))
        set_button_role(self.btn_back, "secondary")
        self.btn_back.clicked.connect(self.prev_step)
        nav_layout.addWidget(self.btn_back)

        self.btn_next = QPushButton("Next")
        self.btn_next.setIcon(get_icon("fa6s.chevron-right"))
        set_button_role(self.btn_next, "primary")
        self.btn_next.clicked.connect(self.next_step)
        nav_layout.addWidget(self.btn_next)

        main_layout.addWidget(nav_frame)

        self.go_to_step(0)

    def _build_pages(self) -> None:
        """Create all wizard pages."""
        self.page_mission = self._create_mission_page()
        self.stack.addWidget(self.page_mission)

        self.page_arch = self._create_architecture_page()
        self.stack.addWidget(self.page_arch)

        self.page_wing_loc = self._create_wing_location_page()
        self.stack.addWidget(self.page_wing_loc)

        self.page_wing_plan = self._create_wing_planform_page()
        self.stack.addWidget(self.page_wing_plan)

        self.page_tail = self._create_tail_page()
        self.stack.addWidget(self.page_tail)

        self.page_prop = self._create_propulsion_page()
        self.stack.addWidget(self.page_prop)

        self.page_battery = self._create_battery_page()
        self.stack.addWidget(self.page_battery)

    def _create_cell(
        self,
        table: QTableWidget,
        row: int,
        label: str,
        val: float,
        quantity: str | None = None,
        suffix: str | None = None,
        min_val: float = 0.0,
        max_val: float = 100000.0,
        step: float = 1.0,
        decimals: int = 2,
    ) -> ExpressionPropertyCell:
        from setuav_studio.ui.widget.spinbox import set_table_spinbox

        cell: ExpressionPropertyCell = set_table_spinbox(
            table,
            row,
            1,
            val,
            min_val=min_val,
            max_val=max_val,
            step=step,
            decimals=decimals,
            quantity=quantity,
            suffix=suffix or "",
            on_changed=lambda _v: self._on_mission_cell_changed(),
            api=self._api,
            label=label,
        )
        return cell

    def _create_mission_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        tok = tokens()
        intro = QLabel(
            "Specify key mission requirements and target flight envelope parameters. "
            "These inputs define the constraint boundary lines on the Matching Chart."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {tok.get('text_muted', '#b9b9b9')}; font-size: 11px;")
        layout.addWidget(intro)

        mission_definitions = [
            ("payload", "Payload Mass"),
            ("endurance", "Flight Endurance"),
            ("v_cruise", "Cruise Speed"),
            ("cruise_alt", "Cruise Altitude"),
            ("v_stall", "Max Stall Speed"),
            ("takeoff_run", "Takeoff Ground Roll"),
            ("climb_rate", "Rate of Climb"),
        ]

        self.mission_table = self._property_table(mission_definitions)

        self.cell_payload = self._create_cell(
            self.mission_table,
            0,
            "Payload Mass",
            self.state["payload_kg"] * 1000.0,
            quantity="mass",
            min_val=10.0,
            max_val=100000.0,
            step=50.0,
            decimals=1,
        )
        self.cell_endurance = self._create_cell(
            self.mission_table,
            1,
            "Flight Endurance",
            self.state["endurance_min"],
            suffix="min",
            min_val=1.0,
            max_val=1000.0,
            step=5.0,
            decimals=1,
        )
        self.cell_cruise_speed = self._create_cell(
            self.mission_table,
            2,
            "Cruise Speed",
            self.state["cruise_speed_ms"],
            quantity="velocity",
            min_val=5.0,
            max_val=100.0,
            step=1.0,
            decimals=1,
        )
        self.cell_altitude = self._create_cell(
            self.mission_table,
            3,
            "Cruise Altitude",
            self.state["cruise_alt_m"],
            quantity="length",
            min_val=0.0,
            max_val=10000.0,
            step=50.0,
            decimals=0,
        )
        self.cell_stall_speed = self._create_cell(
            self.mission_table,
            4,
            "Max Stall Speed",
            self.state["stall_speed_ms"],
            quantity="velocity",
            min_val=3.0,
            max_val=50.0,
            step=0.5,
            decimals=1,
        )
        self.cell_takeoff_run = self._create_cell(
            self.mission_table,
            5,
            "Takeoff Ground Roll",
            self.state["takeoff_run_m"],
            quantity="length",
            min_val=1.0,
            max_val=500.0,
            step=5.0,
            decimals=1,
        )
        self.cell_climb_rate = self._create_cell(
            self.mission_table,
            6,
            "Rate of Climb",
            self.state["climb_rate_ms"],
            quantity="velocity",
            min_val=0.5,
            max_val=30.0,
            step=0.5,
            decimals=1,
        )

        # Expose convenient aliases
        self.input_payload = self.cell_payload
        self.input_endurance = self.cell_endurance
        self.input_cruise_speed = self.cell_cruise_speed
        self.input_altitude = self.cell_altitude
        self.input_stall_speed = self.cell_stall_speed
        self.input_takeoff_run = self.cell_takeoff_run
        self.input_climb_rate = self.cell_climb_rate

        layout.addWidget(self.mission_table)
        layout.addStretch(1)
        return page

    def _create_architecture_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="conventional",
                title="Conventional",
                subtitle="Standard fuselage, wing, and tail architecture.",
                image_filename="config_conventional.jpg",
                badge="Standard",
                details=[
                    "High longitudinal stability and straightforward build",
                    "Spacious internal volume for avionics packaging",
                    "Moderate aerodynamic interference drag",
                ],
            ),
            WizardOption(
                id="pod_boom",
                title="Pod-and-Boom",
                subtitle="Compact fuselage pod with a slender tail boom.",
                image_filename="config_pod_boom.jpg",
                badge="Lightweight",
                details=[
                    "Reduced wetted area and low parasite drag",
                    "Rigid carbon tail boom saves structural mass",
                    "Well-suited for both tractor and pusher layouts",
                ],
            ),
            WizardOption(
                id="twin_boom",
                title="Twin-Boom",
                subtitle="Twin tail booms extending aft from the wing.",
                image_filename="config_twin_boom.jpg",
                badge="Pusher Friendly",
                details=[
                    "Protects aft-mounted pusher propeller",
                    "Clean, unobstructed nose bay for sensor payloads",
                    "Large central payload and battery capacity",
                ],
            ),
            WizardOption(
                id="flying_wing",
                title="Flying Wing / Tailless",
                subtitle="Integrated aerodynamic wing without separate fuselage or tail.",
                image_filename="config_flying_wing.jpg",
                badge="Max L/D",
                details=[
                    "No fuselage/tail wetted area yields minimal parasite drag",
                    "High lift-to-drag ratio and superior cruise range",
                    "Requires reflex airfoil or wing sweep for longitudinal trim",
                ],
            ),
        ]

        self.grid_arch = WizardCardGrid(options, columns=2, parent=page, image_height=140)
        self.grid_arch.selection_changed.connect(
            lambda cid: self._on_selection_changed("config_type", cid)
        )
        layout.addWidget(self.grid_arch)
        return page

    def _create_wing_location_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="high",
                title="High-Wing",
                subtitle="Wing mounted atop the fuselage upper deck.",
                image_filename="wing_loc_high.png",
                badge="Inherent Stability",
                details=[
                    "Pendulum effect provides positive lateral stability",
                    "Generous ground clearance for payloads and rough-field landings",
                    "Continuous internal fuselage cargo and battery bay",
                ],
            ),
            WizardOption(
                id="mid",
                title="Mid-Wing",
                subtitle="Wing mounted along the fuselage horizontal centerline.",
                image_filename="wing_loc_mid.png",
                badge="Lowest Drag",
                details=[
                    "Lowest aerodynamic interference drag",
                    "Symmetric roll and pitch response for high maneuverability",
                    "Wing carry-through structure passes through fuselage bay",
                ],
            ),
            WizardOption(
                id="low",
                title="Low-Wing",
                subtitle="Wing mounted at the fuselage bottom.",
                image_filename="wing_loc_low.png",
                badge="Ground Effect",
                details=[
                    "Favorable ground effect cushioning during takeoff and landing",
                    "Requires dihedral angle for lateral stability",
                    "Convenient top access to payload and battery compartment",
                ],
            ),
        ]

        self.grid_wing_loc = WizardCardGrid(options, columns=3, parent=page, image_height=130)
        self.grid_wing_loc.selection_changed.connect(
            lambda cid: self._on_selection_changed("wing_location", cid)
        )
        layout.addWidget(self.grid_wing_loc)
        return page

    def _create_wing_planform_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="rectangular",
                title="Rectangular",
                subtitle="Constant-chord wing across the entire span.",
                image_filename="planform_rectangular.png",
                badge="Simple Build",
                details=[
                    "Easiest planform to manufacture and cover",
                    "Root-first stall progression maintains roll authority",
                    "Higher induced drag due to non-elliptical lift distribution",
                ],
            ),
            WizardOption(
                id="tapered",
                title="Tapered",
                subtitle="Linear chord taper towards wingtips (taper ratio 0.4 - 0.6).",
                image_filename="planform_tapered.png",
                badge="Optimal L/D",
                details=[
                    "Close approximation to ideal elliptical lift distribution",
                    "Low induced drag with high structural efficiency",
                    "Lighter wing structure for extended cruise endurance",
                ],
            ),
            WizardOption(
                id="swept",
                title="Swept-Tapered",
                subtitle="Wing with aft sweep on the leading edge.",
                image_filename="planform_swept.png",
                badge="High Speed",
                details=[
                    "Delays compressibility drag rise at higher airspeeds",
                    "Provides longitudinal stability for tailless configurations",
                    "Requires aerodynamic washout to mitigate tip stall",
                ],
            ),
            WizardOption(
                id="delta",
                title="Delta Wing",
                subtitle="Triangular wing planform with large root chord.",
                image_filename="planform_delta.png",
                badge="Structural Volume",
                details=[
                    "Large wing area with substantial internal battery volume",
                    "Vortex lift generation at high angles of attack",
                    "Low aspect ratio increases induced drag during climb/turn",
                ],
            ),
        ]

        self.grid_wing_plan = WizardCardGrid(options, columns=2, parent=page, image_height=130)
        self.grid_wing_plan.selection_changed.connect(
            lambda cid: self._on_selection_changed("wing_planform", cid)
        )
        layout.addWidget(self.grid_wing_plan)
        return page

    def _create_tail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="conventional",
                title="Conventional Tail",
                subtitle="Separate horizontal stabilizer and vertical fin.",
                image_filename="tail_conventional.jpg",
                badge="Classic & Reliable",
                details=[
                    "Independent pitch and yaw aerodynamic trim",
                    "Straightforward hinge geometry and control linkage",
                    "Low structural risk and simple analysis",
                ],
            ),
            WizardOption(
                id="t_tail",
                title="T-Tail",
                subtitle="Horizontal stabilizer mounted atop the vertical fin.",
                image_filename="tail_t_tail.jpg",
                badge="Clean Flow",
                details=[
                    "Operates in clean freestream air above wing/prop wash",
                    "High control authority allowing smaller stabilizer area",
                    "Imposes strong bending and torsional loads on vertical fin",
                ],
            ),
            WizardOption(
                id="v_tail",
                title="V-Tail / Ruddervators",
                subtitle="Two angled surfaces combining elevator and rudder functions.",
                image_filename="tail_v_tail.jpg",
                badge="Low Drag",
                details=[
                    "Combines pitch and yaw control via mixer software",
                    "Fewer surface intersections reduce interference drag",
                    "Provides propeller clearance for aft-mounted pusher motors",
                ],
            ),
        ]

        self.grid_tail = WizardCardGrid(options, columns=3, parent=page, image_height=130)
        self.grid_tail.selection_changed.connect(
            lambda cid: self._on_selection_changed("tail_type", cid)
        )
        layout.addWidget(self.grid_tail)
        return page

    def _create_propulsion_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="tractor",
                title="Tractor (Nose)",
                subtitle="Single propeller mounted on the forward fuselage nose.",
                image_filename="prop_tractor.jpg",
                badge="High Efficiency",
                details=[
                    "Propeller operates in clean, undisturbed incoming air",
                    "Slipstream provides excellent motor and ESC cooling",
                    "Nose camera or forward sensor view may be obstructed",
                ],
            ),
            WizardOption(
                id="pusher",
                title="Pusher (Aft / Pylon)",
                subtitle="Propeller mounted aft of fuselage or on an over-wing pylon.",
                image_filename="prop_pusher.jpg",
                badge="Clear Nose",
                details=[
                    "Unobstructed forward view for optical payloads and gimbals",
                    "Laminar airflow over forward fuselage reduces body drag",
                    "Slightly reduced propeller efficiency (~3-5%) in body wake",
                ],
            ),
            WizardOption(
                id="twin",
                title="Twin Tractor (Wing)",
                subtitle="Dual motors mounted on the wing leading edge.",
                image_filename="prop_twin.jpg",
                badge="Redundant & Powerful",
                details=[
                    "Engine-out redundancy for critical mission safety",
                    "Propwash over wing enhances local dynamic lift",
                    "Clear nose compartment; increased motor/ESC wiring mass",
                ],
            ),
        ]

        self.grid_prop = WizardCardGrid(options, columns=3, parent=page, image_height=130)
        self.grid_prop.selection_changed.connect(
            lambda cid: self._on_selection_changed("propulsion_layout", cid)
        )
        layout.addWidget(self.grid_prop)
        return page

    def _create_battery_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="lipo",
                title="Lithium Polymer (LiPo)",
                subtitle="Standard pouch cell RC / UAV pack.",
                badge="160 Wh/kg",
                details=[
                    "High continuous discharge rates (25C - 100C)",
                    "Optimal for high-thrust takeoff and aggressive maneuvers",
                    "Moderate specific energy limits long-range endurance",
                ],
            ),
            WizardOption(
                id="lihv",
                title="High-Voltage LiPo (LiHV)",
                subtitle="Polymer cells charged to 4.35V per cell.",
                badge="195 Wh/kg",
                details=[
                    "~15% greater capacity than standard LiPo",
                    "Strong burst power discharge capability",
                    "Balanced choice for medium-endurance missions",
                ],
            ),
            WizardOption(
                id="li_ion_18650",
                title="Lithium-Ion 18650",
                subtitle="Standard cylindrical metal-cased cells.",
                badge="230 Wh/kg",
                details=[
                    "High energy density for extended cruise missions",
                    "Lower continuous discharge rate (2C - 5C)",
                    "Cost-effective, mature, and widely available",
                ],
            ),
            WizardOption(
                id="li_ion_21700",
                title="Lithium-Ion 21700",
                subtitle="High-capacity cylindrical cells (e.g. Molicel P42A/P45B).",
                badge="260 Wh/kg",
                details=[
                    "Excellent energy density with 10C - 15C discharge current",
                    "Modern benchmark for long-range surveillance UAVs",
                    "Maximizes cruise flight time per unit battery weight",
                ],
            ),
            WizardOption(
                id="solid_state",
                title="Solid-State Battery",
                subtitle="Next-generation solid electrolyte lithium chemistry.",
                badge="350 Wh/kg",
                details=[
                    "Very high energy density for 2-3x endurance potential",
                    "Enhanced thermal safety with non-flammable electrolyte",
                    "Emerging technology with premium cost and limited sourcing",
                ],
            ),
        ]

        self.grid_battery = WizardCardGrid(options, columns=2, parent=page, image_height=50)
        self.grid_battery.selection_changed.connect(
            lambda cid: self._on_selection_changed("battery_chemistry", cid)
        )
        layout.addWidget(self.grid_battery)
        return page

    def _build_summary_sidebar(self) -> QWidget:
        tok = tokens()
        sidebar = QFrame()
        sidebar.setObjectName("wizard_sidebar")
        sidebar.setStyleSheet(
            f"QFrame#wizard_sidebar {{"
            f"  background-color: {tok.get('surface', '#282828')};"
            f"  border: 1px solid {tok.get('border', '#3d3d3d')};"
            f"  border-radius: 6px;"
            f"}}"
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        side_title = QLabel("Concept Summary")
        side_font = QFont()
        side_font.setBold(True)
        side_font.setPointSize(11)
        side_title.setFont(side_font)
        side_title.setStyleSheet(f"color: {tok.get('text', '#ffffff')};")
        layout.addWidget(side_title)

        self.sum_payload = QLabel("0.50 kg")
        self.sum_endurance = QLabel("45 min")
        self.sum_speed = QLabel("18.0 m/s")
        self.sum_config = QLabel("Conventional")
        self.sum_wing_loc = QLabel("High-Wing")
        self.sum_planform = QLabel("Tapered")
        self.sum_tail = QLabel("Conventional")
        self.sum_prop = QLabel("Tractor")
        self.sum_battery = QLabel("Li-Ion 21700")

        items = [
            ("Payload Mass:", self.sum_payload),
            ("Flight Endurance:", self.sum_endurance),
            ("Cruise Speed:", self.sum_speed),
            ("Configuration:", self.sum_config),
            ("Wing Placement:", self.sum_wing_loc),
            ("Wing Planform:", self.sum_planform),
            ("Tail Type:", self.sum_tail),
            ("Propulsion:", self.sum_prop),
            ("Battery:", self.sum_battery),
        ]

        for title, val_lbl in items:
            row = QHBoxLayout()
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(f"color: {tok.get('text_muted', '#b9b9b9')}; font-size: 11px;")
            val_lbl.setStyleSheet(
                f"color: {tok.get('accent', '#4772b3')}; font-size: 11px; font-weight: bold;"
            )
            row.addWidget(t_lbl)
            row.addStretch(1)
            row.addWidget(val_lbl)
            layout.addLayout(row)

        layout.addStretch(1)

        # Estimated parameters preview box
        est_box = QGroupBox("Estimated Parameters")
        est_box.setStyleSheet(
            f"QGroupBox {{"
            f"  color: {tok.get('text_muted', '#b9b9b9')};"
            f"  font-size: 11px;"
            f"  font-weight: bold;"
            f"  border: 1px solid {tok.get('border', '#3d3d3d')};"
            f"  border-radius: 6px;"
            f"  margin-top: 10px;"
            f"  padding-top: 12px;"
            f"}}"
        )
        est_layout = QVBoxLayout(est_box)
        est_layout.setSpacing(4)

        self.lbl_est_cd0 = QLabel("CD0: ~0.027")
        self.lbl_est_e = QLabel("Oswald e: ~0.82")
        self.lbl_est_prop_eta = QLabel("Propeller Efficiency: ~80%")
        self.lbl_est_bat_wh = QLabel("Energy Density: ~260 Wh/kg")

        for lbl in (self.lbl_est_cd0, self.lbl_est_e, self.lbl_est_prop_eta, self.lbl_est_bat_wh):
            lbl.setStyleSheet(f"color: {tok.get('text', '#ffffff')}; font-size: 11px;")
            est_layout.addWidget(lbl)

        layout.addWidget(est_box)
        return sidebar

    def _on_selection_changed(self, key: str, value: str) -> None:
        self.state[key] = value
        self._update_summary()

    def _on_mission_cell_changed(self) -> None:
        self.state["payload_kg"] = self.cell_payload.value() / 1000.0
        self.state["endurance_min"] = self.cell_endurance.value()
        self.state["cruise_speed_ms"] = self.cell_cruise_speed.value()
        self.state["cruise_alt_m"] = self.cell_altitude.value()
        self.state["stall_speed_ms"] = self.cell_stall_speed.value()
        self.state["takeoff_run_m"] = self.cell_takeoff_run.value()
        self.state["climb_rate_ms"] = self.cell_climb_rate.value()
        self._update_summary()

    def _update_summary(self) -> None:
        self.sum_payload.setText(f"{self.state.get('payload_kg', 0.5):.2f} kg")
        self.sum_endurance.setText(f"{self.state.get('endurance_min', 45.0):.0f} min")
        self.sum_speed.setText(f"{self.state.get('cruise_speed_ms', 18.0):.1f} m/s")

        cfg_names = {
            "conventional": "Conventional",
            "pod_boom": "Pod-and-Boom",
            "twin_boom": "Twin-Boom",
            "flying_wing": "Flying Wing",
        }
        self.sum_config.setText(cfg_names.get(self.state.get("config_type", ""), "-"))

        loc_names = {
            "high": "High-Wing",
            "mid": "Mid-Wing",
            "low": "Low-Wing",
        }
        self.sum_wing_loc.setText(loc_names.get(self.state.get("wing_location", ""), "-"))

        plan_names = {
            "rectangular": "Rectangular",
            "tapered": "Tapered",
            "swept": "Swept-Tapered",
            "delta": "Delta",
        }
        self.sum_planform.setText(plan_names.get(self.state.get("wing_planform", ""), "-"))

        tail_names = {
            "conventional": "Conventional",
            "t_tail": "T-Tail",
            "v_tail": "V-Tail",
        }
        self.sum_tail.setText(tail_names.get(self.state.get("tail_type", ""), "-"))

        prop_names = {
            "tractor": "Tractor",
            "pusher": "Pusher",
            "twin": "Twin Tractor",
        }
        self.sum_prop.setText(prop_names.get(self.state.get("propulsion_layout", ""), "-"))

        bat_names = {
            "lipo": "LiPo (160 Wh/kg)",
            "lihv": "LiHV (195 Wh/kg)",
            "li_ion_18650": "Li-Ion 18650 (230 Wh/kg)",
            "li_ion_21700": "Li-Ion 21700 (260 Wh/kg)",
            "solid_state": "Solid-State (350 Wh/kg)",
        }
        self.sum_battery.setText(bat_names.get(self.state.get("battery_chemistry", ""), "-"))

    def go_to_step(self, step_idx: int) -> None:
        total_steps = self.stack.count()
        if not (0 <= step_idx < total_steps):
            return

        self.stack.setCurrentIndex(step_idx)

        # Update step pills
        for idx, btn in enumerate(self._step_buttons):
            btn.setChecked(idx == step_idx)

        # Update counter & headers
        self.step_counter_lbl.setText(f"STEP {step_idx + 1} OF {total_steps}")
        step_meta = [
            (
                "Mission & Performance Requirements",
                "Define payload capacity and primary mission flight envelope requirements.",
            ),
            (
                "Aircraft Configuration",
                "Select overall fuselage, wing, and tail architecture concept.",
            ),
            (
                "Wing Vertical Placement",
                "Select wing-to-fuselage vertical mounting height and interference drag profile.",
            ),
            (
                "Wing Planform Shape",
                "Select wing planform geometry, taper ratio, and lift distribution.",
            ),
            (
                "Tail Configuration",
                "Select empennage layout and aerodynamic control surface arrangement.",
            ),
            (
                "Propulsion Architecture",
                "Select motor arrangement and propeller installation location.",
            ),
            (
                "Battery Technology",
                "Select battery cell chemistry and nominal specific energy density.",
            ),
        ]
        if step_idx < len(step_meta):
            self.step_title_lbl.setText(step_meta[step_idx][0])
            self.step_desc_lbl.setText(step_meta[step_idx][1])

        # Update navigation buttons
        self.btn_back.setEnabled(step_idx > 0)
        if step_idx == total_steps - 1:
            self.btn_next.setText("Apply Concept")
            set_button_role(self.btn_next, "primary", icon_source="fa6s.check")
        else:
            self.btn_next.setText("Next")
            set_button_role(self.btn_next, "primary", icon_source="fa6s.chevron-right")

    def next_step(self) -> None:
        current = self.stack.currentIndex()
        if current < self.stack.count() - 1:
            self.go_to_step(current + 1)
        else:
            self.accept()

    def prev_step(self) -> None:
        current = self.stack.currentIndex()
        if current > 0:
            self.go_to_step(current - 1)


# Backward-compatible alias
SizingWizardDialog = ConceptWizardDialog
