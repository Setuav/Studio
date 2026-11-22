"""Analysis Table dock panel for tabular simulation dataset inspection and CSV export."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    Qt,
    Signal,
)
from PySide6.QtGui import QResizeEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api.events import StudioEvents
from setuav_studio.solver.results import SolverResult, TableDefinition
from setuav_studio.ui.style.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


_EMPTY_INDEX = QModelIndex()


_SHORT_LABEL_MAP: dict[str, str] = {
    "L/D Ratio": "L/D",
    "Lift Coeff (CL)": "CL",
    "Lift Coefficient (CL)": "CL",
    "Drag Coeff (CD)": "CD",
    "Drag Coefficient (CD)": "CD",
    "Pitching Moment (Cm)": "Cm",
    "Pitching Moment Coefficient (Cm)": "Cm",
    "Induced Drag (CDi)": "CDi",
    "Profile Drag (CDp)": "CDp",
    "Lift Force": "Lift",
    "Drag Force": "Drag",
    "Sideforce Coeff (CY)": "CY",
    "Sideforce Coefficient (CY)": "CY",
    "Rolling Moment (Cl)": "Cl",
    "Rolling Moment Coefficient (Cl)": "Cl",
    "Yawing Moment (Cn)": "Cn",
    "Yawing Moment Coefficient (Cn)": "Cn",
    "Sideforce": "Side Force",
    "Advance Ratio (J)": "J (Advance)",
    "System Efficiency": "Sys Eff",
    "Propeller Efficiency": "Prop Eff",
    "Motor Efficiency": "Motor Eff",
    "Electrical Power": "Power",
    "Battery Voltage": "Voltage",
}


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

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _EMPTY_INDEX) -> int:
        if parent.isValid():
            return 0
        return self._table.row_count() + 1

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _EMPTY_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._table.columns)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._table.columns):
                col = self._table.columns[section]
                if role == Qt.ItemDataRole.DisplayRole:
                    label = col.label
                    return _SHORT_LABEL_MAP.get(label, label)
                elif role == Qt.ItemDataRole.ToolTipRole:
                    return col.label or col.key
        elif orientation == Qt.Orientation.Vertical:
            if role == Qt.ItemDataRole.DisplayRole:
                if section == 0:
                    return "Unit"
                return str(section)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
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


class FrozenRowView(QTableView):
    """Child table view specifically displaying the frozen row (Unit row)."""

    def __init__(self, parent_view: FrozenUnitTableView) -> None:
        super().__init__(parent_view)
        self._parent_view = parent_view
        self.setObjectName("frozenUnitView")

    def wheelEvent(self, event: QWheelEvent) -> None:
        # Forward scroll wheel events to parent table so scrolling works on frozen row
        self._parent_view.wheelEvent(event)


class FrozenUnitTableView(QTableView):
    """QTableView keeping row 0 (Unit row) frozen at the top under the horizontal header."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._natural_widths: list[int] = []

        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(False)

        self.frozen_view = FrozenRowView(self)
        self.frozen_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.frozen_view.horizontalHeader().hide()
        self.frozen_view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.frozen_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.frozen_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.frozen_view.horizontalHeader().setStretchLastSection(False)
        self.frozen_view.setAlternatingRowColors(True)
        self.frozen_view.setStyleSheet(
            "#frozenUnitView { border: none; border-bottom: 1px solid rgba(128, 128, 128, 0.3); background-color: palette(base); }"
        )

        self.viewport().stackUnder(self.frozen_view)

        self.horizontalHeader().sectionResized.connect(self._on_section_resized)
        self.horizontalHeader().geometriesChanged.connect(self.update_frozen_geometry)
        self.verticalHeader().geometriesChanged.connect(self.update_frozen_geometry)
        self.horizontalScrollBar().valueChanged.connect(
            self.frozen_view.horizontalScrollBar().setValue
        )
        self.frozen_view.horizontalScrollBar().valueChanged.connect(
            self.horizontalScrollBar().setValue
        )

    def setModel(self, model: QAbstractItemModel | None) -> None:
        old_model = self.model()
        if old_model is not None:
            old_model.modelReset.disconnect(self._sync_frozen_rows)
        super().setModel(model)
        self.frozen_view.setModel(model)
        if model is not None:
            model.modelReset.connect(self._sync_frozen_rows)
            if self.selectionModel() is not None:
                self.frozen_view.setSelectionModel(self.selectionModel())
        self._sync_frozen_rows()
        self.auto_fit_columns()

    def _sync_frozen_rows(self) -> None:
        m = self.model()
        if not m or m.rowCount() == 0:
            self.frozen_view.hide()
            return
        self.frozen_view.show()
        self.frozen_view.setRowHidden(0, False)
        for r in range(1, m.rowCount()):
            self.frozen_view.setRowHidden(r, True)
        self.update_frozen_geometry()

    def auto_fit_columns(self) -> None:
        """Size every column according to its widest cell and header, with breathing room."""
        m = self.model()
        if not m or m.columnCount() == 0:
            return

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.resizeColumnsToContents()

        col_count = m.columnCount()
        self._natural_widths = [max(70, self.columnWidth(c) + 16) for c in range(col_count)]
        self._relayout_columns()
        self.update_frozen_geometry()

    def _relayout_columns(self) -> None:
        """Ensure columns fit naturally or expand to fill available viewport space."""
        m = self.model()
        if not m or m.columnCount() == 0 or not self._natural_widths:
            return
        col_count = m.columnCount()
        if len(self._natural_widths) != col_count:
            return

        total_natural = sum(self._natural_widths)
        viewport_w = self.viewport().width()

        if total_natural < viewport_w and col_count > 0:
            extra = viewport_w - total_natural
            extra_per_col = extra // col_count
            remainder = extra % col_count
            for c in range(col_count):
                add = extra_per_col + (1 if c < remainder else 0)
                self.setColumnWidth(c, self._natural_widths[c] + add)
        else:
            for c in range(col_count):
                if self.columnWidth(c) < self._natural_widths[c]:
                    self.setColumnWidth(c, self._natural_widths[c])

    def _on_section_resized(self, logical_index: int, _old_size: int, new_size: int) -> None:
        self.frozen_view.setColumnWidth(logical_index, new_size)
        self.update_frozen_geometry()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout_columns()
        self.update_frozen_geometry()

    def update_frozen_geometry(self) -> None:
        m = self.model()
        if not m or m.rowCount() == 0:
            return
        vh_w = self.verticalHeader().width() if self.verticalHeader().isVisible() else 0
        self.frozen_view.verticalHeader().setFixedWidth(vh_w)
        self.frozen_view.verticalHeader().setDefaultSectionSize(
            self.verticalHeader().defaultSectionSize()
        )
        hh_h = self.horizontalHeader().height()
        r0_h = self.rowHeight(0) or 22
        w = self.viewport().width() + vh_w
        x = self.frameWidth()
        y = self.frameWidth() + hh_h
        self.frozen_view.setGeometry(x, y, w, r0_h)
        for c in range(m.columnCount()):
            self.frozen_view.setColumnWidth(c, self.columnWidth(c))


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
        self._current_result: SolverResult | None = None
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
        placeholder.setWordWrap(True)
        placeholder.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        placeholder.setStyleSheet("color: #888888; font-size: 12px; line-height: 150%;")
        empty_layout.addWidget(placeholder)
        self._stack.addWidget(self._empty_view)

        # 2. Table View
        self._table_view = FrozenUnitTableView(self)
        self._table_view.setAlternatingRowColors(True)
        self._table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table_view.verticalHeader().setDefaultSectionSize(22)
        self._table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table_view.frozen_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.frozen_view.customContextMenuRequested.connect(self._on_table_context_menu)
        self._stack.addWidget(self._table_view)

        self._stack.setCurrentWidget(self._empty_view)
        self._toolbar.setVisible(False)

    def load_table(
        self,
        table: TableDefinition,
        result: SolverResult | None = None,
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
        self._table_view.auto_fit_columns()

        self._toolbar.setVisible(True)
        self._stack.setCurrentWidget(self._table_view)

    def _on_units_changed(self, _payload: Any = None) -> None:
        if self._model is not None:
            self._model.set_use_display_units(self._use_display_units)
            self._table_view.auto_fit_columns()

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
            result = self._api.get_solver_result(res_id)
            if result and table_id in result.tables:
                self.load_table(result.tables[table_id], result)

    def _on_table_context_menu(self, pos: QPoint) -> None:
        if self._current_table is None:
            return

        sender = self.sender()
        if isinstance(sender, QAbstractScrollArea) and sender.viewport() is not None:
            viewport = sender.viewport()
        else:
            viewport = self._table_view.viewport()
        global_pos = viewport.mapToGlobal(pos)

        menu = QMenu(self)
        add_plot_act = menu.addAction(get_icon("fa6s.chart-line"), "Add Plot…")
        menu.addSeparator()
        export_act = menu.addAction(get_icon("fa6s.file-csv"), "Export CSV…")

        chosen = menu.exec(global_pos)
        if chosen is add_plot_act:
            self._add_plot()
        elif chosen is export_act:
            self._export_csv()

    def _add_plot(self) -> None:
        if self._current_table is None:
            return
        from setuav_studio.ui.panels.project_explorer.dialog_actions import (
            add_plot_action,
        )

        element = {
            "result_id": self._current_result.id if self._current_result else None,
            "table_id": self._current_table.id,
            "config_id": (self._current_result.config.config_id if self._current_result else None),
        }
        add_plot_action(self._api, element, parent=self)
