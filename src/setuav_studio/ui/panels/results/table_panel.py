"""Analysis Table dock panel for tabular simulation dataset inspection and CSV export."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api.events import StudioEvents
from setuav_studio.solver.results import AnalysisResult, TableDefinition
from setuav_studio.ui.style.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


_EMPTY_INDEX = QModelIndex()


class AnalysisTableModel(QAbstractTableModel):
    """Read-only table model backed by a columnar TableDefinition.

    Presents column labels in the horizontal header, a dedicated Unit row
    at index 0, and converted numeric data in the subsequent rows.
    """

    def __init__(
        self,
        table: TableDefinition,
        use_display_units: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._table = table
        self._use_display_units = use_display_units
        self._cache_data()

    def _cache_data(self) -> None:
        self._col_data: list[list[Any]] = [
            (
                self._table.get_column_display_values(col.key)
                if self._use_display_units
                else self._table.get_column(col.key)
            )
            for col in self._table.columns
        ]
        self._col_units: list[str] = [
            col.display_unit(self._use_display_units) for col in self._table.columns
        ]

    def set_use_display_units(self, use_display: bool) -> None:
        self.beginResetModel()
        self._use_display_units = use_display
        self._cache_data()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = _EMPTY_INDEX) -> int:
        if parent.isValid():
            return 0
        return self._table.row_count() + 1

    def columnCount(self, parent: QModelIndex = _EMPTY_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._table.columns)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                if 0 <= section < len(self._table.columns):
                    return self._table.columns[section].label
            elif orientation == Qt.Orientation.Vertical:
                if section == 0:
                    return "Unit"
                return str(section)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        # Row 0: Dedicated Unit Cell under column name
        if row == 0:
            if 0 <= col < len(self._col_units):
                u = self._col_units[col]
                unit_text = f"[{u}]" if u else "[-]"
                if role == Qt.ItemDataRole.DisplayRole:
                    return unit_text
                elif role == Qt.ItemDataRole.TextAlignmentRole:
                    return int(Qt.AlignmentFlag.AlignCenter)
                elif role == Qt.ItemDataRole.ForegroundRole:
                    from PySide6.QtGui import QColor

                    return QColor("#888888")
                elif role == Qt.ItemDataRole.FontRole:
                    from PySide6.QtGui import QFont

                    f = QFont()
                    f.setItalic(True)
                    return f
            return None

        # Data rows (index.row() >= 1)
        data_row = row - 1
        if role == Qt.ItemDataRole.DisplayRole:
            if 0 <= col < len(self._col_data):
                col_list = self._col_data[col]
                if 0 <= data_row < len(col_list):
                    val = col_list[data_row]
                    if isinstance(val, float):
                        if abs(val) < 1e-4 and val != 0.0:
                            return f"{val:.4e}"
                        return f"{val:.4f}"
                    return str(val)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        return None


class AnalysisTablePanel(QWidget):
    """Themed dock panel dedicated to displaying tabular simulation datasets."""

    close_requested = Signal()

    def __init__(
        self,
        api: StudioAPI,
        auto_sync_selection: bool = True,
        show_close_button: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._auto_sync_selection = auto_sync_selection
        self._show_close_button = show_close_button
        self._current_result: AnalysisResult | None = None
        self._current_table: TableDefinition | None = None
        self._use_display_units: bool = True
        self._model: AnalysisTableModel | None = None

        self._init_ui()
        if self._auto_sync_selection:
            self._api.on_selection_changed(self._on_selection_changed)
        self._api.subscribe(str(StudioEvents.UNITS_CHANGED), self._on_units_changed)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Top Toolbar
        self._toolbar = QWidget()
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(4, 2, 4, 2)
        tb_layout.setSpacing(8)

        self._title_label = QLabel("Analysis Table")

        tb_layout.addStretch()

        self._meta_label = QLabel()
        tb_layout.addWidget(self._meta_label)

        # Unit system toggle
        self._units_toggle_btn = QPushButton("Units: Display")
        self._units_toggle_btn.setToolTip("Toggle between User Display Units and Raw SI Units")
        self._units_toggle_btn.clicked.connect(self._toggle_units)
        tb_layout.addWidget(self._units_toggle_btn)

        # Export CSV button
        self._export_csv_btn = QPushButton("Export CSV")
        self._export_csv_btn.setToolTip("Export entire table to RFC 4180 CSV format")
        self._export_csv_btn.setIcon(get_icon("fa6s.file-csv"))
        self._export_csv_btn.clicked.connect(self._export_csv)
        tb_layout.addWidget(self._export_csv_btn)

        if self._show_close_button:
            self._close_btn = QPushButton()
            self._close_btn.setIcon(get_icon("fa6s.xmark"))
            self._close_btn.setToolTip("Close this table view")
            self._close_btn.setFixedSize(24, 24)
            self._close_btn.setStyleSheet("padding: 2px;")
            self._close_btn.clicked.connect(self.close_requested.emit)
            tb_layout.addWidget(self._close_btn)

        main_layout.addWidget(self._toolbar)

        # Stacked view
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

        # 1. Empty placeholder
        self._empty_view = QWidget()
        empty_layout = QVBoxLayout(self._empty_view)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder = QLabel(
            "No analysis table selected.\nRun an analysis or select a table in Project Explorer."
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #888888; font-size: 12px; line-height: 150%;")
        empty_layout.addWidget(placeholder)
        self._stack.addWidget(self._empty_view)

        # 2. Table View
        self._table_view = QTableView(self)
        self._table_view.setAlternatingRowColors(True)
        self._table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table_view.verticalHeader().setDefaultSectionSize(22)
        self._stack.addWidget(self._table_view)

        self._stack.setCurrentWidget(self._empty_view)
        self._toolbar.setVisible(False)

    def load_table(
        self,
        table: TableDefinition,
        result: AnalysisResult | None = None,
    ) -> None:
        """Populate the table view with columnar data from TableDefinition."""
        self._current_table = table
        self._current_result = result

        self._title_label.setText(table.title or table.id)
        self._meta_label.setText(f"{table.row_count()} rows, {len(table.columns)} cols")

        self._model = AnalysisTableModel(
            table, use_display_units=self._use_display_units, parent=self
        )
        self._table_view.setModel(self._model)
        self._table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self._toolbar.setVisible(True)
        self._stack.setCurrentWidget(self._table_view)

    def _toggle_units(self) -> None:
        self._use_display_units = not self._use_display_units
        label_text = "Units: Display" if self._use_display_units else "Units: SI"
        self._units_toggle_btn.setText(label_text)
        if self._model is not None:
            self._model.set_use_display_units(self._use_display_units)

    def _on_units_changed(self, _payload: Any = None) -> None:
        if self._model is not None:
            self._model.set_use_display_units(self._use_display_units)

    def _export_csv(self) -> None:
        if not self._current_table:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Table CSV",
            f"{self._current_table.id}.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        if self._current_result:
            self._current_result.export_table_csv(
                self._current_table.id, file_path, use_display_units=self._use_display_units
            )
        else:
            from pathlib import Path

            Path(file_path).write_text(
                self._current_table.to_csv(use_display_units=self._use_display_units),
                encoding="utf-8",
            )
        self._api.show_status(f"Table exported to {file_path}", "success")

    def _on_selection_changed(self, selection: Any | None) -> None:
        if not isinstance(selection, dict):
            return
        if selection.get("kind") == "analysis_table":
            res_id = str(selection.get("result_id", ""))
            table_id = str(selection.get("table_id", ""))
            result = self._api.get_analysis_result(res_id)
            if result and table_id in result.tables:
                self.load_table(result.tables[table_id], result)
