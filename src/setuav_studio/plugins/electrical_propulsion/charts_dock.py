"""Unified Propulsion Performance Charts Dock hosting all curves simultaneously."""
from __future__ import annotations

from typing import Any, Sequence
from PySide6.QtCore import QPointF, QSettings, Qt
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


class SinglePropulsionChartWidget(QWidget):
    """Sub-chart widget providing themed QtCharts plotting capabilities."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.chart = QChart()
        self.chart.setTitle(title)
        self.chart.setTitleFont(QFont("Inter", 9, QFont.Weight.Bold))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chart.legend().setFont(QFont("Inter", 8))
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.setMargins(QChart.margins(self.chart))

        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.view)

        self.update_theme_style()

    def update_theme_style(self) -> None:
        from setuav_studio.ui.theme import chart_color, current_theme_mode, tokens

        tok = tokens()
        is_light = current_theme_mode() == "light"
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
        self.chart.legend().setLabelBrush(dim_col)

        for axis in list(self.chart.axes()):
            if isinstance(axis, QValueAxis):
                axis.setTitleBrush(dim_col)
                axis.setLabelsBrush(dim_col)
                if axis.isGridLineVisible():
                    axis.setGridLineColor(grid_col)
                axis.setMinorGridLineColor(grid_col)
                axis.setLinePenColor(dim_col)

        for series in self.chart.series():
            role = series.property("themeColorRole")
            if isinstance(role, str) and role:
                pen = series.pen()
                pen.setColor(QColor(chart_color(role)))
                series.setPen(pen)

    def _get_theme_colors(self) -> tuple[QColor, QColor]:
        from setuav_studio.ui.theme import current_theme_mode, tokens

        tok = tokens()
        is_light = current_theme_mode() == "light"
        dim_col = QColor(tok.get("text_dim", "#555555" if is_light else "#888888"))
        grid_col = QColor(tok.get("grid", "#e2e4e8" if is_light else "#2d2d35"))
        return grid_col, dim_col

    def clear(self) -> None:
        self.chart.removeAllSeries()
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)

    def series(self) -> list:
        return self.chart.series()

    def axes(self) -> list:
        return self.chart.axes()


class ThrustPowerChartDock(SinglePropulsionChartWidget):
    """Dock widget for Thrust & Electrical Power."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Thrust & Electrical Power", parent)
        self.setObjectName("propulsion.chart_thrust_widget")

    def plot_data(self, x_label: str, x_values: Sequence[float], thrust_n: Sequence[float], power_w: Sequence[float]) -> None:
        self.clear()
        if not x_values:
            return
        self.update_theme_style()
        x_min, x_max = min(x_values), max(x_values)
        if x_min == x_max:
            x_max += 1.0

        grid_color, text_muted = self._get_theme_colors()

        series_thrust = QLineSeries()
        series_thrust.setName("Thrust (N)")
        series_thrust.setProperty("themeColorRole", "blue")
        from setuav_studio.ui.theme import chart_color

        series_thrust.setPen(QPen(QColor(chart_color("blue")), 2.5))

        series_power = QLineSeries()
        series_power.setName("Power (W)")
        series_power.setProperty("themeColorRole", "orange")
        series_power.setPen(QPen(QColor(chart_color("orange")), 2.5))

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
        axis_x1.setMinorGridLineColor(grid_color)
        axis_x1.setLinePenColor(text_muted)
        axis_x1.setRange(x_min, x_max)

        axis_y_thrust = QValueAxis()
        axis_y_thrust.setTitleText("Thrust (N)")
        axis_y_thrust.setTitleBrush(text_muted)
        axis_y_thrust.setTitleFont(QFont("Inter", 8))
        axis_y_thrust.setLabelsBrush(text_muted)
        axis_y_thrust.setLabelsFont(QFont("Inter", 8))
        axis_y_thrust.setGridLineColor(grid_color)
        axis_y_thrust.setMinorGridLineColor(grid_color)
        axis_y_thrust.setLinePenColor(text_muted)
        t_max = max(thrust_n) * 1.1 if thrust_n else 10.0
        axis_y_thrust.setRange(0, max(t_max, 1.0))

        axis_y_power = QValueAxis()
        axis_y_power.setTitleText("Power (W)")
        axis_y_power.setTitleBrush(text_muted)
        axis_y_power.setTitleFont(QFont("Inter", 8))
        axis_y_power.setLabelsBrush(text_muted)
        axis_y_power.setLabelsFont(QFont("Inter", 8))
        axis_y_power.setGridLineVisible(False)
        axis_y_power.setLinePenColor(text_muted)
        p_max = max(power_w) * 1.1 if power_w else 100.0
        axis_y_power.setRange(0, max(p_max, 10.0))

        self.chart.addAxis(axis_x1, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y_thrust, Qt.AlignmentFlag.AlignLeft)
        self.chart.addAxis(axis_y_power, Qt.AlignmentFlag.AlignRight)

        self.chart.addSeries(series_thrust)
        self.chart.addSeries(series_power)

        series_thrust.attachAxis(axis_x1)
        series_thrust.attachAxis(axis_y_thrust)
        series_power.attachAxis(axis_x1)
        series_power.attachAxis(axis_y_power)


