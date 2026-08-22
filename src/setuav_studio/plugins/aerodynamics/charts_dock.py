"""Unified Aerodynamic Performance Charts Dock hosting all 4 curves simultaneously."""
from __future__ import annotations

from typing import Sequence
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCharts import (
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.theme import tokens
from .engine.base import AeroResult


class SingleChartWidget(QWidget):
    """Sub-chart widget providing themed QtCharts plotting capabilities."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.chart = QChart()
        self.chart.setTitle(title)
        self.chart.setTitleFont(QFont("Inter", 9, QFont.Weight.Bold))
        self.chart.setTitleBrush(QColor("#e0e0e0"))
        self.chart.setBackgroundBrush(QColor(self._tokens.get("surface", "#1e1e1e")))
        self.chart.setPlotAreaBackgroundBrush(QColor(self._tokens.get("plot", "#121212")))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.legend().setVisible(False)
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.setMargins(QChart.margins(self.chart))

        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setStyleSheet(
            f"background-color: {self._tokens.get('surface', '#1e1e1e')}; border: none;"
        )
        layout.addWidget(self.view)

    def clear(self) -> None:
        self.chart.removeAllSeries()
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)

    def series(self) -> list:
        return self.chart.series()

    def axes(self) -> list:
        return self.chart.axes()

    def plot_single(
        self,
        x_vals: Sequence[float],
        y_vals: Sequence[float],
        name: str,
        color: str,
        x_title: str = "",
        y_title: str = "",
    ) -> None:
        self.clear()
        if not x_vals or not y_vals:
            return

        series = QLineSeries()
        series.setName(name)
        pen = QPen(QColor(color), 2.5)
        series.setPen(pen)

        for x, y in zip(x_vals, y_vals):
            series.append(QPointF(x, y))

        self.chart.addSeries(series)

        axis_x = QValueAxis()
        if x_title:
            axis_x.setTitleText(x_title)
            axis_x.setTitleBrush(QColor("#888888"))
            axis_x.setTitleFont(QFont("Inter", 8))
        axis_x.setLabelsBrush(QColor("#888888"))
        axis_x.setLabelsFont(QFont("Inter", 8))
        axis_x.setGridLineColor(QColor("#2d2d35"))
        pad_x = max((max(x_vals) - min(x_vals)) * 0.05, 0.5)
        axis_x.setRange(min(x_vals) - pad_x, max(x_vals) + pad_x)

        axis_y = QValueAxis()
        if y_title:
            axis_y.setTitleText(y_title)
            axis_y.setTitleBrush(QColor("#888888"))
            axis_y.setTitleFont(QFont("Inter", 8))
        axis_y.setLabelsBrush(QColor("#888888"))
        axis_y.setLabelsFont(QFont("Inter", 8))
        axis_y.setGridLineColor(QColor("#2d2d35"))
        pad_y = max((max(y_vals) - min(y_vals)) * 0.05, 0.05)
        axis_y.setRange(min(y_vals) - pad_y, max(y_vals) + pad_y)

        self.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

    def plot_multi(
        self,
        x_vals: Sequence[float],
        curves: list[tuple[Sequence[float], str, str]],
        x_title: str = "",
        y_title: str = "",
    ) -> None:
        self.clear()
        if not x_vals or not curves:
            return

        axis_x = QValueAxis()
        if x_title:
            axis_x.setTitleText(x_title)
            axis_x.setTitleBrush(QColor("#888888"))
            axis_x.setTitleFont(QFont("Inter", 8))
        axis_x.setLabelsBrush(QColor("#888888"))
        axis_x.setLabelsFont(QFont("Inter", 8))
        axis_x.setGridLineColor(QColor("#2d2d35"))

        axis_y = QValueAxis()
        if y_title:
            axis_y.setTitleText(y_title)
            axis_y.setTitleBrush(QColor("#888888"))
            axis_y.setTitleFont(QFont("Inter", 8))
        axis_y.setLabelsBrush(QColor("#888888"))
        axis_y.setLabelsFont(QFont("Inter", 8))
        axis_y.setGridLineColor(QColor("#2d2d35"))

        self.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        all_y: list[float] = []

        for y_vals, name, color in curves:
            series = QLineSeries()
            series.setName(name)
            pen = QPen(QColor(color), 2.5)
            series.setPen(pen)

            for x, y in zip(x_vals, y_vals):
                series.append(QPointF(x, y))

            self.chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)
            all_y.extend(y_vals)

        pad_x = max((max(x_vals) - min(x_vals)) * 0.05, 0.005)
        axis_x.setRange(max(0.0, min(x_vals) - pad_x), max(x_vals) + pad_x)

        if all_y:
            pad_y = max((max(all_y) - min(all_y)) * 0.05, 0.05)
            axis_y.setRange(min(all_y) - pad_y, max(all_y) + pad_y)


class AeroChartsDock(QWidget):
    """Unified dock hosting all 4 aerodynamic charts in a 2x2 grid."""

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.charts_widget")
        self._api = api

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(2)

        # 4 Sub-charts with descriptive compact headers
        self.chart_lift = SingleChartWidget("Lift Curve (CL vs α)")
        self.chart_polar = SingleChartWidget("Drag Polar (CL vs CD)")
        self.chart_moment = SingleChartWidget("Pitching Moment (Cm vs α)")
        self.chart_ld = SingleChartWidget("Aerodynamic Efficiency (L/D vs α)")

        # Main Vertical Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self)

        # Top Row Horizontal Splitter (Lift | Polar)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.top_splitter.addWidget(self.chart_lift)
        self.top_splitter.addWidget(self.chart_polar)

        # Bottom Row Horizontal Splitter (Moment | Efficiency)
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.bottom_splitter.addWidget(self.chart_moment)
        self.bottom_splitter.addWidget(self.chart_ld)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)

        main_layout.addWidget(self.main_splitter)

    def clear_charts(self) -> None:
        self.chart_lift.clear()
        self.chart_polar.clear()
        self.chart_moment.clear()
        self.chart_ld.clear()

    def plot_results(self, result: AeroResult) -> None:
        points = result.polar_points
        if not points:
            self.clear_charts()
            return

        alphas = [p.alpha for p in points]
        cls = [p.cl for p in points]
        cds = [p.cd for p in points]
        cms = [p.cm for p in points]
        lds = [p.cl_over_cd for p in points]

        # 1. Lift Curve
        self.chart_lift.plot_single(
            x_vals=alphas,
            y_vals=cls,
            name="CL",
            color="#4da6ff",
            x_title="α (°)",
            y_title="CL",
        )

        # 2. Drag Polar
        self.chart_polar.plot_multi(
            x_vals=cds,
            curves=[
                (cls, "CL", "#00e676"),
            ],
            x_title="CD",
            y_title="CL",
        )

        # 3. Moment Curve
        self.chart_moment.plot_single(
            x_vals=alphas,
            y_vals=cms,
            name="Cm",
            color="#ff9100",
            x_title="α (°)",
            y_title="Cm",
        )

        # 4. L/D Curve
        self.chart_ld.plot_single(
            x_vals=alphas,
            y_vals=lds,
            name="L/D",
            color="#e040fb",
            x_title="α (°)",
            y_title="L/D",
        )


