import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import SettingsPageContribution
from setuav_studio.ui.style.icons import get_icon, set_label_icon
from setuav_studio.ui.widget.button import set_button_role
from setuav_studio.ui.widget.table import PropertyTableMixin

logger = logging.getLogger(__name__)


VALIDATION_STRICTNESS_LEVELS: tuple[str, ...] = ("strict", "warn", "off")


THEME_MODES: tuple[str, ...] = (
    "native",
    "blender",
    "github",
    "monokai",
    "nord",
)


@dataclass(frozen=True)
class StudioSettings:
    reopen_last_project: bool = False
    recent_project_limit: int = 10
    pythrust_data_dir: str = ""
    validation_strictness: str = "strict"
    theme_mode: str = "native"

    @classmethod
    def load(cls) -> "StudioSettings":
        from PySide6.QtCore import QSettings

        settings = QSettings()
        strictness = str(settings.value("general/validation_strictness", "strict"))
        if strictness not in VALIDATION_STRICTNESS_LEVELS:
            strictness = "strict"
        theme = str(settings.value("appearance/theme_mode", "native")).lower()
        if theme not in THEME_MODES:
            theme = "native"
        return cls(
            reopen_last_project=_as_bool(settings.value("general/reopen_last_project", False)),
            recent_project_limit=int(str(settings.value("general/recent_project_limit", 10))),
            pythrust_data_dir=str(settings.value("propulsion/pythrust_data_dir", "")),
            validation_strictness=strictness,
            theme_mode=theme,
        )

    def save(self) -> None:
        from PySide6.QtCore import QSettings

        settings = QSettings()
        settings.setValue("general/reopen_last_project", self.reopen_last_project)
        settings.setValue("general/recent_project_limit", self.recent_project_limit)
        settings.setValue("propulsion/pythrust_data_dir", self.pythrust_data_dir)
        settings.setValue("general/validation_strictness", self.validation_strictness)
        settings.setValue("appearance/theme_mode", self.theme_mode)


