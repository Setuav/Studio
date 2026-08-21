"""Component Catalog Picker and Database Browser Dialog."""

from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.plugins.electrical_propulsion.database import (
    get_motor_database,
    get_propeller_database,
)
from pythrust.motors.database import MotorEntry
from pythrust.propellers.database import PropellerEntry


class _NumericItem(QTableWidgetItem):
    """Table item that keeps the raw numeric value in UserRole for sorting."""

    def __init__(self, text: str, value: float | None = None) -> None:
        super().__init__(text)
        self.setData(Qt.ItemDataRole.UserRole, value)


class ComponentCatalogDialog(QDialog):
    """Search and select motors or propellers from the PyThrust database."""

    def __init__(
        self,
        component_type: str = "motor",  # "motor", "propeller", or "all"
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.component_type = component_type
        self.selected_motor: MotorEntry | None = None
        self.selected_propeller: PropellerEntry | None = None

        self._motor_entries: list[MotorEntry] = []
        self._prop_entries: list[PropellerEntry] = []

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

        # Buttons
        btn_layout = QHBoxLayout()
        self.status_label = QLabel(self)
        self.status_label.setStyleSheet("color: #8b949e; font-size: 8.5pt;")
        btn_layout.addWidget(self.status_label)
        btn_layout.addStretch()

        self.apply_btn = QPushButton("Apply to Component", self)
        self.apply_btn.setProperty("accent", True)
        self.apply_btn.setIcon(get_icon("fa6s.check"))
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

        self._sort_orders: dict[tuple[int, int], Qt.SortOrder] = {}

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
        self.motor_search.textChanged.connect(self._filter_motors)
        filter_bar.addWidget(self.motor_search, 3)

        self.motor_mfg_combo = QComboBox(page)
        self.motor_mfg_combo.addItem("All Manufacturers", "")
        self.motor_mfg_combo.currentIndexChanged.connect(self._filter_motors)
        filter_bar.addWidget(self.motor_mfg_combo, 2)

        layout.addLayout(filter_bar)

        # Table
        self.motor_table = QTableWidget(0, 7, page)
        self.motor_table.setHorizontalHeaderLabels([
            "Manufacturer", "Model / Name", "KV (RPM/V)", "Max Current (A)", "Max Power (W)", "Mass (g)", "Rm (Ω)"
        ])
        self._style_table(self.motor_table)
        self.motor_table.horizontalHeader().sectionClicked.connect(
            lambda col: self._sort_table(self.motor_table, col)
        )
        self.motor_table.itemSelectionChanged.connect(self._on_motor_selected)
        self.motor_table.doubleClicked.connect(lambda: self.accept() if self.selected_motor else None)
        layout.addWidget(self.motor_table)

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
        self.prop_search.textChanged.connect(self._filter_propellers)
        filter_bar.addWidget(self.prop_search, 3)

        layout.addLayout(filter_bar)

        # Table
        self.prop_table = QTableWidget(0, 6, page)
        self.prop_table.setHorizontalHeaderLabels([
            "Manufacturer", "Model", "Diameter (in)", "Diameter (mm)", "Pitch (in)", "Blades"
        ])
        self._style_table(self.prop_table)
        self.prop_table.horizontalHeader().sectionClicked.connect(
            lambda col: self._sort_table(self.prop_table, col)
        )
        self.prop_table.itemSelectionChanged.connect(self._on_propeller_selected)
        self.prop_table.doubleClicked.connect(lambda: self.accept() if self.selected_propeller else None)
        layout.addWidget(self.prop_table)

        return page

    def _style_table(self, table: QTableWidget) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(24)
        table.horizontalHeader().setFixedHeight(26)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)

    def _load_motors(self) -> None:
        db = get_motor_database()
        all_motors = [db.get(mid) for mid in db.list_motors()]
        self._motor_entries = [m for m in all_motors if m is not None]

        manufacturers = sorted(list({m.manufacturer for m in self._motor_entries if m.manufacturer}))
        self.motor_mfg_combo.blockSignals(True)
        for mfg in manufacturers:
            self.motor_mfg_combo.addItem(mfg, mfg)
        self.motor_mfg_combo.blockSignals(False)

        self._populate_motor_table(self._motor_entries[:300])
        self.status_label.setText(f"Loaded {len(self._motor_entries):,} motors from PyThrust catalog")

    def _filter_motors(self) -> None:
        query = self.motor_search.text().strip().lower()
        selected_mfg = str(self.motor_mfg_combo.currentData() or "").lower()

        filtered = []
        for m in self._motor_entries:
            if selected_mfg and m.manufacturer.lower() != selected_mfg:
                continue
            if query:
                full_text = f"{m.manufacturer} {m.name} {m.id}".lower()
                if query not in full_text:
                    continue
            filtered.append(m)
            if len(filtered) >= 400:
                break

        self._populate_motor_table(filtered)
        self.status_label.setText(f"Showing {len(filtered)} matching motors (out of {len(self._motor_entries):,})")

    def _populate_motor_table(self, motors: list[MotorEntry]) -> None:
        self.motor_table.setRowCount(len(motors))
        for row, m in enumerate(motors):
            items = [
                QTableWidgetItem(m.manufacturer),
                QTableWidgetItem(m.name),
                _NumericItem(f"{m.kv:.0f}", m.kv),
                _NumericItem(f"{m.max_current:.1f}", m.max_current),
                _NumericItem(f"{m.max_power:.0f}" if m.max_power else "-", m.max_power),
                _NumericItem(f"{m.weight_g:.1f}", m.weight_g),
                _NumericItem(f"{m.resistance:.4f}", m.resistance),
            ]
            items[0].setData(Qt.ItemDataRole.UserRole, m.id)
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.motor_table.setItem(row, col, item)

    def _load_propellers(self) -> None:
        db = get_propeller_database()
        all_props = [db.get(pid) for pid in db.list_propellers()]
        self._prop_entries = [p for p in all_props if p is not None]
        self._populate_propeller_table(self._prop_entries)
        if self.component_type in {"propeller", "rotor"}:
            self.status_label.setText(f"Loaded {len(self._prop_entries):,} propellers from PyThrust catalog")

    def _filter_propellers(self) -> None:
        query = self.prop_search.text().strip().lower()
        filtered = []
        for p in self._prop_entries:
            if query and query not in f"{p.metadata.manufacturer} {p.metadata.model} {p.metadata.id}".lower():
                continue
            filtered.append(p)

        self._populate_propeller_table(filtered)
        self.status_label.setText(f"Showing {len(filtered)} matching propellers")

    def _populate_propeller_table(self, props: list[PropellerEntry]) -> None:
        self.prop_table.setRowCount(len(props))
        for row, p in enumerate(props):
            d_mm = p.diameter_m * 1000.0
            items = [
                QTableWidgetItem(p.metadata.manufacturer),
                QTableWidgetItem(p.metadata.model),
                _NumericItem(f"{p.metadata.diameter_in:.1f}", p.metadata.diameter_in),
                _NumericItem(f"{d_mm:.1f}", d_mm),
                _NumericItem(f"{p.metadata.pitch_in:.1f}", p.metadata.pitch_in),
                _NumericItem(str(p.metadata.blade_count), p.metadata.blade_count),
            ]
            items[0].setData(Qt.ItemDataRole.UserRole, p.metadata.id)
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.prop_table.setItem(row, col, item)

    def _sort_table(self, table: QTableWidget, column: int) -> None:
        """Sort a table by the numeric UserRole value of the given column.

        Numeric columns sort numerically in both directions; missing values
        (``None`` / "-") always sort last. Text columns sort alphabetically.
        Qt's built-in sort compares display text, which breaks numeric order
        (e.g. "100" before "20"), so sorting is done manually here.
        """
        key = (id(table), column)
        prev = self._sort_orders.get(key, Qt.SortOrder.DescendingOrder)
        order = (
            Qt.SortOrder.AscendingOrder
            if prev == Qt.SortOrder.DescendingOrder
            else Qt.SortOrder.DescendingOrder
        )
        self._sort_orders[key] = order
        ascending = order == Qt.SortOrder.AscendingOrder

        def row_key(row: int):
            item = table.item(row, column)
            text = item.text() if item is not None else ""
            value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(value, (int, float)):
                sec = value if ascending else -value
                return (0, sec)
            if text in ("", "-"):
                return (2, text)
            return (1, text)

        ordered = sorted(range(table.rowCount()), key=row_key)
        # Text columns honor direction by reversing instead of negating.
        numeric_column = any(
            isinstance(table.item(r, column).data(Qt.ItemDataRole.UserRole), (int, float))
            for r in range(table.rowCount())
        )
        if not ascending and not numeric_column:
            ordered = list(reversed(ordered))

        columns = table.columnCount()
        collected = [
            [table.takeItem(row, col) for col in range(columns)]
            for row in ordered
        ]
        for new_row, row_items in enumerate(collected):
            for col, item in enumerate(row_items):
                table.setItem(new_row, col, item)
        table.horizontalHeader().setSortIndicator(column, order)

    def _on_motor_selected(self) -> None:
        selected_rows = self.motor_table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_motor = None
            self.apply_btn.setEnabled(False)
            return

        row = selected_rows[0].row()
        item = self.motor_table.item(row, 0)
        motor_id = str(item.data(Qt.ItemDataRole.UserRole)) if item else ""
        self.selected_motor = get_motor_database().get(motor_id)
        self.apply_btn.setEnabled(self.selected_motor is not None)

    def _on_propeller_selected(self) -> None:
        selected_rows = self.prop_table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_propeller = None
            self.apply_btn.setEnabled(False)
            return

        row = selected_rows[0].row()
        item = self.prop_table.item(row, 0)
        prop_id = str(item.data(Qt.ItemDataRole.UserRole)) if item else ""
        self.selected_propeller = get_propeller_database().get(prop_id)
        self.apply_btn.setEnabled(self.selected_propeller is not None)
