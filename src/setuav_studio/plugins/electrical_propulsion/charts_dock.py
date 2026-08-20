"""Propulsion Analysis Charts dock widget."""

from __future__ import annotations

from typing import Any, Sequence
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCharts import (
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)

from setuav_studio.icons import get_icon
from setuav_studio.ui.theme import tokens


class PropulsionChartsDock(QWidget):
    """Interactive dark-themed performance curves and sweep visualization dock."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("propulsion.charts_widget")
        self._tokens = tokens()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with tabs and export
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)

        # Tab 1: Thrust & Power
        self.chart_thrust_power = self._create_chart("Thrust & Electrical Power")
        self.view_thrust_power = self._create_chart_view(self.chart_thrust_power)
        self.tabs.addTab(self.view_thrust_power, get_icon("fa6s.bolt"), "Thrust & Power")

        # Tab 2: Electrical (Current & RPM)
        self.chart_electrical = self._create_chart("Current & Motor Speed")
        self.view_electrical = self._create_chart_view(self.chart_electrical)
        self.tabs.addTab(self.view_electrical, get_icon("fa6s.gauge-high"), "Current & RPM")

        # Tab 3: Efficiencies
        self.chart_efficiency = self._create_chart("Efficiency Curves (η)")
        self.view_efficiency = self._create_chart_view(self.chart_efficiency)
        self.tabs.addTab(self.view_efficiency, get_icon("fa6s.chart-line"), "Efficiencies")

        layout.addWidget(self.tabs)

        self._current_data: dict[str, Any] | None = None
        self.clear_charts()

    def _create_chart(self, title: str) -> QChart:
        chart = QChart()
        chart.setTitle(title)
        chart.setTitleFont(QFont("Inter", 11, QFont.Weight.Bold))
        chart.setTitleBrush(QColor("#e0e0e0"))
        chart.setBackgroundBrush(QColor(self._tokens["surface"]))
        chart.setPlotAreaBackgroundBrush(QColor(self._tokens["plot"]))
        chart.setPlotAreaBackgroundVisible(True)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
        chart.legend().setLabelBrush(QColor(self._tokens["text"]))
        chart.legend().setFont(QFont("Inter", 9))
        chart.setMargins(QChart.margins(chart))
        return chart

    def _create_chart_view(self, chart: QChart) -> QChartView:
        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setStyleSheet(f"background-color: {self._tokens['surface']}; border: none;")
        return view

    def clear_charts(self) -> None:
        for chart in (self.chart_thrust_power, self.chart_electrical, self.chart_efficiency):
            chart.removeAllSeries()
            for axis in list(chart.axes()):
                chart.removeAxis(axis)

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

        # --- 1. Thrust & Power Chart ---
        series_thrust = QLineSeries()
        series_thrust.setName("Thrust (N)")
        pen_thrust = QPen(QColor("#4ec9b0"), 2.5)
        series_thrust.setPen(pen_thrust)

        series_power = QLineSeries()
        series_power.setName("Power (W)")
        pen_power = QPen(QColor("#e5c07b"), 2.5)
        series_power.setPen(pen_power)

        for x, t, p in zip(x_values, thrust_n, power_w):
            series_thrust.append(QPointF(x, t))
            series_power.append(QPointF(x, p))

        axis_x1 = QValueAxis()
        axis_x1.setTitleText(x_label)
        axis_x1.setTitleBrush(QColor("#b0b0b0"))
        axis_x1.setLabelsBrush(QColor("#888888"))
        axis_x1.setGridLineColor(QColor(self._tokens["grid"]))
        axis_x1.setRange(x_min, x_max)

        axis_y_thrust = QValueAxis()
        axis_y_thrust.setTitleText("Thrust (N)")
        axis_y_thrust.setTitleBrush(QColor("#4ec9b0"))
        axis_y_thrust.setLabelsBrush(QColor("#4ec9b0"))
        axis_y_thrust.setGridLineColor(QColor(self._tokens["grid"]))
        t_max = max(thrust_n) * 1.1 if thrust_n else 10.0
        axis_y_thrust.setRange(0, max(t_max, 1.0))

        axis_y_power = QValueAxis()
        axis_y_power.setTitleText("Power (W)")
        axis_y_power.setTitleBrush(QColor("#e5c07b"))
        axis_y_power.setLabelsBrush(QColor("#e5c07b"))
        axis_y_power.setGridLineVisible(False)
        p_max = max(power_w) * 1.1 if power_w else 100.0
        axis_y_power.setRange(0, max(p_max, 10.0))

        self.chart_thrust_power.addAxis(axis_x1, Qt.AlignmentFlag.AlignBottom)
        self.chart_thrust_power.addAxis(axis_y_thrust, Qt.AlignmentFlag.AlignLeft)
        self.chart_thrust_power.addAxis(axis_y_power, Qt.AlignmentFlag.AlignRight)

        self.chart_thrust_power.addSeries(series_thrust)
        self.chart_thrust_power.addSeries(series_power)

        series_thrust.attachAxis(axis_x1)
        series_thrust.attachAxis(axis_y_thrust)
        series_power.attachAxis(axis_x1)
        series_power.attachAxis(axis_y_power)

        # --- 2. Current & RPM Chart ---
        series_current = QLineSeries()
        series_current.setName("Current (A)")
        pen_current = QPen(QColor("#e06c75"), 2.5)
        series_current.setPen(pen_current)

        series_rpm = QLineSeries()
        series_rpm.setName("Motor Speed (RPM)")
        pen_rpm = QPen(QColor("#98c379"), 2.5)
        series_rpm.setPen(pen_rpm)

        for x, i_val, r_val in zip(x_values, current_a, rpm):
            series_current.append(QPointF(x, i_val))
            series_rpm.append(QPointF(x, r_val))

        axis_x2 = QValueAxis()
        axis_x2.setTitleText(x_label)
        axis_x2.setTitleBrush(QColor("#b0b0b0"))
        axis_x2.setLabelsBrush(QColor("#888888"))
        axis_x2.setGridLineColor(QColor(self._tokens["grid"]))
        axis_x2.setRange(x_min, x_max)

        axis_y_curr = QValueAxis()
        axis_y_curr.setTitleText("Current (A)")
        axis_y_curr.setTitleBrush(QColor("#e06c75"))
        axis_y_curr.setLabelsBrush(QColor("#e06c75"))
        axis_y_curr.setGridLineColor(QColor(self._tokens["grid"]))
        c_max = max(current_a) * 1.15 if current_a else 20.0
        axis_y_curr.setRange(0, max(c_max, 5.0))

        axis_y_rpm = QValueAxis()
        axis_y_rpm.setTitleText("Speed (RPM)")
        axis_y_rpm.setTitleBrush(QColor("#98c379"))
        axis_y_rpm.setLabelsBrush(QColor("#98c379"))
        axis_y_rpm.setGridLineVisible(False)
        r_max = max(rpm) * 1.1 if rpm else 10000.0
        axis_y_rpm.setRange(0, max(r_max, 1000.0))

        self.chart_electrical.addAxis(axis_x2, Qt.AlignmentFlag.AlignBottom)
        self.chart_electrical.addAxis(axis_y_curr, Qt.AlignmentFlag.AlignLeft)
        self.chart_electrical.addAxis(axis_y_rpm, Qt.AlignmentFlag.AlignRight)

        self.chart_electrical.addSeries(series_current)
        self.chart_electrical.addSeries(series_rpm)

        series_current.attachAxis(axis_x2)
        series_current.attachAxis(axis_y_curr)
        series_rpm.attachAxis(axis_x2)
        series_rpm.attachAxis(axis_y_rpm)

        # --- 3. Efficiency Curves Chart ---
        series_eta_tot = QLineSeries()
        series_eta_tot.setName("Total System η")
        series_eta_tot.setPen(QPen(QColor("#4ec9b0"), 2.5))

        series_eta_prop = QLineSeries()
        series_eta_prop.setName("Propeller ηp")
        series_eta_prop.setPen(QPen(QColor("#61afef"), 2.0, Qt.PenStyle.DashLine))

        series_eta_mot = QLineSeries()
        series_eta_mot.setName("Motor ηm")
        series_eta_mot.setPen(QPen(QColor("#c678dd"), 2.0, Qt.PenStyle.DashLine))

        for x, et, ep, em in zip(x_values, eta_total, eta_prop, eta_motor):
            series_eta_tot.append(QPointF(x, et * 100.0))
            series_eta_prop.append(QPointF(x, ep * 100.0))
            series_eta_mot.append(QPointF(x, em * 100.0))

        axis_x3 = QValueAxis()
        axis_x3.setTitleText(x_label)
        axis_x3.setTitleBrush(QColor("#b0b0b0"))
        axis_x3.setLabelsBrush(QColor("#888888"))
        axis_x3.setGridLineColor(QColor(self._tokens["grid"]))
        axis_x3.setRange(x_min, x_max)

        axis_y_eta = QValueAxis()
        axis_y_eta.setTitleText("Efficiency (%)")
        axis_y_eta.setTitleBrush(QColor("#b0b0b0"))
        axis_y_eta.setLabelsBrush(QColor("#888888"))
        axis_y_eta.setGridLineColor(QColor(self._tokens["grid"]))
        axis_y_eta.setRange(0, 100.0)

        self.chart_efficiency.addAxis(axis_x3, Qt.AlignmentFlag.AlignBottom)
        self.chart_efficiency.addAxis(axis_y_eta, Qt.AlignmentFlag.AlignLeft)

        self.chart_efficiency.addSeries(series_eta_tot)
        self.chart_efficiency.addSeries(series_eta_prop)
        self.chart_efficiency.addSeries(series_eta_mot)

        series_eta_tot.attachAxis(axis_x3)
        series_eta_tot.attachAxis(axis_y_eta)
        series_eta_prop.attachAxis(axis_x3)
        series_eta_prop.attachAxis(axis_y_eta)
        series_eta_mot.attachAxis(axis_x3)
        series_eta_mot.attachAxis(axis_y_eta)
