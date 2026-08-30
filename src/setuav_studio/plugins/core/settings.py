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
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.buttons import set_button_role
from setuav_studio_sdk import SettingsPageContribution

logger = logging.getLogger(__name__)


VALIDATION_STRICTNESS_LEVELS: tuple[str, ...] = ("strict", "warn", "off")


THEME_MODES: tuple[str, ...] = (
    "dark",
    "light",
    "blender",
    "github_dark",
    "github_light",
    "monokai",
    "nord",
)


@dataclass(frozen=True)
class StudioSettings:
    reopen_last_project: bool = False
    recent_project_limit: int = 10
    pythrust_data_dir: str = ""
    validation_strictness: str = "strict"
    theme_mode: str = "blender"

    @classmethod
    def load(cls) -> "StudioSettings":
        from PySide6.QtCore import QSettings

        settings = QSettings()
        strictness = str(settings.value("general/validation_strictness", "strict"))
        if strictness not in VALIDATION_STRICTNESS_LEVELS:
            strictness = "strict"
        theme = str(settings.value("appearance/theme_mode", "blender")).lower()
        if theme not in THEME_MODES:
            theme = "blender"
        return cls(
            reopen_last_project=_as_bool(settings.value("general/reopen_last_project", False)),
            recent_project_limit=int(settings.value("general/recent_project_limit", 10)),
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


class SettingsDialog(QDialog):
    """Categorized application settings dialog with plugin-extensible pages."""

    def __init__(
        self,
        values: StudioSettings,
        parent: QWidget | None = None,
        pages: Iterable[SettingsPageContribution] = (),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(720, 720)

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
        self.category_tree.setIndentation(18)
        self.category_tree.setFixedWidth(220)
        self.category_tree.setIconSize(QSize(0, 0))
        self.category_tree.setAnimated(False)
        self.category_tree.setStyleSheet(
            "QTreeWidget#settingsCategories { font-size: 13px; }"
            "QTreeWidget#settingsCategories::item { min-height: 30px; padding: 5px 8px; }"
        )
        self.category_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content.addWidget(self.category_tree)
        # Compatibility alias for callers that only need to inspect the
        # navigation widget.
        self.category_list = self.category_tree

        self.page_stack = QStackedWidget(self)
        self.page_stack.setObjectName("settingsPages")
        content.addWidget(self.page_stack, 1)
        self.category_tree.currentItemChanged.connect(self._on_category_changed)

        self._build_general_page(values)
        self._build_appearance_page(values)
        self._build_units_page()
        self._build_propulsion_page(values)
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
                group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                font = group_item.font(0)
                font.setBold(True)
                group_item.setFont(0, font)
                self.category_tree.addTopLevelItem(group_item)
                self._group_items[group_name] = group_item
            item = QTreeWidgetItem(group_item, [title])
        else:
            item = QTreeWidgetItem(self.category_tree, [title])
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

    @staticmethod
    def _page_container(title: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 8, 4)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("settingsPageTitle")
        layout.addWidget(heading)
        return page, layout

    def _build_general_page(self, values: StudioSettings) -> None:
        page, layout = self._page_container("General")
        form = QFormLayout()

        self.reopen_check = QCheckBox("Reopen the last project at startup")
        self.reopen_check.setChecked(values.reopen_last_project)
        form.addRow(self.reopen_check)

        self.recent_limit_spin = QSpinBox()
        self.recent_limit_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.recent_limit_spin.setRange(1, 20)
        self.recent_limit_spin.setValue(values.recent_project_limit)
        form.addRow("Recent projects:", self.recent_limit_spin)

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
        if idx >= 0:
            self.validation_strictness_combo.setCurrentIndex(idx)
        form.addRow("Schema validation:", self.validation_strictness_combo)

        layout.addLayout(form)
        layout.addStretch(1)
        self._add_page("general", "General", page, "fa6s.gear")

    def _build_appearance_page(self, values: StudioSettings) -> None:
        page, layout = self._page_container("Appearance")
        form = QFormLayout()

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Native Dark", "dark")
        self.theme_combo.addItem("Native Light", "light")
        self.theme_combo.addItem("Blender Theme", "blender")
        self.theme_combo.addItem("GitHub Dark", "github_dark")
        self.theme_combo.addItem("GitHub Light", "github_light")
        self.theme_combo.addItem("Monokai", "monokai")
        self.theme_combo.addItem("Nord", "nord")
        idx = self.theme_combo.findData(values.theme_mode)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        form.addRow("Application theme:", self.theme_combo)

        layout.addLayout(form)
        layout.addStretch(1)
        self._add_page("appearance", "Appearance", page, "fa6s.palette")

    def _build_units_page(self) -> None:
        from setuav_studio.units import QUANTITIES, get_unit_manager

        um = get_unit_manager()
        page, layout = self._page_container("Units & Dimensions")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._units_updating = True
        self._unit_combos: dict[str, QComboBox] = {}

        # 1. Preset Selector
        self.units_preset_combo = QComboBox()
        self.units_preset_combo.addItem("Metric (SI Standard)", "si")
        self.units_preset_combo.addItem("Aviation Standard", "aviation")
        self.units_preset_combo.addItem("Imperial (US Customary)", "imperial")
        self.units_preset_combo.addItem("Custom", "custom")

        preset_idx = self.units_preset_combo.findData(um.get_active_preset())
        self.units_preset_combo.setCurrentIndex(preset_idx if preset_idx >= 0 else 0)
        self.units_preset_combo.currentIndexChanged.connect(self._on_units_preset_changed)
        form.addRow("Preset System:", self.units_preset_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(sep)

        # 2. Individual Quantities
        for q_id, q_def in QUANTITIES.items():
            combo = QComboBox()
            for u_id, u_def in q_def.units.items():
                combo.addItem(f"{u_def.name}", u_id)
            cur_unit = um.get_display_unit(q_id)
            idx = combo.findData(cur_unit)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(lambda _idx, q=q_id: self._on_single_unit_changed(q))
            self._unit_combos[q_id] = combo
            form.addRow(f"{q_def.name}:", combo)

        self._units_updating = False
        layout.addLayout(form)
        layout.addStretch(1)
        self._add_page("units", "Units", page, "fa6s.ruler-combined")

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
            if all(current_map.get(k) == v for k, v in p_map.items()):
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

    def _build_propulsion_page(self, values: StudioSettings) -> None:
        page, layout = self._page_container("Propulsion")
        form = QFormLayout()

        self.pythrust_dir_edit = QLineEdit(values.pythrust_data_dir)
        self.pythrust_dir_edit.setPlaceholderText(
            "Bundled with the pythrust package; or set PYTHRUST_DATA_DIR"
        )
        form.addRow("PyThrust data directory:", self.pythrust_dir_edit)

        layout.addLayout(form)
        layout.addStretch(1)
        self._add_page("propulsion", "Propulsion", page, "fa6s.bolt")

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
            pythrust_data_dir=self.pythrust_dir_edit.text().strip(),
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