class SettingsDialog(PropertyTableMixin, QDialog):
    """Categorized application settings dialog with compact property tables and plugin pages."""

    def __init__(
        self,
        values: StudioSettings,
        parent: QWidget | None = None,
        pages: Iterable[SettingsPageContribution] = (),
    ) -> None:
        super().__init__(parent)
        self._values = values
        self.setWindowTitle("Settings")
        self.resize(760, 620)
        self.setMinimumSize(680, 520)

        self._plugin_pages: list[tuple[SettingsPageContribution, QWidget]] = []
        self._group_items: dict[str, QTreeWidgetItem] = {}
        self._first_page_item: QTreeWidgetItem | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        content = QHBoxLayout()
        content.setSpacing(10)
        outer.addLayout(content, 1)

        self.category_tree = QTreeWidget(self)
        self.category_tree.setObjectName("settingsCategories")
        self.category_tree.setHeaderHidden(True)
        self.category_tree.setRootIsDecorated(True)
        self.category_tree.setIndentation(16)
        self.category_tree.setFixedWidth(210)
        self.category_tree.setIconSize(QSize(16, 16))
        self.category_tree.setAnimated(False)
        self.category_tree.setStyleSheet(
            "QTreeWidget#settingsCategories { font-size: 13px; }"
            "QTreeWidget#settingsCategories::item { min-height: 26px; padding: 2px 4px; }"
        )
        self.category_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content.addWidget(self.category_tree)

        self.page_stack = QStackedWidget(self)
        self.page_stack.setObjectName("settingsPages")
        content.addWidget(self.page_stack, 1)
        self.category_tree.currentItemChanged.connect(self._on_category_changed)

        self._build_general_page(values)
        self._build_appearance_page(values)
        self._build_units_page()
        for contribution in sorted(
            pages,
            key=lambda page: (page.order, page.title.casefold(), page.id),
        ):
            self._add_plugin_page(contribution)

        self.category_tree.expandAll()
        if self._first_page_item is not None:
            self.category_tree.setCurrentItem(self._first_page_item)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            set_button_role(ok_button, "primary")
        outer.addWidget(buttons)

    def _create_section(
        self,
        title: str,
        icon_name: str | None = None,
        parent_layout: QVBoxLayout | None = None,
    ) -> tuple[QWidget, QVBoxLayout]:
        section = QWidget()
        section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        if icon_name:
            icon_label = QLabel()
            set_label_icon(icon_label, icon_name, 14)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header)
        if parent_layout is not None:
            parent_layout.addWidget(section)
        return section, layout

    def _create_settings_table(
        self,
        definitions: list[tuple[str, str]],
        col0_width: int = 180,
    ) -> QTableWidget:
        table = self._property_table(definitions)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, col0_width)
        return table

    def _add_page(
        self,
        page_id: str,
        title: str,
        page: QWidget,
        icon: str | Path | QIcon | None = None,
        group: str | None = None,
        group_icon: str | Path | QIcon | None = None,
    ) -> None:
        scroll = QScrollArea(self.page_stack)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        page_index = self.page_stack.addWidget(scroll)

        group_name = group.strip() if isinstance(group, str) else ""
        if group_name:
            group_item = self._group_items.get(group_name)
            if group_item is None:
                group_item = QTreeWidgetItem([group_name])
                group_item.setFirstColumnSpanned(True)
                group_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                font = group_item.font(0)
                font.setBold(True)
                group_item.setFont(0, font)
                if group_icon:
                    group_item.setIcon(
                        0,
                        get_icon(group_icon)
                        if isinstance(group_icon, str)
                        else QIcon(str(group_icon)),
                    )
                elif group_name == "Application":
                    group_item.setIcon(0, get_icon("fa6s.gears"))
                else:
                    group_item.setIcon(0, get_icon("fa6s.cubes"))
                self.category_tree.addTopLevelItem(group_item)
                self._group_items[group_name] = group_item
            item = QTreeWidgetItem(group_item, [title])
        else:
            item = QTreeWidgetItem(self.category_tree, [title])

        if icon:
            item.setIcon(0, get_icon(icon) if isinstance(icon, str) else QIcon(str(icon)))
        item.setData(0, Qt.ItemDataRole.UserRole, page_id)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, page_index)
        if self._first_page_item is None:
            self._first_page_item = item

    def _on_category_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            return
        index = current.data(0, Qt.ItemDataRole.UserRole + 1)
        if isinstance(index, int) and index >= 0:
            self.page_stack.setCurrentIndex(index)
        elif current.childCount() > 0:
            first_child = current.child(0)
            if first_child is not None:
                self.category_tree.setCurrentItem(first_child)

    @staticmethod
    def _page_container(title: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 8, 12, 8)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("settingsPageTitle")
        font = heading.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        return page, layout

    def _build_general_page(self, values: StudioSettings) -> None:
        page, layout = self._page_container("General Settings")

        # 1. Startup
        _, s1_layout = self._create_section("Startup", "fa6s.clock-rotate-left", layout)
        t1 = self._create_settings_table(
            [
                ("reopen_last_project", "Reopen Last Project"),
                ("recent_project_limit", "Recent Projects Limit"),
            ]
        )
        check_widget = QWidget()
        check_layout = QHBoxLayout(check_widget)
        check_layout.setContentsMargins(6, 0, 0, 0)
        check_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.reopen_check = QCheckBox("Reopen the last project at startup")
        self.reopen_check.setChecked(values.reopen_last_project)
        check_layout.addWidget(self.reopen_check)
        t1.setCellWidget(0, 1, check_widget)

        self.recent_limit_spin = QSpinBox()
        self.recent_limit_spin.setRange(1, 20)
        self.recent_limit_spin.setValue(values.recent_project_limit)
        self.recent_limit_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        t1.setCellWidget(1, 1, self.recent_limit_spin)

        self._fit_table_height(t1, 2)
        s1_layout.addWidget(t1)

        # 2. Validation & Diagnostics
        _, s2_layout = self._create_section(
            "Validation & Diagnostics", "fa6s.shield-halved", layout
        )
        t2 = self._create_settings_table([("validation_strictness", "Schema Validation")])
        self.validation_strictness_combo = QComboBox()
        self.validation_strictness_combo.addItem(
            "Strict: block on validation errors (read-only or cancel)",
            "strict",
        )
        self.validation_strictness_combo.addItem(
            "Warn: open read-only and show a status-bar warning",
            "warn",
        )
        self.validation_strictness_combo.addItem(
            "Off: skip runtime validation",
            "off",
        )
        idx = self.validation_strictness_combo.findData(values.validation_strictness)
        self.validation_strictness_combo.setCurrentIndex(idx if idx >= 0 else 0)
        t2.setCellWidget(0, 1, self.validation_strictness_combo)
        self._fit_table_height(t2, 1)
        s2_layout.addWidget(t2)

        layout.addStretch(1)
        self._add_page("general", "General", page, "fa6s.gear", group="Application")

    def _build_appearance_page(self, values: StudioSettings) -> None:
        page, layout = self._page_container("Appearance Settings")

        _, s1_layout = self._create_section("Theme & Styling", "fa6s.palette", layout)
        t1 = self._create_settings_table([("theme_mode", "Application Theme")])
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Native", "native")
        self.theme_combo.addItem("Blender", "blender")
        self.theme_combo.addItem("GitHub", "github")
        self.theme_combo.addItem("Monokai", "monokai")
        self.theme_combo.addItem("Nord", "nord")
        idx = self.theme_combo.findData(values.theme_mode)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        t1.setCellWidget(0, 1, self.theme_combo)
        self._fit_table_height(t1, 1)
        s1_layout.addWidget(t1)

        layout.addStretch(1)
        self._add_page("appearance", "Appearance", page, "fa6s.palette", group="Application")

    def _build_units_page(self) -> None:
        from setuav_studio.units import QUANTITIES, get_unit_manager

        um = get_unit_manager()
        page, layout = self._page_container("Units & Dimensions")

        self._units_updating = True
        self._unit_combos: dict[str, QComboBox] = {}

        # 1. Preset System
        _, s1_layout = self._create_section("Unit Preset", "fa6s.sliders", layout)
        t1 = self._create_settings_table([("preset", "System Preset")])
        self.units_preset_combo = QComboBox()
        self.units_preset_combo.addItem("Metric (SI Standard)", "si")
        self.units_preset_combo.addItem("Aviation Standard", "aviation")
        self.units_preset_combo.addItem("Imperial (US Customary)", "imperial")
        self.units_preset_combo.addItem("Custom", "custom")

        preset_idx = self.units_preset_combo.findData(um.get_active_preset())
        self.units_preset_combo.setCurrentIndex(preset_idx if preset_idx >= 0 else 0)
        self.units_preset_combo.currentIndexChanged.connect(self._on_units_preset_changed)
        t1.setCellWidget(0, 1, self.units_preset_combo)
        self._fit_table_height(t1, 1)
        s1_layout.addWidget(t1)

        # 2. Physical Quantities
        _, s2_layout = self._create_section("Physical Quantities", "fa6s.ruler-combined", layout)
        quantity_defs = [(q_id, q_def.name) for q_id, q_def in QUANTITIES.items()]
        t2 = self._create_settings_table(quantity_defs, col0_width=180)

        for row, (q_id, q_def) in enumerate(QUANTITIES.items()):
            combo = QComboBox()
            for u_id, u_def in q_def.units.items():
                combo.addItem(f"{u_def.name} ({u_def.symbol})", u_id)
            cur_unit = um.get_display_unit(q_id)
            idx = combo.findData(cur_unit)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(lambda _idx, q=q_id: self._on_single_unit_changed(q))
            self._unit_combos[q_id] = combo
            t2.setCellWidget(row, 1, combo)

        self._fit_table_height(t2, len(QUANTITIES), maximum_visible_rows=None)
        s2_layout.addWidget(t2)

        self._units_updating = False
        layout.addStretch(1)
        self._add_page("units", "Units", page, "fa6s.ruler-combined", group="Application")

    def _on_units_preset_changed(self) -> None:
        if getattr(self, "_units_updating", False):
            return
        from setuav_studio.units import PRESETS

        preset_id = str(self.units_preset_combo.currentData())
        if preset_id not in PRESETS:
            return
        preset_map = PRESETS[preset_id]
        self._units_updating = True
        try:
            for q_id, combo in self._unit_combos.items():
                target_unit = preset_map.get(q_id)
                if target_unit:
                    idx = combo.findData(target_unit)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
        finally:
            self._units_updating = False

    def _on_single_unit_changed(self, quantity_id: str) -> None:
        if getattr(self, "_units_updating", False):
            return
        from setuav_studio.units import PRESETS

        current_map = {q_id: str(c.currentData()) for q_id, c in self._unit_combos.items()}
        matched_preset = "custom"
        for p_id, p_map in PRESETS.items():
            if all(current_map.get(k) == v for k, v in p_map.items() if k != "name"):
                matched_preset = p_id
                break

        self._units_updating = True
        try:
            idx = self.units_preset_combo.findData(matched_preset)
            if idx >= 0:
                self.units_preset_combo.setCurrentIndex(idx)
        finally:
            self._units_updating = False

    def apply_units(self) -> None:
        from setuav_studio.units import get_unit_manager

        if not hasattr(self, "_unit_combos"):
            return
        um = get_unit_manager()
        preset_id = str(self.units_preset_combo.currentData())
        um.set_active_preset(preset_id)
        for q_id, combo in self._unit_combos.items():
            um.set_display_unit(q_id, str(combo.currentData()))
        um.save_to_settings()

    def _add_plugin_page(self, contribution: SettingsPageContribution) -> None:
        try:
            page = contribution.factory()
            if not isinstance(page, QWidget):
                raise TypeError("settings page factory must return a QWidget")
        except Exception as exc:
            logger.exception("Could not create settings page %s", contribution.id)
            page = QLabel(f"Could not load this settings page.\n{exc}")
            page.setWordWrap(True)

        self._plugin_pages.append((contribution, page))
        self._add_page(
            contribution.id,
            contribution.title,
            page,
            contribution.icon,
            contribution.group,
            contribution.group_icon,
        )

    def values(self) -> StudioSettings:
        return StudioSettings(
            reopen_last_project=self.reopen_check.isChecked(),
            recent_project_limit=self.recent_limit_spin.value(),
            pythrust_data_dir=getattr(self._values, "pythrust_data_dir", "").strip(),
            validation_strictness=str(self.validation_strictness_combo.currentData()),
            theme_mode=str(self.theme_combo.currentData()),
        )

    def apply_plugin_pages(self) -> None:
        """Persist plugin pages after the dialog has been accepted."""
        for contribution, page in self._plugin_pages:
            if contribution.apply is None:
                continue
            try:
                contribution.apply(page)
            except Exception:
                logger.exception("Could not apply settings page %s", contribution.id)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes"}
