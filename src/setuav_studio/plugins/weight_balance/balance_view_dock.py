"""Interactive centre-of-gravity projections for the Weight-Balance plugin."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

from setuav_studio.plugin_system import StudioAPI

from .models import WeightBalanceResult


class _ProjectionCanvas(QWidget):
    """Paint one labelled, scaled projection of the body-frame CG points."""

    _COMPONENT_COLOR = QColor("#4c9aff")
    _TOTAL_COLOR = QColor("#ff5c5c")

    def __init__(
        self,
        *,
        x_axis: int,
        y_axis: int,
        x_label: str,
        y_label: str,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._x_axis = x_axis
        self._y_axis = y_axis
        self._x_label = x_label
        self._y_label = y_label
        self._title = title
        self.result: WeightBalanceResult | None = None
        self.setMinimumSize(280, 190)
        self.setToolTip(
            f"{title} projection in the body frame. Coordinates are shown in mm."
        )

    def set_result(self, result: WeightBalanceResult) -> None:
        self.result = result
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())

        if self.result is None or not self.result.components:
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Run Weight-Balance to display CG",
            )
            return

        points_mm = [
            (
                item.cg_body_m[self._x_axis] * 1000.0,
                item.cg_body_m[self._y_axis] * 1000.0,
            )
            for item in self.result.components
        ]
        total = self.result.total.cg_body_m
        total_mm = (
            total[self._x_axis] * 1000.0,
            total[self._y_axis] * 1000.0,
        )

        plot = QRectF(58.0, 40.0, self.width() - 78.0, self.height() - 84.0)
        if plot.width() <= 40.0 or plot.height() <= 40.0:
            return

        xs = [point[0] for point in points_mm] + [total_mm[0], 0.0]
        ys = [point[1] for point in points_mm] + [total_mm[1], 0.0]
        min_x, max_x = self._bounds(min(xs), max(xs))
        min_y, max_y = self._bounds(min(ys), max(ys))

        self._draw_title_and_legend(painter)
        self._draw_grid(painter, plot, min_x, max_x, min_y, max_y)

        def map_point(point: tuple[float, float]) -> QPointF:
            px = plot.left() + (point[0] - min_x) / (max_x - min_x) * plot.width()
            py = plot.bottom() - (point[1] - min_y) / (max_y - min_y) * plot.height()
            return QPointF(px, py)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._COMPONENT_COLOR)
        for point in points_mm:
            painter.drawEllipse(map_point(point), 4.0, 4.0)

        cg = map_point(total_mm)
        painter.setPen(QPen(self._TOTAL_COLOR, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(cg.x() - 9.0, cg.y()), QPointF(cg.x() + 9.0, cg.y()))
        painter.drawLine(QPointF(cg.x(), cg.y() - 9.0), QPointF(cg.x(), cg.y() + 9.0))
        painter.drawEllipse(cg, 6.0, 6.0)

    @staticmethod
    def _bounds(minimum: float, maximum: float) -> tuple[float, float]:
        span = max(maximum - minimum, 1.0)
        padding = max(span * 0.12, 1.0)
        return minimum - padding, maximum + padding

    def _draw_title_and_legend(self, painter: QPainter) -> None:
        painter.setPen(self.palette().text().color())
        title_font = painter.font()
        title_font.setBold(True)
        painter.setFont(title_font)
        title_text = f"{self._title} projection"
        painter.drawText(QPointF(58.0, 17.0), title_text)

        normal_font = painter.font()
        normal_font.setBold(False)
        painter.setFont(normal_font)
        metrics = QFontMetrics(normal_font)
        component_text = "Components"
        total_text = "Aircraft CG"
        legend_width = (
            7.0
            + metrics.horizontalAdvance(component_text)
            + 18.0
            + 12.0
            + metrics.horizontalAdvance(total_text)
        )
        legend_x = max(58.0, self.width() - legend_width - 8.0)
        legend_y = 14.0
        # On a narrow dock, keep the legend on a second header line instead
        # of letting it collide with the projection title.
        if legend_x < 58.0 + metrics.horizontalAdvance(title_text) + 12.0:
            legend_x = 58.0
            legend_y = 34.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._COMPONENT_COLOR)
        painter.drawEllipse(QPointF(legend_x, legend_y), 3.5, 3.5)
        painter.setPen(self.palette().text().color())
        painter.drawText(QPointF(legend_x + 9.0, legend_y + 4.0), component_text)
        legend_x += 9.0 + metrics.horizontalAdvance(component_text) + 14.0
        painter.setPen(QPen(self._TOTAL_COLOR, 1.6))
        painter.drawLine(
            QPointF(legend_x - 4.0, legend_y),
            QPointF(legend_x + 4.0, legend_y),
        )
        painter.drawLine(
            QPointF(legend_x, legend_y - 4.0),
            QPointF(legend_x, legend_y + 4.0),
        )
        painter.setPen(self.palette().text().color())
        painter.drawText(QPointF(legend_x + 9.0, legend_y + 4.0), total_text)

    def _draw_grid(
        self,
        painter: QPainter,
        plot: QRectF,
        min_x: float,
        max_x: float,
        min_y: float,
        max_y: float,
    ) -> None:
        mid = self.palette().mid().color()
        grid = QColor(mid)
        grid.setAlpha(105)
        painter.setPen(QPen(grid, 1.0))

        metrics = QFontMetrics(painter.font())
        for index in range(5):
            ratio = index / 4.0
            value_x = min_x + (max_x - min_x) * ratio
            value_y = min_y + (max_y - min_y) * ratio
            x = plot.left() + plot.width() * ratio
            y = plot.bottom() - plot.height() * ratio
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

            painter.setPen(self.palette().text().color())
            painter.drawText(
                QRectF(x - 34.0, plot.bottom() + 5.0, 68.0, 16.0),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._format_axis(value_x),
            )
            painter.drawText(
                QRectF(0.0, y - metrics.height() / 2.0, 53.0, metrics.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._format_axis(value_y),
            )
            painter.setPen(QPen(grid, 1.0))

        border = self.palette().mid().color()
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(plot)

        # Draw the body-frame origin when it falls inside the current scale.
        if min_x <= 0.0 <= max_x:
            x = plot.left() + (-min_x) / (max_x - min_x) * plot.width()
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        if min_y <= 0.0 <= max_y:
            y = plot.bottom() - (-min_y) / (max_y - min_y) * plot.height()
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        painter.setPen(self.palette().text().color())
        painter.drawText(
            QRectF(plot.left(), self.height() - 24.0, plot.width(), 18.0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            f"{self._x_label} (mm)",
        )
        painter.drawText(
            QRectF(4.0, plot.top() - 20.0, 50.0, 18.0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._y_label} (mm)",
        )

    @staticmethod
    def _format_axis(value: float) -> str:
        if abs(value) >= 100.0:
            return f"{value:.0f}"
        if abs(value) >= 10.0:
            return f"{value:.1f}"
        return f"{value:.2f}"


class WeightBalanceViewDock(QMainWindow):
    """Container with two persistent, rearrangeable CG projection docks.

    The two inner docks intentionally are not registered as shell panels. This
    keeps them out of the global View menu while still allowing users to dock,
    float, resize, tabify, or stack them inside the CG View panel.
    """

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("weight_balance.view_widget")
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )

        self.top_canvas = _ProjectionCanvas(
            x_axis=0,
            y_axis=1,
            x_label="X",
            y_label="Y",
            title="Top (X / Y)",
            parent=self,
        )
        self.side_canvas = _ProjectionCanvas(
            x_axis=0,
            y_axis=2,
            x_label="X",
            y_label="Z",
            title="Side (X / Z)",
            parent=self,
        )
        # Compatibility alias for integrations that used the original canvas.
        self.canvas = self.top_canvas

        self.top_dock = self._projection_dock(
            "Top View · X / Y",
            "weight_balance.cg_top_dock",
            self.top_canvas,
        )
        self.side_dock = self._projection_dock(
            "Side View · X / Z",
            "weight_balance.cg_side_dock",
            self.side_canvas,
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.top_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.side_dock)
        self.resizeDocks(
            [self.top_dock, self.side_dock],
            [1, 1],
            Qt.Orientation.Horizontal,
        )

        api.subscribe("weight_balance.analysis_completed", self._set_result)

    @staticmethod
    def _projection_dock(title: str, object_name: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title)
        dock.setObjectName(object_name)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        dock.setMinimumSize(300, 210)
        dock.setWidget(widget)
        return dock

    def _set_result(self, result: WeightBalanceResult) -> None:
        self.top_canvas.set_result(result)
        self.side_canvas.set_result(result)
