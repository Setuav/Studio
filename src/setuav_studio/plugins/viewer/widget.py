from array import array
import math

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMatrix4x4, QSurfaceFormat, QVector3D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFunctions_3_3_Core,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget


_GL_COLOR_BUFFER_BIT = 0x00004000
_GL_DEPTH_BUFFER_BIT = 0x00000100
_GL_DEPTH_TEST = 0x0B71
_GL_FLOAT = 0x1406
_GL_LINES = 0x0001
_GL_MULTISAMPLE = 0x809D

_VERTEX_SHADER = """
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

_FRAGMENT_SHADER = """
#version 330 core
in vec3 vertexColor;
out vec4 fragmentColor;

void main() {
    fragmentColor = vec4(vertexColor, 1.0);
}
"""


class OpenGLViewer(QOpenGLWidget):
    """OpenGL workspace. Geometry mesh support is added in the next step."""

    def __init__(self, parent=None) -> None:
        surface_format = QSurfaceFormat()
        surface_format.setVersion(3, 3)
        surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        surface_format.setSamples(8)

        super().__init__(parent)
        self.setFormat(surface_format)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._functions: QOpenGLFunctions_3_3_Core | None = None
        self._program: QOpenGLShaderProgram | None = None
        self._vao = QOpenGLVertexArrayObject()
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._vertex_count = 0

        self._azimuth = 35.0
        self._elevation = 25.0
        self._distance = 1800.0
        self._target = QVector3D(0.0, 0.0, 0.0)
        self._last_mouse = QPoint()

    def initializeGL(self) -> None:
        functions = QOpenGLFunctions_3_3_Core()
        if not functions.initializeOpenGLFunctions():
            raise RuntimeError("OpenGL 3.3 core functions are unavailable")
        self._functions = functions

        functions.glClearColor(0.08, 0.08, 0.08, 1.0)
        functions.glEnable(_GL_DEPTH_TEST)
        functions.glEnable(_GL_MULTISAMPLE)

        self._program = self._create_program()
        self._create_reference_geometry()

        context = self.context()
        if context is not None:
            context.aboutToBeDestroyed.connect(self._release_resources)

    def resizeGL(self, width: int, height: int) -> None:
        if self._functions is not None:
            self._functions.glViewport(0, 0, width, height)

    def paintGL(self) -> None:
        if self._functions is None or self._program is None:
            return

        self._functions.glClear(_GL_COLOR_BUFFER_BIT | _GL_DEPTH_BUFFER_BIT)
        self._program.bind()
        self._program.setUniformValue("mvp", self._projection() * self._view())
        self._vao.bind()
        self._functions.glDrawArrays(_GL_LINES, 0, self._vertex_count)
        self._vao.release()
        self._program.release()

    def mousePressEvent(self, event) -> None:
        self._last_mouse = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        current = event.position().toPoint()
        dx = current.x() - self._last_mouse.x()
        dy = current.y() - self._last_mouse.y()
        self._last_mouse = current

        if event.buttons() & Qt.MouseButton.LeftButton:
            self._azimuth -= dx * 0.4
            self._elevation = max(
                -89.0,
                min(89.0, self._elevation + dy * 0.4),
            )
        elif event.buttons() & Qt.MouseButton.MiddleButton:
            azimuth = math.radians(self._azimuth)
            right = QVector3D(math.cos(azimuth), -math.sin(azimuth), 0.0)
            scale = self._distance * 0.001
            self._target -= right * (dx * scale)
            self._target += QVector3D(0.0, 0.0, 1.0) * (dy * scale)
        self.update()

    def wheelEvent(self, event) -> None:
        self._distance *= 0.9 if event.angleDelta().y() > 0 else 1.1
        self._distance = max(10.0, min(100_000.0, self._distance))
        self.update()
        event.accept()

    def _create_program(self) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram(self)
        if not program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex,
            _VERTEX_SHADER,
        ):
            raise RuntimeError(f"Vertex shader failed: {program.log()}")
        if not program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment,
            _FRAGMENT_SHADER,
        ):
            raise RuntimeError(f"Fragment shader failed: {program.log()}")
        if not program.link():
            raise RuntimeError(f"OpenGL shader link failed: {program.log()}")
        return program

    def _create_reference_geometry(self) -> None:
        if self._program is None:
            return

        vertices = array("f", self._reference_vertices())
        self._vertex_count = len(vertices) // 6

        self._vao.create()
        self._vbo.create()
        self._vao.bind()
        self._vbo.bind()
        self._vbo.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)
        self._vbo.allocate(vertices.tobytes(), len(vertices) * vertices.itemsize)

        self._program.bind()
        self._program.enableAttributeArray(0)
        self._program.setAttributeBuffer(0, _GL_FLOAT, 0, 3, 6 * 4)
        self._program.enableAttributeArray(1)
        self._program.setAttributeBuffer(1, _GL_FLOAT, 3 * 4, 3, 6 * 4)
        self._program.release()
        self._vbo.release()
        self._vao.release()

    @staticmethod
    def _reference_vertices() -> list[float]:
        vertices: list[float] = []
        grid_color = (0.22, 0.22, 0.22)
        grid_extent = 1000
        grid_step = 100

        def add_line(start, end, color) -> None:
            vertices.extend((*start, *color, *end, *color))

        for offset in range(-grid_extent, grid_extent + 1, grid_step):
            add_line(
                (-grid_extent, offset, 0.0),
                (grid_extent, offset, 0.0),
                grid_color,
            )
            add_line(
                (offset, -grid_extent, 0.0),
                (offset, grid_extent, 0.0),
                grid_color,
            )

        axis_length = 400.0
        add_line((0.0, 0.0, 0.0), (axis_length, 0.0, 0.0), (0.85, 0.25, 0.25))
        add_line((0.0, 0.0, 0.0), (0.0, axis_length, 0.0), (0.25, 0.75, 0.35))
        add_line((0.0, 0.0, 0.0), (0.0, 0.0, axis_length), (0.25, 0.45, 0.90))
        return vertices

    def _eye_position(self) -> QVector3D:
        azimuth = math.radians(self._azimuth)
        elevation = math.radians(self._elevation)
        return QVector3D(
            self._target.x()
            + self._distance * math.cos(elevation) * math.sin(azimuth),
            self._target.y()
            + self._distance * math.cos(elevation) * math.cos(azimuth),
            self._target.z() + self._distance * math.sin(elevation),
        )

    def _view(self) -> QMatrix4x4:
        matrix = QMatrix4x4()
        matrix.lookAt(
            self._eye_position(),
            self._target,
            QVector3D(0.0, 0.0, 1.0),
        )
        return matrix

    def _projection(self) -> QMatrix4x4:
        matrix = QMatrix4x4()
        matrix.perspective(
            45.0,
            self.width() / max(1, self.height()),
            1.0,
            100_000.0,
        )
        return matrix

    def _release_resources(self) -> None:
        if not self.isValid():
            return
        self.makeCurrent()
        if self._vbo.isCreated():
            self._vbo.destroy()
        if self._vao.isCreated():
            self._vao.destroy()
        self.doneCurrent()
