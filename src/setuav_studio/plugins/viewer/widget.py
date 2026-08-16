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

from setuav_studio.geometry_data import GeometryData
from setuav_studio.plugins.viewer.mesh import (
    FACE_COLORED,
    FACE_MONOCHROME,
    FACE_TRANSPARENT,
    build_loft_solid_vertices,
    build_loft_wire_vertices,
)


WIREFRAME = "wireframe"
SOLID = "solid"
SOLID_WIRE = "solid+wire"

_GL_COLOR_BUFFER_BIT = 0x00004000
_GL_DEPTH_BUFFER_BIT = 0x00000100
_GL_DEPTH_TEST = 0x0B71
_GL_FLOAT = 0x1406
_GL_LINES = 0x0001
_GL_MULTISAMPLE = 0x809D
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
out vec4 fragmentColor;
void main() {
    fragmentColor = vec4(vertexColor, 1.0);
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
    float diffuse = abs(dot(normalize(vertexNormal), normalize(eyeDirection)));
    vec3 shaded = vertexColor * (0.20 + 0.80 * diffuse);
    fragmentColor = vec4(shaded, alpha);
}
"""


class OpenGLViewer(QOpenGLWidget):
    def __init__(self, parent=None) -> None:
        surface_format = QSurfaceFormat()
        surface_format.setVersion(3, 3)
        surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        surface_format.setSamples(8)
        super().__init__(parent)
        self.setFormat(surface_format)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._functions: QOpenGLFunctions_3_3_Core | None = None
        self._wire_program: QOpenGLShaderProgram | None = None
        self._solid_program: QOpenGLShaderProgram | None = None
        self._wire_vao = QOpenGLVertexArrayObject()
        self._wire_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._solid_vao = QOpenGLVertexArrayObject()
        self._solid_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._wire_count = 0
        self._solid_count = 0
        self._mode = SOLID_WIRE
        self._face_style = FACE_COLORED
        self._geometry_data = GeometryData()
        self._selected_component_id: str | None = None

        self._azimuth = 30.0
        self._elevation = 20.0
        self._distance = 1500.0
        self._target = QVector3D(400.0, 0.0, 0.0)
        self._last_mouse = QPoint()

    def initializeGL(self) -> None:
        functions = QOpenGLFunctions_3_3_Core()
        if not functions.initializeOpenGLFunctions():
            raise RuntimeError("OpenGL 3.3 core functions are unavailable")
        self._functions = functions
        functions.glClearColor(0.10, 0.10, 0.10, 1.0)
        functions.glEnable(_GL_DEPTH_TEST)
        functions.glEnable(_GL_MULTISAMPLE)

        self._wire_program = self._create_program(
            _WIRE_VERTEX_SHADER,
            _WIRE_FRAGMENT_SHADER,
        )
        self._solid_program = self._create_program(
            _SOLID_VERTEX_SHADER,
            _SOLID_FRAGMENT_SHADER,
        )
        self._setup_buffer(
            self._wire_vao,
            self._wire_vbo,
            self._wire_program,
            6,
            ((0, 0, 3), (1, 3, 3)),
        )
        self._setup_buffer(
            self._solid_vao,
            self._solid_vbo,
            self._solid_program,
            9,
            ((0, 0, 3), (1, 3, 3), (2, 6, 3)),
        )
        self._upload_meshes()
        context = self.context()
        if context is not None:
            context.aboutToBeDestroyed.connect(self._release_resources)

    def resizeGL(self, width: int, height: int) -> None:
        if self._functions is not None:
            self._functions.glViewport(0, 0, width, height)

    def paintGL(self) -> None:
        if self._functions is None:
            return
        self._functions.glClear(_GL_COLOR_BUFFER_BIT | _GL_DEPTH_BUFFER_BIT)
        mvp = self._projection() * self._view()

        if self._mode in (SOLID, SOLID_WIRE) and self._solid_program is not None:
            eye_direction = self._eye_position() - self._target
            eye_direction.normalize()
            self._solid_program.bind()
            self._solid_program.setUniformValue("mvp", mvp)
            self._solid_program.setUniformValue("eyeDirection", eye_direction)
            transparent = self._face_style == FACE_TRANSPARENT
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

        if self._mode in (WIREFRAME, SOLID_WIRE) and self._wire_program is not None:
            self._wire_program.bind()
            self._wire_program.setUniformValue("mvp", mvp)
            self._wire_vao.bind()
            self._functions.glDrawArrays(_GL_LINES, 0, self._wire_count)
            self._wire_vao.release()
            self._wire_program.release()

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

    def set_mode(self, mode: str) -> None:
        if mode not in {WIREFRAME, SOLID, SOLID_WIRE}:
            raise ValueError(f"Unknown viewer mode: {mode}")
        self._mode = mode
        self.update()

    def set_face_style(self, face_style: str) -> None:
        if face_style not in {FACE_COLORED, FACE_MONOCHROME, FACE_TRANSPARENT}:
            raise ValueError(f"Unknown face style: {face_style}")
        self._face_style = face_style
        self._update_gpu_meshes()

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
        diagonal = math.dist(minimum, maximum)
        self._target = QVector3D(*centre)
        self._distance = max(10.0, diagonal * 1.35)
        self.update()

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
            self._elevation = max(-89.0, min(89.0, self._elevation + dy * 0.4))
        elif event.buttons() & Qt.MouseButton.RightButton:
            azimuth = math.radians(self._azimuth)
            right = QVector3D(math.cos(azimuth), -math.sin(azimuth), 0.0)
            scale = self._distance * 0.001
            self._target -= right * (dx * scale)
            self._target -= QVector3D(0.0, 0.0, 1.0) * (dy * scale)
        self.update()

    def wheelEvent(self, event) -> None:
        self._distance *= 0.9 if event.angleDelta().y() > 0 else 1.1
        self._distance = max(10.0, min(100_000.0, self._distance))
        self.update()
        event.accept()

    def _update_gpu_meshes(self) -> None:
        if self._wire_program is None or not self.isValid():
            return
        self.makeCurrent()
        self._upload_meshes()
        self.doneCurrent()
        self.update()

    def _upload_meshes(self) -> None:
        wire_values = self._reference_vertices()
        wire_values.extend(
            build_loft_wire_vertices(
                self._geometry_data,
                self._selected_component_id,
                self._face_style,
            )
        )
        solid_values = build_loft_solid_vertices(
            self._geometry_data,
            self._selected_component_id,
            self._face_style,
        )
        self._wire_count = self._allocate(self._wire_vbo, wire_values, 6)
        self._solid_count = self._allocate(self._solid_vbo, solid_values, 9)

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
    def _reference_vertices() -> list[float]:
        vertices: list[float] = []

        def add_line(start, end, color) -> None:
            vertices.extend((*start, *color, *end, *color))

        for offset in range(-1000, 1001, 100):
            add_line((-1000, offset, 0.0), (1000, offset, 0.0), (0.22, 0.22, 0.22))
            add_line((offset, -1000, 0.0), (offset, 1000, 0.0), (0.22, 0.22, 0.22))
        add_line((0, 0, 0), (400, 0, 0), (0.85, 0.25, 0.25))
        add_line((0, 0, 0), (0, 400, 0), (0.25, 0.75, 0.35))
        add_line((0, 0, 0), (0, 0, 400), (0.25, 0.45, 0.90))
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
        matrix.perspective(45.0, self.width() / max(1, self.height()), 1.0, 100_000.0)
        return matrix

    def _release_resources(self) -> None:
        if not self.isValid():
            return
        self.makeCurrent()
        for buffer in (self._wire_vbo, self._solid_vbo):
            if buffer.isCreated():
                buffer.destroy()
        for vao in (self._wire_vao, self._solid_vao):
            if vao.isCreated():
                vao.destroy()
        self.doneCurrent()
