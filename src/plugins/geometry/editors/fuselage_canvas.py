"""Interactive 2D vector canvas for inspecting and editing fuselage cross-sections."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QSizePolicy,
    QWidget,
)

from setuav_studio.ui.theme import accent_color, tokens

from ..engine.fuselage_geometry import compute_section_metrics, sample_profile


class FuselageCanvasWidget(QWidget):
    """Interactive 2D vector canvas for inspecting and editing fuselage cross-sections.

    Supports:
    - Direct vertex selection & dragging on canvas for polygon profiles
    - Edge hovering and click-to-insert new vertices
    - Pan (middle/left drag) & Zoom (mouse wheel)
    - Full two-way synchronization with table selection
    """

    vertexSelected = Signal(int)  # 0-based index or -1 if deselected
    vertexMoved = Signal(int, float, float)  # index, live y, live z
    vertexDragFinished = Signal(
        int, float, float, float, float
    )  # index, old_y, old_z, new_y, new_z
    vertexInserted = Signal(int, float, float)  # insert_index, y, z
    vertexDeleteRequested = Signal(int)  # delete_index
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens()
        self._profile: dict[str, Any] = {}
        self._prev_profile: dict[str, Any] | None = None
        self._next_profile: dict[str, Any] | None = None
        self._title_info: str = ""

        # Points
        self._active_points: tuple[tuple[float, float], ...] = ()
        self._prev_points: tuple[tuple[float, float], ...] = ()
        self._next_points: tuple[tuple[float, float], ...] = ()
        self._metrics: dict[str, float] = {}

        # Interactive Polygon State
        self.selected_vertex_index: int | None = None
        self._hovered_vertex_index: int | None = None
        self._hovered_edge: tuple[int, QPointF, tuple[float, float]] | None = (
            None  # (insert_after_idx, screen_pt, world_pt)
        )
        self._is_dragging_vertex: bool = False
        self._drag_start_world: tuple[float, float] | None = None

        # View settings
        self.show_previous: bool = True
        self.show_next: bool = True
        self.show_grid: bool = True
        self.show_axes: bool = True
        self.show_dimensions: bool = True
        self.show_centroid: bool = True
        self.show_radial_samples: bool = False

        # Pan & Zoom state
        self._scale: float = 2.0  # pixels per mm
        self._pan_offset: QPointF = QPointF(0.0, 0.0)
        self._last_mouse_pos: QPointF | None = None
        self._is_panning: bool = False

        self.setMinimumSize(360, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def set_section_data(
        self,
        profile: dict[str, Any],
        prev_profile: dict[str, Any] | None = None,
        next_profile: dict[str, Any] | None = None,
        title_info: str = "",
        auto_fit: bool = False,
    ) -> None:
        """Update section geometry and refresh canvas."""
        self._profile = profile
        self._prev_profile = prev_profile
        self._next_profile = next_profile
        self._title_info = title_info

        self._active_points = sample_profile(profile) if profile else ()
        self._prev_points = sample_profile(prev_profile) if prev_profile else ()
        self._next_points = sample_profile(next_profile) if next_profile else ()
        self._metrics = compute_section_metrics(self._active_points)

        # Validate selected vertex index
        if self._profile.get("type") == "polygon":
            verts = self._profile.get("vertices")
            num_v = len(verts) if isinstance(verts, list) else 0
            if self.selected_vertex_index is not None and self.selected_vertex_index >= num_v:
                self.selected_vertex_index = num_v - 1 if num_v > 0 else None
        else:
            self.selected_vertex_index = None

        if auto_fit:
            self.fit_view()
        else:
            self.update()

    def set_selected_vertex(self, index: int | None) -> None:
        """Select a vertex from external control (e.g. table row click)."""
        if index is not None and index >= 0:
            self.selected_vertex_index = index
        else:
            self.selected_vertex_index = None
        self.update()

    def world_to_screen(self, y_mm: float, z_mm: float) -> QPointF:
        ox = self.width() / 2.0 + self._pan_offset.x()
        oy = self.height() / 2.0 + self._pan_offset.y()
        return QPointF(ox + y_mm * self._scale, oy - z_mm * self._scale)

    def screen_to_world(self, screen_pos: QPointF) -> tuple[float, float]:
        ox = self.width() / 2.0 + self._pan_offset.x()
        oy = self.height() / 2.0 + self._pan_offset.y()
        y_mm = (screen_pos.x() - ox) / self._scale
        z_mm = (oy - screen_pos.y()) / self._scale
        return y_mm, z_mm

    def fit_view(self) -> None:
        """Fit all visible profiles within the canvas viewport with margin."""
        all_pts: list[tuple[float, float]] = list(self._active_points)
        if self.show_previous and self._prev_points:
            all_pts.extend(self._prev_points)
        if self.show_next and self._next_points:
            all_pts.extend(self._next_points)

        if not all_pts:
            self._scale = 2.0
            self._pan_offset = QPointF(0.0, 0.0)
            self.update()
            return

        ys = [p[0] for p in all_pts]
        zs = [p[1] for p in all_pts]
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)

        span_y = max(max_y - min_y, 20.0)
        span_z = max(max_z - min_z, 20.0)
        center_y = (min_y + max_y) * 0.5
        center_z = (min_z + max_z) * 0.5

        margin = 60.0
        avail_w = max(self.width() - 2 * margin, 50.0)
        avail_h = max(self.height() - 2 * margin, 50.0)

        scale_y = avail_w / span_y
        scale_z = avail_h / span_z
        self._scale = max(min(scale_y, scale_z), 0.1)

        self._pan_offset = QPointF(-center_y * self._scale, center_z * self._scale)
        self.update()

    def zoom_in(self) -> None:
        self._scale = min(self._scale * 1.25, 50.0)
        self.update()

    def zoom_out(self) -> None:
        self._scale = max(self._scale / 1.25, 0.05)
        self.update()

    def reset_view(self) -> None:
        self.fit_view()

    # -------------------------------------------------------------------------
    # Hit Testing
    # -------------------------------------------------------------------------
    def _hit_test_vertex(self, screen_pos: QPointF, threshold_px: float = 10.0) -> int | None:
        if self._profile.get("type") != "polygon":
            return None
        verts = self._profile.get("vertices")
        if not isinstance(verts, list):
            return None

        for idx, v in enumerate(verts):
            if not isinstance(v, dict):
                continue
            vy = float(v.get("y", 0.0))
            vz = float(v.get("z", 0.0))
            v_screen = self.world_to_screen(vy, vz)
            dist = math.hypot(screen_pos.x() - v_screen.x(), screen_pos.y() - v_screen.y())
            if dist <= threshold_px:
                return idx
        return None

    def _hit_test_edge(
        self,
        screen_pos: QPointF,
        threshold_px: float = 8.0,
    ) -> tuple[int, QPointF, tuple[float, float]] | None:
        """Find if screen_pos is close to any edge of the polygon outline."""
        if self._profile.get("type") != "polygon":
            return None
        verts = self._profile.get("vertices")
        if not isinstance(verts, list) or len(verts) < 2:
            return None

        num_v = len(verts)
        for i in range(num_v):
            v0 = verts[i]
            v1 = verts[(i + 1) % num_v]
            if not isinstance(v0, dict) or not isinstance(v1, dict):
                continue

            p0 = self.world_to_screen(float(v0.get("y", 0.0)), float(v0.get("z", 0.0)))
            p1 = self.world_to_screen(float(v1.get("y", 0.0)), float(v1.get("z", 0.0)))

            # Distance from point to line segment
            dx = p1.x() - p0.x()
            dy = p1.y() - p0.y()
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-4:
                continue

            t = max(
                0.0,
                min(
                    1.0,
                    ((screen_pos.x() - p0.x()) * dx + (screen_pos.y() - p0.y()) * dy) / seg_len_sq,
                ),
            )
            # Don't hit too close to endpoints
            if t < 0.1 or t > 0.9:
                continue

            proj_x = p0.x() + t * dx
            proj_y = p0.y() + t * dy
            dist = math.hypot(screen_pos.x() - proj_x, screen_pos.y() - proj_y)

            if dist <= threshold_px:
                proj_screen = QPointF(proj_x, proj_y)
                world_y, world_z = self.screen_to_world(proj_screen)
                return (i + 1, proj_screen, (world_y, world_z))

        return None

    # -------------------------------------------------------------------------
    # Mouse & Keyboard Events
    # -------------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicked on a vertex handle
            v_idx = self._hit_test_vertex(event.position())
            if v_idx is not None:
                self.selected_vertex_index = v_idx
                self._is_dragging_vertex = True
                verts = self._profile.get("vertices", [])
                self._drag_start_world = (
                    float(verts[v_idx].get("y", 0.0)),
                    float(verts[v_idx].get("z", 0.0)),
                )
                self.vertexSelected.emit(v_idx)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update()
                return

            # Check if clicked on an edge to insert a vertex
            edge_hit = self._hit_test_edge(event.position())
            if edge_hit is not None:
                ins_idx, _, (wy, wz) = edge_hit
                self.vertexInserted.emit(ins_idx, round(wy, 1), round(wz, 1))
                return

            # Deselect if clicked on empty space
            if self.selected_vertex_index is not None:
                self.selected_vertex_index = None
                self.vertexSelected.emit(-1)
                self.update()

            # Start canvas panning
            self._is_panning = True
            self._last_mouse_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        elif event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._last_mouse_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # 1. Dragging a polygon vertex
        if self._is_dragging_vertex and self.selected_vertex_index is not None:
            new_y, new_z = self.screen_to_world(event.position())
            # Snap to 0.1 mm precision
            new_y = round(new_y, 1)
            new_z = round(new_z, 1)

            verts = self._profile.get("vertices")
            if isinstance(verts, list) and 0 <= self.selected_vertex_index < len(verts):
                verts[self.selected_vertex_index]["y"] = new_y
                verts[self.selected_vertex_index]["z"] = new_z
                self._active_points = sample_profile(self._profile)
                self._metrics = compute_section_metrics(self._active_points)
                self.vertexMoved.emit(self.selected_vertex_index, new_y, new_z)
                self.update()
            return

        # 2. Panning canvas
        if self._is_panning and self._last_mouse_pos is not None:
            delta = event.position() - self._last_mouse_pos
            self._pan_offset += delta
            self._last_mouse_pos = event.position()
            self.update()
            return

        # 3. Hovering feedback (when not dragging)
        if self._profile.get("type") == "polygon":
            v_idx = self._hit_test_vertex(event.position())
            if v_idx != self._hovered_vertex_index:
                self._hovered_vertex_index = v_idx
                self.update()

            if v_idx is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                self._hovered_edge = None
                return

            edge_hit = self._hit_test_edge(event.position())
            if edge_hit != self._hovered_edge:
                self._hovered_edge = edge_hit
                self.update()

            if edge_hit is not None:
                self.setCursor(Qt.CursorShape.CrossCursor)
                return

        self.setCursor(Qt.CursorShape.ArrowCursor)
        if self._hovered_edge is not None:
            self._hovered_edge = None
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging_vertex:
            self._is_dragging_vertex = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

            if self.selected_vertex_index is not None and self._drag_start_world is not None:
                verts = self._profile.get("vertices", [])
                if 0 <= self.selected_vertex_index < len(verts):
                    cur_y = float(verts[self.selected_vertex_index].get("y", 0.0))
                    cur_z = float(verts[self.selected_vertex_index].get("z", 0.0))
                    old_y, old_z = self._drag_start_world
                    if abs(cur_y - old_y) > 1e-4 or abs(cur_z - old_z) > 1e-4:
                        self.vertexDragFinished.emit(
                            self.selected_vertex_index, old_y, old_z, cur_y, cur_z
                        )
            self._drag_start_world = None

        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._is_panning = False
            self._last_mouse_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Double click on edge or canvas inserts a vertex
            if self._profile.get("type") == "polygon":
                edge_hit = self._hit_test_edge(event.position(), threshold_px=14.0)
                if edge_hit is not None:
                    ins_idx, _, (wy, wz) = edge_hit
                    self.vertexInserted.emit(ins_idx, round(wy, 1), round(wz, 1))
                    return
            self.fit_view()

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        mouse_pos = event.position()

        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        mouse_offset = mouse_pos - (center + self._pan_offset)

        new_scale = max(min(self._scale * factor, 100.0), 0.02)
        scale_ratio = new_scale / self._scale
        self._pan_offset = mouse_pos - center - mouse_offset * scale_ratio
        self._scale = new_scale
        self.update()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.selected_vertex_index is not None:
                self.vertexDeleteRequested.emit(self.selected_vertex_index)
                return
        elif event.matches(QKeySequence.StandardKey.Undo):
            self.undoRequested.emit()
            return
        elif event.matches(QKeySequence.StandardKey.Redo):
            self.redoRequested.emit()
            return
        elif event.key() == Qt.Key.Key_F or (
            event.key() == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.fit_view()
            return
        super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------
    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # Canvas background
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        bg_color = QColor(tok.get("elevated", "#ffffff" if is_light else "#1a1a1c"))
        painter.fillRect(0, 0, width, height, bg_color)

        ox = width / 2.0 + self._pan_offset.x()
        oy = height / 2.0 + self._pan_offset.y()

        def world_to_screen(y_mm: float, z_mm: float) -> QPointF:
            return QPointF(ox + y_mm * self._scale, oy - z_mm * self._scale)

        # 1. Grid & Axes
        if self.show_grid:
            self._draw_grid(painter, width, height, ox, oy)

        if self.show_axes:
            self._draw_axes(painter, width, height, ox, oy)

        # 2. Ghost Overlays
        if self.show_previous and self._prev_points:
            self._draw_profile_outline(
                painter,
                self._prev_points,
                world_to_screen,
                stroke_color=QColor(51, 127, 229, 160),
                fill_color=QColor(51, 127, 229, 15),
                pen_style=Qt.PenStyle.DashLine,
                line_width=1.5,
            )

        if self.show_next and self._next_points:
            self._draw_profile_outline(
                painter,
                self._next_points,
                world_to_screen,
                stroke_color=QColor(230, 126, 34, 160),
                fill_color=QColor(230, 126, 34, 15),
                pen_style=Qt.PenStyle.DashLine,
                line_width=1.5,
            )

        self._draw_active_profile(painter, world_to_screen)

        # 4. Centroid & Dimensions
        if self.show_centroid and self._metrics and self._metrics["area"] > 0:
            cg_y = self._metrics["y_cg"]
            cg_z = self._metrics["z_cg"]
            cg_pt = world_to_screen(cg_y, cg_z)

            painter.setPen(QPen(QColor("#f39c12"), 1.5, Qt.PenStyle.SolidLine))
            painter.drawLine(int(cg_pt.x() - 6), int(cg_pt.y()), int(cg_pt.x() + 6), int(cg_pt.y()))
            painter.drawLine(int(cg_pt.x()), int(cg_pt.y() - 6), int(cg_pt.x()), int(cg_pt.y() + 6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(cg_pt, 4.0, 4.0)

            painter.setFont(QFont("sans-serif", 7))
            painter.setPen(QColor("#f39c12"))
            painter.drawText(
                int(cg_pt.x()) + 7, int(cg_pt.y()) + 11, f"CG ({cg_y:.1f}, {cg_z:.1f})"
            )

        if self.show_dimensions and self._active_points:
            self._draw_dimension_lines(painter, self._active_points, world_to_screen)

        # 5. HUD Header & Legend
        self._draw_hud(painter, width, height)

    def _draw_active_profile(self, painter: QPainter, world_to_screen: Any) -> None:
        if not self._active_points:
            return
        self._draw_profile_outline(
            painter,
            self._active_points,
            world_to_screen,
            stroke_color=QColor(accent_color()),
            fill_color=QColor(*QColor(accent_color()).getRgb()[:3], 38),
            pen_style=Qt.PenStyle.SolidLine,
            line_width=2.2,
        )
        if self.show_radial_samples:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(accent_color()))
            for y, z in self._active_points:
                painter.drawEllipse(world_to_screen(y, z), 1.8, 1.8)
        if self._hovered_edge is not None:
            _, screen_point, (world_y, world_z) = self._hovered_edge
            painter.setPen(QPen(QColor("#2ecc71"), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(46, 204, 113, 80))
            painter.drawEllipse(screen_point, 6.0, 6.0)
            painter.setPen(QColor("#2ecc71"))
            painter.setFont(QFont("sans-serif", 8, QFont.Weight.Bold))
            painter.drawText(
                int(screen_point.x()) + 8,
                int(screen_point.y()) - 4,
                f"+ Add ({world_y:.1f}, {world_z:.1f})",
            )
        if self._profile.get("type") == "polygon":
            self._draw_polygon_handles(painter, world_to_screen)

    def _draw_polygon_handles(self, painter: QPainter, to_screen: Any) -> None:
        from setuav_studio.ui.theme import tokens

        tok = tokens()
        text_color = QColor(tok["text"])
        surface_color = QColor(tok["surface"])
        border_color = QColor(tok["border_strong"])
        verts = self._profile.get("vertices")
        if not isinstance(verts, list):
            return

        painter.setFont(QFont("sans-serif", 8, QFont.Weight.Bold))

        for idx, v in enumerate(verts):
            if not isinstance(v, dict):
                continue
            vy = float(v.get("y", 0.0))
            vz = float(v.get("z", 0.0))
            vr = float(v.get("radius", 0.0))
            pt = to_screen(vy, vz)

            is_selected = idx == self.selected_vertex_index
            is_hovered = idx == self._hovered_vertex_index

            # Selection / Hover Rings
            if is_selected:
                # Outer glow ring
                painter.setPen(QPen(surface_color, 2.0))
                painter.setBrush(QColor("#f39c12"))
                painter.drawEllipse(pt, 6.5, 6.5)

                # Coordinate badge for selected vertex
                badge_text = f"P{idx + 1}: ({vy:.1f}, {vz:.1f}) r={vr:.1f}"
                painter.setPen(text_color)
                painter.setBrush(surface_color)
                text_rect = QRectF(pt.x() + 8, pt.y() - 18, len(badge_text) * 6.5 + 8, 16)
                painter.drawRoundedRect(text_rect, 3, 3)
                painter.setPen(text_color)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

            elif is_hovered:
                painter.setPen(QPen(QColor(accent_color()), 2.0))
                painter.setBrush(QColor("#e67e22"))
                painter.drawEllipse(pt, 5.5, 5.5)
                painter.setPen(text_color)
                painter.drawText(int(pt.x()) + 8, int(pt.y()) - 4, f"P{idx + 1}")
            else:
                painter.setPen(QPen(border_color, 1.2))
                painter.setBrush(QColor("#f39c12"))
                painter.drawEllipse(pt, 4.0, 4.0)
                painter.setPen(text_color)
                painter.drawText(int(pt.x()) + 6, int(pt.y()) - 4, f"P{idx + 1}")

    def _draw_profile_outline(
        self,
        painter: QPainter,
        points: tuple[tuple[float, float], ...],
        to_screen: Any,
        stroke_color: QColor,
        fill_color: QColor,
        pen_style: Qt.PenStyle,
        line_width: float,
    ) -> None:
        if not points:
            return
        path = QPainterPath()
        poly = QPolygonF()
        for i, (y, z) in enumerate(points):
            pt = to_screen(y, z)
            poly.append(pt)
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()

        painter.fillPath(path, QBrush(fill_color))
        painter.strokePath(path, QPen(stroke_color, line_width, pen_style))

    def _draw_grid(
        self,
        painter: QPainter,
        width: int,
        height: int,
        ox: float,
        oy: float,
    ) -> None:
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        grid_color = QColor(tok.get("grid", "#e2e4e8" if is_light else "#262626"))
        dim_text = QColor(tok.get("text_dim", "#787878" if is_light else "#555555"))

        raw_step = 60.0 / max(self._scale, 1e-4)
        magnitude = 10.0 ** math.floor(math.log10(max(raw_step, 1.0)))
        step_candidates = [1.0 * magnitude, 2.0 * magnitude, 5.0 * magnitude, 10.0 * magnitude]
        grid_step_mm = min(step_candidates, key=lambda s: abs(s * self._scale - 60.0))
        grid_step_px = grid_step_mm * self._scale

        grid_pen = QPen(grid_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        painter.setFont(QFont("sans-serif", 7))

        start_k_y = math.floor(-ox / grid_step_px)
        end_k_y = math.ceil((width - ox) / grid_step_px)
        for k in range(start_k_y, end_k_y + 1):
            gx = ox + k * grid_step_px
            painter.setPen(grid_pen)
            painter.drawLine(int(gx), 0, int(gx), height)
            val_y = k * grid_step_mm
            if abs(val_y) > 1e-4:
                painter.setPen(dim_text)
                painter.drawText(int(gx) + 3, height - 6, f"{val_y:.0f}")

        start_k_z = math.floor((oy - height) / grid_step_px)
        end_k_z = math.ceil(oy / grid_step_px)
        for k in range(start_k_z, end_k_z + 1):
            gy = oy - k * grid_step_px
            painter.setPen(grid_pen)
            painter.drawLine(0, int(gy), width, int(gy))
            val_z = k * grid_step_mm
            if abs(val_z) > 1e-4:
                painter.setPen(dim_text)
                painter.drawText(6, int(gy) - 3, f"{val_z:.0f}")

    def _draw_axes(
        self,
        painter: QPainter,
        width: int,
        height: int,
        ox: float,
        oy: float,
    ) -> None:
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        axis_color = QColor(tok.get("border_strong", "#b0b4bc" if is_light else "#404040"))
        dim_text = QColor(tok.get("text_dim", "#787878" if is_light else "#777777"))

        axis_pen = QPen(axis_color, 1.2, Qt.PenStyle.SolidLine)
        painter.setPen(axis_pen)

        painter.drawLine(0, int(oy), width, int(oy))
        painter.drawLine(int(ox), 0, int(ox), height)

        painter.setBrush(dim_text)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(ox, oy), 2.5, 2.5)

        painter.setFont(QFont("sans-serif", 8, QFont.Weight.Bold))
        painter.setPen(dim_text)
        painter.drawText(width - 25, int(oy) - 6, "+Y")
        painter.drawText(int(ox) + 6, 16, "+Z")

    def _draw_dimension_lines(
        self,
        painter: QPainter,
        points: tuple[tuple[float, float], ...],
        to_screen: Any,
    ) -> None:
        ys = [p[0] for p in points]
        zs = [p[1] for p in points]
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        w_mm = max_y - min_y
        h_mm = max_z - min_z

        from setuav_studio.ui.theme import tokens

        dim_pen = QPen(QColor(tokens()["text_dim"]), 1.0, Qt.PenStyle.SolidLine)
        painter.setPen(dim_pen)
        painter.setFont(QFont("sans-serif", 8))

        offset_down = 18.0
        p_left = to_screen(min_y, min_z)
        p_right = to_screen(max_y, min_z)
        dim_y = p_left.y() + offset_down

        painter.drawLine(int(p_left.x()), int(dim_y - 4), int(p_left.x()), int(dim_y + 4))
        painter.drawLine(int(p_right.x()), int(dim_y - 4), int(p_right.x()), int(dim_y + 4))
        painter.drawLine(int(p_left.x()), int(dim_y), int(p_right.x()), int(dim_y))
        painter.drawText(
            QRectF(p_left.x(), dim_y + 2, p_right.x() - p_left.x(), 16),
            Qt.AlignmentFlag.AlignCenter,
            f"W = {w_mm:.1f} mm",
        )

        offset_right = 18.0
        p_bot = to_screen(max_y, min_z)
        p_top = to_screen(max_y, max_z)
        dim_x = p_bot.x() + offset_right

        painter.drawLine(int(dim_x - 4), int(p_bot.y()), int(dim_x + 4), int(p_bot.y()))
        painter.drawLine(int(dim_x - 4), int(p_top.y()), int(dim_x + 4), int(p_top.y()))
        painter.drawLine(int(dim_x), int(p_bot.y()), int(dim_x), int(p_top.y()))
        painter.drawText(
            int(dim_x + 6), int((p_bot.y() + p_top.y()) / 2.0 + 4), f"H = {h_mm:.1f} mm"
        )

    def _draw_hud(self, painter: QPainter, width: int, _height: int) -> None:
        from setuav_studio.ui.theme import chart_color, tokens

        tok = tokens()
        painter.setPen(QColor(tok["text"]))
        painter.setFont(QFont("sans-serif", 9, QFont.Weight.Bold))
        prof_type = str(self._profile.get("type", "Unknown")).capitalize()
        painter.drawText(12, 22, f"{self._title_info} ({prof_type})")

        legend_x = width - 180
        legend_y = 12
        painter.setFont(QFont("sans-serif", 7))

        painter.setPen(QPen(QColor(accent_color()), 2.0))
        painter.drawLine(legend_x, legend_y + 6, legend_x + 16, legend_y + 6)
        painter.setPen(QColor(tok["text_muted"]))
        painter.drawText(legend_x + 22, legend_y + 10, "Current Section")

        if self.show_previous and self._prev_points:
            painter.setPen(QPen(QColor(chart_color("blue")), 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(legend_x, legend_y + 20, legend_x + 16, legend_y + 20)
            painter.setPen(QColor(tok["text_muted"]))
            painter.drawText(legend_x + 22, legend_y + 24, "Previous (Loft In)")

        if self.show_next and self._next_points:
            painter.setPen(QPen(QColor(chart_color("orange")), 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(legend_x, legend_y + 34, legend_x + 16, legend_y + 34)
            painter.setPen(QColor(tok["text_muted"]))
            painter.drawText(legend_x + 22, legend_y + 38, "Next (Loft Out)")


__all__ = ["FuselageCanvasWidget"]
