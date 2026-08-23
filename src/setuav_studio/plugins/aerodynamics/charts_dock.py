"""Unified Aerodynamic Performance Charts Dock hosting all 4 curves simultaneously."""
from __future__ import annotations

from typing import Sequence
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
from .engine.base import AeroResult


class SingleChartWidget(QWidget):
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
        self.chart.legend().setVisible(False)
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

        for axis in list(self.chart.axes()):
            if isinstance(axis, QValueAxis):
                axis.setTitleBrush(dim_col)
                axis.setLabelsBrush(dim_col)
                axis.setGridLineColor(grid_col)
                axis.setMinorGridLineColor(grid_col)
                axis.setLinePenColor(dim_col)

        for series in self.chart.series():
            role = series.property("themeColorRole")
            if isinstance(role, str) and role:
                pen = series.pen()
                pen.setColor(QColor(chart_color(role)))
                series.setPen(pen)

    def clear(self) -> None:
        self.chart.removeAllSeries()
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)

    def series(self) -> list:
        return self.chart.series()

    def axes(self) -> list:
        return self.chart.axes()

    def _create_axis(self, title: str = "") -> QValueAxis:
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        dim_col = QColor(tok.get("text_dim", "#555555" if is_light else "#888888"))
        grid_col = QColor(tok.get("grid", "#e2e4e8" if is_light else "#2d2d35"))

        axis = QValueAxis()
        if title:
            axis.setTitleText(title)
            axis.setTitleBrush(dim_col)
            axis.setTitleFont(QFont("Inter", 8))
        axis.setLabelsBrush(dim_col)
        axis.setLabelsFont(QFont("Inter", 8))
        axis.setGridLineColor(grid_col)
        axis.setMinorGridLineColor(grid_col)
        axis.setLinePenColor(dim_col)
        return axis

    def plot_single(
        self,
        x_vals: Sequence[float],
        y_vals: Sequence[float],
        name: str,
        color_role: str,
        x_title: str = "",
        y_title: str = "",
    ) -> None:
        self.clear()
        if not x_vals or not y_vals:
            return

        self.update_theme_style()

        series = QLineSeries()
        series.setName(name)
        series.setProperty("themeColorRole", color_role)
        from setuav_studio.ui.theme import chart_color

        pen = QPen(QColor(chart_color(color_role)), 2.5)
        series.setPen(pen)

        for x, y in zip(x_vals, y_vals):
            series.append(QPointF(x, y))

        self.chart.addSeries(series)

        axis_x = self._create_axis(x_title)
        pad_x = max((max(x_vals) - min(x_vals)) * 0.05, 0.5)
        axis_x.setRange(min(x_vals) - pad_x, max(x_vals) + pad_x)

        axis_y = self._create_axis(y_title)
        pad_y = max((max(y_vals) - min(y_vals)) * 0.05, 0.05)
        axis_y.setRange(min(y_vals) - pad_y, max(y_vals) + pad_y)

        self.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

    def plot_multi(
        self,
        curves: list[tuple[Sequence[float], Sequence[float], str, str]],
        x_title: str = "",
        y_title: str = "",
    ) -> None:
        self.clear()
        if not curves:
            return

        self.update_theme_style()

        axis_x = self._create_axis(x_title)
        axis_y = self._create_axis(y_title)

        self.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        all_x: list[float] = []
        all_y: list[float] = []

        from setuav_studio.ui.theme import chart_color

        for x_vals, y_vals, name, color_role in curves:
            if not x_vals or not y_vals:
                continue
            series = QLineSeries()
            series.setName(name)
            series.setProperty("themeColorRole", color_role)

            pen = QPen(QColor(chart_color(color_role)), 2.2)
            series.setPen(pen)

            for x, y in zip(x_vals, y_vals):
                series.append(QPointF(x, y))

            self.chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)
            all_x.extend(x_vals)
            all_y.extend(y_vals)

        if len(curves) > 1:
            self.chart.legend().setVisible(True)
            self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
            self.chart.legend().setFont(QFont("Inter", 7.5))
        else:
            self.chart.legend().setVisible(False)

        if all_x:
            pad_x = max((max(all_x) - min(all_x)) * 0.05, 0.005)
            axis_x.setRange(min(all_x) - pad_x, max(all_x) + pad_x)

        if all_y:
            pad_y = max((max(all_y) - min(all_y)) * 0.05, 0.05)
            axis_y.setRange(min(all_y) - pad_y, max(all_y) + pad_y)