class ElectricalChartDock(SinglePropulsionChartWidget):
    """Dock widget for Current & Motor Speed."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Current & Motor Speed", parent)
        self.setObjectName("propulsion.chart_electrical_widget")

    def plot_data(self, x_label: str, x_values: Sequence[float], current_a: Sequence[float], rpm: Sequence[float]) -> None:
        self.clear()
        if not x_values:
            return
        self.update_theme_style()
        x_min, x_max = min(x_values), max(x_values)
        if x_min == x_max:
            x_max += 1.0

        grid_color, text_muted = self._get_theme_colors()

        series_current = QLineSeries()
        series_current.setName("Current (A)")
        series_current.setProperty("themeColorRole", "red")
        from setuav_studio.ui.theme import chart_color

        series_current.setPen(QPen(QColor(chart_color("red")), 2.5))

        series_rpm = QLineSeries()
        series_rpm.setName("RPM")
        series_rpm.setProperty("themeColorRole", "green")
        series_rpm.setPen(QPen(QColor(chart_color("green")), 2.5))

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
        axis_x2.setMinorGridLineColor(grid_color)
        axis_x2.setLinePenColor(text_muted)
        axis_x2.setRange(x_min, x_max)

        axis_y_curr = QValueAxis()
        axis_y_curr.setTitleText("Current (A)")
        axis_y_curr.setTitleBrush(text_muted)
        axis_y_curr.setTitleFont(QFont("Inter", 8))
        axis_y_curr.setLabelsBrush(text_muted)
        axis_y_curr.setLabelsFont(QFont("Inter", 8))
        axis_y_curr.setGridLineColor(grid_color)
        axis_y_curr.setMinorGridLineColor(grid_color)
        axis_y_curr.setLinePenColor(text_muted)
        c_max = max(current_a) * 1.15 if current_a else 20.0
        axis_y_curr.setRange(0, max(c_max, 5.0))

        axis_y_rpm = QValueAxis()
        axis_y_rpm.setTitleText("Speed (RPM)")
        axis_y_rpm.setTitleBrush(text_muted)
        axis_y_rpm.setTitleFont(QFont("Inter", 8))
        axis_y_rpm.setLabelsBrush(text_muted)
        axis_y_rpm.setLabelsFont(QFont("Inter", 8))
        axis_y_rpm.setGridLineVisible(False)
        axis_y_rpm.setLinePenColor(text_muted)
        r_max = max(rpm) * 1.1 if rpm else 10000.0
        axis_y_rpm.setRange(0, max(r_max, 1000.0))

        self.chart.addAxis(axis_x2, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y_curr, Qt.AlignmentFlag.AlignLeft)
        self.chart.addAxis(axis_y_rpm, Qt.AlignmentFlag.AlignRight)

        self.chart.addSeries(series_current)
        self.chart.addSeries(series_rpm)

        series_current.attachAxis(axis_x2)
        series_current.attachAxis(axis_y_curr)
        series_rpm.attachAxis(axis_x2)
        series_rpm.attachAxis(axis_y_rpm)


class EfficiencyChartDock(SinglePropulsionChartWidget):
    """Dock widget for Efficiency Breakdown."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Efficiency Breakdown (η)", parent)
        self.setObjectName("propulsion.chart_efficiency_widget")

    def plot_data(self, x_label: str, x_values: Sequence[float], eta_total: Sequence[float], eta_prop: Sequence[float], eta_motor: Sequence[float]) -> None:
        self.clear()
        if not x_values:
            return
        self.update_theme_style()
        x_min, x_max = min(x_values), max(x_values)
        if x_min == x_max:
            x_max += 1.0

        grid_color, text_muted = self._get_theme_colors()

        series_eta_tot = QLineSeries()
        series_eta_tot.setName("Total η")
        series_eta_tot.setProperty("themeColorRole", "green")
        from setuav_studio.ui.theme import chart_color

        series_eta_tot.setPen(QPen(QColor(chart_color("green")), 2.5))

        series_eta_prop = QLineSeries()
        series_eta_prop.setName("Prop ηp")
        series_eta_prop.setProperty("themeColorRole", "blue")
        series_eta_prop.setPen(QPen(QColor(chart_color("blue")), 2.0, Qt.PenStyle.DashLine))

        series_eta_mot = QLineSeries()
        series_eta_mot.setName("Motor ηm")
        series_eta_mot.setProperty("themeColorRole", "magenta")
        series_eta_mot.setPen(QPen(QColor(chart_color("magenta")), 2.0, Qt.PenStyle.DashLine))

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
        axis_x3.setMinorGridLineColor(grid_color)
        axis_x3.setLinePenColor(text_muted)
        axis_x3.setRange(x_min, x_max)

        axis_y_eta = QValueAxis()
        axis_y_eta.setTitleText("Efficiency (%)")
        axis_y_eta.setTitleBrush(text_muted)
        axis_y_eta.setTitleFont(QFont("Inter", 8))
        axis_y_eta.setLabelsBrush(text_muted)
        axis_y_eta.setLabelsFont(QFont("Inter", 8))
        axis_y_eta.setGridLineColor(grid_color)
        axis_y_eta.setMinorGridLineColor(grid_color)
        axis_y_eta.setLinePenColor(text_muted)
        axis_y_eta.setRange(0, 100.0)

        self.chart.addAxis(axis_x3, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y_eta, Qt.AlignmentFlag.AlignLeft)

        self.chart.addSeries(series_eta_tot)
        self.chart.addSeries(series_eta_prop)
        self.chart.addSeries(series_eta_mot)

        series_eta_tot.attachAxis(axis_x3)
        series_eta_tot.attachAxis(axis_y_eta)
        series_eta_prop.attachAxis(axis_x3)
        series_eta_prop.attachAxis(axis_y_eta)
        series_eta_mot.attachAxis(axis_x3)
        series_eta_mot.attachAxis(axis_y_eta)


