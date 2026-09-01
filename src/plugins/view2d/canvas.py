"""Theme-aware interactive 2D projection canvas."""

from __future__ import annotations

from itertools import pairwise
from math import hypot
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from setuav_studio.ui.theme import is_light_theme

from .geometry import View2DGeometrySource
from .scene import ColorValue, View2DMarker, View2DPath, View2DScene


class View2DCanvas(QWidget):
    """Render a projection scene and inject shared project geometry.

    Consumers provide only overlays (markers, vectors, annotations). When an
    API object is supplied, this canvas obtains the current renderer-neutral
    geometry through ``StudioAPI.build_geometry_data`` and projects it itself.
    This keeps geometry ownership in the 2D view plugin rather than duplicating
    geometry extraction in every analysis plugin.
    """

    itemHovered = Signal(str)
    itemClicked = Signal(str)

    _GRID_ALPHA = 105

    def __init__(
        self,
        *,
        api: Any | None = None,
        axes: tuple[int, int] = (0, 1),
        title: str = "2D View",
        x_label: str = "X",
        y_label: str = "Y",
        units: str = "mm",
        invert_vertical: bool = False,
        geometry_source: View2DGeometrySource | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._axes = axes
        self._title = title
        self._x_label = x_label
        self._y_label = y_label
        self._units = units
        self._invert_vertical = bool(invert_vertical)
        self._geometry_source = geometry_source or (
            View2DGeometrySource(api) if api is not None else None
        )
        self._overlay_scene: View2DScene | None = None
        self._scene = View2DScene(
            title=title,
            x_label=x_label,
            y_label=y_label,
            units=units,
        )
        self._hovered_id = ""
        self._show_geometry = True
        self._show_labels = False
        self._show_legend = True
        self.setMinimumSize(280, 190)
        self.setMouseTracking(True)

        if api is not None:
            api.on_project_changed(self._on_project_changed)
            api.on_project_content_changed(self._on_project_changed)

    @property
    def scene(self) -> View2DScene:
        return self._scene

    def set_scene(self, scene: View2DScene | None) -> None:
        """Set domain overlays; project geometry is added automatically."""
        self._overlay_scene = scene
        self._rebuild_scene()

    def set_show_geometry(self, visible: bool) -> None:
        self._show_geometry = bool(visible)
        self._rebuild_scene()

    def set_show_labels(self, visible: bool) -> None:
        self._show_labels = bool(visible)
        self.update()

    def set_show_legend(self, visible: bool) -> None:
        """Toggle the in-canvas legend (useful when a dock owns a legend bar)."""
        self._show_legend = bool(visible)
        self.update()

    def refresh_geometry(self) -> None:
        self._rebuild_scene()

    def fit_to_content(self) -> None:
        if self._overlay_scene is not None:
            self._overlay_scene.x_bounds = None
            self._overlay_scene.y_bounds = None
        self._rebuild_scene()

    def _on_project_changed(self, _project: Any) -> None:
        self._rebuild_scene()

    def _rebuild_scene(self) -> None:
        overlay = self._overlay_scene
        if overlay is None:
            self._scene = View2DScene(
                title=self._title,
                x_label=self._x_label,
                y_label=self._y_label,
                units=self._units,
            )
        else:
            self._scene = View2DScene(
                title=overlay.title,
                x_label=overlay.x_label,
                y_label=overlay.y_label,
                units=overlay.units,
                x_bounds=overlay.x_bounds,
                y_bounds=overlay.y_bounds,
                paths=list(overlay.paths),
                markers=list(overlay.markers),
                legend=list(overlay.legend),
            )

        if self._show_geometry and self._geometry_source is not None:
            geometry_data = self._geometry_source.current()
            self._scene.add_geometry(
                geometry_data,
                axes=self._axes,
                color=self._geometry_color(),
                width=self._geometry_style()[0],
                fill_alpha=self._geometry_style()[1],
            )
        self.update()

    def _geometry_color(self) -> ColorValue | None:
        """Return an optional projection-wide geometry colour override."""
        return None

    def _geometry_style(self) -> tuple[float, int]:
        """Return geometry outline width and fill opacity for this canvas."""
        return 1.1, 42

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())

        if not self._scene.paths and not self._scene.markers:
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No 2D view data available",
            )
            return

        bounds = self._bounds()
        if bounds is None:
            return
        plot = self._plot_rect(bounds)
        if plot.width() <= 40.0 or plot.height() <= 40.0:
            return
        min_x, max_x, min_y, max_y = bounds

        self._draw_header(painter)
        self._draw_grid(painter, plot, min_x, max_x, min_y, max_y)

        for path in self._scene.paths:
            self._draw_path(painter, path, plot, bounds)
        for marker in sorted(self._scene.markers, key=self._marker_layer_order):
            self._draw_marker(painter, marker, plot, bounds)

    def _plot_rect(
        self,
        bounds: tuple[float, float, float, float],
    ) -> QRectF:
        """Return a letterboxed plot rectangle with a uniform data scale."""
        container = QRectF(58.0, 28.0, self.width() - 78.0, self.height() - 72.0)
        if container.width() <= 0.0 or container.height() <= 0.0:
            return QRectF()
        min_x, max_x, min_y, max_y = bounds
        data_width = max(max_x - min_x, 1.0)
        data_height = max(max_y - min_y, 1.0)
        scale = min(
            container.width() / data_width,
            container.height() / data_height,
        )
        width = data_width * scale
        height = data_height * scale
        return QRectF(
            container.center().x() - width / 2.0,
            container.center().y() - height / 2.0,
            width,
            height,
        )

    def _bounds(self) -> tuple[float, float, float, float] | None:
        values = [point for path in self._scene.paths for point in path.points] + [
            marker.position for marker in self._scene.markers
        ]
        if not values:
            return None
        xs = [point[0] for point in values] + [0.0]
        ys = [point[1] for point in values] + [0.0]
        min_x, max_x = self._axis_bounds(self._scene.x_bounds, min(xs), max(xs))
        min_y, max_y = self._axis_bounds(self._scene.y_bounds, min(ys), max(ys))
        return min_x, max_x, min_y, max_y

    @staticmethod
    def _axis_bounds(
        override: tuple[float, float] | None,
        minimum: float,
        maximum: float,
    ) -> tuple[float, float]:
        if override is not None and len(override) == 2 and override[1] > override[0]:
            minimum, maximum = float(override[0]), float(override[1])
        span = max(maximum - minimum, 1.0)
        padding = max(span * 0.12, 1.0)
        return minimum - padding, maximum + padding

    def _draw_header(self, painter: QPainter) -> None:
        painter.setPen(self.palette().text().color())
        title_font = painter.font()
        title_font.setBold(True)
        painter.setFont(title_font)
        if self._scene.title:
            painter.drawText(QPointF(58.0, 17.0), self._scene.title)

        normal = painter.font()
        normal.setBold(False)
        painter.setFont(normal)
        metrics = QFontMetrics(normal)
        entries = self._scene.legend[:4] if self._show_legend else ()
        title_width = metrics.horizontalAdvance(self._scene.title) if self._scene.title else 0.0
        legend_width = sum(metrics.horizontalAdvance(label) + 30.0 for label, _ in entries)
        right_x = self.width() - legend_width - 8.0 if self._scene.title else 58.0
        if not self._scene.title or right_x >= 58.0 + title_width + 12.0:
            x = right_x
            for label, color in entries:
                width = metrics.horizontalAdvance(label) + 22.0
                self._draw_color_dot(painter, x + 4.0, 14.0, color)
                painter.setPen(self.palette().text().color())
                painter.drawText(QPointF(x + 13.0, 18.0), label)
                x += width + 8.0
            return

        # On narrow docks, move the legend to a second header line rather
        # than letting it collide with the projection title.
        x = 58.0
        for label, color in entries:
            width = metrics.horizontalAdvance(label) + 22.0
            self._draw_color_dot(painter, x + 4.0, 34.0, color)
            painter.setPen(self.palette().text().color())
            painter.drawText(QPointF(x + 13.0, 38.0), label)
            x += width + 8.0

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
        grid.setAlpha(self._GRID_ALPHA)
        painter.setPen(QPen(grid, 1.0))
        metrics = QFontMetrics(painter.font())
        for index in range(5):
            ratio = index / 4.0
            value_x = min_x + (max_x - min_x) * ratio
            value_y = min_y + (max_y - min_y) * ratio
            x = plot.left() + plot.width() * ratio
            y = self._map_y(value_y, plot, min_y, max_y)
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

        painter.setPen(QPen(mid, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(plot)
        if min_x <= 0.0 <= max_x:
            x = plot.left() + (-min_x) / (max_x - min_x) * plot.width()
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        if min_y <= 0.0 <= max_y:
            y = self._map_y(0.0, plot, min_y, max_y)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        painter.setPen(self.palette().text().color())
        painter.drawText(
            QRectF(plot.left(), self.height() - 24.0, plot.width(), 18.0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            f"{self._scene.x_label} ({self._scene.units})",
        )
        painter.drawText(
            QRectF(4.0, plot.top() - 20.0, 50.0, 18.0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._scene.y_label} ({self._scene.units})",
        )

    def _draw_path(
        self,
        painter: QPainter,
        path: View2DPath,
        plot: QRectF,
        bounds: tuple[float, float, float, float],
    ) -> None:
        points = [self._map_point(point, plot, bounds) for point in path.points]
        if len(points) < 2:
            return
        color = self._display_color(path.color)
        painter.setPen(QPen(color, max(0.5, path.width)))
        fill = QColor(color)
        fill.setAlpha(max(0, min(255, path.fill_alpha)))
        painter.setBrush(fill if path.closed and path.fill_alpha else Qt.BrushStyle.NoBrush)
        if path.closed:
            outline = QPainterPath()
            outline.moveTo(points[0])
            for point in points[1:]:
                outline.lineTo(point)
            outline.closeSubpath()
            painter.drawPath(outline)
        else:
            for first, second in pairwise(points):
                painter.drawLine(first, second)

    def _draw_marker(
        self,
        painter: QPainter,
        marker: View2DMarker,
        plot: QRectF,
        bounds: tuple[float, float, float, float],
    ) -> None:
        point = self._map_point(marker.position, plot, bounds)
        color = self._color(marker.color)
        radius = marker.radius + (1.5 if marker.id == self._hovered_id else 0.0)
        if marker.symbol == "crosshair":
            painter.setPen(QPen(color, 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(plot.left(), point.y()), QPointF(plot.right(), point.y()))
            painter.drawLine(QPointF(point.x(), plot.top()), QPointF(point.x(), plot.bottom()))
            if marker.label and (self._show_labels or marker.id == self._hovered_id):
                painter.setPen(self.palette().text().color())
                painter.drawText(QPointF(point.x() + 6.0, point.y() - 6.0), marker.label)
            return
        painter.setPen(QPen(color, 2.0))
        painter.setBrush(color if marker.symbol == "dot" else Qt.BrushStyle.NoBrush)
        if marker.symbol == "cross":
            painter.drawLine(
                QPointF(point.x() - radius, point.y()), QPointF(point.x() + radius, point.y())
            )
            painter.drawLine(
                QPointF(point.x(), point.y() - radius), QPointF(point.x(), point.y() + radius)
            )
            painter.drawEllipse(point, radius, radius)
        elif marker.symbol == "ring":
            painter.drawEllipse(point, radius, radius)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(point, radius, radius)

        if marker.label and (self._show_labels or marker.id == self._hovered_id):
            painter.setPen(self.palette().text().color())
            painter.drawText(QPointF(point.x() + radius + 4.0, point.y() - 3.0), marker.label)

    def _map_point(
        self,
        point: tuple[float, float],
        plot: QRectF,
        bounds: tuple[float, float, float, float],
    ) -> QPointF:
        min_x, max_x, min_y, max_y = bounds
        return QPointF(
            plot.left() + (point[0] - min_x) / (max_x - min_x) * plot.width(),
            self._map_y(point[1], plot, min_y, max_y),
        )

    def _map_y(
        self,
        value: float,
        plot: QRectF,
        minimum: float,
        maximum: float,
    ) -> float:
        ratio = (value - minimum) / (maximum - minimum)
        if self._invert_vertical:
            return plot.top() + ratio * plot.height()
        return plot.bottom() - ratio * plot.height()

    def _marker_at(self, position) -> View2DMarker | None:
        bounds = self._bounds()
        if bounds is None:
            return None
        plot = self._plot_rect(bounds)
        px = position.x()
        py = position.y()
        for marker in sorted(self._scene.markers, key=self._marker_layer_order, reverse=True):
            mapped = self._map_point(marker.position, plot, bounds)
            if hypot(mapped.x() - px, mapped.y() - py) <= max(10.0, marker.radius + 4.0):
                return marker
        return None

    @staticmethod
    def _marker_layer_order(marker: View2DMarker) -> tuple[int, str]:
        # Aircraft CG guides must remain behind component rings.  Geometry is
        # rendered as paths before all markers, so it naturally stays below
        # both layers.
        order = {"cg": 0, "component": 1}
        return order.get(marker.layer, 2), marker.id

    def mouseMoveEvent(self, event) -> None:
        marker = self._marker_at(event.position())
        marker_id = marker.id if marker is not None else ""
        if marker_id != self._hovered_id:
            self._hovered_id = marker_id
            self.itemHovered.emit(marker_id)
            if marker_id and marker_id != "aircraft-cg":
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.unsetCursor()
            self.update()
        if marker is not None and marker.tooltip:
            QToolTip.showText(event.globalPosition().toPoint(), marker.tooltip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered_id = ""
        self.unsetCursor()
        QToolTip.hideText()
        self.itemHovered.emit("")
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            marker = self._marker_at(event.position())
            if marker is not None:
                self.itemClicked.emit(marker.id)
                event.accept()
                return
        super().mousePressEvent(event)

    @staticmethod
    def _draw_color_dot(painter: QPainter, x: float, y: float, color: ColorValue) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(View2DCanvas._display_color(color))
        painter.drawEllipse(QPointF(x, y), 3.5, 3.5)

    @staticmethod
    def _color(value: ColorValue) -> QColor:
        if isinstance(value, (tuple, list)):
            values = [float(component) for component in value[:3]]
            if max(values, default=0.0) <= 1.0:
                values = [component * 255.0 for component in values]
            return QColor(*[max(0, min(255, round(component))) for component in values])
        color = QColor(value)
        return color if color.isValid() else QColor("#7f9bb5")

    @staticmethod
    def _display_color(value: ColorValue) -> QColor:
        color = View2DCanvas._color(value)
        # Titanium/pearl geometry colours are intentionally pale for the 3D
        # viewer. Darken them only in light 2D plots where white outlines
        # otherwise disappear against the plot background.
        if is_light_theme() and color.lightness() > 185:
            return color.darker(170)
        return color

    @staticmethod
    def _format_axis(value: float) -> str:
        if abs(value) >= 100.0:
            return f"{value:.0f}"
        if abs(value) >= 10.0:
            return f"{value:.1f}"
        return f"{value:.2f}"
