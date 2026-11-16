"""Analysis Chart dock panel for interactive engineering curve visualization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCharts import QLineSeries
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
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

from setuav_studio.api.events import StudioEvents
from setuav_studio.solver.results import PlotDefinition, SolverResult, TableDefinition
from setuav_studio.ui.style.icons import get_icon
from setuav_studio.ui.widget.chart import StudioChartWidget

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


class AnalysisChartPanel(QWidget):
    """Themed dock panel dedicated to displaying interactive plots derived from analysis tables."""

    close_requested = Signal()

    def __init__(
        self,
        api: StudioAPI,
        auto_sync_selection: bool = True,
        show_close_button: bool = False,
        show_toolbar: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._auto_sync_selection = auto_sync_selection
        self._show_close_button = show_close_button
        self._show_toolbar = show_toolbar
        self._current_result: SolverResult | None = None
        self._current_plot: PlotDefinition | None = None
        self._current_table: TableDefinition | None = None
        self._active_x_column: str = ""

        self._init_ui()
        if self._auto_sync_selection:
            self._api.on_selection_changed(self._on_selection_changed)
        self._api.subscribe(str(StudioEvents.UNITS_CHANGED), self._on_units_changed)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

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

        if self._show_close_button:
            self._close_btn = QPushButton()
            self._close_btn.setIcon(get_icon("fa6s.xmark"))
            self._close_btn.setToolTip("Close this chart view")
            self._close_btn.setFixedSize(24, 24)
            self._close_btn.setStyleSheet("padding: 2px;")
            self._close_btn.clicked.connect(self.close_requested.emit)
            tb_layout.addWidget(self._close_btn)

        if self._show_toolbar:
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
        placeholder.setWordWrap(True)
        placeholder.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        placeholder.setStyleSheet("color: #888888; font-size: 12px; line-height: 150%;")
        empty_layout.addWidget(placeholder)
        self._stack.addWidget(self._empty_view)

        # 2. Chart Widget
        self._chart_widget = StudioChartWidget(
            parent=self,
            legend_alignment=Qt.AlignmentFlag.AlignTop,
            mouse_interaction=False,
        )
        self._chart_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack.addWidget(self._chart_widget)

        self._stack.setCurrentWidget(self._empty_view)
        self._toolbar.setVisible(False)

    def load_plot(
        self,
        plot: PlotDefinition,
        table: TableDefinition,
        result: SolverResult | None = None,
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
        if self._show_toolbar:
            self._toolbar.setVisible(True)
        else:
            self._toolbar.setVisible(False)
        self._stack.setCurrentWidget(self._chart_widget)

    def reload_plot(self) -> None:
        """Re-render the active plot using updated definition/series."""
        if hasattr(self._chart_widget, "chart"):
            self._chart_widget.chart.zoomReset()
        if self._current_plot is not None:
            self._active_x_column = self._current_plot.x_column
            self._title_label.setText(self._current_plot.title or self._current_plot.id)
        self._render_chart()

    def reset_view(self) -> None:
        """Auto-scale axes to fit all curve data and reset zoom."""
        if hasattr(self._chart_widget, "chart"):
            self._chart_widget.chart.zoomReset()
        self._render_chart()

    def _on_units_changed(self, _payload: Any = None) -> None:
        if self._current_plot is not None:
            self.reload_plot()

    def export_png(self, file_path: str | None = None) -> str | None:
        """Export chart as a high-resolution PNG image."""
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Chart Image",
                f"{(self._current_plot.title if self._current_plot else 'chart').replace(' ', '_').lower()}.png",
                "PNG Images (*.png);;All Files (*)",
            )
        if not file_path:
            return None

        pixmap = QPixmap(self._chart_widget.view.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._chart_widget.view.render(painter)
        painter.end()
        pixmap.save(file_path, "PNG")
        self._api.show_status(f"Chart image exported to {file_path}", "success")
        return file_path

    def export_csv(self, file_path: str | None = None) -> str | None:
        """Export underlying table data to RFC 4180 CSV."""
        if not self._current_table:
            return None
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Table Data",
                f"{self._current_table.id}.csv",
                "CSV Files (*.csv);;All Files (*)",
            )
        if not file_path:
            return None

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
        return file_path

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
        self._chart_widget.setTitle("")

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

        palette = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4"]
        curves: list[tuple[Any, str, QPen, list[tuple[float, float]]]] = []
        for i, s_def in enumerate(plot.series):
            y_col_def = table.get_column_def(s_def.y_column)
            points = [
                (float(x), float(y))
                for x, y in zip(
                    x_vals, table.get_column_display_values(s_def.y_column), strict=True
                )
                if isinstance(x, (int, float)) and isinstance(y, (int, float))
            ]
            line_style = {
                "dashed": Qt.PenStyle.DashLine,
                "dotted": Qt.PenStyle.DotLine,
            }.get(s_def.style, Qt.PenStyle.SolidLine)
            pen = QPen(QColor(s_def.color or palette[i % len(palette)]), 2.0, line_style)
            name = s_def.label or (y_col_def.label if y_col_def else s_def.y_column)
            curves.append((s_def, name, pen, points))

        axis_y = self._chart_widget.create_axis(title=self._axis_title(plot, table, "left"))
        self._chart_widget.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self._chart_widget.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        y_axes = {"left": axis_y}
        if any(s_def.axis == "right" for s_def, *_ in curves):
            axis_y2 = self._chart_widget.create_axis(
                title=self._axis_title(plot, table, "right"), show_grid=False
            )
            self._chart_widget.chart.addAxis(axis_y2, Qt.AlignmentFlag.AlignRight)
            y_axes["right"] = axis_y2

        min_x, max_x = min(x_numeric), max(x_numeric)
        dx = max(abs(max_x - min_x) * 0.05, 0.1)
        axis_x.setRange(min_x - dx, max_x + dx)
        for side, axis in y_axes.items():
            values = [y for s_def, _, _, pts in curves if s_def.axis == side for _, y in pts]
            if values:
                min_y, max_y = min(values), max(values)
                dy = max(abs(max_y - min_y) * 0.05, 0.1)
                axis.setRange(min_y - dy, max_y + dy)

        if plot.valid_column is not None:
            self._shade_invalid_ranges(table, plot.valid_column, x_vals, axis_x, axis_y)

        for s_def, name, pen, points in curves:
            line_series = self._chart_widget.create_line_series(name=name, width=2.0)
            for x, y in points:
                line_series.append(x, y)
            self._chart_widget.add_line_series(line_series, axis_x, y_axes[s_def.axis])
            # Apply custom pen AFTER add_line_series so QChart doesn't overwrite it
            line_series.setPen(pen)

        self._chart_widget.update_theme_style()

    @staticmethod
    def _axis_title(plot: PlotDefinition, table: TableDefinition, side: str) -> str:
        explicit = plot.y_label if side == "left" else plot.y2_label
        if explicit:
            return explicit
        series = next((s for s in plot.series if s.axis == side), None)
        col_def = table.get_column_def(series.y_column) if series is not None else None
        return col_def.header_text(use_display_units=True) if col_def is not None else "Value"

    def _shade_invalid_ranges(
        self,
        table: TableDefinition,
        valid_column: str,
        x_vals: list[Any],
        axis_x: Any,
        axis_y: Any,
    ) -> None:
        """Shade the x ranges whose ``valid_column`` value is false."""
        points = sorted(
            (float(x), bool(valid))
            for x, valid in zip(x_vals, table.get_column(valid_column), strict=True)
            if isinstance(x, (int, float))
        )
        low_x, high_x = axis_x.min(), axis_x.max()
        low_y, high_y = axis_y.min(), axis_y.max()
        shade = QColor(128, 128, 128, 45)
        index = 0
        while index < len(points):
            if points[index][1]:
                index += 1
                continue
            first = index
            while index < len(points) and not points[index][1]:
                index += 1
            last = index - 1
            # The shade reaches halfway to the neighbouring valid points.
            left = (points[first - 1][0] + points[first][0]) * 0.5 if first > 0 else low_x
            right = (points[last][0] + points[last + 1][0]) * 0.5 if index < len(points) else high_x
            upper = QLineSeries()
            upper.append(left, high_y)
            upper.append(right, high_y)
            lower = QLineSeries()
            lower.append(left, low_y)
            lower.append(right, low_y)
            area = self._chart_widget.add_area_series(upper, lower, shade, axis_x, axis_y)
            area.setName("Infeasible")
            for marker in self._chart_widget.chart.legend().markers(area):
                marker.setVisible(False)

    def _reset_view(self) -> None:
        self.reset_view()

    def _export_png(self) -> None:
        self.export_png()

    def _export_csv(self) -> None:
        self.export_csv()

    def _on_selection_changed(self, selection: Any | None) -> None:
        if not isinstance(selection, dict):
            return
        if selection.get("kind") == "analysis_plot":
            res_id = str(selection.get("result_id", ""))
            plot_id = str(selection.get("plot_id", ""))
            result = self._api.get_solver_result(res_id)
            if result and plot_id in result.plots:
                plot = result.plots[plot_id]
                table = result.tables.get(plot.table_id)
                if table:
                    self.load_plot(plot, table, result)
