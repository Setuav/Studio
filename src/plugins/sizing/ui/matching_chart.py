"""Interactive Matching Chart (Constraint Diagram) Widget using StudioChartWidget."""

from __future__ import annotations

from typing import Any

from PySide6.QtCharts import (
    QAreaSeries,
    QLineSeries,
    QScatterSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from plugins.sizing.engine.solver import MatchingChartAnalysis
from setuav_studio.ui.widget import StudioChartWidget


class LegendBadge(QWidget):
    """Small graphic indicator matching the curve or region appearance."""

    def __init__(
        self,
        color: str,
        kind: str = "line",
        line_style: Qt.PenStyle = Qt.PenStyle.SolidLine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 10)
        self._color = color
        self._kind = kind
        self._line_style = line_style
        self._dimmed = False

    def set_dimmed(self, dimmed: bool) -> None:
        self._dimmed = dimmed
        self.update()

    def paintEvent(self, event: Any) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._dimmed:
            p.setOpacity(0.3)

        if self._kind == "area":
            p.setBrush(QBrush(QColor(76, 175, 80, 80)))
            p.setPen(QPen(QColor(76, 175, 80), 1))
            p.drawRect(1, 1, 11, 7)
        elif self._kind == "point":
            p.setBrush(QBrush(QColor("#FFD600")))
            p.setPen(QPen(QColor("#000000"), 1))
            p.drawEllipse(2, 1, 8, 8)
        else:
            pen = QPen(QColor(self._color), 2.2, self._line_style)
            p.setPen(pen)
            p.drawLine(0, 5, 13, 5)


class LegendItem(QWidget):
    """Clickable legend item widget with badge and text label."""

    def __init__(
        self,
        label: str,
        color: str,
        kind: str = "line",
        line_style: Qt.PenStyle = Qt.PenStyle.SolidLine,
        series_list: list[Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._series_list: list[Any] = series_list or []
        self._is_visible = True
        self._default_color = "#888888"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.badge = LegendBadge(color, kind, line_style, self)
        layout.addWidget(self.badge)

        self.text_label = QLabel(label, self)
        self.text_label.setFont(QFont("Inter", 8))
        layout.addWidget(self.text_label)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._series_list:
            self._is_visible = not self._is_visible
            for s in self._series_list:
                s.setVisible(self._is_visible)
            self.badge.set_dimmed(not self._is_visible)
            self._update_text_color()
        super().mousePressEvent(event)

    def set_text(self, text: str) -> None:
        self.text_label.setText(text)

    def set_default_color(self, color_hex: str) -> None:
        self._default_color = color_hex
        self._update_text_color()

    def _update_text_color(self) -> None:
        c = self._default_color if self._is_visible else "#555555"
        self.text_label.setStyleSheet(f"color: {c};")


class TwoRowLegendWidget(QWidget):
    """Compact 2-row legend widget positioned below the matching chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sizing.two_row_legend")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 3, 4, 3)
        main_layout.setSpacing(3)

        self._row1 = QHBoxLayout()
        self._row1.setContentsMargins(0, 0, 0, 0)
        self._row1.setSpacing(14)
        self._row1.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._row2 = QHBoxLayout()
        self._row2.setContentsMargins(0, 0, 0, 0)
        self._row2.setSpacing(14)
        self._row2.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addLayout(self._row1)
        main_layout.addLayout(self._row2)

        self._items: list[LegendItem] = []
        self._dp_item: LegendItem | None = None

    def clear(self) -> None:
        """Clear all legend items."""
        self._items.clear()
        self._dp_item = None
        while self._row1.count():
            item = self._row1.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        while self._row2.count():
            item = self._row2.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

    def set_items(self, item_defs: list[dict[str, Any]]) -> None:
        """Populate items divided evenly across the two rows."""
        self.clear()
        mid = (len(item_defs) + 1) // 2
        for idx, d in enumerate(item_defs):
            item = LegendItem(
                label=d["label"],
                color=d["color"],
                kind=d.get("kind", "line"),
                line_style=d.get("style", Qt.PenStyle.SolidLine),
                series_list=d.get("series", []),
                parent=self,
            )
            self._items.append(item)
            if d.get("kind") == "point":
                self._dp_item = item

            if idx < mid:
                self._row1.addWidget(item)
            else:
                self._row2.addWidget(item)

        self.update_theme()

    def update_design_point(
        self,
        ws: float,
        y_val: float,
        unit_str: str,
        dp_series: Any = None,
    ) -> None:
        """Update label and optional series reference for the design point."""
        if self._dp_item:
            self._dp_item.set_text(f"Design Point ({ws:.1f} N/m², {y_val:.1f} {unit_str})")
            if dp_series is not None:
                self._dp_item._series_list = [dp_series]

    def update_theme(self) -> None:
        """Update text colors matching active application theme tokens."""
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        dim_color = tok.get("text_dim", "#555555" if is_light else "#888888")
        for item in self._items:
            item.set_default_color(dim_color)


class MatchingChartWidget(StudioChartWidget):
    """Theme-aware constraint diagram widget plotting W/S vs P/W and T/W."""

    design_point_changed = Signal(float, float)  # (ws_pa, pw_wn)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Matching Chart (Constraint Analysis)",
            parent=parent,
            legend_visible=False,
        )
        self.setObjectName("sizing.matching_chart_widget")
        self._analysis: MatchingChartAnalysis | None = None
        self._current_design_point: tuple[float, float] | None = None
        self._view_mode: str = "pw"  # 'pw' (Power Loading W/N) or 'tw' (Thrust-to-Weight)
        self._series_refs: list[Any] = []
        self._axis_x: QValueAxis | None = None
        self._axis_y: QValueAxis | None = None
        self._scatter_point: QScatterSeries | None = None

        self._custom_legend = TwoRowLegendWidget(self)
        chart_layout = self.layout()
        if chart_layout is not None:
            chart_layout.addWidget(self._custom_legend)

        # Intercept mouse clicks on view to let users pick design points interactively
        self.view.mousePressEvent = self._on_view_mouse_press  # type: ignore

    def clear_chart(self) -> None:
        """Remove all series and axes from the chart."""
        for s in list(self.chart.series()):
            self.chart.removeSeries(s)
        for ax in list(self.chart.axes()):
            self.chart.removeAxis(ax)
        self._series_refs.clear()
        self._scatter_point = None
        self._custom_legend.clear()

    def set_view_mode(self, mode: str) -> None:
        """Set vertical axis mode ('pw' for Power Loading, 'tw' for Thrust-to-Weight)."""
        if mode in ("pw", "tw") and mode != self._view_mode:
            self._view_mode = mode
            if self._analysis:
                self.plot_analysis(self._analysis, self._current_design_point)

    def plot_analysis(
        self,
        analysis: MatchingChartAnalysis,
        selected_design_point: tuple[float, float] | None = None,
    ) -> None:
        """Render all constraint curves, vertical limits, feasible envelope, and design point."""
        self._analysis = analysis
        self._current_design_point = selected_design_point or analysis.optimum_design_point

        self.clear_chart()

        # 1. Setup X Axis (Wing Loading W/S)
        ws_max_plot = float(max(analysis.ws_grid_pa[-1], analysis.ws_max_stall_pa * 1.15))
        self._axis_x = self.create_axis("Wing Loading W/S (N/m²)", show_grid=True)
        self._axis_x.setRange(0.0, ws_max_plot)
        self.chart.addAxis(self._axis_x, Qt.AlignmentFlag.AlignBottom)

        # 2. Setup Y Axis
        if self._view_mode == "tw":
            y_title = "Thrust-to-Weight Ratio T/W (-)"
            max_y_val = 1.6
        else:
            y_title = "Power Loading P/W (W/N)"
            max_y_val = float(max(analysis.combined_min_pw_wn.max() * 1.35, 25.0))

        self._axis_y = self.create_axis(y_title, show_grid=True)
        self._axis_y.setRange(0.0, max_y_val)
        self.chart.addAxis(self._axis_y, Qt.AlignmentFlag.AlignLeft)

        legend_items: list[dict[str, Any]] = []

        # 3. Add Feasible Design Space Shading (if viewing P/W)
        area = self._add_feasible_area(analysis, ws_max_plot, max_y_val)
        if area is not None:
            legend_items.append({
                "label": "Feasible Region",
                "color": "#4CAF50",
                "kind": "area",
                "series": [area],
            })

        # 4. Add Continuous Constraint Curves
        for curve in analysis.curves:
            if curve.is_vertical:
                continue

            y_data = curve.tw if self._view_mode == "tw" else curve.pw
            series = QLineSeries()
            series.setName(curve.label)

            pen = QPen(QColor(curve.color), 2.2)
            if curve.line_style == "dash":
                pen.setStyle(Qt.PenStyle.DashLine)
            series.setPen(pen)

            for x_val, y_val in zip(curve.ws_pa, y_data, strict=False):
                if not (0.0 <= y_val <= max_y_val * 1.5):
                    continue
                series.append(float(x_val), float(y_val))

            self.chart.addSeries(series)
            series.attachAxis(self._axis_x)
            series.attachAxis(self._axis_y)
            self._series_refs.append(series)

            style = Qt.PenStyle.DashLine if curve.line_style == "dash" else Qt.PenStyle.SolidLine
            legend_items.append({
                "label": curve.label,
                "color": curve.color,
                "kind": "line",
                "style": style,
                "series": [series],
            })

        # 5. Add Vertical Cutoff Lines (Stall & Landing Limits)
        stall_series = self._add_vertical_cutoff(
            "Stall Limit", analysis.ws_max_stall_pa, max_y_val, "#D81B60"
        )
        legend_items.append({
            "label": "Stall Limit",
            "color": "#D81B60",
            "kind": "line",
            "style": Qt.PenStyle.DashDotLine,
            "series": [stall_series],
        })

        landing_series = self._add_vertical_cutoff(
            "Landing Limit", analysis.ws_max_landing_pa, max_y_val, "#00897B"
        )
        legend_items.append({
            "label": "Landing Limit",
            "color": "#00897B",
            "kind": "line",
            "style": Qt.PenStyle.DashDotLine,
            "series": [landing_series],
        })

        # 6. Add Design Point Marker
        dp_series = self._update_design_point_marker()
        ws_des, pw_des = self._current_design_point or (0.0, 0.0)
        y_val = pw_des if self._view_mode == "pw" else pw_des / 20.0
        unit_str = "W/N" if self._view_mode == "pw" else "T/W"
        legend_items.append({
            "label": f"Design Point ({ws_des:.1f} N/m², {y_val:.1f} {unit_str})",
            "color": "#FFD600",
            "kind": "point",
            "series": [dp_series] if dp_series else [],
        })

        self._custom_legend.set_items(legend_items)
        self.update_theme_style()

    def update_theme_style(self) -> None:
        """Update chart styling and custom legend text colors."""
        super().update_theme_style()
        if hasattr(self, "_custom_legend"):
            self._custom_legend.update_theme()

    def _add_feasible_area(
        self,
        analysis: MatchingChartAnalysis,
        ws_max_plot: float,
        max_y_val: float,
    ) -> QAreaSeries | None:
        """Add translucent green area series shading the feasible design domain."""
        limit_ws = min(analysis.ws_max_stall_pa, analysis.ws_max_landing_pa)
        mask = analysis.ws_grid_pa <= limit_ws

        if not any(mask):
            return None

        ws_sub = analysis.ws_grid_pa[mask]
        combined_y = (
            analysis.combined_min_pw_wn[mask]
            if self._view_mode == "pw"
            else analysis.combined_min_pw_wn[mask] / 15.0  # Approx scaling for tw
        )

        upper_line = QLineSeries()
        lower_line = QLineSeries()

        for x_val, y_val in zip(ws_sub, combined_y, strict=False):
            lower_line.append(float(x_val), float(y_val))
            upper_line.append(float(x_val), float(max_y_val))

        # Close up to vertical cutoff
        lower_line.append(float(limit_ws), float(combined_y[-1]))
        upper_line.append(float(limit_ws), float(max_y_val))

        area = QAreaSeries(upper_line, lower_line)
        area.setName("Feasible Region")
        area.setBrush(QBrush(QColor(76, 175, 80, 45)))  # Soft green
        area.setPen(QPen(QColor(76, 175, 80, 120), 1, Qt.PenStyle.DashLine))

        self.chart.addSeries(area)
        if self._axis_x and self._axis_y:
            area.attachAxis(self._axis_x)
            area.attachAxis(self._axis_y)
        self._series_refs.extend([upper_line, lower_line, area])
        return area

    def _add_vertical_cutoff(
        self,
        label: str,
        ws_val: float,
        max_y: float,
        color_hex: str,
    ) -> QLineSeries:
        """Add vertical boundary line representing maximum allowable wing loading."""
        series = QLineSeries()
        series.setName(label)
        pen = QPen(QColor(color_hex), 2.0, Qt.PenStyle.DashDotLine)
        series.setPen(pen)

        series.append(float(ws_val), 0.0)
        series.append(float(ws_val), float(max_y))

        self.chart.addSeries(series)
        if self._axis_x and self._axis_y:
            series.attachAxis(self._axis_x)
            series.attachAxis(self._axis_y)
        self._series_refs.append(series)
        return series

    def _update_design_point_marker(self) -> QScatterSeries | None:
        """Add or reposition the design point scatter marker."""
        if not self._current_design_point or not self._axis_x or not self._axis_y:
            return None

        ws_des, pw_des = self._current_design_point
        y_val = pw_des if self._view_mode == "pw" else pw_des / 20.0

        if self._scatter_point is not None:
            self.chart.removeSeries(self._scatter_point)

        scatter = QScatterSeries()
        unit_str = "W/N" if self._view_mode == "pw" else "T/W"
        scatter.setName(f"Design Point ({ws_des:.1f} N/m², {y_val:.1f} {unit_str})")
        scatter.setMarkerShape(QScatterSeries.MarkerShape.MarkerShapeCircle)
        scatter.setMarkerSize(13.0)
        scatter.setColor(QColor("#FFD600"))  # Bright Gold
        scatter.setBorderColor(QColor("#000000"))

        scatter.append(float(ws_des), float(y_val))

        self.chart.addSeries(scatter)
        scatter.attachAxis(self._axis_x)
        scatter.attachAxis(self._axis_y)
        self._scatter_point = scatter

        self._custom_legend.update_design_point(ws_des, y_val, unit_str, scatter)
        return scatter

    def _on_view_mouse_press(self, event: QMouseEvent) -> None:
        """Handle user clicking on chart to pick custom design wing loading & power loading."""
        if event.button() == Qt.MouseButton.LeftButton and self._axis_x and self._axis_y:
            pos = event.position()
            val = self.chart.mapToValue(pos)
            x_val = float(val.x())
            y_val = float(val.y())

            if self._axis_x.min() <= x_val <= self._axis_x.max() and 0.0 <= y_val <= self._axis_y.max():
                x_val = max(x_val, 10.0)
                pw_val = y_val if self._view_mode == "pw" else y_val * 20.0
                pw_val = max(pw_val, 1.0)
                self._current_design_point = (x_val, pw_val)
                self._update_design_point_marker()
                self.design_point_changed.emit(x_val, pw_val)

        # Call base handler
        super(type(self.view), self.view).mousePressEvent(event)


class SizingChartDock(QWidget):
    """Dock wrapper enclosing MatchingChartWidget with top control bar for Y-axis toggle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sizing.chart_dock_widget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header bar with mode selector
        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(4, 2, 4, 2)
        h_layout.setSpacing(8)

        lbl = QLabel("Vertical Axis Mode:")
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Power Loading P/W (W/N)", "pw")
        self.combo_mode.addItem("Thrust-to-Weight T/W (-)", "tw")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        h_layout.addWidget(lbl)
        h_layout.addWidget(self.combo_mode)
        h_layout.addStretch(1)

        layout.addWidget(header)

        # Chart widget
        self.chart_widget = MatchingChartWidget(self)
        layout.addWidget(self.chart_widget)

    def _on_mode_changed(self, index: int) -> None:
        mode = self.combo_mode.itemData(index)
        if isinstance(mode, str):
            self.chart_widget.set_view_mode(mode)


__all__ = [
    "LegendBadge",
    "LegendItem",
    "MatchingChartWidget",
    "SizingChartDock",
    "TwoRowLegendWidget",
]
