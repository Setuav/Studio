"""Unified Propulsion Performance Charts Dock hosting all curves simultaneously."""
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

from setuav_studio.ui.theme import tokens


class SinglePropulsionChartWidget(QWidget):
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
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chart.legend().setLabelBrush(QColor("#aaaaaa"))
        self.chart.legend().setFont(QFont("Inter", 8))
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


class PropulsionChartsDock(QWidget):
    """Unified dock hosting all 4 propulsion performance curves simultaneously in a 2x2 grid."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("propulsion.charts_widget")
        self._tokens = tokens()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(2)

        # 4 Sub-charts
        self.chart_thrust_power = SinglePropulsionChartWidget("Thrust & Electrical Power")
        self.chart_electrical = SinglePropulsionChartWidget("Current & Motor Speed")
        self.chart_efficiency = SinglePropulsionChartWidget("Efficiency Breakdown (η)")
        self.chart_power_loading = SinglePropulsionChartWidget("Power Loading — g/W")
        self.chart_power_loading.chart.legend().setVisible(False)

        # Main Vertical Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self)

        # Top Row Horizontal Splitter (Thrust/Power | Current/RPM)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.top_splitter.addWidget(self.chart_thrust_power)
        self.top_splitter.addWidget(self.chart_electrical)

        # Bottom Row Horizontal Splitter (Efficiencies | Power Loading)
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.bottom_splitter.addWidget(self.chart_efficiency)
        self.bottom_splitter.addWidget(self.chart_power_loading)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)

        main_layout.addWidget(self.main_splitter)
        self.clear_charts()

    def clear_charts(self) -> None:
        self.chart_thrust_power.clear()
        self.chart_electrical.clear()
        self.chart_efficiency.clear()
        self.chart_power_loading.clear()

    def plot_sweep_results(
        self,
        x_label: str,
        x_values: Sequence[float],
        thrust_n: Sequence[float],
        power_w: Sequence[float],
        current_a: Sequence[float],
        rpm: Sequence[float],
        eta_total: Sequence[float],
        eta_prop: Sequence[float],
        eta_motor: Sequence[float],
    ) -> None:
        self.clear_charts()
        if not x_values:
            return

        x_min, x_max = min(x_values), max(x_values)
        if x_min == x_max:
            x_max += 1.0

        grid_color = QColor("#2d2d35")
        text_muted = QColor("#888888")

        # --- 1. Thrust & Power Chart ---
        c1 = self.chart_thrust_power.chart
        series_thrust = QLineSeries()
        series_thrust.setName("Thrust (N)")
        series_thrust.setPen(QPen(QColor("#4da6ff"), 2.5))

        series_power = QLineSeries()
        series_power.setName("Power (W)")
        series_power.setPen(QPen(QColor("#e5c07b"), 2.5))

        for x, t, p in zip(x_values, thrust_n, power_w):
            series_thrust.append(QPointF(x, t))
            series_power.append(QPointF(x, p))

        axis_x1 = QValueAxis()
        axis_x1.setTitleText(x_label)
        axis_x1.setTitleBrush(text_muted)
        axis_x1.setTitleFont(QFont("Inter", 8))
        axis_x1.setLabelsBrush(text_muted)
        axis_x1.setLabelsFont(QFont("Inter", 8))
        axis_x1.setGridLineColor(grid_color)
        axis_x1.setRange(x_min, x_max)

        axis_y_thrust = QValueAxis()
        axis_y_thrust.setTitleText("Thrust (N)")
        axis_y_thrust.setTitleBrush(text_muted)
        axis_y_thrust.setTitleFont(QFont("Inter", 8))
        axis_y_thrust.setLabelsBrush(text_muted)
        axis_y_thrust.setLabelsFont(QFont("Inter", 8))
        axis_y_thrust.setGridLineColor(grid_color)
        t_max = max(thrust_n) * 1.1 if thrust_n else 10.0
        axis_y_thrust.setRange(0, max(t_max, 1.0))

        axis_y_power = QValueAxis()
        axis_y_power.setTitleText("Power (W)")
        axis_y_power.setTitleBrush(text_muted)
        axis_y_power.setTitleFont(QFont("Inter", 8))
        axis_y_power.setLabelsBrush(text_muted)
        axis_y_power.setLabelsFont(QFont("Inter", 8))
        axis_y_power.setGridLineVisible(False)
        p_max = max(power_w) * 1.1 if power_w else 100.0
        axis_y_power.setRange(0, max(p_max, 10.0))

        c1.addAxis(axis_x1, Qt.AlignmentFlag.AlignBottom)
        c1.addAxis(axis_y_thrust, Qt.AlignmentFlag.AlignLeft)
        c1.addAxis(axis_y_power, Qt.AlignmentFlag.AlignRight)

        c1.addSeries(series_thrust)
        c1.addSeries(series_power)

        series_thrust.attachAxis(axis_x1)
        series_thrust.attachAxis(axis_y_thrust)
        series_power.attachAxis(axis_x1)
        series_power.attachAxis(axis_y_power)

        # --- 2. Current & RPM Chart ---
        c2 = self.chart_electrical.chart
        series_current = QLineSeries()
        series_current.setName("Current (A)")
        series_current.setPen(QPen(QColor("#e06c75"), 2.5))

        series_rpm = QLineSeries()
        series_rpm.setName("RPM")
        series_rpm.setPen(QPen(QColor("#98c379"), 2.5))

        for x, i_val, r_val in zip(x_values, current_a, rpm):
            series_current.append(QPointF(x, i_val))
            series_rpm.append(QPointF(x, r_val))

        axis_x2 = QValueAxis()
        axis_x2.setTitleText(x_label)
        axis_x2.setTitleBrush(text_muted)
        axis_x2.setTitleFont(QFont("Inter", 8))
        axis_x2.setLabelsBrush(text_muted)
        axis_x2.setLabelsFont(QFont("Inter", 8))
        axis_x2.setGridLineColor(grid_color)
        axis_x2.setRange(x_min, x_max)

        axis_y_curr = QValueAxis()
        axis_y_curr.setTitleText("Current (A)")
        axis_y_curr.setTitleBrush(text_muted)
        axis_y_curr.setTitleFont(QFont("Inter", 8))
        axis_y_curr.setLabelsBrush(text_muted)
        axis_y_curr.setLabelsFont(QFont("Inter", 8))
        axis_y_curr.setGridLineColor(grid_color)
        c_max = max(current_a) * 1.15 if current_a else 20.0
        axis_y_curr.setRange(0, max(c_max, 5.0))

        axis_y_rpm = QValueAxis()
        axis_y_rpm.setTitleText("Speed (RPM)")
        axis_y_rpm.setTitleBrush(text_muted)
        axis_y_rpm.setTitleFont(QFont("Inter", 8))
        axis_y_rpm.setLabelsBrush(text_muted)
        axis_y_rpm.setLabelsFont(QFont("Inter", 8))
        axis_y_rpm.setGridLineVisible(False)
        r_max = max(rpm) * 1.1 if rpm else 10000.0
        axis_y_rpm.setRange(0, max(r_max, 1000.0))

        c2.addAxis(axis_x2, Qt.AlignmentFlag.AlignBottom)
        c2.addAxis(axis_y_curr, Qt.AlignmentFlag.AlignLeft)
        c2.addAxis(axis_y_rpm, Qt.AlignmentFlag.AlignRight)

        c2.addSeries(series_current)
        c2.addSeries(series_rpm)

        series_current.attachAxis(axis_x2)
        series_current.attachAxis(axis_y_curr)
        series_rpm.attachAxis(axis_x2)
        series_rpm.attachAxis(axis_y_rpm)

        # --- 3. Efficiency Curves Chart ---
        c3 = self.chart_efficiency.chart
        series_eta_tot = QLineSeries()
        series_eta_tot.setName("Total η")
        series_eta_tot.setPen(QPen(QColor("#00e676"), 2.5))

        series_eta_prop = QLineSeries()
        series_eta_prop.setName("Prop ηp")
        series_eta_prop.setPen(QPen(QColor("#4da6ff"), 2.0, Qt.PenStyle.DashLine))

        series_eta_mot = QLineSeries()
        series_eta_mot.setName("Motor ηm")
        series_eta_mot.setPen(QPen(QColor("#e040fb"), 2.0, Qt.PenStyle.DashLine))

        for x, et, ep, em in zip(x_values, eta_total, eta_prop, eta_motor):
            series_eta_tot.append(QPointF(x, et * 100.0))
            series_eta_prop.append(QPointF(x, ep * 100.0))
            series_eta_mot.append(QPointF(x, em * 100.0))

        axis_x3 = QValueAxis()
        axis_x3.setTitleText(x_label)
        axis_x3.setTitleBrush(text_muted)
        axis_x3.setTitleFont(QFont("Inter", 8))
        axis_x3.setLabelsBrush(text_muted)
        axis_x3.setLabelsFont(QFont("Inter", 8))
        axis_x3.setGridLineColor(grid_color)
        axis_x3.setRange(x_min, x_max)

        axis_y_eta = QValueAxis()
        axis_y_eta.setTitleText("Efficiency (%)")
        axis_y_eta.setTitleBrush(text_muted)
        axis_y_eta.setTitleFont(QFont("Inter", 8))
        axis_y_eta.setLabelsBrush(text_muted)
        axis_y_eta.setLabelsFont(QFont("Inter", 8))
        axis_y_eta.setGridLineColor(grid_color)
        axis_y_eta.setRange(0, 100.0)

        c3.addAxis(axis_x3, Qt.AlignmentFlag.AlignBottom)
        c3.addAxis(axis_y_eta, Qt.AlignmentFlag.AlignLeft)

        c3.addSeries(series_eta_tot)
        c3.addSeries(series_eta_prop)
        c3.addSeries(series_eta_mot)

        series_eta_tot.attachAxis(axis_x3)
        series_eta_tot.attachAxis(axis_y_eta)
        series_eta_prop.attachAxis(axis_x3)
        series_eta_prop.attachAxis(axis_y_eta)
        series_eta_mot.attachAxis(axis_x3)
        series_eta_mot.attachAxis(axis_y_eta)

        # --- 4. Power Loading (g/W) Chart ---
        c4 = self.chart_power_loading.chart
        series_pl = QLineSeries()
        series_pl.setName("g/W")
        series_pl.setPen(QPen(QColor("#ff9100"), 2.5))

        pl_values: list[float] = []
        for x, t, p in zip(x_values, thrust_n, power_w):
            val = (t * 1000.0 / 9.80665) / max(p, 0.001)
            series_pl.append(QPointF(x, val))
            pl_values.append(val)

        axis_x4 = QValueAxis()
        axis_x4.setTitleText(x_label)
        axis_x4.setTitleBrush(text_muted)
        axis_x4.setTitleFont(QFont("Inter", 8))
        axis_x4.setLabelsBrush(text_muted)
        axis_x4.setLabelsFont(QFont("Inter", 8))
        axis_x4.setGridLineColor(grid_color)
        axis_x4.setRange(x_min, x_max)

        axis_y_pl = QValueAxis()
        axis_y_pl.setTitleText("Power Loading (g/W)")
        axis_y_pl.setTitleBrush(text_muted)
        axis_y_pl.setTitleFont(QFont("Inter", 8))
        axis_y_pl.setLabelsBrush(text_muted)
        axis_y_pl.setLabelsFont(QFont("Inter", 8))
        axis_y_pl.setGridLineColor(grid_color)
        pl_max = max(pl_values) * 1.1 if pl_values else 10.0
        axis_y_pl.setRange(0, max(pl_max, 2.0))

        c4.addAxis(axis_x4, Qt.AlignmentFlag.AlignBottom)
        c4.addAxis(axis_y_pl, Qt.AlignmentFlag.AlignLeft)

        c4.addSeries(series_pl)
        series_pl.attachAxis(axis_x4)
        series_pl.attachAxis(axis_y_pl)
