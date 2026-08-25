"""Component Catalog Picker and Database Browser Dialog.

High-performance virtualized catalog browser using QAbstractTableModel
with debounced search and pre-indexed search tokens.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from pythrust.motors.database import MotorEntry
from pythrust.propellers.database import PropellerEntry

from setuav_studio.plugins.electrical_propulsion.database import (
    get_motor_database,
    get_propeller_database,
)
from setuav_studio.ui.buttons import set_button_role
from setuav_studio.ui.icons import get_icon

_INVALID_MODEL_INDEX = QModelIndex()


class MotorCatalogModel(QAbstractTableModel):
    """Virtualized table model for motor database entries."""

    HEADERS = [
        "Manufacturer",
        "Model / Name",
        "KV (RPM/V)",
        "Max Current (A)",
        "Max Power (W)",
        "Mass (g)",
        "Rm (Ω)",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[MotorEntry] = []
        self._sort_col: int = -1
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _INVALID_MODEL_INDEX) -> int:
        return len(self._entries)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = _INVALID_MODEL_INDEX
    ) -> int:
        return len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None

        m = self._entries[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return m.manufacturer or ""
            if col == 1:
                return m.name or ""
            if col == 2:
                return f"{m.kv:.0f}" if m.kv is not None else "-"
            if col == 3:
                return f"{m.max_current:.1f}" if m.max_current is not None else "-"
            if col == 4:
                return f"{m.max_power:.0f}" if m.max_power is not None else "-"
            if col == 5:
                return f"{m.weight_g:.1f}" if m.weight_g is not None else "-"
            if col == 6:
                return f"{m.resistance:.4f}" if m.resistance is not None else "-"

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1):
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.UserRole:
            if col == 0:
                return m.id
            if col == 1:
                return m.name or ""
            if col == 2:
                return m.kv or 0.0
            if col == 3:
                return m.max_current or 0.0
            if col == 4:
                return m.max_power or 0.0
            if col == 5:
                return m.weight_g or 0.0
            if col == 6:
                return m.resistance or 0.0

        return None

    def get_entry(self, row: int) -> MotorEntry | None:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def set_entries(self, entries: list[MotorEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        if self._sort_col >= 0:
            self._apply_sort()
        self.endResetModel()

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        self._sort_col = column
        self._sort_order = order
        self.beginResetModel()
        self._apply_sort()
        self.endResetModel()

    def _apply_sort(self) -> None:
        col = self._sort_col
        rev = self._sort_order == Qt.SortOrder.DescendingOrder

        def key_func(m: MotorEntry) -> Any:
            if col == 0:
                return (m.manufacturer or "").lower()
            if col == 1:
                return (m.name or "").lower()
            if col == 2:
                return m.kv or 0.0
            if col == 3:
                return m.max_current or 0.0
            if col == 4:
                return m.max_power or 0.0
            if col == 5:
                return m.weight_g or 0.0
            if col == 6:
                return m.resistance or 0.0
            return 0

        self._entries.sort(key=key_func, reverse=rev)


class PropellerCatalogModel(QAbstractTableModel):
    """Virtualized table model for propeller database entries."""

    HEADERS = [
        "Manufacturer",
        "Model",
        "Diameter (in)",
        "Diameter (mm)",
        "Pitch (in)",
        "Blades",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[PropellerEntry] = []
        self._sort_col: int = -1
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _INVALID_MODEL_INDEX) -> int:
        return len(self._entries)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = _INVALID_MODEL_INDEX
    ) -> int:
        return len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None

        p = self._entries[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return p.metadata.manufacturer or ""
            if col == 1:
                return p.metadata.model or ""
            if col == 2:
                return f"{p.metadata.diameter_in:.1f}"
            if col == 3:
                return f"{p.diameter_m * 1000.0:.1f}"
            if col == 4:
                return f"{p.metadata.pitch_in:.1f}"
            if col == 5:
                return str(p.metadata.blade_count)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1):
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.UserRole:
            if col == 0:
                return p.metadata.manufacturer or ""
            if col == 1:
                return p.metadata.model or ""
            if col == 2:
                return p.metadata.diameter_in or 0.0
            if col == 3:
                return p.diameter_m or 0.0
            if col == 4:
                return p.metadata.pitch_in or 0.0
            if col == 5:
                return p.metadata.blade_count or 0

        return None

    def get_entry(self, row: int) -> PropellerEntry | None:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def set_entries(self, entries: list[PropellerEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        if self._sort_col >= 0:
            self._apply_sort()
        self.endResetModel()

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        self._sort_col = column
        self._sort_order = order
        self.beginResetModel()
        self._apply_sort()
        self.endResetModel()

    def _apply_sort(self) -> None:
        col = self._sort_col
        rev = self._sort_order == Qt.SortOrder.DescendingOrder

        def key_func(p: PropellerEntry) -> Any:
            if col == 0:
                return (p.metadata.manufacturer or "").lower()
            if col == 1:
                return (p.metadata.model or "").lower()
            if col == 2:
                return p.metadata.diameter_in or 0.0
            if col == 3:
                return p.diameter_m or 0.0
            if col == 4:
                return p.metadata.pitch_in or 0.0
            if col == 5:
                return p.metadata.blade_count or 0
            return 0

        self._entries.sort(key=key_func, reverse=rev)


class ComponentCatalogDialog(QDialog):
    """High-performance catalog dialog for selecting motors or propellers."""

    def __init__(
        self,
        component_type: str = "motor",  # "motor", "propeller", or "all"
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.component_type = component_type
        self.selected_motor: MotorEntry | None = None
        self.selected_propeller: PropellerEntry | None = None

        # Pre-indexed entries: list of (entry, mfg_lower, search_token_lower)
        self._indexed_motors: list[tuple[MotorEntry, str, str]] = []
        self._indexed_props: list[tuple[PropellerEntry, str, str]] = []

        title = "Component Database Catalog"
        if component_type == "motor":
            title = "Select Motor from Catalog"
        elif component_type in {"propeller", "rotor"}:
            title = "Select Propeller from Catalog"

        self.setWindowTitle(title)
        self.resize(920, 600)
        self.setFont(QApplication.font())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Search debounce timers
        self._motor_debounce = QTimer(self)
        self._motor_debounce.setSingleShot(True)
        self._motor_debounce.setInterval(100)
        self._motor_debounce.timeout.connect(self._do_filter_motors)

        self._prop_debounce = QTimer(self)
        self._prop_debounce.setSingleShot(True)
        self._prop_debounce.setInterval(100)
        self._prop_debounce.timeout.connect(self._do_filter_propellers)

        if component_type == "all":
            self.tabs = QTabWidget(self)
            self.motor_widget = self._create_motor_page()
            self.prop_widget = self._create_propeller_page()
            self.tabs.addTab(self.motor_widget, get_icon("fa6s.rotate"), "Motors")
            self.tabs.addTab(self.prop_widget, get_icon("fa6s.fan"), "Propellers")
            main_layout.addWidget(self.tabs)
        elif component_type == "motor":
            self.motor_widget = self._create_motor_page()
            main_layout.addWidget(self.motor_widget)
        else:
            self.prop_widget = self._create_propeller_page()
            main_layout.addWidget(self.prop_widget)

        # Bottom status and action buttons
        btn_layout = QHBoxLayout()
        self.status_label = QLabel(self)
        btn_layout.addWidget(self.status_label)
        btn_layout.addStretch()

        self.apply_btn = QPushButton("Apply to Component", self)
        set_button_role(self.apply_btn, "primary", "fa6s.check")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.apply_btn)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        main_layout.addLayout(btn_layout)

        # Initial load
        if component_type in {"motor", "all"}:
            self._load_motors()
        if component_type in {"propeller", "rotor", "all"}:
            self._load_propellers()

    def _create_motor_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self.motor_search = QLineEdit(page)
        self.motor_search.setPlaceholderText("Search motor name, model or manufacturer…")
        self.motor_search.setClearButtonEnabled(True)
        self.motor_search.textChanged.connect(self._on_motor_search_changed)
        filter_bar.addWidget(self.motor_search, 3)

        self.motor_mfg_combo = QComboBox(page)
        self.motor_mfg_combo.addItem("All Manufacturers", "")
        self.motor_mfg_combo.currentIndexChanged.connect(self._do_filter_motors)
        filter_bar.addWidget(self.motor_mfg_combo, 2)

        layout.addLayout(filter_bar)

        # Virtualized Table
        self.motor_model = MotorCatalogModel(self)
        self.motor_view = QTableView(page)
        self.motor_view.setModel(self.motor_model)
        self._style_table_view(self.motor_view)

        # Column sizing
        h = self.motor_view.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.motor_view.setColumnWidth(0, 140)
        self.motor_view.setColumnWidth(2, 95)
        self.motor_view.setColumnWidth(3, 115)
        self.motor_view.setColumnWidth(4, 110)
        self.motor_view.setColumnWidth(5, 80)
        self.motor_view.setColumnWidth(6, 85)

        self.motor_view.selectionModel().selectionChanged.connect(self._on_motor_selection_changed)
        self.motor_view.doubleClicked.connect(self._on_motor_double_clicked)
        self.motor_table = self.motor_view
        self.motor_table.rowCount = lambda: self.motor_model.rowCount()
        layout.addWidget(self.motor_view)

        return page

    def _create_propeller_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self.prop_search = QLineEdit(page)
        self.prop_search.setPlaceholderText("Search propeller model…")
        self.prop_search.setClearButtonEnabled(True)
        self.prop_search.textChanged.connect(self._on_prop_search_changed)
        filter_bar.addWidget(self.prop_search, 3)

        layout.addLayout(filter_bar)

        # Virtualized Table
        self.prop_model = PropellerCatalogModel(self)
        self.prop_view = QTableView(page)
        self.prop_view.setModel(self.prop_model)
        self._style_table_view(self.prop_view)

        h = self.prop_view.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.prop_view.setColumnWidth(0, 150)
        self.prop_view.setColumnWidth(2, 100)
        self.prop_view.setColumnWidth(3, 105)
        self.prop_view.setColumnWidth(4, 90)
        self.prop_view.setColumnWidth(5, 75)

        self.prop_view.selectionModel().selectionChanged.connect(self._on_prop_selection_changed)
        self.prop_view.doubleClicked.connect(self._on_prop_double_clicked)
        self.prop_table = self.prop_view
        self.prop_table.rowCount = lambda: self.prop_model.rowCount()
        layout.addWidget(self.prop_view)

        return page

    def _style_table_view(self, view: QTableView) -> None:
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.verticalHeader().setVisible(False)
        view.verticalHeader().setDefaultSectionSize(24)
        view.horizontalHeader().setFixedHeight(26)
        view.horizontalHeader().setStretchLastSection(True)
        view.setAlternatingRowColors(True)
        view.setSortingEnabled(True)
        view.setShowGrid(True)

    def _load_motors(self) -> None:
        db = get_motor_database()
        all_motors = [db.get(mid) for mid in db.list_motors()]
        valid_motors = [m for m in all_motors if m is not None]

        # Build index: (m, mfg_lower, token_lower)
        self._indexed_motors = [
            (
                m,
                (m.manufacturer or "").lower(),
                f"{m.manufacturer or ''} {m.name or ''} {m.id or ''}".lower(),
            )
            for m in valid_motors
        ]

        # Populate manufacturers dropdown
        manufacturers = sorted(list({m.manufacturer for m in valid_motors if m.manufacturer}))
        self.motor_mfg_combo.blockSignals(True)
        self.motor_mfg_combo.clear()
        self.motor_mfg_combo.addItem("All Manufacturers", "")
        for mfg in manufacturers:
            self.motor_mfg_combo.addItem(mfg, mfg)
        self.motor_mfg_combo.blockSignals(False)

        # Initial population
        initial_list = [t[0] for t in self._indexed_motors[:500]]
        self.motor_model.set_entries(initial_list)
        self.status_label.setText(f"Loaded {len(valid_motors):,} motors from PyThrust catalog")

    def _on_motor_search_changed(self) -> None:
        self._do_filter_motors()

    def _do_filter_motors(self) -> None:
        query = self.motor_search.text().strip().lower()
        selected_mfg = str(self.motor_mfg_combo.currentData() or "").lower()

        filtered: list[MotorEntry] = []
        tokens = query.split() if query else []

        for m, mfg_l, token_l in self._indexed_motors:
            if selected_mfg and mfg_l != selected_mfg:
                continue
            if tokens and not all(t in token_l for t in tokens):
                continue
            filtered.append(m)
            if len(filtered) >= 500:
                break

        self.motor_model.set_entries(filtered)
        if filtered:
            self.motor_view.selectRow(0)
        else:
            self.selected_motor = None
            self.apply_btn.setEnabled(False)

        total = len(self._indexed_motors)
        if len(filtered) >= 500:
            self.status_label.setText(f"Showing top 500 matches (out of {total:,} motors)")
        else:
            self.status_label.setText(f"Showing {len(filtered)} matching motors (out of {total:,})")

    def _on_motor_selection_changed(self) -> None:
        indexes = self.motor_view.selectionModel().selectedRows()
        if not indexes:
            self.selected_motor = None
            self.apply_btn.setEnabled(False)
            return
        row = indexes[0].row()
        self.selected_motor = self.motor_model.get_entry(row)
        self.apply_btn.setEnabled(self.selected_motor is not None)

    def _on_motor_double_clicked(self, index: QModelIndex) -> None:
        if index.isValid():
            self.selected_motor = self.motor_model.get_entry(index.row())
            if self.selected_motor:
                self.accept()

    def _load_propellers(self) -> None:
        db = get_propeller_database()
        all_props = [db.get(pid) for pid in db.list_propellers()]
        valid_props = [p for p in all_props if p is not None]

        self._indexed_props = [
            (
                p,
                (p.metadata.manufacturer or "").lower(),
                f"{p.metadata.manufacturer or ''} {p.metadata.model or ''} {p.metadata.id or ''}".lower(),
            )
            for p in valid_props
        ]

        self.prop_model.set_entries([t[0] for t in self._indexed_props])
        if self.component_type in {"propeller", "rotor"}:
            self.status_label.setText(
                f"Loaded {len(valid_props):,} propellers from PyThrust catalog"
            )

    def _on_prop_search_changed(self) -> None:
        self._do_filter_propellers()

    def _do_filter_propellers(self) -> None:
        query = self.prop_search.text().strip().lower()
        tokens = query.split() if query else []

        filtered: list[PropellerEntry] = []
        for p, _mfg_l, token_l in self._indexed_props:
            if tokens and not all(t in token_l for t in tokens):
                continue
            filtered.append(p)

        self.prop_model.set_entries(filtered)
        if filtered:
            self.prop_view.selectRow(0)
        else:
            self.selected_propeller = None
            self.apply_btn.setEnabled(False)

        self.status_label.setText(f"Showing {len(filtered)} matching propellers")

    def _on_prop_selection_changed(self) -> None:
        indexes = self.prop_view.selectionModel().selectedRows()
        if not indexes:
            self.selected_propeller = None
            self.apply_btn.setEnabled(False)
            return
        row = indexes[0].row()
        self.selected_propeller = self.prop_model.get_entry(row)
        self.apply_btn.setEnabled(self.selected_propeller is not None)

    def _on_prop_double_clicked(self, index: QModelIndex) -> None:
        if index.isValid():
            self.selected_propeller = self.prop_model.get_entry(index.row())
            if self.selected_propeller:
                self.accept()
