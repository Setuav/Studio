"""Flight Performance Envelope Charts Dock hosting 4 performance curves in a 2x2 grid with infeasible region shading."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCharts import (
    QAreaSeries,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from setuav_studio_sdk import StudioAPI

from .engine.models import FlightEnvelopeResult


class SinglePerformanceChartWidget(QWidget):
    """Sub-chart widget providing themed QtCharts plotting capabilities with dual-axis & infeasible region shading."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._overlay_refs: list[Any] = []

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
            if isinstance(series, QLineSeries):
                role = series.property("themeColorRole")
                if isinstance(role, str) and role:
                    pen = series.pen()
                    pen.setColor(QColor(chart_color(role)))
                    series.setPen(pen)

    def _get_theme_colors(self) -> tuple[QColor, QColor]:
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        dim_col = QColor(tok.get("text_dim", "#555555" if is_light else "#888888"))
        grid_col = QColor(tok.get("grid", "#e2e4e8" if is_light else "#2d2d35"))
        return grid_col, dim_col

    def clear(self) -> None:
        self._overlay_refs.clear()
        self.chart.removeAllSeries()
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)

    def series(self) -> list:
        return self.chart.series()

    def axes(self) -> list:
        return self.chart.axes()

    def _create_axis(
        self,
        title: str,
        dim_col: QColor,
        grid_col: QColor,
        show_grid: bool = True,
    ) -> QValueAxis:
        axis = QValueAxis()
        axis.setTitleText(title)
        axis.setTitleBrush(dim_col)
        axis.setTitleFont(QFont("Inter", 8))
        axis.setLabelsBrush(dim_col)
        axis.setLabelsFont(QFont("Inter", 8))
        axis.setGridLineVisible(show_grid)
        axis.setGridLineColor(grid_col)
        axis.setMinorGridLineColor(grid_col)
        axis.setLinePenColor(dim_col)
        return axis

    def plot_dual_curves(
        self,
        x_vals: Sequence[float],
        y1_vals: Sequence[float],
        y1_label: str,
        y1_unit: str,
        y1_color_role: str,
        y2_vals: Sequence[float] | None = None,
        y2_label: str = "",
        y2_unit: str = "",
        y2_color_role: str = "",
        x_label: str = "Airspeed (m/s)",
        feasible_mask: Sequence[bool] | None = None,
        same_axis: bool = False,
    ) -> None:
        self.clear()
        if not x_vals or not y1_vals:
            return

        grid_color, dim_color = self._get_theme_colors()
        axis_x = self._x_axis(x_vals, x_label, dim_color, grid_color)
        y1_min, y1_max = self._combined_primary_bounds(
            y1_vals,
            y2_vals,
            same_axis,
        )
        axis_y1, y1_bounds = self._primary_axis(
            y1_min,
            y1_max,
            y1_label,
            y1_unit,
            same_axis,
            dim_color,
            grid_color,
        )
        self._add_infeasible_overlays(
            x_vals,
            feasible_mask,
            axis_x,
            axis_y1,
            y1_bounds,
        )
        self._add_line_series(
            x_vals,
            y1_vals,
            y1_label,
            y1_color_role,
            2.2,
            axis_x,
            axis_y1,
        )
        if y2_vals and any(value is not None for value in y2_vals):
            self._add_secondary_series(
                x_vals,
                y2_vals,
                y2_label,
                y2_unit,
                y2_color_role,
                same_axis,
                axis_x,
                axis_y1,
                dim_color,
                grid_color,
            )
        self._hide_area_legend_markers()

    def _x_axis(
        self,
        values: Sequence[float],
        label: str,
        dim_color: QColor,
        grid_color: QColor,
    ) -> QValueAxis:
        minimum, maximum = float(min(values)), float(max(values))
        if minimum == maximum:
            maximum += 1.0
        axis = self._create_axis(label, dim_color, grid_color, show_grid=True)
        axis.setRange(minimum, maximum)
        self.chart.addAxis(axis, Qt.AlignmentFlag.AlignBottom)
        return axis

    @staticmethod
    def _combined_primary_bounds(
        primary: Sequence[float],
        secondary: Sequence[float] | None,
        same_axis: bool,
    ) -> tuple[float, float]:
        minimum, maximum = SinglePerformanceChartWidget._value_bounds(primary)
        if same_axis and secondary:
            second_minimum, second_maximum = SinglePerformanceChartWidget._value_bounds(secondary)
            minimum = min(minimum, second_minimum)
            maximum = max(maximum, second_maximum)
        return minimum, maximum

    @staticmethod
    def _value_bounds(values: Sequence[float]) -> tuple[float, float]:
        valid = [value for value in values if value is not None]
        minimum = float(min(valid)) if valid else 0.0
        maximum = float(max(valid)) if valid else 1.0
        if minimum == maximum:
            maximum += 1.0
        return minimum, maximum

    def _primary_axis(
        self,
        minimum: float,
        maximum: float,
        label: str,
        unit: str,
        same_axis: bool,
        dim_color: QColor,
        grid_color: QColor,
    ) -> tuple[QValueAxis, tuple[float, float]]:
        if unit and not same_axis:
            title = f"{label} ({unit})"
        elif same_axis and unit:
            title = f"Power ({unit})"
        else:
            title = label
        axis = self._create_axis(title, dim_color, grid_color, show_grid=True)
        bounds = self._padded_bounds(minimum, maximum)
        axis.setRange(*bounds)
        self.chart.addAxis(axis, Qt.AlignmentFlag.AlignLeft)
        return axis, bounds

    @staticmethod
    def _padded_bounds(minimum: float, maximum: float) -> tuple[float, float]:
        padding = max((maximum - minimum) * 0.05, 0.05)
        return max(0.0, minimum - padding), maximum + padding

    def _add_infeasible_overlays(
        self,
        x_values: Sequence[float],
        feasible_mask: Sequence[bool] | None,
        axis_x: QValueAxis,
        axis_y: QValueAxis,
        y_bounds: tuple[float, float],
    ) -> None:
        if feasible_mask is None or len(feasible_mask) != len(x_values):
            return
        for start, end in self._infeasible_spans(x_values, feasible_mask):
            upper = QLineSeries()
            upper.append(float(start), float(y_bounds[1]))
            upper.append(float(end), float(y_bounds[1]))
            lower = QLineSeries()
            lower.append(float(start), float(y_bounds[0]))
            lower.append(float(end), float(y_bounds[0]))
            area = QAreaSeries(upper, lower)
            area.setName("Infeasible")
            area.setBrush(QBrush(QColor(235, 55, 55, 38)))
            area.setPen(QPen(QColor(235, 55, 55, 90), 1, Qt.PenStyle.DashLine))
            self.chart.addSeries(area)
            area.attachAxis(axis_x)
            area.attachAxis(axis_y)
            self._overlay_refs.extend([upper, lower, area])

    @staticmethod
    def _infeasible_spans(
        x_values: Sequence[float],
        feasible_mask: Sequence[bool],
    ) -> list[tuple[float, float]]:
        spans: list[tuple[float, float]] = []
        start: float | None = None
        for x_value, feasible in zip(x_values, feasible_mask, strict=True):
            if not feasible and start is None:
                start = float(x_value)
            elif feasible and start is not None:
                spans.append((start, float(x_value)))
                start = None
        if start is not None:
            spans.append((start, float(x_values[-1])))
        return spans

    def _add_line_series(
        self,
        x_values: Sequence[float],
        y_values: Sequence[float],
        label: str,
        color_role: str,
        width: float,
        axis_x: QValueAxis,
        axis_y: QValueAxis,
    ) -> QLineSeries:
        from setuav_studio.ui.theme import chart_color

        series = QLineSeries()
        series.setName(label)
        series.setProperty("themeColorRole", color_role)
        series.setPen(QPen(QColor(chart_color(color_role)), width))
        for x_value, y_value in zip(x_values, y_values, strict=True):
            if y_value is not None:
                series.append(QPointF(float(x_value), float(y_value)))
        self.chart.addSeries(series)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        return series

    def _add_secondary_series(
        self,
        x_values: Sequence[float],
        y_values: Sequence[float],
        label: str,
        unit: str,
        color_role: str,
        same_axis: bool,
        axis_x: QValueAxis,
        axis_y1: QValueAxis,
        dim_color: QColor,
        grid_color: QColor,
    ) -> None:
        if same_axis:
            self._add_line_series(
                x_values,
                y_values,
                label,
                color_role,
                2.0,
                axis_x,
                axis_y1,
            )
            return
        minimum, maximum = self._value_bounds(y_values)
        title = f"{label} ({unit})" if unit else label
        axis_y2 = self._create_axis(title, dim_color, grid_color, show_grid=False)
        axis_y2.setRange(*self._padded_bounds(minimum, maximum))
        self.chart.addAxis(axis_y2, Qt.AlignmentFlag.AlignRight)
        self._add_line_series(
            x_values,
            y_values,
            label,
            color_role,
            2.0,
            axis_x,
            axis_y2,
        )

    def _hide_area_legend_markers(self) -> None:
        for marker in self.chart.legend().markers():
            if isinstance(marker.series(), QAreaSeries):
                marker.setVisible(False)