class PowerLoadingChartDock(SinglePropulsionChartWidget):
    """Dock widget for Power Loading (g/W)."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Power Loading — g/W", parent)
        self.setObjectName("propulsion.chart_power_loading_widget")
        self.chart.legend().setVisible(False)

    def plot_data(self, x_label: str, x_values: Sequence[float], thrust_n: Sequence[float], power_w: Sequence[float]) -> None:
        self.clear()
        if not x_values:
            return
        self.update_theme_style()
        x_min, x_max = min(x_values), max(x_values)
        if x_min == x_max:
            x_max += 1.0

        grid_color, text_muted = self._get_theme_colors()

        series_pl = QLineSeries()
        series_pl.setName("g/W")
        series_pl.setProperty("themeColorRole", "orange")
        from setuav_studio.ui.theme import chart_color

        series_pl.setPen(QPen(QColor(chart_color("orange")), 2.5))

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
        axis_x4.setMinorGridLineColor(grid_color)
        axis_x4.setLinePenColor(text_muted)
        axis_x4.setRange(x_min, x_max)

        axis_y_pl = QValueAxis()
        axis_y_pl.setTitleText("Power Loading (g/W)")
        axis_y_pl.setTitleBrush(text_muted)
        axis_y_pl.setTitleFont(QFont("Inter", 8))
        axis_y_pl.setLabelsBrush(text_muted)
        axis_y_pl.setLabelsFont(QFont("Inter", 8))
        axis_y_pl.setGridLineColor(grid_color)
        axis_y_pl.setMinorGridLineColor(grid_color)
        axis_y_pl.setLinePenColor(text_muted)
        pl_max = max(pl_values) * 1.1 if pl_values else 10.0
        axis_y_pl.setRange(0, max(pl_max, 2.0))

        self.chart.addAxis(axis_x4, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y_pl, Qt.AlignmentFlag.AlignLeft)

        self.chart.addSeries(series_pl)
        series_pl.attachAxis(axis_x4)
        series_pl.attachAxis(axis_y_pl)


class PropulsionChartsDock(QWidget):
    """Unified dock hosting all 4 propulsion performance curves simultaneously in a 2x2 grid with persistent splitters."""

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("propulsion.charts_widget")
        self._api = api

        if self._api is not None:
            self._api.subscribe("propulsion.plot_sweep", self._on_plot_sweep)
            self._api.subscribe("propulsion.clear_charts", lambda _p=None: self.clear_charts())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(2)

        # 4 Sub-charts
        self.chart_thrust_power = ThrustPowerChartDock(self)
        self.chart_electrical = ElectricalChartDock(self)
        self.chart_efficiency = EfficiencyChartDock(self)
        self.chart_power_loading = PowerLoadingChartDock(self)

        # Main Vertical Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(4)

        # Top Row Horizontal Splitter (Thrust/Power | Current/RPM)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.setHandleWidth(4)
        self.top_splitter.addWidget(self.chart_thrust_power)
        self.top_splitter.addWidget(self.chart_electrical)

        # Bottom Row Horizontal Splitter (Efficiencies | Power Loading)
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.bottom_splitter.setChildrenCollapsible(False)
        self.bottom_splitter.setHandleWidth(4)
        self.bottom_splitter.addWidget(self.chart_efficiency)
        self.bottom_splitter.addWidget(self.chart_power_loading)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)

        self.main_splitter.splitterMoved.connect(self._save_splitter_state)
        self.top_splitter.splitterMoved.connect(self._save_splitter_state)
        self.bottom_splitter.splitterMoved.connect(self._save_splitter_state)

        main_layout.addWidget(self.main_splitter)
        self.clear_charts()
        self._restore_splitter_state()

    def _save_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        settings.setValue("propulsion_charts/main_splitter", self.main_splitter.saveState())
        settings.setValue("propulsion_charts/top_splitter", self.top_splitter.saveState())
        settings.setValue("propulsion_charts/bottom_splitter", self.bottom_splitter.saveState())

    def _restore_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        ms = settings.value("propulsion_charts/main_splitter")
        if ms:
            self.main_splitter.restoreState(ms)
        ts = settings.value("propulsion_charts/top_splitter")
        if ts:
            self.top_splitter.restoreState(ts)
        bs = settings.value("propulsion_charts/bottom_splitter")
        if bs:
            self.bottom_splitter.restoreState(bs)

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
        self.chart_thrust_power.plot_data(x_label, x_values, thrust_n, power_w)
        self.chart_electrical.plot_data(x_label, x_values, current_a, rpm)
        self.chart_efficiency.plot_data(x_label, x_values, eta_total, eta_prop, eta_motor)
        self.chart_power_loading.plot_data(x_label, x_values, thrust_n, power_w)

    def _on_plot_sweep(self, payload: dict[str, Any]) -> None:
        if not payload:
            return
        if payload.get("clear_charts", False):
            self.clear_charts()
        self.plot_sweep_results(
            x_label=payload["x_label"],
            x_values=payload["x_values"],
            thrust_n=payload["thrust_n"],
            power_w=payload["power_w"],
            current_a=payload["current_a"],
            rpm=payload["rpm"],
            eta_total=payload["eta_total"],
            eta_prop=payload["eta_prop"],
            eta_motor=payload["eta_motor"],
        )

    def update_theme_style(self) -> None:
        self.chart_thrust_power.update_theme_style()
        self.chart_electrical.update_theme_style()
        self.chart_efficiency.update_theme_style()
        self.chart_power_loading.update_theme_style()
