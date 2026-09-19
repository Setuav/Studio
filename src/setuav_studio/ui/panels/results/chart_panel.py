"""Analysis Chart dock panel for interactive engineering curve visualization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.solver.results import AnalysisResult, PlotDefinition, TableDefinition
from setuav_studio.ui.style.icons import get_icon
from setuav_studio.ui.widget.chart import StudioChartWidget

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class AnalysisChartPanel(QWidget):
    """Themed dock panel dedicated to displaying interactive plots derived from analysis tables."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._current_result: AnalysisResult | None = None
        self._current_plot: PlotDefinition | None = None
        self._current_table: TableDefinition | None = None
        self._active_x_column: str = ""

        self._init_ui()
        self._api.on_selection_changed(self._on_selection_changed)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Top Toolbar
        self._toolbar = QWidget()
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(4, 2, 4, 2)
        tb_layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setPixmap(get_icon("fa6s.chart-line").pixmap(16, 16))
        tb_layout.addWidget(self._icon_label)

        self._title_label = QLabel("Analysis Plot")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        tb_layout.addWidget(self._title_label)

        tb_layout.addStretch()

        # X-Axis Selector
        self._x_label = QLabel("X:")
        self._x_label.setStyleSheet("color: #888888; font-size: 10px;")
        tb_layout.addWidget(self._x_label)

        self._x_combo = QComboBox()
        self._x_combo.setToolTip("Select independent variable (X-axis)")
        self._x_combo.currentTextChanged.connect(self._on_x_column_changed)
        tb_layout.addWidget(self._x_combo)

        # Actions
        self._reset_btn = QPushButton("Reset View")
        self._reset_btn.setToolTip("Auto-scale axes to fit all curve data")
        self._reset_btn.setIcon(get_icon("fa6s.arrows-rotate"))
        self._reset_btn.clicked.connect(self._reset_view)
        tb_layout.addWidget(self._reset_btn)

        self._export_png_btn = QPushButton("Export PNG")
        self._export_png_btn.setToolTip("Export chart as a high-resolution image")
        self._export_png_btn.setIcon(get_icon("fa6s.image"))
        self._export_png_btn.clicked.connect(self._export_png)
        tb_layout.addWidget(self._export_png_btn)

        self._export_csv_btn = QPushButton("Export CSV")
        self._export_csv_btn.setToolTip("Export underlying table data to RFC 4180 CSV")
        self._export_csv_btn.setIcon(get_icon("fa6s.file-csv"))
        self._export_csv_btn.clicked.connect(self._export_csv)
        tb_layout.addWidget(self._export_csv_btn)

        main_layout.addWidget(self._toolbar)

        # Stacked view for content vs empty placeholder
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

        # 1. Empty placeholder
        self._empty_view = QWidget()
        empty_layout = QVBoxLayout(self._empty_view)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder = QLabel(
            "No analysis plot selected.\nRun an analysis or select a plot in Project Explorer."
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #888888; font-size: 12px; line-height: 150%;")
        empty_layout.addWidget(placeholder)
        self._stack.addWidget(self._empty_view)

        # 2. Chart Widget
        self._chart_widget = StudioChartWidget(parent=self)
        self._chart_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack.addWidget(self._chart_widget)

        self._stack.setCurrentWidget(self._empty_view)
        self._toolbar.setVisible(False)

    def load_plot(
        self,
        plot: PlotDefinition,
        table: TableDefinition,
        result: AnalysisResult | None = None,
    ) -> None:
        """Load and plot curves from table according to PlotDefinition."""
        self._current_plot = plot
        self._current_table = table
        self._current_result = result
        self._active_x_column = plot.x_column

        self._title_label.setText(plot.title or plot.id)

        # Populate X combo
        self._x_combo.blockSignals(True)
        self._x_combo.clear()
        for col in table.columns:
            self._x_combo.addItem(col.header_text(use_display_units=True), col.key)
        # Select active X
        idx = self._x_combo.findData(self._active_x_column)
        if idx >= 0:
            self._x_combo.setCurrentIndex(idx)
        self._x_combo.blockSignals(False)

        self._render_chart()
        self._toolbar.setVisible(True)
        self._stack.setCurrentWidget(self._chart_widget)

    def _on_x_column_changed(self) -> None:
        if not self._current_table or not self._current_plot:
            return
        selected_key = self._x_combo.currentData()
        if selected_key and selected_key != self._active_x_column:
            self._active_x_column = str(selected_key)
            self._render_chart()

    def _render_chart(self) -> None:
        if not self._current_table or not self._current_plot:
            return

        table = self._current_table
        plot = self._current_plot
        x_col = self._active_x_column

        self._chart_widget.clear()
        self._chart_widget.setTitle(plot.title)

        x_vals = table.get_column_display_values(x_col)
        if not x_vals:
            return

        x_numeric: list[float] = [float(v) for v in x_vals if isinstance(v, (int, float))]
        if not x_numeric:
            return

        # Setup X Axis
        x_col_def = table.get_column_def(x_col)
        x_title = x_col_def.header_text(use_display_units=True) if x_col_def else x_col
        axis_x = self._chart_widget.create_axis(title=x_title)

        # Setup Y Axis
        y_label = plot.y_label or (
            table.get_column_def(plot.series[0].y_column).header_text(use_display_units=True)
            if plot.series and table.get_column_def(plot.series[0].y_column)
            else "Value"
        )
        axis_y = self._chart_widget.create_axis(title=y_label)

        self._chart_widget.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self._chart_widget.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        min_x, max_x = min(x_numeric), max(x_numeric)
        all_y_numeric: list[float] = []

        # Color roles / palettes
        palette = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4"]

        for i, s_def in enumerate(plot.series):
            y_col = s_def.y_column
            y_vals = table.get_column_display_values(y_col)
            if not y_vals:
                continue

            y_col_def = table.get_column_def(y_col)
            series_name = s_def.label or (y_col_def.label if y_col_def else y_col)

            color = s_def.color or palette[i % len(palette)]
            line_style = Qt.PenStyle.SolidLine
            if s_def.style == "dashed":
                line_style = Qt.PenStyle.DashLine
            elif s_def.style == "dotted":
                line_style = Qt.PenStyle.DotLine

            line_series = self._chart_widget.create_line_series(
                name=series_name,
                width=2.0,
                style=line_style,
            )
            # Apply color
            pen = line_series.pen()
            pen.setColor(color)
            line_series.setPen(pen)

            for x, y in zip(x_vals, y_vals, strict=False):
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    line_series.append(float(x), float(y))
                    all_y_numeric.append(float(y))

            self._chart_widget.add_line_series(line_series, axis_x, axis_y)

        # Set range with 5% margin
        dx = max(abs(max_x - min_x) * 0.05, 0.1)
        axis_x.setRange(min_x - dx, max_x + dx)

        if all_y_numeric:
            min_y, max_y = min(all_y_numeric), max(all_y_numeric)
            dy = max(abs(max_y - min_y) * 0.05, 0.1)
            axis_y.setRange(min_y - dy, max_y + dy)

        self._chart_widget.update_theme_style()

    def _reset_view(self) -> None:
        self._render_chart()

    def _export_png(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chart Image",
            f"{self._title_label.text().replace(' ', '_').lower()}.png",
            "PNG Images (*.png);;All Files (*)",
        )
        if not file_path:
            return

        pixmap = QPixmap(self._chart_widget.view.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._chart_widget.view.render(painter)
        painter.end()
        pixmap.save(file_path, "PNG")
        self._api.show_status(f"Chart image exported to {file_path}", "success")

    def _export_csv(self) -> None:
        if not self._current_table:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Table Data",
            f"{self._current_table.id}.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        if self._current_result:
            self._current_result.export_table_csv(
                self._current_table.id, file_path, use_display_units=True
            )
        else:
            from pathlib import Path

            Path(file_path).write_text(
                self._current_table.to_csv(use_display_units=True), encoding="utf-8"
            )
        self._api.show_status(f"Table data exported to {file_path}", "success")

    def _on_selection_changed(self, selection: Any | None) -> None:
        if not isinstance(selection, dict):
            return
        if selection.get("kind") == "analysis_plot":
            res_id = str(selection.get("result_id", ""))
            plot_id = str(selection.get("plot_id", ""))
            result = self._api.get_analysis_result(res_id)
            if result and plot_id in result.plots:
                plot = result.plots[plot_id]
                table = result.tables.get(plot.table_id)
                if table:
                    self.load_plot(plot, table, result)
