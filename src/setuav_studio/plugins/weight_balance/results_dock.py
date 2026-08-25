"""Weight-and-balance summary and component breakdown."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.icons import get_icon, set_label_icon
from setuav_studio.ui.property_tables import ContentFitTableWidget, PropertyTableMixin
from setuav_studio.ui.theme import status_color

from .models import WeightBalanceResult


class WeightBalanceResultsDock(PropertyTableMixin, QWidget):
    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("weight_balance.results_widget")
        self._api = api
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)
        summary_page = QWidget(self)
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(4, 4, 4, 4)
        summary_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        summary_layout.setSpacing(6)

        self.summary_table = self._property_table([
            ("mass", "Total Mass"),
            ("components", "Components Included"),
        ])
        summary_layout.addWidget(self.summary_table)

        summary_layout.addWidget(self._section_label("Center of Gravity", "fa6s.crosshairs"))
        self.cg_table = self._vector_table("Body CG (mm)")
        summary_layout.addWidget(self.cg_table)

        summary_layout.addWidget(self._section_label("Inertia Tensor", "fa6s.cube"))
        self.inertia_table = self._inertia_table()
        summary_layout.addWidget(self.inertia_table)

        warning_row = QWidget(summary_page)
        warning_layout = QHBoxLayout(warning_row)
        warning_layout.setContentsMargins(0, 0, 0, 0)
        warning_layout.setSpacing(6)
        self.warning_icon = QLabel(warning_row)
        self.warning_icon.setFixedSize(16, 16)
        warning_layout.addWidget(self.warning_icon)
        self.warning_label = QLabel("No analysis result", warning_row)
        self.warning_label.setWordWrap(True)
        self.warning_label.setObjectName("weightBalanceWarningLabel")
        self.warning_label.setToolTip("")
        warning_layout.addWidget(self.warning_label, 1)
        self._set_info_icon(self.warning_icon, warning=False)
        summary_layout.addWidget(warning_row)
        summary_layout.addStretch(1)
        tabs.addTab(summary_page, get_icon("fa6s.chart-simple"), "Summary")

        self.component_table = self._create_component_table()
        tabs.addTab(self.component_table, get_icon("fa6s.table-list"), "Components")
        layout.addWidget(tabs, 1)

        api.subscribe("weight_balance.analysis_completed", self.display_result)

    @staticmethod
    def _section_label(title: str, icon_name: str) -> QWidget:
        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)
        icon_label = QLabel(header)
        set_label_icon(icon_label, icon_name)
        icon_label.setFixedSize(14, 14)
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel(title, header))
        header_layout.addStretch(1)
        return header

    @staticmethod
    def _vector_table(row_label: str) -> QTableWidget:
        table = QTableWidget(1, 3)
        table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        table.setVerticalHeaderLabels([row_label])
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(23)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.verticalHeader().setDefaultSectionSize(23)
        table.verticalHeader().setMinimumWidth(96)
        table.setFixedHeight(48)
        return table

    @staticmethod
    def _inertia_table() -> QTableWidget:
        table = QTableWidget(2, 3)
        table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        table.setVerticalHeaderLabels(["Moments", "Products"])
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(23)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.verticalHeader().setDefaultSectionSize(23)
        table.verticalHeader().setMinimumWidth(96)
        table.setFixedHeight(71)
        return table

    def _create_component_table(self) -> ContentFitTableWidget:
        table = ContentFitTableWidget(0, 8, self)
        headers = [
            "Component",
            "Mass (g)",
            "CG-X (mm)",
            "CG-Y (mm)",
            "CG-Z (mm)",
            "Mass Source",
            "Model Quality",
            "Notes",
        ]
        table.setHorizontalHeaderLabels(headers)
        header_tooltips = [
            "Component name",
            "Component mass",
            "Body-frame centre of gravity, X axis (mm)",
            "Body-frame centre of gravity, Y axis (mm)",
            "Body-frame centre of gravity, Z axis (mm)",
            "Where the mass value came from",
            "Declared or approximate model",
            "Warnings generated during aggregation",
        ]
        for column, tooltip in enumerate(header_tooltips):
            header_item = table.horizontalHeaderItem(column)
            if header_item is not None:
                header_item.setToolTip(tooltip)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setTextElideMode(Qt.TextElideMode.ElideNone)
        table.setWordWrap(False)
        font = QFont(table.font().family())
        font.setPointSizeF(9.5)
        table.setFont(font)
        return table

    def display_result(self, result: WeightBalanceResult) -> None:
        total = result.total
        inertia = total.inertia_cg_kg_m2
        values = {
            "mass": f"{total.mass_kg:.4f} kg ({total.mass_kg * 1000.0:.1f} g)",
            "components": str(len(result.components)),
        }
        for key, value in values.items():
            self._set_property_value(self.summary_table, key, value)

        for column, value in enumerate(total.cg_body_m):
            self.cg_table.setItem(
                0,
                column,
                QTableWidgetItem(f"{value * 1000.0:+.2f}"),
            )

        inertia_values = (
            (inertia.ixx, inertia.iyy, inertia.izz),
            (inertia.ixy, inertia.ixz, inertia.iyz),
        )
        for row, row_values in enumerate(inertia_values):
            for column, value in enumerate(row_values):
                self.inertia_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(f"{value:.6g} kg·m²"),
                )

        warning_tooltip = self._warning_tooltip(result.warnings)
        has_warnings = bool(result.warnings)
        self.warning_label.setText(
            f"{len(result.warnings)} warning(s)"
            if has_warnings
            else "Mass model complete with no warnings."
        )
        self.warning_label.setToolTip(warning_tooltip)
        self._set_info_icon(self.warning_icon, warning=has_warnings)
        self.warning_icon.setToolTip(warning_tooltip)
        self.component_table.setRowCount(len(result.components))
        for row, item in enumerate(result.components):
            values = (
                item.component_name,
                f"{item.mass_kg * 1000.0:.2f}",
                f"{item.cg_body_m[0] * 1000.0:+.2f}",
                f"{item.cg_body_m[1] * 1000.0:+.2f}",
                f"{item.cg_body_m[2] * 1000.0:+.2f}",
                item.source,
                item.quality,
                (
                    f"{len(item.warnings)} warning(s)"
                    if item.warnings
                    else "—"
                ),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 7 and item.warnings:
                    warning_color = status_color("warning")
                    cell.setForeground(QBrush(QColor(warning_color)))
                    cell.setIcon(get_icon("fa6s.circle-info", color=warning_color))
                    cell.setToolTip(self._warning_tooltip(item.warnings))
                self.component_table.setItem(row, column, cell)
        self.component_table.fit_columns_to_viewport()

    @staticmethod
    def _set_info_icon(label: QLabel, *, warning: bool) -> None:
        color = status_color("warning") if warning else None
        label.setPixmap(get_icon("fa6s.circle-info", color=color).pixmap(16, 16))

    @staticmethod
    def _warning_tooltip(warnings: list[str] | tuple[str, ...]) -> str:
        if not warnings:
            return ""
        return "<b>Warnings</b><br>" + "<br>".join(
            f"• {warning}" for warning in warnings
        )
