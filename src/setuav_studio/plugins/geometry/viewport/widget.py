from array import array
import math

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QMatrix4x4, QPainter, QPalette, QSurfaceFormat, QVector3D, QVector4D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFunctions_3_3_Core,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from ..engine.data import GeometryData, Point3D
from .mesh import (
    FACE_COLORED,
    FACE_MONOCHROME,
    FACE_TRANSPARENT,
    build_component_wire_vertices,
    build_loft_solid_vertices,
    build_loft_wire_vertices,
    build_section_ring_vertices,
    hit_test_loft,
)

import logging


logger = logging.getLogger(__name__)


WIREFRAME = "wireframe"
SOLID = "solid"
SOLID_WIRE = "solid+wire"

_GL_COLOR_BUFFER_BIT = 0x00004000
_GL_DEPTH_BUFFER_BIT = 0x00000100
_GL_DEPTH_TEST = 0x0B71
_GL_LEQUAL = 0x0203
_GL_LESS = 0x0201
_GL_FLOAT = 0x1406
_GL_LINES = 0x0001
_GL_POLYGON_OFFSET_FILL = 0x8037
_GL_TRIANGLES = 0x0004
_GL_BLEND = 0x0BE2
_GL_SRC_ALPHA = 0x0302
_GL_ONE_MINUS_SRC_ALPHA = 0x0303

_WIRE_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec3 color;
uniform mat4 mvp;
out vec3 vertexColor;
void main() {
    gl_Position = mvp * vec4(position, 1.0);
    vertexColor = color;
}
"""

_WIRE_FRAGMENT_SHADER = """
#version 330 core
in vec3 vertexColor;
uniform float alpha;
out vec4 fragmentColor;
void main() {
    fragmentColor = vec4(vertexColor, alpha);
}
"""

_SOLID_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec3 normal;
layout(location = 2) in vec3 color;
uniform mat4 mvp;
out vec3 vertexNormal;
out vec3 vertexColor;
void main() {
    gl_Position = mvp * vec4(position, 1.0);
    vertexNormal = normal;
    vertexColor = color;
}
"""

_SOLID_FRAGMENT_SHADER = """
#version 330 core
in vec3 vertexNormal;
in vec3 vertexColor;
uniform vec3 eyeDirection;
uniform float alpha;
out vec4 fragmentColor;
void main() {
    vec3 normal = normalize(vertexNormal);
    vec3 eye = normalize(eyeDirection);
    float diffuse = abs(dot(normal, eye));
    vec3 shaded = vertexColor * (0.45 + 0.55 * diffuse);
    float specular = pow(max(diffuse, 0.0), 32.0) * 0.04;
    shaded += vec3(specular);
    fragmentColor = vec4(shaded, alpha);
}
"""


def _add_reference_line(vertices: list[float], start, end, color) -> None:
    vertices.extend((*start, *color, *end, *color))


def _cross(left: Point3D, right: Point3D) -> Point3D:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