class PerformanceChartsDock(QWidget):
    """Right-dock widget hosting all 4 flight performance charts in a 2x2 grid."""

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("flight_performance.charts_widget")
        self._api = api

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)

        # 4 Sub-charts
        self.chart_power = SinglePerformanceChartWidget("Power Required vs Available", self)
        self.chart_climb = SinglePerformanceChartWidget(
            "Climb Performance (ROC & Climb Angle)", self
        )
        self.chart_mission = SinglePerformanceChartWidget("Mission Range & Endurance", self)
        self.chart_electrical = SinglePerformanceChartWidget("Electrical Power & Throttle", self)

        # Main Vertical Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(4)

        # Top Row Horizontal Splitter (Power | Climb)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.setHandleWidth(4)
        self.top_splitter.addWidget(self.chart_power)
        self.top_splitter.addWidget(self.chart_climb)

        # Bottom Row Horizontal Splitter (Mission | Electrical)
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.bottom_splitter.setChildrenCollapsible(False)
        self.bottom_splitter.setHandleWidth(4)
        self.bottom_splitter.addWidget(self.chart_mission)
        self.bottom_splitter.addWidget(self.chart_electrical)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)

        self.main_splitter.splitterMoved.connect(self._save_splitter_state)
        self.top_splitter.splitterMoved.connect(self._save_splitter_state)
        self.bottom_splitter.splitterMoved.connect(self._save_splitter_state)

        main_layout.addWidget(self.main_splitter)
        self._restore_splitter_state()

        if self._api:
            self._api.subscribe("flight_performance.analysis_completed", self.set_results)

    def _save_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        settings.setValue("flight_charts/main_splitter", self.main_splitter.saveState())
        settings.setValue("flight_charts/top_splitter", self.top_splitter.saveState())
        settings.setValue("flight_charts/bottom_splitter", self.bottom_splitter.saveState())

    def _restore_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        ms = settings.value("flight_charts/main_splitter")
        ts = settings.value("flight_charts/top_splitter")
        bs = settings.value("flight_charts/bottom_splitter")
        if ms:
            self.main_splitter.restoreState(ms)
        if ts:
            self.top_splitter.restoreState(ts)
        if bs:
            self.bottom_splitter.restoreState(bs)

    def update_theme_style(self) -> None:
        self.chart_power.update_theme_style()
        self.chart_climb.update_theme_style()
        self.chart_mission.update_theme_style()
        self.chart_electrical.update_theme_style()

    def set_results(self, result: FlightEnvelopeResult) -> None:
        """Plot all 4 flight performance curves from the analysis result."""
        if not result or not result.curves or not result.curves.velocities:
            return

        c = result.curves
        v_list = c.velocities
        feas_list = c.feasible
        propulsion_available = result.propulsion_available

        # 1. Chart 1 (Top-Left): Power Required vs Available (Both in Watts -> shared axis)
        self.chart_power.plot_dual_curves(
            x_vals=v_list,
            y1_vals=c.power_required,
            y1_label="Power Required (P_req)",
            y1_unit="W",
            y1_color_role="blue",
            y2_vals=c.power_available if propulsion_available else None,
            y2_label="Power Available (P_avail)",
            y2_unit="W",
            y2_color_role="orange",
            x_label="Airspeed (m/s)",
            feasible_mask=feas_list,
            same_axis=True,
        )

        # 2. Chart 2 (Top-Right): Climb Performance (ROC & Climb Angle)
        self.chart_climb.plot_dual_curves(
            x_vals=v_list,
            y1_vals=c.rate_of_climb if propulsion_available else [],
            y1_label="Rate of Climb (ROC)",
            y1_unit="m/s",
            y1_color_role="green",
            y2_vals=c.climb_angle_deg if propulsion_available else None,
            y2_label="Climb Angle (γ)",
            y2_unit="°",
            y2_color_role="teal",
            x_label="Airspeed (m/s)",
            feasible_mask=feas_list,
            same_axis=False,
        )

        # 3. Chart 3 (Bottom-Left): Mission Range & Endurance
        self.chart_mission.plot_dual_curves(
            x_vals=v_list,
            y1_vals=c.range_km if propulsion_available else [],
            y1_label="Range",
            y1_unit="km",
            y1_color_role="blue",
            y2_vals=c.endurance_hours if propulsion_available else None,
            y2_label="Endurance",
            y2_unit="h",
            y2_color_role="magenta",
            x_label="Airspeed (m/s)",
            feasible_mask=feas_list,
            same_axis=False,
        )

        # 4. Chart 4 (Bottom-Right): Electrical Power & Throttle
        self.chart_electrical.plot_dual_curves(
            x_vals=v_list,
            y1_vals=c.electrical_power if propulsion_available else [],
            y1_label="Electrical Power (P_elec)",
            y1_unit="W",
            y1_color_role="red",
            y2_vals=c.throttle_pct if propulsion_available else None,
            y2_label="Throttle",
            y2_unit="%",
            y2_color_role="orange",
            x_label="Airspeed (m/s)",
            feasible_mask=feas_list,
            same_axis=False,
        )
