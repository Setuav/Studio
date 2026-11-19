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
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
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
        mouse_interaction: bool = False,
    ) -> None:
        super().__init__(parent)
        self._overlay_refs: list[Any] = []
        self._mouse_interaction = mouse_interaction

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
        if self._mouse_interaction:
            self.view.setRubberBand(QChartView.RubberBand.RectangleRubberBand)
        else:
            self.view.setRubberBand(QChartView.RubberBand.NoRubberBand)
        self.view.installEventFilter(self)
        layout.addWidget(self.view)

        self.update_theme_style()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.view:
            if not self._mouse_interaction:
                if event.type() in (
                    QEvent.Type.MouseButtonPress,
                    QEvent.Type.MouseButtonRelease,
                    QEvent.Type.MouseButtonDblClick,
                    QEvent.Type.Wheel,
                ):
                    return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                from PySide6.QtGui import QMouseEvent

                if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.RightButton:
                    self.chart.zoomReset()
                    return True
        return super().eventFilter(watched, event)

    def setTitle(self, title: str) -> None:
        """Set the chart title."""
        self.chart.setTitle(title)

    def update_theme_style(self) -> None:
        """Synchronize colors and pens with current application theme tokens."""
        from setuav_studio.ui.style.theme import chart_color, tokens

        tok = tokens()
        text_col = QColor(tok["text"])
        dim_col = QColor(tok["text_dim"])
        bg_col = QColor(tok["surface"])
        plot_bg_col = QColor(tok["plot"])
        grid_col = QColor(tok["grid"])
        border_col = QColor(tok["border"])

        self.chart.setTitleBrush(text_col)
        self.chart.setBackgroundBrush(bg_col)
        self.chart.setBackgroundPen(QPen(border_col))
        self.chart.setPlotAreaBackgroundBrush(plot_bg_col)
        self.chart.setDropShadowEnabled(False)

        legend = self.chart.legend()
        legend.setLabelBrush(dim_col)
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
        from setuav_studio.ui.style.theme import tokens

        tok = tokens()
        dim_col = QColor(tok["text_dim"])
        grid_col = QColor(tok["grid"])
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
        from setuav_studio.ui.style.theme import chart_color

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


__all__ = [
    "StudioChartWidget",
]