class OpenGLViewer(QOpenGLWidget):
    componentPicked = Signal(object)

    def __init__(self, parent=None) -> None:
        surface_format = QSurfaceFormat.defaultFormat()
        surface_format.setDepthBufferSize(24)
        surface_format.setStencilBufferSize(8)
        surface_format.setSamples(0)
        super().__init__(parent)
        self.setFormat(surface_format)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._initialization_error: str | None = None
        self._mesh_dirty = True

        self._functions: QOpenGLFunctions_3_3_Core | None = None
        self._wire_program: QOpenGLShaderProgram | None = None
        self._solid_program: QOpenGLShaderProgram | None = None
        self._wire_vao = QOpenGLVertexArrayObject()
        self._wire_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._solid_vao = QOpenGLVertexArrayObject()
        self._solid_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._grid_vao = QOpenGLVertexArrayObject()
        self._grid_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._axis_vao = QOpenGLVertexArrayObject()
        self._axis_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._highlight_vao = QOpenGLVertexArrayObject()
        self._highlight_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._section_ring_vao = QOpenGLVertexArrayObject()
        self._section_ring_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._wire_count = 0
        self._solid_count = 0
        self._grid_count = 0
        self._axis_count = 0
        self._highlight_count = 0
        self._section_ring_count = 0
        self._show_solid = True
        self._show_wireframe = True
        self._show_grid = True
        self._mode = SOLID_WIRE
        self._face_style = FACE_COLORED
        self._transparent = False
        # Aircraft inspection benefits from a distortion-free technical
        # view: parallel edges stay parallel and front/rear dimensions remain
        # visually comparable while orbiting the model.
        self._orthographic = True
        self._geometry_data = GeometryData()
        self._selected_component_id: str | None = None
        self._hovered_component_id: str | None = None
        self._section_selection: tuple[str, int, int] | None = None

        self._azimuth = 30.0
        self._elevation = 20.0
        self._distance = 1500.0
        self._target = QVector3D(400.0, 0.0, 0.0)
        self._last_mouse = QPoint()
        self._press_position = QPoint()
        self._press_button = Qt.MouseButton.NoButton

    def initializeGL(self) -> None:
        try:
            functions = QOpenGLFunctions_3_3_Core()
            if not functions.initializeOpenGLFunctions():
                raise RuntimeError("OpenGL 3.3 functions are unavailable")
            self._functions = functions
            functions.glClearColor(0.12, 0.12, 0.12, 1.0)
            functions.glEnable(_GL_DEPTH_TEST)
            functions.glLineWidth(1.0)

            self._wire_program = self._create_program(
                _WIRE_VERTEX_SHADER,
                _WIRE_FRAGMENT_SHADER,
            )
            self._solid_program = self._create_program(
                _SOLID_VERTEX_SHADER,
                _SOLID_FRAGMENT_SHADER,
            )
            for vao, vbo in (
                (self._wire_vao, self._wire_vbo),
                (self._grid_vao, self._grid_vbo),
                (self._axis_vao, self._axis_vbo),
                (self._highlight_vao, self._highlight_vbo),
                (self._section_ring_vao, self._section_ring_vbo),
            ):
                self._setup_buffer(vao, vbo, self._wire_program, 6, ((0, 0, 3), (1, 3, 3)))
            self._setup_buffer(
                self._solid_vao,
                self._solid_vbo,
                self._solid_program,
                9,
                ((0, 0, 3), (1, 3, 3), (2, 6, 3)),
            )
            self._upload_meshes()
            self._mesh_dirty = False
            self._initialization_error = None
            context = self.context()
            if context is not None:
                context.aboutToBeDestroyed.connect(self._release_resources)
        except Exception as exc:
            self._functions = None
            self._wire_program = None
            self._solid_program = None
            self._initialization_error = str(exc)
            logger.exception("Geometry OpenGL viewer initialization failed")
            QTimer.singleShot(0, self.update)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(250, self._check_context)

    def _check_context(self) -> None:
        if self.isVisible() and not self.isValid() and self._initialization_error is None:
            self._initialization_error = "OpenGL context could not be created"
            logger.error("Geometry OpenGL viewer context is invalid")
            self.update()

    def paintEvent(self, event) -> None:
        if self._initialization_error is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Base))
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(
            self.rect().adjusted(24, 24, -24, -24),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "3D viewer could not be initialized.\n"
            f"{self._initialization_error}\n\n"
            "OpenGL 3.3 or newer is required.",
        )

    def resizeGL(self, width: int, height: int) -> None:
        if self._functions is not None:
            self._functions.glViewport(0, 0, width, height)

    def paintGL(self) -> None:
        if self._functions is None:
            return
        if self._mesh_dirty:
            try:
                self._upload_meshes()
                self._mesh_dirty = False
            except Exception:
                # Keep the data dirty so a later, valid paint context can
                # retry instead of leaving the viewer permanently empty.
                logger.exception("Geometry OpenGL mesh upload failed")
        from setuav_studio.ui.theme import is_light_theme, tokens

        tok = tokens()
        is_light = is_light_theme()
        bg_hex = tok.get("plot", "#ffffff" if is_light else "#141414")
        from PySide6.QtGui import QColor

        qbg = QColor(bg_hex)
        self._functions.glClearColor(qbg.redF(), qbg.greenF(), qbg.blueF(), 1.0)
        self._functions.glClear(_GL_COLOR_BUFFER_BIT | _GL_DEPTH_BUFFER_BIT)
        mvp = self._projection() * self._view()

        lines_overlay = (self._show_wireframe and self._wire_count > 0) or self._highlight_count > 0 or self._section_ring_count > 0
        if self._show_solid and self._solid_program is not None:
            eye_direction = self._eye_position() - self._target
            eye_direction.normalize()
            if lines_overlay:
                self._functions.glEnable(_GL_POLYGON_OFFSET_FILL)
                self._functions.glPolygonOffset(1.0, 1.0)
            self._solid_program.bind()
            self._solid_program.setUniformValue("mvp", mvp)
            self._solid_program.setUniformValue("eyeDirection", eye_direction)
            transparent = self._transparent or (self._face_style == FACE_TRANSPARENT)
            alpha_location = self._solid_program.uniformLocation("alpha")
            self._functions.glUniform1f(
                alpha_location,
                0.35 if transparent else 1.0,
            )
            if transparent:
                self._functions.glEnable(_GL_BLEND)
                self._functions.glBlendFunc(_GL_SRC_ALPHA, _GL_ONE_MINUS_SRC_ALPHA)
                self._functions.glDepthMask(False)
            self._solid_vao.bind()
            self._functions.glDrawArrays(_GL_TRIANGLES, 0, self._solid_count)
            self._solid_vao.release()
            self._solid_program.release()
            if transparent:
                self._functions.glDepthMask(True)
                self._functions.glDisable(_GL_BLEND)
            if lines_overlay:
                self._functions.glDisable(_GL_POLYGON_OFFSET_FILL)

        if self._wire_program is None:
            return
        self._wire_program.bind()
        self._wire_program.setUniformValue("mvp", mvp)
        alpha_location = self._wire_program.uniformLocation("alpha")
        self._functions.glUniform1f(alpha_location, 1.0)
        if self._show_grid:
            self._grid_vao.bind()
            self._functions.glDrawArrays(_GL_LINES, 0, self._grid_count)
            self._grid_vao.release()
        if self._highlight_count > 0:
            self._highlight_vao.bind()
            self._functions.glDrawArrays(_GL_LINES, 0, self._highlight_count)
            self._highlight_vao.release()
        if self._section_ring_count > 0:
            self._section_ring_vao.bind()
            self._functions.glDrawArrays(_GL_LINES, 0, self._section_ring_count)
            self._section_ring_vao.release()
        if self._show_wireframe:
            self._functions.glEnable(_GL_BLEND)
            self._functions.glBlendFunc(_GL_SRC_ALPHA, _GL_ONE_MINUS_SRC_ALPHA)
            self._functions.glUniform1f(alpha_location, 0.9)
            self._wire_vao.bind()
            self._functions.glDrawArrays(_GL_LINES, 0, self._wire_count)
            self._wire_vao.release()
            self._functions.glUniform1f(alpha_location, 1.0)
            self._functions.glDisable(_GL_BLEND)
        self._wire_program.release()
        self._draw_axis_gizmo()

    def _draw_axis_gizmo(self) -> None:
        if self.width() < 1 or self.height() < 1:
            return
        rotation = self._view()
        rotation.setColumn(3, QVector4D(0.0, 0.0, 0.0, 1.0))
        vertices = self._axis_gizmo_quads(rotation)
        if not vertices:
            return
        size = 160
        margin = 12
        x = margin
        y = margin
        self._functions.glViewport(x, y, size, size)
        self._functions.glDisable(_GL_DEPTH_TEST)
        projection = QMatrix4x4()
        projection.ortho(-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)

        count = self._allocate(self._axis_vbo, vertices, 6)
        self._wire_program.bind()
        self._wire_program.setUniformValue("mvp", projection)
        alpha_location = self._wire_program.uniformLocation("alpha")
        self._functions.glUniform1f(alpha_location, 1.0)
        self._axis_vao.bind()
        self._functions.glDrawArrays(_GL_TRIANGLES, 0, count)
        self._axis_vao.release()
        self._wire_program.release()

        self._functions.glEnable(_GL_DEPTH_TEST)
        self._functions.glViewport(0, 0, self.width(), self.height())

    def set_geometry(self, data: GeometryData, fit: bool = False) -> None:
        self._geometry_data = data
        if fit:
            self.fit_view()
        self._update_gpu_meshes()

    def set_selected_component(self, component_id: str | None) -> None:
        if self._selected_component_id == component_id:
            return
        self._selected_component_id = component_id
        self._update_gpu_meshes()

    def set_selected_section(
        self,
        component_id: str | None,
        segment_index: int | None,
        section_index: int | None,
    ) -> None:
        selection = None
        if component_id is not None and segment_index is not None and section_index is not None:
            selection = (component_id, segment_index, section_index)
        if self._section_selection == selection:
            return
        self._section_selection = selection
        self._update_gpu_meshes()

    def set_show_solid(self, show: bool) -> None:
        self._show_solid = show
        self._sync_mode()
        self.update()

    def set_show_wireframe(self, show: bool) -> None:
        self._show_wireframe = show
        self._sync_mode()
        self.update()

    def set_show_grid(self, show: bool) -> None:
        self._show_grid = show
        self.update()

    def update_theme_style(self) -> None:
        """Queue palette-dependent GPU data for the next valid paint context."""
        self._mesh_dirty = True
        self.update()

    def set_transparent(self, transparent: bool) -> None:
        self._transparent = transparent
        self.update()

    def _sync_mode(self) -> None:
        if self._show_solid and self._show_wireframe:
            self._mode = SOLID_WIRE
        elif self._show_solid:
            self._mode = SOLID
        elif self._show_wireframe:
            self._mode = WIREFRAME

    def set_mode(self, mode: str) -> None:
        if mode not in {WIREFRAME, SOLID, SOLID_WIRE}:
            raise ValueError(f"Unknown viewer mode: {mode}")
        self._mode = mode
        self._show_solid = mode in (SOLID, SOLID_WIRE)
        self._show_wireframe = mode in (WIREFRAME, SOLID_WIRE)
        self.update()

    def set_face_style(self, face_style: str) -> None:
        if face_style == FACE_TRANSPARENT:
            self._transparent = True
        elif face_style in {FACE_COLORED, FACE_MONOCHROME}:
            self._face_style = face_style
        else:
            raise ValueError(f"Unknown face style: {face_style}")
        self._update_gpu_meshes()
        self.update()

    def set_view(self, azimuth: float, elevation: float) -> None:
        self._azimuth = azimuth
        self._elevation = max(-89.0, min(89.0, elevation))
        self.update()

    def fit_view(self) -> None:
        points = list(self._geometry_data.points())
        if not points:
            self._target = QVector3D(0.0, 0.0, 0.0)
            self._distance = 1500.0
            self.update()
            return
        minimum = [min(point[axis] for point in points) for axis in range(3)]
        maximum = [max(point[axis] for point in points) for axis in range(3)]
        centre = [(minimum[axis] + maximum[axis]) * 0.5 for axis in range(3)]
        azimuth = math.radians(self._azimuth)
        elevation = math.radians(self._elevation)
        eye_direction = (
            math.cos(elevation) * math.sin(azimuth),
            math.cos(elevation) * math.cos(azimuth),
            math.sin(elevation),
        )
        right = _cross(eye_direction, (0.0, 0.0, 1.0))
        right_length = math.sqrt(
            right[0] * right[0] + right[1] * right[1] + right[2] * right[2]
        )
        if right_length < 1e-6:
            right = (1.0, 0.0, 0.0)
        else:
            right = (
                right[0] / right_length,
                right[1] / right_length,
                right[2] / right_length,
            )
        up = _cross(right, eye_direction)
        width = 0.0
        height = 0.0
        depth = 0.0
        for point in points:
            offset = (
                point[0] - centre[0],
                point[1] - centre[1],
                point[2] - centre[2],
            )
            width = max(width, abs(offset[0] * right[0] + offset[1] * right[1] + offset[2] * right[2]))
            height = max(height, abs(offset[0] * up[0] + offset[1] * up[1] + offset[2] * up[2]))
            depth = max(depth, abs(offset[0] * eye_direction[0] + offset[1] * eye_direction[1] + offset[2] * eye_direction[2]))
        fov = math.radians(45.0)
        aspect = self.width() / max(1, self.height())
        distance = max(
            width / (math.tan(fov * 0.5) * aspect),
            height / math.tan(fov * 0.5),
        ) + depth
        self._target = QVector3D(*centre)
        self._distance = max(100.0, distance * 1.35)
        self.update()

    def mousePressEvent(self, event) -> None:
        self._last_mouse = event.position().toPoint()
        self._press_position = self._last_mouse
        self._press_button = event.button()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_button == Qt.MouseButton.LeftButton:
            delta = event.position().toPoint() - self._press_position
            if delta.manhattanLength() <= 4:
                self._pick(self._press_position)
        self._press_button = Qt.MouseButton.NoButton
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:
        current = event.position().toPoint()
        dx = current.x() - self._last_mouse.x()
        dy = current.y() - self._last_mouse.y()
        self._last_mouse = current
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._azimuth -= dx * 0.4
            self._elevation = max(-89.0, min(89.0, self._elevation + dy * 0.4))
        elif event.buttons() & Qt.MouseButton.MiddleButton:
            azimuth = math.radians(self._azimuth)
            elevation = math.radians(self._elevation)
            right = QVector3D(math.cos(azimuth), -math.sin(azimuth), 0.0)
            up = QVector3D(
                -math.sin(azimuth) * math.sin(elevation),
                -math.cos(azimuth) * math.sin(elevation),
                math.cos(elevation),
            )
            scale = self._distance * 0.001
            self._target -= right * (dx * scale)
            self._target -= up * (dy * scale)
        elif event.buttons() & Qt.MouseButton.RightButton:
            # Match PyVista's trackball-camera controls: dragging upward
            # dollies in, while dragging downward dollies out.  VTK scales
            # the motion against half the viewport height.
            half_height = max(self.height() * 0.5, 1.0)
            zoom_factor = math.pow(1.1, (dy * 10.0) / half_height)
            self._distance *= zoom_factor
            self._distance = max(10.0, min(100_000.0, self._distance))
        else:
            self._pick_hover(current)
        self.update()

    def wheelEvent(self, event) -> None:
        self._distance *= 0.9 if event.angleDelta().y() > 0 else 1.1
        self._distance = max(10.0, min(100_000.0, self._distance))
        self.update()
        event.accept()

    def leaveEvent(self, event) -> None:
        if self._hovered_component_id is not None:
            self._hovered_component_id = None
            self._update_gpu_meshes()
        super().leaveEvent(event)

    def _pick(self, point: QPoint) -> None:
        component_id = None
        if self._solid_count > 0:
            origin, direction = self._screen_ray(point)
            component_id = hit_test_loft(self._geometry_data, origin, direction)
        self.componentPicked.emit(component_id)

    def _pick_hover(self, point: QPoint) -> None:
        component_id = None
        if self._solid_count > 0:
            origin, direction = self._screen_ray(point)
            component_id = hit_test_loft(self._geometry_data, origin, direction)
        if self._hovered_component_id != component_id:
            self._hovered_component_id = component_id
            self._update_gpu_meshes()

    def _screen_ray(self, point: QPoint) -> tuple[Point3D, Point3D]:
        width = max(1, self.width())
        height = max(1, self.height())
        x_ndc = (2.0 * point.x() / width) - 1.0
        y_ndc = 1.0 - (2.0 * point.y() / height)
        inverted, _invertible = (self._projection() * self._view()).inverted()
        near = inverted.map(QVector3D(x_ndc, y_ndc, -1.0))
        far = inverted.map(QVector3D(x_ndc, y_ndc, 1.0))
        direction = far - near
        direction.normalize()
        return (
            (near.x(), near.y(), near.z()),
            (direction.x(), direction.y(), direction.z()),
        )

    def _update_gpu_meshes(self) -> None:
        # Project and selection events may arrive before the widget has a
        # native surface. Upload only from paintGL, where Qt owns the context.
        self._mesh_dirty = True
        self.update()

    def _upload_meshes(self) -> None:
        from PySide6.QtGui import QColor
        from setuav_studio.ui.theme import chart_color, tokens

        def rgb(color: str) -> tuple[float, float, float]:
            value = QColor(color)
            return value.redF(), value.greenF(), value.blueF()

        tok = tokens()
        grid_values = self._reference_grid_vertices()
        wire_values = build_loft_wire_vertices(
            self._geometry_data,
            self._selected_component_id,
            self._hovered_component_id,
            self._face_style,
        )
        solid_values = build_loft_solid_vertices(
            self._geometry_data,
            self._selected_component_id,
            self._hovered_component_id,
            self._face_style,
        )
        highlight_values = build_component_wire_vertices(
            self._geometry_data,
            self._selected_component_id,
            rgb(chart_color("orange")),
        )
        hovered = (
            self._hovered_component_id
            if self._hovered_component_id != self._selected_component_id
            else None
        )
        highlight_values.extend(
            build_component_wire_vertices(
                self._geometry_data,
                hovered,
                rgb(tok["text"]),
            )
        )
        ring_values = []
        if self._section_selection is not None:
            component_id, segment_index, section_index = self._section_selection
            ring_values = build_section_ring_vertices(
                self._geometry_data,
                component_id,
                segment_index,
                section_index,
                rgb(chart_color("orange")),
            )
        self._grid_count = self._allocate(self._grid_vbo, grid_values, 6)
        self._wire_count = self._allocate(self._wire_vbo, wire_values, 6)
        self._solid_count = self._allocate(self._solid_vbo, solid_values, 9)
        self._highlight_count = self._allocate(self._highlight_vbo, highlight_values, 6)
        self._section_ring_count = self._allocate(self._section_ring_vbo, ring_values, 6)

    @staticmethod
    def _allocate(buffer: QOpenGLBuffer, values: list[float], stride: int) -> int:
        data = array("f", values)
        buffer.bind()
        buffer.allocate(data.tobytes(), len(data) * data.itemsize)
        buffer.release()
        return len(data) // stride

    def _create_program(self, vertex_source: str, fragment_source: str) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram(self)
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertex_source):
            raise RuntimeError(f"Vertex shader failed: {program.log()}")
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment_source):
            raise RuntimeError(f"Fragment shader failed: {program.log()}")
        if not program.link():
            raise RuntimeError(f"OpenGL shader link failed: {program.log()}")
        return program

    @staticmethod
    def _setup_buffer(vao, vbo, program, stride, attributes) -> None:
        vao.create()
        vbo.create()
        vao.bind()
        vbo.bind()
        vbo.setUsagePattern(QOpenGLBuffer.UsagePattern.DynamicDraw)
        program.bind()
        for location, offset, size in attributes:
            program.enableAttributeArray(location)
            program.setAttributeBuffer(location, _GL_FLOAT, offset * 4, size, stride * 4)
        program.release()
        vbo.release()
        vao.release()

    @staticmethod
    def _reference_grid_vertices() -> list[float]:
        from setuav_studio.ui.theme import is_light_theme

        is_light = is_light_theme()
        major_col = (0.78, 0.78, 0.78) if is_light else (0.24, 0.24, 0.24)
        minor_col = (0.88, 0.88, 0.88) if is_light else (0.16, 0.16, 0.16)

        vertices: list[float] = []
        for offset in range(-2000, 2001, 100):
            color = major_col if offset % 500 == 0 else minor_col
            _add_reference_line(
                vertices,
                (-2000, offset, 0.0),
                (2000, offset, 0.0),
                color,
            )
            _add_reference_line(
                vertices,
                (offset, -2000, 0.0),
                (offset, 2000, 0.0),
                color,
            )
        return vertices

    @staticmethod
    def _axis_gizmo_quads(rotation: QMatrix4x4) -> list[float]:
        vertices: list[float] = []
        axes = (
            ((0.85, 0.25, 0.25), 0),
            ((0.25, 0.75, 0.35), 1),
            ((0.25, 0.45, 0.90), 2),
        )
        length = 0.65
        half_width = 0.0175
        for color, column_index in axes:
            direction = rotation.column(column_index).toVector3D()
            if abs(direction.x()) < 1e-4 and abs(direction.y()) < 1e-4:
                continue
            perpendicular = QVector3D(-direction.y(), direction.x(), 0.0)
            perpendicular.normalize()
            offset = perpendicular * half_width
            tip = direction * length
            corners = (offset, -offset, tip - offset, tip + offset)
            for a, b, c in ((0, 1, 2), (0, 2, 3)):
                for index in (a, b, c):
                    vertices.extend((*corners[index].toTuple(), *color))
        return vertices

    def _eye_position(self) -> QVector3D:
        azimuth = math.radians(self._azimuth)
        elevation = math.radians(self._elevation)
        return QVector3D(
            self._target.x() + self._distance * math.cos(elevation) * math.sin(azimuth),
            self._target.y() + self._distance * math.cos(elevation) * math.cos(azimuth),
            self._target.z() + self._distance * math.sin(elevation),
        )

    def _view(self) -> QMatrix4x4:
        matrix = QMatrix4x4()
        matrix.lookAt(self._eye_position(), self._target, QVector3D(0.0, 0.0, 1.0))
        return matrix

    def _projection(self) -> QMatrix4x4:
        matrix = QMatrix4x4()
        aspect = self.width() / max(1, self.height())
        if self._orthographic:
            half_height = max(
                self._distance * math.tan(math.radians(45.0) * 0.5),
                1.0,
            )
            half_width = half_height * aspect
            matrix.ortho(
                -half_width,
                half_width,
                -half_height,
                half_height,
                -100_000.0,
                100_000.0,
            )
        else:
            matrix.perspective(45.0, aspect, 1.0, 100_000.0)
        return matrix

    def _release_resources(self) -> None:
        has_context = self.isValid()
        try:
            if has_context:
                self.makeCurrent()
                for buffer in (
                    self._wire_vbo,
                    self._solid_vbo,
                    self._grid_vbo,
                    self._axis_vbo,
                    self._highlight_vbo,
                    self._section_ring_vbo,
                ):
                    if buffer.isCreated():
                        buffer.destroy()
                for vao in (
                    self._wire_vao,
                    self._solid_vao,
                    self._grid_vao,
                    self._axis_vao,
                    self._highlight_vao,
                    self._section_ring_vao,
                ):
                    if vao.isCreated():
                        vao.destroy()
        finally:
            if has_context:
                self.doneCurrent()
            # A QOpenGLWidget can receive a fresh context after native widget
            # or screen changes. Never let wrappers from the old context be
            # reused by the next initializeGL call.
            self._functions = None
            self._wire_program = None
            self._solid_program = None
            self._wire_count = 0
            self._solid_count = 0
            self._grid_count = 0
            self._axis_count = 0
            self._highlight_count = 0
            self._section_ring_count = 0
            self._mesh_dirty = True
