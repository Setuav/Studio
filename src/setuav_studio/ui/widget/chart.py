"""Unified, theme-aware QtCharts widget and multi-chart grid layout."""

from __future__ import annotations

from typing import Any

from PySide6.QtCharts import (
    QAreaSeries,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QSplitter,
    QVBoxLayout,
    QWidget,
)


class StudioChartWidget(QWidget):
    """Themed QtCharts sub-chart widget with automatic palette management and axis helpers."""

    def __init__(
        self,
        title: str = "",
        parent: QWidget | None = None,
        legend_visible: bool = True,
        legend_alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignTop,
        animated: bool = False,
    ) -> None:
        super().__init__(parent)
        self._overlay_refs: list[Any] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.chart = QChart()
        if title:
            self.chart.setTitle(title)
        self.chart.setTitleFont(QFont("Inter", 9, QFont.Weight.Bold))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.legend().setVisible(legend_visible)
        self.chart.legend().setAlignment(legend_alignment)
        self.chart.legend().setFont(QFont("Inter", 8))
        if not animated:
            self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.setMargins(QChart.margins(self.chart))

        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.view)

        self.update_theme_style()

    def setTitle(self, title: str) -> None:
        """Set the chart title."""
        self.chart.setTitle(title)

    def update_theme_style(self) -> None:
        """Synchronize colors and pens with current application theme tokens."""
        from setuav_studio.ui.theme import chart_color, is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        text_col = QColor(tok.get("text", "#1e1e1e" if is_light else "#e0e0e0"))
        dim_col = QColor(tok.get("text_dim", "#666666" if is_light else "#888888"))
        bg_col = QColor(tok.get("surface", "#ffffff" if is_light else "#1e1e1e"))
        plot_bg_col = QColor(tok.get("plot", "#ffffff" if is_light else "#141414"))
        grid_col = QColor(tok.get("grid", "#e0e0e0" if is_light else "#333333"))
        border_col = QColor(tok.get("border", "#dddddd" if is_light else "#282828"))

        self.chart.setTitleBrush(text_col)
        self.chart.setBackgroundBrush(bg_col)
        self.chart.setBackgroundPen(QPen(border_col))
        self.chart.setPlotAreaBackgroundBrush(plot_bg_col)
        self.chart.setDropShadowEnabled(False)

        legend = self.chart.legend()
        legend.setLabelBrush(dim_col)
        if hasattr(legend, "setLabelColor"):
            legend.setLabelColor(text_col)

        for axis in list(self.chart.axes()):
            if isinstance(axis, QValueAxis):
                axis.setTitleBrush(dim_col)
                axis.setLabelsBrush(dim_col)
                if axis.isGridLineVisible():
                    axis.setGridLineColor(grid_col)
                axis.setMinorGridLineColor(grid_col)
                axis.setLinePenColor(dim_col)

        for series in self.chart.series():
            if isinstance(series, QLineSeries):
                role = series.property("themeColorRole")
                if isinstance(role, str) and role:
                    pen = series.pen()
                    pen.setColor(QColor(chart_color(role)))
                    series.setPen(pen)

    def get_theme_colors(self) -> tuple[QColor, QColor]:
        """Return (grid_color, dim_text_color) based on current theme."""
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        dim_col = QColor(tok.get("text_dim", "#555555" if is_light else "#888888"))
        grid_col = QColor(tok.get("grid", "#e2e4e8" if is_light else "#2d2d35"))
        return grid_col, dim_col

    def create_axis(
        self,
        title: str = "",
        show_grid: bool = True,
        font_size: int = 8,
    ) -> QValueAxis:
        """Create and return a styled QValueAxis."""
        grid_col, dim_col = self.get_theme_colors()

        axis = QValueAxis()
        if title:
            axis.setTitleText(title)
            axis.setTitleBrush(dim_col)
            axis.setTitleFont(QFont("Inter", font_size))
        axis.setLabelsBrush(dim_col)
        axis.setLabelsFont(QFont("Inter", font_size))
        axis.setGridLineColor(grid_col)
        axis.setGridLineVisible(show_grid)
        axis.setLinePenColor(dim_col)
        return axis

    def create_line_series(
        self,
        name: str = "",
        color_role: str = "",
        width: float = 2.0,
        style: Qt.PenStyle = Qt.PenStyle.SolidLine,
    ) -> QLineSeries:
        """Create and return a styled QLineSeries with optional themeColorRole."""
        from setuav_studio.ui.theme import chart_color

        series = QLineSeries()
        if name:
            series.setName(name)
        if color_role:
            series.setProperty("themeColorRole", color_role)
            col = QColor(chart_color(color_role))
        else:
            col = QColor("#2196F3")

        pen = QPen(col, width, style)
        series.setPen(pen)
        return series

    def add_line_series(
        self,
        series: QLineSeries,
        axis_x: QValueAxis,
        axis_y: QValueAxis,
    ) -> None:
        """Attach a line series to the chart and associate it with axes."""
        self.chart.addSeries(series)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

    def add_area_series(
        self,
        upper_series: QLineSeries,
        lower_series: QLineSeries | None,
        color: QColor,
        axis_x: QValueAxis,
        axis_y: QValueAxis,
    ) -> QAreaSeries:
        """Create, style, and attach a QAreaSeries to the chart."""
        area = QAreaSeries(upper_series, lower_series)
        area.setBrush(QBrush(color))
        area.setPen(QPen(Qt.PenStyle.NoPen))
        self._overlay_refs.extend([upper_series, lower_series, area])
        self.chart.addSeries(area)
        area.attachAxis(axis_x)
        area.attachAxis(axis_y)
        return area

    def clear(self) -> None:
        """Remove all series and axes from the chart."""
        self._overlay_refs.clear()
        self.chart.removeAllSeries()
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)

    def series(self) -> list:
        """Return all series currently on the chart."""
        return self.chart.series()

    def axes(self) -> list:
        """Return all axes currently on the chart."""
        return self.chart.axes()


class StudioSplitterGrid(QWidget):
    """Reusable 2x2 grid layout of widgets using nested QSplitters."""

    def __init__(
        self,
        top_left: QWidget,
        top_right: QWidget,
        bottom_left: QWidget,
        bottom_right: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.top_splitter.addWidget(top_left)
        self.top_splitter.addWidget(top_right)
        self.top_splitter.setChildrenCollapsible(False)

        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.bottom_splitter.addWidget(bottom_left)
        self.bottom_splitter.addWidget(bottom_right)
        self.bottom_splitter.setChildrenCollapsible(False)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)
        self.main_splitter.setChildrenCollapsible(False)

        layout.addWidget(self.main_splitter)

    def save_state(self, settings_key: str) -> None:
        """Persist splitter states to QSettings."""
        s = QSettings()
        s.setValue(f"{settings_key}/main", self.main_splitter.saveState())
        s.setValue(f"{settings_key}/top", self.top_splitter.saveState())
        s.setValue(f"{settings_key}/bottom", self.bottom_splitter.saveState())

    def restore_state(self, settings_key: str) -> None:
        """Restore splitter states from QSettings."""
        s = QSettings()
        main_st = s.value(f"{settings_key}/main")
        if main_st:
            self.main_splitter.restoreState(main_st)
        top_st = s.value(f"{settings_key}/top")
        if top_st:
            self.top_splitter.restoreState(top_st)
        bot_st = s.value(f"{settings_key}/bottom")
        if bot_st:
            self.bottom_splitter.restoreState(bot_st)


__all__ = [
    "StudioChartWidget",
    "StudioSplitterGrid",
]
