"""Properties panel editor for a selected Analysis Table dataset."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.solver.results import AnalysisResult, TableDefinition
from setuav_studio.ui.style.icons import get_icon, set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


class AnalysisTablePropertyEditor(PropertyTableMixin, QWidget):
    """Property editor for AnalysisTable objects displaying metadata, column units and CSV export."""

    def __init__(
        self,
        api: StudioAPI,
        table_item: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._result_id = str(table_item.get("result_id") or "")
        self._table_id = str(table_item.get("table_id") or "")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_details_section()
        self._create_columns_section()
        self._create_actions_section()
        self._content_layout.addStretch()

        self._load_data()

    def _get_result_and_table(self) -> tuple[AnalysisResult | None, TableDefinition | None]:
        if not self._result_id or not self._table_id:
            return None, None
        res = self._api.get_analysis_result(self._result_id)
        if res is None or self._table_id not in res.tables:
            return None, None
        table = res.tables[self._table_id]
        return res, table

    def _create_section(
        self,
        title: str,
        icon_name: str | None = None,
        action_widget: QWidget | None = None,
    ) -> QVBoxLayout:
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
            set_label_icon(icon_label, icon_name)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        if action_widget is not None:
            header_layout.addWidget(action_widget)

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_details_section(self) -> None:
        layout = self._create_section("Table Details", "fa6s.table")
        self.details_table = self._property_table(
            [
                ("table_name", "Table Name"),
                ("result_name", "Result"),
                ("row_count", "Rows"),
                ("col_count", "Columns"),
            ]
        )
        layout.addWidget(self.details_table)

    def _create_columns_section(self) -> None:
        layout = self._create_section("Column Definitions", "fa6s.list-check")
        self.columns_table = self._property_table([])
        layout.addWidget(self.columns_table)

    def _create_actions_section(self) -> None:
        layout = self._create_section("Actions", "fa6s.wrench")

        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(0, 2, 0, 0)
        btn_layout.setSpacing(6)

        self._view_table_btn = QPushButton("View Table")
        self._view_table_btn.setIcon(get_icon("fa6s.table"))
        self._view_table_btn.setToolTip("Open table in Result panel")
        self._view_table_btn.clicked.connect(self._on_view_table_clicked)
        btn_layout.addWidget(self._view_table_btn)

        self._export_csv_btn = QPushButton("Export CSV")
        self._export_csv_btn.setIcon(get_icon("fa6s.file-csv"))
        self._export_csv_btn.setToolTip("Export entire table to RFC 4180 CSV")
        self._export_csv_btn.clicked.connect(self._on_export_csv_clicked)
        btn_layout.addWidget(self._export_csv_btn)

        layout.addWidget(btn_bar)

    def _load_data(self) -> None:
        res, table = self._get_result_and_table()
        if res is None or table is None:
            return

        # 1. Details
        self._set_property_value(
            self.details_table, "table_name", table.title or table.id, editable=False
        )
        self._set_property_value(
            self.details_table, "result_name", res.name or res.id, editable=False
        )
        self._set_property_value(
            self.details_table, "row_count", f"{table.row_count()} rows", editable=False
        )
        self._set_property_value(
            self.details_table, "col_count", f"{len(table.columns)} columns", editable=False
        )

        # 2. Columns summary
        col_fields = [(c.key, c.header_text(use_display_units=True)) for c in table.columns]
        self._configure_property_table(self.columns_table, col_fields)
        for c in table.columns:
            val_text = f"Unit: {c.unit or '—'}"
            if c.quantity_id:
                val_text += f" ({c.quantity_id})"
            self._set_property_value(self.columns_table, c.key, val_text, editable=False)

    def _on_view_table_clicked(self) -> None:
        res, table = self._get_result_and_table()
        if res is None or table is None:
            return
        self._api.show_panel("core:result")
        self._api.set_selection(
            {
                "kind": "analysis_table",
                "id": f"{res.id}:table:{table.id}",
                "result_id": res.id,
                "table_id": table.id,
                "name": table.title or table.id,
            }
        )

    def _on_export_csv_clicked(self) -> None:
        res, table = self._get_result_and_table()
        if res is None or table is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Table Data",
            f"{table.id}.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if file_path:
            res.export_table_csv(table.id, file_path, use_display_units=True)
            self._api.show_status(f"Table data exported to {file_path}", "success")
