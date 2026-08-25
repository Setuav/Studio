"""Interactive 2D Fuselage Cross-Section Inspector and Profile Editor Dialog."""

from __future__ import annotations

import copy
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
    QUndoCommand,
    QUndoStack,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.buttons import set_button_role, set_native_button
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.numeric_spinbox import (
    NoWheelComboBox,
    set_table_spinbox,
)
from setuav_studio.ui.theme import accent_color, tokens

from ..engine.fuselage_geometry import compute_section_metrics, sample_profile
from ..settings import _EDITOR_AUTO_FIT_KEY, _EDITOR_GRID_KEY, _as_bool, editor_setting


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
    vertexDragFinished = Signal(int, float, float, float, float)  # index, old_y, old_z, new_y, new_z
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
        self._hovered_edge: tuple[int, QPointF, tuple[float, float]] | None = None  # (insert_after_idx, screen_pt, world_pt)
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

            t = max(0.0, min(1.0, ((screen_pos.x() - p0.x()) * dx + (screen_pos.y() - p0.y()) * dy) / seg_len_sq))
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
                self._drag_start_world = (float(verts[v_idx].get("y", 0.0)), float(verts[v_idx].get("z", 0.0)))
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
                        self.vertexDragFinished.emit(self.selected_vertex_index, old_y, old_z, cur_y, cur_z)
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
        elif event.key() == Qt.Key.Key_F or (event.key() == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
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

        # 3. Active Profile
        if self._active_points:
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
                    pt = world_to_screen(y, z)
                    painter.drawEllipse(pt, 1.8, 1.8)

            # Edge insertion preview marker
            if self._hovered_edge is not None:
                _, screen_pt, (wy, wz) = self._hovered_edge
                painter.setPen(QPen(QColor("#2ecc71"), 1.5, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(46, 204, 113, 80))
                painter.drawEllipse(screen_pt, 6.0, 6.0)
                painter.setPen(QColor("#2ecc71"))
                painter.setFont(QFont("sans-serif", 8, QFont.Weight.Bold))
                painter.drawText(int(screen_pt.x()) + 8, int(screen_pt.y()) - 4, f"+ Add ({wy:.1f}, {wz:.1f})")

            # Interactive Polygon Handles
            if self._profile.get("type") == "polygon":
                self._draw_polygon_handles(painter, world_to_screen)

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
            painter.drawText(int(cg_pt.x()) + 7, int(cg_pt.y()) + 11, f"CG ({cg_y:.1f}, {cg_z:.1f})")

        if self.show_dimensions and self._active_points:
            self._draw_dimension_lines(painter, self._active_points, world_to_screen)

        # 5. HUD Header & Legend
        self._draw_hud(painter, width, height)

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
                badge_text = f"P{idx+1}: ({vy:.1f}, {vz:.1f}) r={vr:.1f}"
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
                painter.drawText(int(pt.x()) + 8, int(pt.y()) - 4, f"P{idx+1}")
            else:
                painter.setPen(QPen(border_color, 1.2))
                painter.setBrush(QColor("#f39c12"))
                painter.drawEllipse(pt, 4.0, 4.0)
                painter.setPen(text_color)
                painter.drawText(int(pt.x()) + 6, int(pt.y()) - 4, f"P{idx+1}")

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
        painter.drawText(int(dim_x + 6), int((p_bot.y() + p_top.y()) / 2.0 + 4), f"H = {h_mm:.1f} mm")

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


# -----------------------------------------------------------------------------
# Undo Commands for 2D Section Editor
# -----------------------------------------------------------------------------
class MoveVertexCommand(QUndoCommand):
    def __init__(
        self,
        dialog: FuselageSectionDialog,
        vertex_idx: int,
        old_pos: tuple[float, float],
        new_pos: tuple[float, float],
    ) -> None:
        super().__init__(f"Move Vertex P{vertex_idx+1}")
        self.dialog = dialog
        self.vertex_idx = vertex_idx
        self.old_pos = old_pos
        self.new_pos = new_pos

    def redo(self) -> None:
        self.dialog._apply_vertex_pos(self.vertex_idx, self.new_pos[0], self.new_pos[1])

    def undo(self) -> None:
        self.dialog._apply_vertex_pos(self.vertex_idx, self.old_pos[0], self.old_pos[1])


class AddVertexCommand(QUndoCommand):
    def __init__(
        self,
        dialog: FuselageSectionDialog,
        insert_idx: int,
        vertex_data: dict[str, float],
    ) -> None:
        super().__init__(f"Add Vertex P{insert_idx+1}")
        self.dialog = dialog
        self.insert_idx = insert_idx
        self.vertex_data = copy.deepcopy(vertex_data)

    def redo(self) -> None:
        self.dialog._insert_vertex_internal(self.insert_idx, self.vertex_data)

    def undo(self) -> None:
        self.dialog._remove_vertex_internal(self.insert_idx)


class DeleteVertexCommand(QUndoCommand):
    def __init__(
        self,
        dialog: FuselageSectionDialog,
        delete_idx: int,
        vertex_data: dict[str, float],
    ) -> None:
        super().__init__(f"Delete Vertex P{delete_idx+1}")
        self.dialog = dialog
        self.delete_idx = delete_idx
        self.vertex_data = copy.deepcopy(vertex_data)

    def redo(self) -> None:
        self.dialog._remove_vertex_internal(self.delete_idx)

    def undo(self) -> None:
        self.dialog._insert_vertex_internal(self.delete_idx, self.vertex_data)


class ChangePropertyCommand(QUndoCommand):
    def __init__(
        self,
        dialog: FuselageSectionDialog,
        key: str,
        old_val: Any,
        new_val: Any,
    ) -> None:
        super().__init__(f"Edit {key}")
        self.dialog = dialog
        self.key = key
        self.old_val = old_val
        self.new_val = new_val

    def redo(self) -> None:
        self.dialog._apply_profile_property(self.key, self.new_val)

    def undo(self) -> None:
        self.dialog._apply_profile_property(self.key, self.old_val)


class ChangeProfileTypeCommand(QUndoCommand):
    def __init__(
        self,
        dialog: FuselageSectionDialog,
        old_profile: dict[str, Any],
        new_profile: dict[str, Any],
    ) -> None:
        super().__init__(f"Change Profile to {new_profile.get('type')}")
        self.dialog = dialog
        self.old_profile = copy.deepcopy(old_profile)
        self.new_profile = copy.deepcopy(new_profile)

    def redo(self) -> None:
        self.dialog._apply_full_profile(self.new_profile)

    def undo(self) -> None:
        self.dialog._apply_full_profile(self.old_profile)


class FuselageSectionDialog(QDialog):
    """Detailed 2D cross-section inspector and interactive profile editor dialog with Undo/Redo."""

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        segment_index: int = 0,
        section_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._component = component
        self._original_component = copy.deepcopy(component)
        self._segment_index = segment_index
        self._section_index = section_index
        self._loading = False
        self._auto_fit_sections = _as_bool(
            editor_setting(_EDITOR_AUTO_FIT_KEY, True),
            True,
        )

        # Dedicated QUndoStack for interactive 2D editing
        self.undo_stack = QUndoStack(self)

        self.setWindowTitle(f"Fuselage Section Inspector — {component.get('name', 'Fuselage')}")
        self.setMinimumSize(900, 600)
        self.resize(980, 650)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Top Section Navigator Bar
        nav_bar = QWidget()
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)

        nav_layout.addWidget(QLabel("Segment:"))
        self.segment_combo = NoWheelComboBox()
        self.segment_combo.currentIndexChanged.connect(self._on_segment_combo_changed)
        nav_layout.addWidget(self.segment_combo)

        nav_layout.addSpacing(16)

        self.prev_btn = QToolButton()
        self.prev_btn.setIcon(get_icon("fa6s.chevron-left"))
        self.prev_btn.setToolTip("Previous Section")
        self.prev_btn.clicked.connect(self._on_prev_section)
        nav_layout.addWidget(self.prev_btn)

        self.section_label = QLabel("Section 1 of 1")
        nav_layout.addWidget(self.section_label)

        self.next_btn = QToolButton()
        self.next_btn.setIcon(get_icon("fa6s.chevron-right"))
        self.next_btn.setToolTip("Next Section")
        self.next_btn.clicked.connect(self._on_next_section)
        nav_layout.addWidget(self.next_btn)

        nav_layout.addStretch()
        main_layout.addWidget(nav_bar)

        # 2. Main Horizontal Splitter (Left: Controls, Right: Canvas)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 8, 0)
        self._scroll_layout.setSpacing(10)

        # Group A: Profile Definition
        prof_box = QGroupBox("Profile Definition")
        prof_layout = QVBoxLayout(prof_box)
        prof_layout.setSpacing(6)

        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Profile Type:"))
        self.profile_type_combo = NoWheelComboBox()
        self.profile_type_combo.addItems([
            "circle",
            "ellipse",
            "rectangle",
            "trapezoid",
            "triangle",
            "polygon",
        ])
        self.profile_type_combo.currentTextChanged.connect(self._on_profile_type_changed)
        type_layout.addWidget(self.profile_type_combo)
        prof_layout.addLayout(type_layout)

        self.props_table = QTableWidget(0, 2)
        self.props_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.props_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.props_table.cellChanged.connect(self._on_prop_table_cell_changed)
        prof_layout.addWidget(self.props_table)

        # Polygon vertices table
        self.poly_box = QWidget()
        poly_layout = QVBoxLayout(self.poly_box)
        poly_layout.setContentsMargins(0, 0, 0, 0)
        poly_layout.setSpacing(4)
        poly_layout.addWidget(QLabel("Polygon Vertices (Interactive on Canvas):"))

        self.vertices_table = QTableWidget(0, 3)
        self.vertices_table.setHorizontalHeaderLabels(["Y (mm)", "Z (mm)", "Radius (mm)"])
        self.vertices_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.vertices_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.vertices_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.vertices_table.cellChanged.connect(self._on_vertices_cell_changed)
        self.vertices_table.currentCellChanged.connect(self._on_vertices_row_selected)
        poly_layout.addWidget(self.vertices_table)

        v_actions = QHBoxLayout()
        self.add_v_btn = QToolButton()
        set_native_button(self.add_v_btn, "add")
        self.add_v_btn.setToolTip("Add Vertex")
        self.add_v_btn.clicked.connect(self._add_polygon_vertex)
        self.del_v_btn = QToolButton()
        set_native_button(self.del_v_btn, "remove")
        self.del_v_btn.setToolTip("Delete Vertex (Delete key)")
        self.del_v_btn.clicked.connect(self._delete_polygon_vertex)
        v_actions.addWidget(self.add_v_btn)
        v_actions.addWidget(self.del_v_btn)
        v_actions.addStretch()
        poly_layout.addLayout(v_actions)

        prof_layout.addWidget(self.poly_box)
        self._scroll_layout.addWidget(prof_box)

        # Group B: Transform
        trans_box = QGroupBox("Section Transform")
        trans_layout = QVBoxLayout(trans_box)
        self.trans_table = QTableWidget(2, 3)
        self.trans_table.setHorizontalHeaderLabels(["X (mm)", "Y (mm)", "Z (mm)"])
        self.trans_table.setVerticalHeaderLabels(["Position", "Rotation (°)"])
        self.trans_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trans_table.verticalHeader().setDefaultSectionSize(24)
        self.trans_table.setFixedHeight(75)
        for r in range(2):
            for c in range(3):
                item = QTableWidgetItem("0.0")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.trans_table.setItem(r, c, item)
        self.trans_table.cellChanged.connect(self._on_transform_cell_changed)
        trans_layout.addWidget(self.trans_table)
        self._scroll_layout.addWidget(trans_box)

        # Group C: Display Options
        disp_box = QGroupBox("Display Options")
        disp_layout = QVBoxLayout(disp_box)
        disp_layout.setSpacing(4)

        self.cb_prev = QCheckBox("Show Previous Section (Ghost)")
        self.cb_prev.setChecked(True)
        self.cb_prev.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_prev)

        self.cb_next = QCheckBox("Show Next Section (Ghost)")
        self.cb_next.setChecked(True)
        self.cb_next.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_next)

        self.cb_dims = QCheckBox("Show Dimension Annotations")
        self.cb_dims.setChecked(True)
        self.cb_dims.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_dims)

        self.cb_cg = QCheckBox("Show Centroid (CG)")
        self.cb_cg.setChecked(True)
        self.cb_cg.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_cg)

        self.cb_grid = QCheckBox("Show Grid & Coordinate Axes")
        self.cb_grid.setChecked(
            _as_bool(editor_setting(_EDITOR_GRID_KEY, True), True)
        )
        self.cb_grid.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_grid)

        self.cb_radial = QCheckBox("Show 128 Radial Sample Points")
        self.cb_radial.setChecked(False)
        self.cb_radial.toggled.connect(self._on_display_option_toggled)
        disp_layout.addWidget(self.cb_radial)

        self._scroll_layout.addWidget(disp_box)
        self._scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        splitter.addWidget(left_widget)

        # Right Panel (2D Canvas + Metrics Panel)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Canvas Toolbar (Undo, Redo, Zoom, Pan controls)
        canvas_bar = QWidget()
        c_layout = QHBoxLayout(canvas_bar)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(4)

        # Undo Action & Button
        self.undo_btn = QToolButton()
        self.undo_btn.setIcon(get_icon("fa6s.rotate-left"))
        self.undo_btn.setToolTip("Undo (Ctrl+Z)")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo_stack.undo)
        c_layout.addWidget(self.undo_btn)

        # Redo Action & Button
        self.redo_btn = QToolButton()
        self.redo_btn.setIcon(get_icon("fa6s.rotate-right"))
        self.redo_btn.setToolTip("Redo (Ctrl+Y)")
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.undo_stack.redo)
        c_layout.addWidget(self.redo_btn)

        self.undo_stack.canUndoChanged.connect(self.undo_btn.setEnabled)
        self.undo_stack.canRedoChanged.connect(self.redo_btn.setEnabled)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        c_layout.addWidget(sep1)

        fit_btn = QToolButton()
        fit_btn.setIcon(get_icon("fit"))
        fit_btn.setToolTip("Fit View (Reset Camera)")
        fit_btn.clicked.connect(self._on_fit_view)
        c_layout.addWidget(fit_btn)

        zin_btn = QToolButton()
        zin_btn.setIcon(get_icon("fa6s.magnifying-glass-plus"))
        zin_btn.setToolTip("Zoom In")
        zin_btn.clicked.connect(self._on_zoom_in)
        c_layout.addWidget(zin_btn)

        zout_btn = QToolButton()
        zout_btn.setIcon(get_icon("fa6s.magnifying-glass-minus"))
        zout_btn.setToolTip("Zoom Out")
        zout_btn.clicked.connect(self._on_zoom_out)
        c_layout.addWidget(zout_btn)

        c_layout.addStretch()
        right_layout.addWidget(canvas_bar)

        self.canvas = FuselageCanvasWidget()
        self.canvas.vertexSelected.connect(self._on_canvas_vertex_selected)
        self.canvas.vertexMoved.connect(self._on_canvas_vertex_moved)
        self.canvas.vertexDragFinished.connect(self._on_canvas_vertex_drag_finished)
        self.canvas.vertexInserted.connect(self._on_canvas_vertex_inserted)
        self.canvas.vertexDeleteRequested.connect(self._delete_polygon_vertex)
        self.canvas.undoRequested.connect(self.undo_stack.undo)
        self.canvas.redoRequested.connect(self.undo_stack.redo)

        right_layout.addWidget(self.canvas, 1)

        # Metrics Card
        metrics_box = QGroupBox("Section Properties & Engineering Metrics")
        m_layout = QGridLayout(metrics_box)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setHorizontalSpacing(20)
        m_layout.setVerticalSpacing(4)

        self.lbl_area = QLabel("Area: 0.0 mm²")
        self.lbl_perim = QLabel("Perimeter: 0.0 mm")
        self.lbl_dims = QLabel("Dimensions (W × H): 0.0 × 0.0 mm")
        self.lbl_aspect = QLabel("Aspect Ratio (W/H): 0.00")
        self.lbl_cg = QLabel("Centroid (Y, Z): (0.0, 0.0) mm")
        self.lbl_dh = QLabel("Hydraulic Diameter (Dh): 0.0 mm")

        m_layout.addWidget(self.lbl_area, 0, 0)
        m_layout.addWidget(self.lbl_perim, 0, 1)
        m_layout.addWidget(self.lbl_dims, 1, 0)
        m_layout.addWidget(self.lbl_aspect, 1, 1)
        m_layout.addWidget(self.lbl_cg, 2, 0)
        m_layout.addWidget(self.lbl_dh, 2, 1)

        right_layout.addWidget(metrics_box)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        main_layout.addWidget(splitter, 1)

        # 3. Bottom Action Buttons
        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)

        btn_layout.addStretch()

        self.apply_btn = QPushButton("Apply")
        set_native_button(self.apply_btn, "fa6s.check")
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.apply_btn)

        self.ok_btn = QPushButton("Save & Close")
        set_button_role(self.ok_btn, "primary", "fa6s.floppy-disk")
        self.ok_btn.clicked.connect(self._on_ok_clicked)
        btn_layout.addWidget(self.ok_btn)

        self.close_btn = QPushButton("Cancel")
        self.close_btn.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.close_btn)

        main_layout.addWidget(btn_bar)

        self._populate_segments()
        self._load_section(auto_fit=self._auto_fit_sections)

    # -------------------------------------------------------------------------
    # Population & Section Loading
    # -------------------------------------------------------------------------
    def _segments(self) -> list[dict[str, Any]]:
        params = self._component.get("parameters")
        params = params if isinstance(params, dict) else {}
        geom = params.get("geometry")
        geom = geom if isinstance(geom, dict) else {}
        segs = geom.get("segments")
        if not isinstance(segs, list):
            segs = []
            geom["segments"] = segs
            params["geometry"] = geom
            self._component["parameters"] = params
        return [s for s in segs if isinstance(s, dict)]

    def _current_segment(self) -> dict[str, Any] | None:
        segs = self._segments()
        if 0 <= self._segment_index < len(segs):
            return segs[self._segment_index]
        return None

    def _sections(self) -> list[dict[str, Any]]:
        seg = self._current_segment()
        if not seg:
            return []
        secs = seg.get("sections")
        if not isinstance(secs, list):
            secs = []
            seg["sections"] = secs
        return [s for s in secs if isinstance(s, dict)]

    def _current_section(self) -> dict[str, Any] | None:
        secs = self._sections()
        if 0 <= self._section_index < len(secs):
            return secs[self._section_index]
        return None

    def _populate_segments(self) -> None:
        self._loading = True
        self.segment_combo.clear()
        segs = self._segments()
        for idx, seg in enumerate(segs):
            tag = str(seg.get("tag") or f"Segment {idx+1}")
            self.segment_combo.addItem(f"{idx+1}: {tag}")
        if 0 <= self._segment_index < len(segs):
            self.segment_combo.setCurrentIndex(self._segment_index)
        self._loading = False

    def _load_section(self, auto_fit: bool = False) -> None:
        self._loading = True
        secs = self._sections()
        num_secs = len(secs)

        if num_secs == 0:
            self.section_label.setText("No Sections")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self._loading = False
            return

        self._section_index = max(0, min(self._section_index, num_secs - 1))
        sec = secs[self._section_index]

        pos = sec.get("position", {}) if isinstance(sec.get("position"), dict) else {}
        x_val = float(pos.get("x", 0.0))
        self.section_label.setText(f"Section {self._section_index + 1} of {num_secs} (X = {x_val:.1f} mm)")

        self.prev_btn.setEnabled(self._section_index > 0)
        self.next_btn.setEnabled(self._section_index < num_secs - 1)

        prof = sec.get("profile", {}) if isinstance(sec.get("profile"), dict) else {}
        prof_type = str(prof.get("type", "circle")).lower()

        idx = self.profile_type_combo.findText(prof_type)
        if idx >= 0:
            self.profile_type_combo.setCurrentIndex(idx)

        self._populate_props_table(prof)
        self._populate_transform_table(sec)

        prev_prof = secs[self._section_index - 1].get("profile") if self._section_index > 0 else None
        next_prof = secs[self._section_index + 1].get("profile") if self._section_index < num_secs - 1 else None

        title_str = f"Sec {self._section_index + 1} / {num_secs}"
        self.canvas.set_section_data(prof, prev_prof, next_prof, title_info=title_str, auto_fit=auto_fit)
        self._update_metrics_labels()
        self._loading = False

    def _populate_props_table(self, profile: dict[str, Any]) -> None:
        prof_type = str(profile.get("type", "circle")).lower()
        self.props_table.setRowCount(0)

        is_polygon = prof_type == "polygon"
        self.poly_box.setVisible(is_polygon)
        self.props_table.setVisible(not is_polygon)

        if prof_type == "circle":
            self._add_prop_row("Diameter (mm)", profile.get("diameter", 100.0), "diameter")
        elif prof_type == "ellipse":
            self._add_prop_row("Width (mm)", profile.get("width", 120.0), "width")
            self._add_prop_row("Height (mm)", profile.get("height", 80.0), "height")
        elif prof_type == "rectangle":
            self._add_prop_row("Width (mm)", profile.get("width", 120.0), "width")
            self._add_prop_row("Height (mm)", profile.get("height", 80.0), "height")
            self._add_prop_row("Corner Radius (mm)", profile.get("corner_radius", 10.0), "corner_radius")
        elif prof_type == "trapezoid":
            self._add_prop_row("Top Width (mm)", profile.get("top_width", 80.0), "top_width")
            self._add_prop_row("Bottom Width (mm)", profile.get("bottom_width", 120.0), "bottom_width")
            self._add_prop_row("Height (mm)", profile.get("height", 80.0), "height")
            self._add_prop_row("Corner Radius (mm)", profile.get("corner_radius", 5.0), "corner_radius")
        elif prof_type == "triangle":
            self._add_prop_row("Base Width (mm)", profile.get("base_width", 100.0), "base_width")
            self._add_prop_row("Height (mm)", profile.get("height", 80.0), "height")
            self._add_prop_row("Corner Radius (mm)", profile.get("corner_radius", 5.0), "corner_radius")
            self._add_prop_row("Orientation", profile.get("orientation", "up"), "orientation")
        elif prof_type == "polygon":
            self._populate_vertices_table(profile)

    def _add_prop_row(self, label: str, value: Any, key: str) -> None:
        row = self.props_table.rowCount()
        self.props_table.insertRow(row)

        lbl_item = QTableWidgetItem(label)
        lbl_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        lbl_item.setData(Qt.ItemDataRole.UserRole, key)
        self.props_table.setItem(row, 0, lbl_item)

        if key == "orientation":
            combo = NoWheelComboBox(self.props_table)
            combo.addItems(["up", "down"])
            combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(lambda txt, k=key: self._on_prop_spin_changed(k, txt))
            self.props_table.setCellWidget(row, 1, combo)
        else:
            try:
                num_val = float(value)
            except (ValueError, TypeError):
                num_val = 0.0
            step_val = 5.0 if any(sub in key for sub in ("width", "height", "diameter", "radius")) else 1.0
            set_table_spinbox(
                self.props_table,
                row,
                1,
                num_val,
                min_val=0.0,
                step=step_val,
                decimals=2,
                suffix="mm",
                on_changed=lambda _v, k=key: self._on_prop_spin_changed(k, _v),
            )

    def _on_prop_spin_changed(self, key: str, new_val: Any) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict):
            return
        old_val = prof.get(key)
        if old_val == new_val:
            return
        cmd = ChangePropertyCommand(self, key, old_val, new_val)
        self.undo_stack.push(cmd)

    def _populate_vertices_table(self, profile: dict[str, Any]) -> None:
        self.vertices_table.setRowCount(0)
        raw_v = profile.get("vertices")
        if not isinstance(raw_v, list):
            return

        for r, v in enumerate(raw_v):
            if not isinstance(v, dict):
                continue
            row = self.vertices_table.rowCount()
            self.vertices_table.insertRow(row)

            set_table_spinbox(
                self.vertices_table,
                row,
                0,
                float(v.get("y", 0.0)),
                step=1.0,
                decimals=2,
                suffix="mm",
                on_changed=lambda val, row_idx=row: self._on_vertex_cell_spin_changed(row_idx, "y", val),
            )
            set_table_spinbox(
                self.vertices_table,
                row,
                1,
                float(v.get("z", 0.0)),
                step=1.0,
                decimals=2,
                suffix="mm",
                on_changed=lambda val, row_idx=row: self._on_vertex_cell_spin_changed(row_idx, "z", val),
            )
            set_table_spinbox(
                self.vertices_table,
                row,
                2,
                float(v.get("radius", 0.0)),
                min_val=0.0,
                step=0.5,
                decimals=2,
                suffix="mm",
                on_changed=lambda val, row_idx=row: self._on_vertex_cell_spin_changed(row_idx, "radius", val),
            )

        # Restore row selection if any
        if self.canvas.selected_vertex_index is not None and 0 <= self.canvas.selected_vertex_index < len(raw_v):
            self.vertices_table.selectRow(self.canvas.selected_vertex_index)

    def _on_vertex_cell_spin_changed(self, row: int, key: str, value: float) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list) or not (0 <= row < len(verts)):
            return
        old_val = float(verts[row].get(key, 0.0))
        if abs(value - old_val) < 1e-4:
            return
        verts[row][key] = float(value)
        self._refresh_canvas_and_metrics()

    def _populate_transform_table(self, section: dict[str, Any]) -> None:
        pos = section.get("position", {}) if isinstance(section.get("position"), dict) else {}
        rot = section.get("rotation", {}) if isinstance(section.get("rotation"), dict) else {}

        rotation_aliases = {"x": "roll", "y": "pitch", "z": "yaw"}
        for col, axis in enumerate(("x", "y", "z")):
            set_table_spinbox(
                self.trans_table,
                0,
                col,
                float(pos.get(axis, 0.0)),
                step=5.0,
                decimals=2,
                suffix="mm",
                on_changed=lambda _v: self._on_transform_spinbox_changed(),
            )
            set_table_spinbox(
                self.trans_table,
                1,
                col,
                float(rot.get(axis, rot.get(rotation_aliases[axis], 0.0))),
                min_val=-360.0,
                max_val=360.0,
                step=1.0,
                decimals=2,
                suffix="°",
                on_changed=lambda _v: self._on_transform_spinbox_changed(),
            )

    def _on_transform_spinbox_changed(self) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        pos = sec.get("position") if isinstance(sec.get("position"), dict) else {}
        rotation: dict[str, float] = {}

        for col, axis in enumerate(("x", "y", "z")):
            w_pos = self.trans_table.cellWidget(0, col)
            if isinstance(w_pos, QDoubleSpinBox):
                pos[axis] = float(w_pos.value())
            w_rot = self.trans_table.cellWidget(1, col)
            if isinstance(w_rot, QDoubleSpinBox):
                rotation[axis] = float(w_rot.value())
        sec["position"] = pos
        sec["rotation"] = rotation
        self._refresh_canvas_and_metrics()

    def _update_metrics_labels(self) -> None:
        m = self.canvas._metrics
        if not m or m.get("area", 0) <= 0:
            self.lbl_area.setText("Area: 0.0 mm²")
            self.lbl_perim.setText("Perimeter: 0.0 mm")
            self.lbl_dims.setText("Dimensions (W × H): 0.0 × 0.0 mm")
            self.lbl_aspect.setText("Aspect Ratio (W/H): 0.00")
            self.lbl_cg.setText("Centroid (Y, Z): (0.0, 0.0) mm")
            self.lbl_dh.setText("Hydraulic Diameter (Dh): 0.0 mm")
            return

        area_mm2 = m["area"]
        area_dm2 = area_mm2 / 10000.0
        self.lbl_area.setText(f"Area: {area_mm2:,.1f} mm² ({area_dm2:.3f} dm²)")
        self.lbl_perim.setText(f"Perimeter: {m['perimeter']:,.1f} mm")
        self.lbl_dims.setText(f"Dimensions (W × H): {m['width']:.1f} × {m['height']:.1f} mm")
        self.lbl_aspect.setText(f"Aspect Ratio (W/H): {m['aspect_ratio']:.2f}")
        self.lbl_cg.setText(f"Centroid (Y, Z): ({m['y_cg']:.1f}, {m['z_cg']:.1f}) mm")
        self.lbl_dh.setText(f"Hydraulic Diameter (Dh): {m['hydraulic_diam']:.1f} mm")

    # -------------------------------------------------------------------------
    # Undo / Redo Internal Application Methods
    # -------------------------------------------------------------------------
    def _apply_vertex_pos(self, vertex_idx: int, y: float, z: float) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if isinstance(verts, list) and 0 <= vertex_idx < len(verts):
            verts[vertex_idx]["y"] = y
            verts[vertex_idx]["z"] = z
            self._loading = True
            if vertex_idx < self.vertices_table.rowCount():
                wy = self.vertices_table.cellWidget(vertex_idx, 0)
                if isinstance(wy, QDoubleSpinBox):
                    wy.setValue(y)
                wz = self.vertices_table.cellWidget(vertex_idx, 1)
                if isinstance(wz, QDoubleSpinBox):
                    wz.setValue(z)
            self._loading = False
            self._refresh_canvas_and_metrics()

    def _insert_vertex_internal(self, insert_idx: int, vertex_data: dict[str, float]) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list):
            verts = []
            prof["vertices"] = verts
        insert_idx = max(0, min(insert_idx, len(verts)))
        verts.insert(insert_idx, copy.deepcopy(vertex_data))
        self.canvas.selected_vertex_index = insert_idx
        self._populate_vertices_table(prof)
        self._refresh_canvas_and_metrics()

    def _remove_vertex_internal(self, delete_idx: int) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if isinstance(verts, list) and 0 <= delete_idx < len(verts):
            verts.pop(delete_idx)
            self.canvas.selected_vertex_index = min(delete_idx, len(verts) - 1) if verts else None
            self._populate_vertices_table(prof)
            self._refresh_canvas_and_metrics()

    def _apply_profile_property(self, key: str, value: Any) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict):
            return
        prof[key] = value
        self._populate_props_table(prof)
        self._refresh_canvas_and_metrics()

    def _apply_full_profile(self, profile: dict[str, Any]) -> None:
        sec = self._current_section()
        if not sec:
            return
        sec["profile"] = copy.deepcopy(profile)
        prof_type = str(profile.get("type", "circle")).lower()
        idx = self.profile_type_combo.findText(prof_type)
        self._loading = True
        if idx >= 0:
            self.profile_type_combo.setCurrentIndex(idx)
        self._populate_props_table(profile)
        self._loading = False
        self._refresh_canvas_and_metrics()

    # -------------------------------------------------------------------------
    # Interactive Canvas Signals
    # -------------------------------------------------------------------------
    def _on_canvas_vertex_selected(self, index: int) -> None:
        if 0 <= index < self.vertices_table.rowCount():
            self._loading = True
            self.vertices_table.selectRow(index)
            self._loading = False

    def _on_canvas_vertex_moved(self, index: int, y: float, z: float) -> None:
        if 0 <= index < self.vertices_table.rowCount():
            self._loading = True
            wy = self.vertices_table.cellWidget(index, 0)
            if isinstance(wy, QDoubleSpinBox):
                wy.setValue(y)
            wz = self.vertices_table.cellWidget(index, 1)
            if isinstance(wz, QDoubleSpinBox):
                wz.setValue(z)
            self._loading = False
            self._update_metrics_labels()

    def _on_canvas_vertex_drag_finished(self, index: int, old_y: float, old_z: float, new_y: float, new_z: float) -> None:
        cmd = MoveVertexCommand(self, index, (old_y, old_z), (new_y, new_z))
        self.undo_stack.push(cmd)

    def _on_canvas_vertex_inserted(self, insert_idx: int, y: float, z: float) -> None:
        v_data = {"y": y, "z": z, "radius": 0.0}
        cmd = AddVertexCommand(self, insert_idx, v_data)
        self.undo_stack.push(cmd)

    def _on_vertices_row_selected(self, row: int, _column: int, *_previous: int) -> None:
        if self._loading:
            return
        self.canvas.set_selected_vertex(row if row >= 0 else None)

    # -------------------------------------------------------------------------
    # Navigation & Table Change Handlers
    # -------------------------------------------------------------------------
    def _on_segment_combo_changed(self, index: int) -> None:
        if self._loading:
            return
        self._segment_index = index
        self._section_index = 0
        self._load_section(auto_fit=self._auto_fit_sections)

    def _on_prev_section(self) -> None:
        if self._section_index > 0:
            self._section_index -= 1
            self._load_section(auto_fit=False)

    def _on_next_section(self) -> None:
        if self._section_index < len(self._sections()) - 1:
            self._section_index += 1
            self._load_section(auto_fit=False)

    def _on_profile_type_changed(self, new_type: str) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        old_prof = copy.deepcopy(sec.get("profile", {}))
        new_prof = copy.deepcopy(old_prof)
        new_prof["type"] = new_type

        if new_type == "circle" and "diameter" not in new_prof:
            new_prof["diameter"] = 100.0
        elif new_type in ("ellipse", "rectangle") and ("width" not in new_prof or "height" not in new_prof):
            new_prof["width"] = 120.0
            new_prof["height"] = 80.0
            if new_type == "rectangle":
                new_prof["corner_radius"] = 10.0
        elif new_type == "trapezoid" and "top_width" not in new_prof:
            new_prof["top_width"] = 80.0
            new_prof["bottom_width"] = 120.0
            new_prof["height"] = 80.0
            new_prof["corner_radius"] = 5.0
        elif new_type == "triangle" and "base_width" not in new_prof:
            new_prof["base_width"] = 100.0
            new_prof["height"] = 80.0
            new_prof["corner_radius"] = 5.0
            new_prof["orientation"] = "up"
        elif new_type == "polygon" and "vertices" not in new_prof:
            new_prof["vertices"] = [
                {"y": -50.0, "z": -40.0, "radius": 10.0},
                {"y": 50.0, "z": -40.0, "radius": 10.0},
                {"y": 60.0, "z": 40.0, "radius": 15.0},
                {"y": -60.0, "z": 40.0, "radius": 15.0},
            ]

        cmd = ChangeProfileTypeCommand(self, old_prof, new_prof)
        self.undo_stack.push(cmd)

    def _on_prop_table_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict):
            return

        key_item = self.props_table.item(row, 0)
        val_item = self.props_table.item(row, 1)
        if not key_item or not val_item:
            return

        key = key_item.data(Qt.ItemDataRole.UserRole)
        val_text = val_item.text().strip()
        old_val = prof.get(key)

        try:
            new_val = float(val_text)
        except ValueError:
            new_val = val_text

        if old_val == new_val:
            return

        cmd = ChangePropertyCommand(self, key, old_val, new_val)
        self.undo_stack.push(cmd)

    def _on_vertices_cell_changed(self, row: int, column: int) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list) or not (0 <= row < len(verts)):
            return

        item = self.vertices_table.item(row, column)
        if not item:
            return

        try:
            val = float(item.text())
        except ValueError:
            val = 0.0

        key = ["y", "z", "radius"][column]
        old_val = verts[row].get(key, 0.0)
        if abs(val - old_val) < 1e-4:
            return

        verts[row][key] = val
        self._refresh_canvas_and_metrics()

    def _add_polygon_vertex(self) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list):
            verts = []
            prof["vertices"] = verts

        # If a vertex is selected, insert after it, else append
        curr_row = self.vertices_table.currentRow()
        insert_idx = (curr_row + 1) if 0 <= curr_row < len(verts) else len(verts)

        # Default position: offset from previous or (0, 0)
        if verts and 0 <= curr_row < len(verts):
            ref_y = float(verts[curr_row].get("y", 0.0))
            ref_z = float(verts[curr_row].get("z", 0.0))
            v_data = {"y": round(ref_y + 10.0, 1), "z": round(ref_z + 10.0, 1), "radius": 0.0}
        else:
            v_data = {"y": 0.0, "z": 0.0, "radius": 0.0}

        cmd = AddVertexCommand(self, insert_idx, v_data)
        self.undo_stack.push(cmd)

    def _delete_polygon_vertex(self, delete_idx: int | None = None) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile")
        if not isinstance(prof, dict) or prof.get("type") != "polygon":
            return
        verts = prof.get("vertices")
        if not isinstance(verts, list) or len(verts) <= 3:
            return

        if delete_idx is None or not (0 <= delete_idx < len(verts)):
            curr_row = self.vertices_table.currentRow()
            delete_idx = curr_row if 0 <= curr_row < len(verts) else (len(verts) - 1)

        v_data = verts[delete_idx]
        cmd = DeleteVertexCommand(self, delete_idx, v_data)
        self.undo_stack.push(cmd)

    def _on_transform_cell_changed(self, row: int, column: int) -> None:
        if self._loading:
            return
        sec = self._current_section()
        if not sec:
            return
        item = self.trans_table.item(row, column)
        if not item:
            return

        try:
            val = float(item.text().strip())
        except ValueError:
            val = 0.0

        key_axis = ["x", "y", "z"][column]
        if row == 0:
            pos = sec.get("position")
            if not isinstance(pos, dict):
                pos = {}
                sec["position"] = pos
            pos[key_axis] = val
        else:
            rot = sec.get("rotation")
            if not isinstance(rot, dict):
                rot = {}
            canonical_rotation = {
                "x": float(rot.get("x", rot.get("roll", 0.0))),
                "y": float(rot.get("y", rot.get("pitch", 0.0))),
                "z": float(rot.get("z", rot.get("yaw", 0.0))),
            }
            canonical_rotation[key_axis] = val
            sec["rotation"] = canonical_rotation

    def _on_display_option_toggled(self) -> None:
        self.canvas.show_previous = self.cb_prev.isChecked()
        self.canvas.show_next = self.cb_next.isChecked()
        self.canvas.show_dimensions = self.cb_dims.isChecked()
        self.canvas.show_centroid = self.cb_cg.isChecked()
        self.canvas.show_grid = self.cb_grid.isChecked()
        self.canvas.show_radial_samples = self.cb_radial.isChecked()
        self.canvas.update()

    def _on_fit_view(self) -> None:
        self.canvas.fit_view()

    def _on_zoom_in(self) -> None:
        self.canvas.zoom_in()

    def _on_zoom_out(self) -> None:
        self.canvas.zoom_out()

    def _refresh_canvas_and_metrics(self) -> None:
        sec = self._current_section()
        if not sec:
            return
        prof = sec.get("profile", {}) if isinstance(sec.get("profile"), dict) else {}
        secs = self._sections()
        prev_prof = secs[self._section_index - 1].get("profile") if self._section_index > 0 else None
        next_prof = secs[self._section_index + 1].get("profile") if self._section_index < len(secs) - 1 else None

        title_str = f"Sec {self._section_index + 1} / {len(secs)}"
        self.canvas.set_section_data(prof, prev_prof, next_prof, title_info=title_str, auto_fit=False)
        self._update_metrics_labels()

    def _on_apply_clicked(self) -> None:
        """Trigger project mutation to update 3D scene while keeping dialog open."""
        after_data = copy.deepcopy(self._component)
        self._component.clear()
        self._component.update(self._original_component)
        self._api.edit_component(
            self._component,
            f"Edit fuselage section {self._section_index + 1}",
            lambda: self._component.update(after_data),
        )
        self._original_component = copy.deepcopy(self._component)

    def _on_ok_clicked(self) -> None:
        """Apply changes and close dialog."""
        after_data = copy.deepcopy(self._component)
        self._component.clear()
        self._component.update(self._original_component)
        self._api.edit_component(
            self._component,
            f"Edit fuselage section {self._section_index + 1}",
            lambda: self._component.update(after_data),
        )
        self.accept()

    def _on_cancel_clicked(self) -> None:
        """Discard changes and restore original component state."""
        self._component.clear()
        self._component.update(self._original_component)
        if self._api.current_project:
            self._api.edit_component(
                self._component,
                "Cancel fuselage section edit",
                lambda: None,
            )
        self.reject()
