"""Preliminary Sizing Wizard Dialog for SetUAV Studio.

Provides an interactive multi-step visual wizard that guides the engineer
through high-level mission and architectural decisions:
1. Mission & Performance Requirements
2. Aircraft Architecture (Configuration)
3. Wing Vertical Placement
4. Wing Planform Shape
5. Tail Configuration
6. Propulsion Layout
7. Battery Chemistry
8. Summary & Sizing Requirements Export
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.theme import tokens
from setuav_studio.ui.widget.button import set_button_role

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
    """Interactive visual option card with thumbnail, title, and pros/cons."""

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
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header_row.addWidget(title_lbl)

        if option.badge:
            badge_lbl = QLabel(f" {option.badge} ")
            badge_font = QFont()
            badge_font.setPointSize(8)
            badge_font.setBold(True)
            badge_lbl.setFont(badge_font)
            badge_lbl.setStyleSheet(
                "background-color: rgba(71, 114, 179, 0.25); "
                "color: #5db6ea; border-radius: 4px; padding: 2px 4px;"
            )
            header_row.addWidget(badge_lbl)

        layout.addLayout(header_row)

        # Subtitle
        sub_lbl = QLabel(option.subtitle)
        sub_lbl.setWordWrap(True)
        sub_font = QFont()
        sub_font.setPointSize(9)
        sub_lbl.setFont(sub_font)
        sub_lbl.setStyleSheet("color: #b9b9b9;")
        layout.addWidget(sub_lbl)

        # Details / bullets
        if option.details:
            details_text = "\n".join(f"• {d}" for d in option.details)
            det_lbl = QLabel(details_text)
            det_lbl.setWordWrap(True)
            det_font = QFont()
            det_font.setPointSize(8)
            det_lbl.setFont(det_font)
            det_lbl.setStyleSheet("color: #848484; margin-top: 2px;")
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
        accent = tok.get("accent", "#4772b3")
        border = tok.get("border_strong", "#6c6c6c")

        if self._selected:
            self.setStyleSheet(
                f"WizardOptionCard {{"
                f"  background-color: {surface};"
                f"  border: 2px solid {accent};"
                f"  border-radius: 8px;"
                f"}}"
            )
        else:
            self.setStyleSheet(
                f"WizardOptionCard {{"
                f"  background-color: {surface};"
                f"  border: 1px solid {border};"
                f"  border-radius: 8px;"
                f"}}"
                f"WizardOptionCard:hover {{"
                f"  border: 1px solid {accent};"
                f"}}"
            )


class WizardCardGrid(QWidget):
    """Grid container for selectable visual cards with single-selection."""

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


class SizingWizardDialog(QDialog):
    """Interactive multi-step visual wizard for preliminary UAV sizing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sizing.wizard_dialog")
        self.setWindowTitle("UAV Preliminary Sizing Wizard — SetUAV Studio")
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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Header Banner & Step Title
        header_frame = QFrame()
        header_frame.setObjectName("wizard_header")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 10, 12, 10)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        self.step_counter_lbl = QLabel("ADIM 1 / 7")
        self.step_counter_lbl.setStyleSheet("color: #5db6ea; font-size: 11px; font-weight: bold;")
        title_vbox.addWidget(self.step_counter_lbl)

        self.step_title_lbl = QLabel("Görev ve Performans Gereksinimleri")
        step_title_font = QFont()
        step_title_font.setPointSize(13)
        step_title_font.setBold(True)
        self.step_title_lbl.setFont(step_title_font)
        title_vbox.addWidget(self.step_title_lbl)

        self.step_desc_lbl = QLabel("İHA'nın taşıyacağı faydalı yük ve hedef uçuş performans hedefleri.")
        self.step_desc_lbl.setStyleSheet("color: #b9b9b9; font-size: 10px;")
        title_vbox.addWidget(self.step_desc_lbl)

        header_layout.addLayout(title_vbox, 1)

        # Quick breadcrumbs / step tabs
        self.step_pill_layout = QHBoxLayout()
        self.step_pill_layout.setSpacing(4)
        self._step_buttons: list[QPushButton] = []
        step_short_names = ["Görev", "Gövde", "Kanat Düşey", "Kanat Form", "Kuyruk", "İtki", "Batarya"]
        for idx, name in enumerate(step_short_names):
            btn = QPushButton(f"{idx+1}. {name}")
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background-color: #282828; color: #848484; border: 1px solid #3d3d3d; border-radius: 4px; padding: 2px 8px; font-size: 9px; }"
                "QPushButton:checked { background-color: #4772b3; color: #ffffff; border: 1px solid #5db6ea; font-weight: bold; }"
                "QPushButton:hover { border: 1px solid #5db6ea; }"
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
        nav_layout.setContentsMargins(6, 6, 6, 6)

        self.btn_cancel = QPushButton("İptal")
        self.btn_cancel.clicked.connect(self.reject)
        nav_layout.addWidget(self.btn_cancel)

        nav_layout.addStretch(1)

        self.btn_back = QPushButton("◀ Geri")
        self.btn_back.clicked.connect(self.prev_step)
        nav_layout.addWidget(self.btn_back)

        self.btn_next = QPushButton("İleri ▶")
        set_button_role(self.btn_next, "primary")
        self.btn_next.clicked.connect(self.next_step)
        nav_layout.addWidget(self.btn_next)

        main_layout.addWidget(nav_frame)

        self.go_to_step(0)

    def _build_pages(self) -> None:
        """Create all wizard pages."""
        # Page 0: Mission Requirements
        self.page_mission = self._create_mission_page()
        self.stack.addWidget(self.page_mission)

        # Page 1: Architecture
        self.page_arch = self._create_architecture_page()
        self.stack.addWidget(self.page_arch)

        # Page 2: Wing Location
        self.page_wing_loc = self._create_wing_location_page()
        self.stack.addWidget(self.page_wing_loc)

        # Page 3: Wing Planform
        self.page_wing_plan = self._create_wing_planform_page()
        self.stack.addWidget(self.page_wing_plan)

        # Page 4: Tail Configuration
        self.page_tail = self._create_tail_page()
        self.stack.addWidget(self.page_tail)

        # Page 5: Propulsion Layout
        self.page_prop = self._create_propulsion_page()
        self.stack.addWidget(self.page_prop)

        # Page 6: Battery Chemistry
        self.page_battery = self._create_battery_page()
        self.stack.addWidget(self.page_battery)

    def _create_mission_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        intro = QLabel(
            "Hedeflediğiniz İHA görevinin sayısal temel isterlerini giriniz. "
            "Bu parametreler Eşleme Diyagramı (Matching Chart) kısıt analizinin sınır çizgilerini belirler."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #b9b9b9; font-size: 11px;")
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setSpacing(12)

        # Input fields
        self.input_payload = QLineEdit(str(self.state["payload_kg"] * 1000.0))
        self.input_endurance = QLineEdit(str(self.state["endurance_min"]))
        self.input_cruise_speed = QLineEdit(str(self.state["cruise_speed_ms"]))
        self.input_altitude = QLineEdit(str(self.state["cruise_alt_m"]))
        self.input_stall_speed = QLineEdit(str(self.state["stall_speed_ms"]))
        self.input_takeoff_run = QLineEdit(str(self.state["takeoff_run_m"]))
        self.input_climb_rate = QLineEdit(str(self.state["climb_rate_ms"]))

        fields = [
            ("Faydalı Yük Kütlesi (Payload)", self.input_payload, "gram (g)", "Kamera, gimbal, sensör veya kargo ağırlığı"),
            ("Hedef Uçuş Süresi (Endurance)", self.input_endurance, "dakika (dk)", "Batarya ile hedeflenen havada kalış süresi"),
            ("Seyir Hızı (Cruise Speed)", self.input_cruise_speed, "m/s", "Ekonomik seyir uçuşu operasyon hızı"),
            ("Seyir İrtifası (Altitude)", self.input_altitude, "metre (m)", "Operasyon irtifası (hava yoğunluğu hesabı için)"),
            ("Maksimum Stall Hızı (Vs)", self.input_stall_speed, "m/s", "Güvenli tutunma alt hız sınırı"),
            ("Kalkış Mesafesi (Takeoff Run)", self.input_takeoff_run, "metre (m)", "Yerden teker kesme pist uzunluğu"),
            ("Tırmanma Hızı (Climb Rate)", self.input_climb_rate, "m/s", "Deniz seviyesinde dikey tırmanma varyosu"),
        ]

        for row, (label_text, edit, unit, hint) in enumerate(fields):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-weight: bold; color: #ffffff;")
            grid.addWidget(lbl, row, 0)

            edit.setFixedHeight(28)
            edit.setStyleSheet("background-color: #1d1d1d; border: 1px solid #3d3d3d; border-radius: 4px; padding: 2px 6px; color: #ffffff;")
            edit.textChanged.connect(self._on_mission_input_changed)
            grid.addWidget(edit, row, 1)

            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet("color: #5db6ea; font-size: 10px; font-weight: bold;")
            grid.addWidget(unit_lbl, row, 2)

            hint_lbl = QLabel(hint)
            hint_lbl.setStyleSheet("color: #848484; font-size: 9px;")
            grid.addWidget(hint_lbl, row, 3)

        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    def _create_architecture_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="conventional",
                title="Konvansiyonel (Conventional)",
                subtitle="Geleneksel gövde, kanat ve kuyruk mimarisi.",
                image_filename="config_conventional.jpg",
                badge="En Yaygın",
                details=[
                    "Yüksek stabilite ve kolay üretim",
                    "İç hacim geniştir, aviyonik yerleşimi basittir",
                    "Orta seviye aerodinamik girişim direnci",
                ],
            ),
            WizardOption(
                id="pod_boom",
                title="Kapsül ve Boru Kuyruk (Pod-and-Boom)",
                subtitle="Kompakt gövde podu ve ince karbon kuyruk borusu.",
                image_filename="config_pod_boom.jpg",
                badge="Hafif Gövde",
                details=[
                    "Minimum ıslak alan ve düşük parazit direnç",
                    "Hafif karbon boru yapı ile ağırlık tasarrufu",
                    "Burunda veya arkada itici motor yerleşimi",
                ],
            ),
            WizardOption(
                id="twin_boom",
                title="İkiz Kirişli (Twin-Boom)",
                subtitle="Kanatlardan geriye uzanan çift kuyruk kirişi.",
                image_filename="config_twin_boom.jpg",
                badge="İticiye Uygun",
                details=[
                    "Gövde arkasına itici motor yerleşiminde pervaneyi korur",
                    "Kamera için temiz ve titreşimsiz burun hacmi",
                    "Geniş faydalı yük ve batarya bölmesi",
                ],
            ),
            WizardOption(
                id="flying_wing",
                title="Uçan Kanat (Flying Wing / Tailless)",
                subtitle="Ayrı gövde ve kuyruk taşımayan aerodinamik delta form.",
                image_filename="config_flying_wing.jpg",
                badge="Maksimum Verim",
                details=[
                    "Kuyruk olmadığı için minimum parazit sürtünme",
                    "En yüksek süzülme oranı (L/D) ve yüksek menzil",
                    "Boyuna stabilite için refleks profil veya ok açısı gerektirir",
                ],
            ),
        ]

        self.grid_arch = WizardCardGrid(options, columns=2, parent=page, image_height=140)
        self.grid_arch.selection_changed.connect(lambda cid: self._on_selection_changed("config_type", cid))
        layout.addWidget(self.grid_arch)
        return page

    def _create_wing_location_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="high",
                title="Üstten Kanat (High-Wing)",
                subtitle="Kanat gövdenin en üst çatısına monte edilir.",
                image_filename="wing_loc_high.png",
                badge="Doğal Kararlılık",
                details=[
                    "Sarkaç etkisi (pendulum effect) ile yüksek yanal kararlılık",
                    "Gövde altı yer açıklığı yüksektir (çim inişi ve kamera koruması)",
                    "Kesintisiz kargo ve batarya iç hacmi",
                ],
            ),
            WizardOption(
                id="mid",
                title="Ortadan Kanat (Mid-Wing)",
                subtitle="Kanat gövdenin tam yatay simetri ekseninden geçer.",
                image_filename="wing_loc_mid.png",
                badge="En Düşük Direnç",
                details=[
                    "En düşük aerodinamik girişim direnci (interference drag)",
                    "Simetrik yalpa ve yuvarlanma tepkisi (akrobasi/yüksek manevra)",
                    "Kanat ana kirişi gövde iç hacmini ortadan böler",
                ],
            ),
            WizardOption(
                id="low",
                title="Alttan Kanat (Low-Wing)",
                subtitle="Kanat gövdenin tabanına monte edilir.",
                image_filename="wing_loc_low.png",
                badge="Yer Etkisi",
                details=[
                    "Kalkış ve inişte yer etkisi (ground effect) belirgindir",
                    "Yanal kararlılık için pozitif dihedral açısı gerektirir",
                    "Üstten kargo ve batarya kapağıyla çok kolay erişim",
                ],
            ),
        ]

        self.grid_wing_loc = WizardCardGrid(options, columns=3, parent=page, image_height=130)
        self.grid_wing_loc.selection_changed.connect(lambda cid: self._on_selection_changed("wing_location", cid))
        layout.addWidget(self.grid_wing_loc)
        return page

    def _create_wing_planform_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="rectangular",
                title="Dikdörtgen (Rectangular)",
                subtitle="Sabit veterli düz kanat geometrisi.",
                image_filename="planform_rectangular.png",
                badge="Kolay Üretim",
                details=[
                    "Üretimi ve kaplaması en basit kanat formu",
                    "Kökten uca doğru perdövites (stall) eğilimi güvenlidir",
                    "Uçlarda indüklenmiş direnç biraz daha yüksektir",
                ],
            ),
            WizardOption(
                id="tapered",
                title="Trapez / Sivrilen (Tapered)",
                subtitle="Uçlara doğru sivrilen veter dağılımı (lambda ~ 0.4 - 0.6).",
                image_filename="planform_tapered.png",
                badge="Optimum L/D",
                details=[
                    "Eliptik yük dağılımına en yakın pratik form",
                    "Düşük indüklenmiş sürtünme ve yüksek yapısal verim",
                    "Hafif kanat yapısı ile uzun menzil uçuşu",
                ],
            ),
            WizardOption(
                id="swept",
                title="Geriye Ok Açılı (Swept-Tapered)",
                subtitle="Hücum kenarı geriye doğru açılı kanat.",
                image_filename="planform_swept.png",
                badge="Yüksek Hız",
                details=[
                    "Kritik Mach sayısını artırır ve dalga direncini öteler",
                    "Uçan kanatlarda boyuna kararlılık ve yapay dihedral sağlar",
                    "Uç perdövitesi (tip stall) eğilimine dikkat edilmelidir",
                ],
            ),
            WizardOption(
                id="delta",
                title="Delta (Delta Wing)",
                subtitle="Geniş kök veterli üçgen kanat formu.",
                image_filename="planform_delta.png",
                badge="Yüksek Mukavemet",
                details=[
                    "Geniş kanat alanı ve devasa iç batarya hacmi",
                    "Yüksek hücum açılarında girdap taşıması (vortex lift)",
                    "Düşük açıklık oranı nedeniyle yüksek indüklenmiş direnç",
                ],
            ),
        ]

        self.grid_wing_plan = WizardCardGrid(options, columns=2, parent=page, image_height=130)
        self.grid_wing_plan.selection_changed.connect(lambda cid: self._on_selection_changed("wing_planform", cid))
        layout.addWidget(self.grid_wing_plan)
        return page

    def _create_tail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="conventional",
                title="Konvansiyonel Kuyruk (Conventional)",
                subtitle="Ayrı dikey fin ve gövdeye bağlı yatay kuyruk.",
                image_filename="tail_conventional.jpg",
                badge="Klasik & Güvenilir",
                details=[
                    "İrtifa ve istikamet kontrolü tamamen bağımsızdır",
                    "Tasarımı, trimi ve kontrol yüzeyi ayrımı kolaydır",
                    "Düşük yapısal ağırlık ve basit menteşe mekaniği",
                ],
            ),
            WizardOption(
                id="t_tail",
                title="T-Kuyruk (T-Tail)",
                subtitle="Yatay stabilize dikey finin en tepesine montelidir.",
                image_filename="tail_t_tail.jpg",
                badge="Temiz Akış",
                details=[
                    "Kanat ve pervane girdabından (wake) uzakta temiz akışta çalışır",
                    "Yüksek kontrol otoritesi ve daha küçük gerekli kuyruk alanı",
                    "Dikey fin kökünde yüksek burulma yükü taşır",
                ],
            ),
            WizardOption(
                id="v_tail",
                title="V-Kuyruk (V-Tail / Ruddervators)",
                subtitle="İki açılı stabilize yüzeyinin kontrolü birleştirmesi.",
                image_filename="tail_v_tail.jpg",
                badge="Düşük Direnç",
                details=[
                    "İki yüzey ile hem pitch hem yaw kontrolü (mikserli kontrol)",
                    "Daha az birleşim noktası ile düşük girişim direnci",
                    "Gövde arkası itici pervane açıklığı için elverişlidir",
                ],
            ),
        ]

        self.grid_tail = WizardCardGrid(options, columns=3, parent=page, image_height=130)
        self.grid_tail.selection_changed.connect(lambda cid: self._on_selection_changed("tail_type", cid))
        layout.addWidget(self.grid_tail)
        return page

    def _create_propulsion_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="tractor",
                title="Çekici Motor (Tractor — Burun)",
                subtitle="Pervane uçağın en ön burnunda çekici konumdadır.",
                image_filename="prop_tractor.jpg",
                badge="Yüksek Verim",
                details=[
                    "Pervane temiz havada çalışır (yüksek pervane verimi: %80-82)",
                    "Motor ve ESC doğrudan pervane rüzgarıyla mükemmel soğur",
                    "Burundaki kamera veya sensör görüşünü pervane bölebilir",
                ],
            ),
            WizardOption(
                id="pusher",
                title="İtici Motor (Pusher — Kanat Arkası/Gövde)",
                subtitle="Pervane gövdenin arkasında veya kanat üstü pilonda iter.",
                image_filename="prop_pusher.jpg",
                badge="Temiz Burun",
                details=[
                    "Burun tamamen boştur; gimbal ve kamera için kesintisiz görüş",
                    "Gövde üzerinde laminer hava akışı (düşük sürtünme)",
                    "Pervane gövde izinde çalıştığı için verim %3-5 daha düşüktür",
                ],
            ),
            WizardOption(
                id="twin",
                title="Çift Motor (Twin Engine — Kanat Önü)",
                subtitle="Kanat hücum kenarına simetrik monte edilmiş iki motor.",
                image_filename="prop_twin.jpg",
                badge="Yedekli & Güçlü",
                details=[
                    "Motor arızasında tek motorla uçuş güvenliği (yedeklilik)",
                    "Kanat üstü akış üflemesi (blown wing) ile ilave kaldırma",
                    "Burun boştur; iki kat motor/ESC ağırlığı ve kablo tesisatı",
                ],
            ),
        ]

        self.grid_prop = WizardCardGrid(options, columns=3, parent=page, image_height=130)
        self.grid_prop.selection_changed.connect(lambda cid: self._on_selection_changed("propulsion_layout", cid))
        layout.addWidget(self.grid_prop)
        return page

    def _create_battery_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        options = [
            WizardOption(
                id="lipo",
                title="Lityum Polimer (LiPo)",
                subtitle="Standart RC ve İHA bataryası.",
                badge="160 Wh/kg",
                details=[
                    "Yüksek anlık akım verme (C-rate: 25C - 100C)",
                    "Kalkış ve tırmanmada yüksek güç ihtiyacı için ideal",
                    "Düşük özgül enerji nedeniyle orta seviye uçuş süresi",
                ],
            ),
            WizardOption(
                id="lihv",
                title="Yüksek Voltajlı LiPo (LiHV)",
                subtitle="Hücre başı 4.35V şarj edilen polimer batarya.",
                badge="195 Wh/kg",
                details=[
                    "Standart LiPo'ya kıyasla %15 daha fazla enerji depolama",
                    "Yüksek güç deşarj kabiliyeti",
                    "Orta-uzun menzil görevler için dengeli seçenek",
                ],
            ),
            WizardOption(
                id="li_ion_18650",
                title="Lityum İyon 18650 (Li-Ion)",
                subtitle="Standart silindirik çelik kılıflı hücreler.",
                badge="230 Wh/kg",
                details=[
                    "Yüksek enerji yoğunluğu, uzun menzil seyir uçuşu için ideal",
                    "Daha düşük anlık C deşarj oranı (2C - 5C)",
                    "Ekonomik ve yaygın hücre mimarisi",
                ],
            ),
            WizardOption(
                id="li_ion_21700",
                title="Lityum İyon 21700 (Li-Ion)",
                subtitle="Yeni nesil yüksek kapasiteli silindirik hücreler (Molicel P42A/P45B vb.).",
                badge="260 Wh/kg",
                details=[
                    "Mükemmel enerji yoğunluğu ve 10C-15C akım kapasitesi",
                    "Uzun menzilli keşif İHA'larında güncel endüstri standardı",
                    "Ağırlık başına maksimum uçuş süresi",
                ],
            ),
            WizardOption(
                id="solid_state",
                title="Katı Hal Batarya (Solid-State)",
                subtitle="Gelecek nesil katı elektrolitli lityum hücre teknolojisi.",
                badge="350 Wh/kg",
                details=[
                    "Devasa enerji yoğunluğu ile 2-3 kat uçuş süresi potansiyeli",
                    "Yüksek termal güvenlik ve alev almaz yapı",
                    "Yüksek maliyet ve sınırlı piyasa temini",
                ],
            ),
        ]

        self.grid_battery = WizardCardGrid(options, columns=2, parent=page, image_height=50)
        self.grid_battery.selection_changed.connect(lambda cid: self._on_selection_changed("battery_chemistry", cid))
        layout.addWidget(self.grid_battery)
        return page

    def _build_summary_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("wizard_sidebar")
        sidebar.setStyleSheet(
            "QFrame#wizard_sidebar { background-color: #242424; border: 1px solid #333333; border-radius: 8px; padding: 10px; }"
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        side_title = QLabel("Seçim Özeti")
        side_font = QFont()
        side_font.setBold(True)
        side_font.setPointSize(11)
        side_title.setFont(side_font)
        side_title.setStyleSheet("color: #ffffff;")
        layout.addWidget(side_title)

        # Labels for summary items
        self.sum_payload = QLabel("0.5 kg")
        self.sum_endurance = QLabel("45 dk")
        self.sum_speed = QLabel("18 m/s")
        self.sum_config = QLabel("Konvansiyonel")
        self.sum_wing_loc = QLabel("Üstten Kanat")
        self.sum_planform = QLabel("Trapez")
        self.sum_tail = QLabel("Konvansiyonel")
        self.sum_prop = QLabel("Çekici Motor")
        self.sum_battery = QLabel("Li-Ion 21700")

        items = [
            ("Faydalı Yük:", self.sum_payload),
            ("Uçuş Süresi:", self.sum_endurance),
            ("Seyir Hızı:", self.sum_speed),
            ("Gövde Tipi:", self.sum_config),
            ("Kanat Yüksekliği:", self.sum_wing_loc),
            ("Kanat Formu:", self.sum_planform),
            ("Kuyruk Tipi:", self.sum_tail),
            ("İtki Yerleşimi:", self.sum_prop),
            ("Batarya:", self.sum_battery),
        ]

        for title, val_lbl in items:
            row = QHBoxLayout()
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("color: #848484; font-size: 10px;")
            val_lbl.setStyleSheet("color: #5db6ea; font-size: 10px; font-weight: bold;")
            row.addWidget(t_lbl)
            row.addStretch(1)
            row.addWidget(val_lbl)
            layout.addLayout(row)

        layout.addStretch(1)

        # Estimated coefficients preview box
        est_box = QGroupBox("Tahmini Katsayılar")
        est_box.setStyleSheet("QGroupBox { color: #b9b9b9; font-size: 10px; font-weight: bold; border: 1px solid #3d3d3d; border-radius: 6px; margin-top: 8px; padding-top: 10px; }")
        est_layout = QVBoxLayout(est_box)
        est_layout.setSpacing(4)

        self.lbl_est_cd0 = QLabel("CD0: ~0.027")
        self.lbl_est_e = QLabel("Oswald e: ~0.82")
        self.lbl_est_prop_eta = QLabel("Pervane Verimi: ~80%")
        self.lbl_est_bat_wh = QLabel("Enerji Yoğunluğu: ~260 Wh/kg")

        for lbl in (self.lbl_est_cd0, self.lbl_est_e, self.lbl_est_prop_eta, self.lbl_est_bat_wh):
            lbl.setStyleSheet("color: #ffffff; font-size: 9px;")
            est_layout.addWidget(lbl)

        layout.addWidget(est_box)
        return sidebar

    def _on_selection_changed(self, key: str, value: str) -> None:
        self.state[key] = value
        self._update_summary()

    def _on_mission_input_changed(self) -> None:
        try:
            self.state["payload_kg"] = float(self.input_payload.text()) / 1000.0
            self.state["endurance_min"] = float(self.input_endurance.text())
            self.state["cruise_speed_ms"] = float(self.input_cruise_speed.text())
            self.state["cruise_alt_m"] = float(self.input_altitude.text())
            self.state["stall_speed_ms"] = float(self.input_stall_speed.text())
            self.state["takeoff_run_m"] = float(self.input_takeoff_run.text())
            self.state["climb_rate_ms"] = float(self.input_climb_rate.text())
        except ValueError:
            pass
        self._update_summary()

    def _update_summary(self) -> None:
        self.sum_payload.setText(f"{self.state.get('payload_kg', 0.5):.2f} kg")
        self.sum_endurance.setText(f"{self.state.get('endurance_min', 45.0):.0f} dk")
        self.sum_speed.setText(f"{self.state.get('cruise_speed_ms', 18.0):.1f} m/s")

        cfg_names = {
            "conventional": "Konvansiyonel",
            "pod_boom": "Pod & Boru",
            "twin_boom": "İkiz Kirişli",
            "flying_wing": "Uçan Kanat",
        }
        self.sum_config.setText(cfg_names.get(self.state.get("config_type", ""), "-"))

        loc_names = {"high": "Üstten", "mid": "Ortadan", "low": "Alttan"}
        self.sum_wing_loc.setText(loc_names.get(self.state.get("wing_location", ""), "-"))

        plan_names = {"rectangular": "Dikdörtgen", "tapered": "Trapez", "swept": "Ok Açılı", "delta": "Delta"}
        self.sum_planform.setText(plan_names.get(self.state.get("wing_planform", ""), "-"))

        tail_names = {"conventional": "Konvansiyonel", "t_tail": "T-Kuyruk", "v_tail": "V-Kuyruk"}
        self.sum_tail.setText(tail_names.get(self.state.get("tail_type", ""), "-"))

        prop_names = {"tractor": "Çekici (Burun)", "pusher": "İtici (Pilon)", "twin": "Çift Motor"}
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
        self.step_counter_lbl.setText(f"ADIM {step_idx + 1} / {total_steps}")
        step_meta = [
            ("Görev ve Performans Gereksinimleri", "İHA'nın taşıyacağı faydalı yük ve hedef uçuş performans hedefleri."),
            ("Genel Konfigürasyon Tipi (Architecture)", "Uçağın temel gövde mimarisi ve aerodinamik düzeni."),
            ("Kanat Konumu ve Düşey Yerleşimi", "Gövde-kanat birleşim yüksekliği ve girişim direnci özellikleri."),
            ("Kanat Planform Şekli", "Kanadın üstten görünüşü, veter dağılımı ve indüklenmiş direnç formu."),
            ("Kuyruk Tipi (Tail Configuration)", "Kuyruk kontrol yüzeyleri yerleşimi ve hava akışı verimi."),
            ("İtki ve Motor Yerleşimi", "Pervane konumu, motor sayısı ve aerodinamik etkileşim."),
            ("Batarya Teknolojisi", "Kimyasal hücre tipi, özgül enerji yoğunluğu ve ağırlık payı."),
        ]
        if step_idx < len(step_meta):
            self.step_title_lbl.setText(step_meta[step_idx][0])
            self.step_desc_lbl.setText(step_meta[step_idx][1])

        # Update navigation buttons
        self.btn_back.setEnabled(step_idx > 0)
        if step_idx == total_steps - 1:
            self.btn_next.setText("✨ Boyutlandırmayı Başlat")
        else:
            self.btn_next.setText("İleri ▶")

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