class AeroChartsDock(QWidget):
    """Unified dock hosting all 4 aerodynamic charts in a 2x2 grid with persistent resizable splitters."""

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.charts_widget")
        self._api = api

        if self._api is not None:
            self._api.subscribe("aerodynamics.analysis_completed", self.plot_results)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(2)

        # 4 Sub-charts with descriptive compact headers
        self.chart_lift = SingleChartWidget("Lift Curve (CL vs α)", self)
        self.chart_polar = SingleChartWidget("Drag Polar (CL vs CD)", self)
        self.chart_moment = SingleChartWidget("Pitching Moment (Cm vs α)", self)
        self.chart_ld = SingleChartWidget("Aerodynamic Efficiency (L/D vs α)", self)

        # Main Vertical Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(4)

        # Top Row Horizontal Splitter (Lift | Polar)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.setHandleWidth(4)
        self.top_splitter.addWidget(self.chart_lift)
        self.top_splitter.addWidget(self.chart_polar)

        # Bottom Row Horizontal Splitter (Moment | Efficiency)
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.bottom_splitter.setChildrenCollapsible(False)
        self.bottom_splitter.setHandleWidth(4)
        self.bottom_splitter.addWidget(self.chart_moment)
        self.bottom_splitter.addWidget(self.chart_ld)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)

        self.main_splitter.splitterMoved.connect(self._save_splitter_state)
        self.top_splitter.splitterMoved.connect(self._save_splitter_state)
        self.bottom_splitter.splitterMoved.connect(self._save_splitter_state)

        main_layout.addWidget(self.main_splitter)
        self._restore_splitter_state()

    def _save_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        settings.setValue("aero_charts/main_splitter", self.main_splitter.saveState())
        settings.setValue("aero_charts/top_splitter", self.top_splitter.saveState())
        settings.setValue("aero_charts/bottom_splitter", self.bottom_splitter.saveState())

    def _restore_splitter_state(self) -> None:
        settings = QSettings("Setware", "SetuavStudio")
        ms = settings.value("aero_charts/main_splitter")
        if ms:
            self.main_splitter.restoreState(ms)
        ts = settings.value("aero_charts/top_splitter")
        if ts:
            self.top_splitter.restoreState(ts)
        bs = settings.value("aero_charts/bottom_splitter")
        if bs:
            self.bottom_splitter.restoreState(bs)

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
        cd_inds = [p.cd_induced for p in points]
        cd_profs = [p.cd_profile for p in points]
        cms = [p.cm for p in points]
        lds = [p.cl_over_cd for p in points]

        solvers = result.solver_results

        # 1. Lift Curves (Unified, VLM, Buildup, LLT)
        lift_curves = [(alphas, cls, "Total CL", "blue")]
        if "vlm" in solvers:
            v_pts = solvers["vlm"]
            lift_curves.append(([p.alpha for p in v_pts], [p.cl for p in v_pts], "VLM (Inviscid)", "cyan"))
        if "aero_buildup" in solvers:
            ab_pts = solvers["aero_buildup"]
            lift_curves.append(([p.alpha for p in ab_pts], [p.cl for p in ab_pts], "Buildup (Viscous)", "orange"))
        if "lifting_line" in solvers:
            ll_pts = solvers["lifting_line"]
            lift_curves.append(([p.alpha for p in ll_pts], [p.cl for p in ll_pts], "LiftingLine", "purple"))

        self.chart_lift.plot_multi(
            curves=lift_curves,
            x_title="α (°)",
            y_title="CL",
        )

        # 2. Drag Polar (Total Drag, Induced Drag CDi, Profile Drag CDp)
        polar_curves = [(cds, cls, "Total CD", "green")]
        if any(abs(cdi) > 1e-6 for cdi in cd_inds):
            polar_curves.append((cd_inds, cls, "Induced CDi", "blue"))
        if any(abs(cdp) > 1e-6 for cdp in cd_profs):
            polar_curves.append((cd_profs, cls, "Profile CDp", "orange"))

        self.chart_polar.plot_multi(
            curves=polar_curves,
            x_title="CD",
            y_title="CL",
        )

        # 3. Moment Curves
        moment_curves = [(alphas, cms, "Total Cm", "orange")]
        if "vlm" in solvers:
            v_pts = solvers["vlm"]
            moment_curves.append(([p.alpha for p in v_pts], [p.cm for p in v_pts], "VLM Cm", "cyan"))
        if "aero_buildup" in solvers:
            ab_pts = solvers["aero_buildup"]
            moment_curves.append(([p.alpha for p in ab_pts], [p.cm for p in ab_pts], "Buildup Cm", "magenta"))

        self.chart_moment.plot_multi(
            curves=moment_curves,
            x_title="α (°)",
            y_title="Cm",
        )

        # 4. L/D Curves
        ld_curves = [(alphas, lds, "Total L/D", "magenta")]
        if "vlm" in solvers:
            v_pts = solvers["vlm"]
            ld_curves.append(([p.alpha for p in v_pts], [p.cl_over_cd for p in v_pts], "VLM L/D", "cyan"))
        if "aero_buildup" in solvers:
            ab_pts = solvers["aero_buildup"]
            ld_curves.append(([p.alpha for p in ab_pts], [p.cl_over_cd for p in ab_pts], "Buildup L/D", "orange"))

        self.chart_ld.plot_multi(
            curves=ld_curves,
            x_title="α (°)",
            y_title="L/D",
        )

    def update_theme_style(self) -> None:
        self.chart_lift.update_theme_style()
        self.chart_polar.update_theme_style()
        self.chart_moment.update_theme_style()
        self.chart_ld.update_theme_style()
