"""Aero 3D Visualization Dock Widget using PyVista and VTK."""
from __future__ import annotations

from typing import Any, Sequence
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.theme import accent_color, rgba, tokens
from .engine.base import AeroResult

try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
    PYVISTA_AVAILABLE = True
except Exception:
    PYVISTA_AVAILABLE = False
    QtInteractor = None


class Aero3DDock(QWidget):
    """Interactive 3D aerodynamic viewer dock with wings, fuselage, VLM panels, and streamlines."""

    def __init__(self, api: StudioAPI | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.aero_3d_widget")
        self._api = api
        self._tokens = tokens()

        self._airplane = None
        self._vlm_instance = None
        self._velocity = 20.0
        self._current_alpha = 4.0
        self._alpha_min = -4.0
        self._alpha_max = 20.0

        self._surface_meshes: list[Any] = []
        self._fuselage_meshes: list[Any] = []
        self._vlm_mesh: Any | None = None
        self._scalar_data: dict[str, np.ndarray] = {}
        self._vlm_summary: dict[str, float] = {}
        self.plotter: Any | None = None
        self._placeholder: QLabel | None = None

        # Visibility flags
        self._show_surface = True
        self._show_fuselage = True
        self._show_vlm_panels = True
        self._show_wake = True
        self._show_freestream = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(2, 2, 2, 2)
        self.main_layout.setSpacing(2)

        tok = tokens()
        acc = accent_color()

        # 1. Compact Control Toolbar
        toolbar = QWidget(self)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(4, 4, 4, 4)
        tb_layout.setSpacing(6)

        # Visibility Toggles
        self.chk_surface = QCheckBox("Wings", self)
        self.chk_surface.setChecked(self._show_surface)
        self.chk_surface.setToolTip("Toggle 3D Wing Surface (OML)")
        self.chk_surface.toggled.connect(self._on_surface_toggled)
        tb_layout.addWidget(self.chk_surface)

        self.chk_fuselage = QCheckBox("Fuselage", self)
        self.chk_fuselage.setChecked(self._show_fuselage)
        self.chk_fuselage.setToolTip("Toggle Fuselage Solid Mesh")
        self.chk_fuselage.toggled.connect(self._on_fuselage_toggled)
        tb_layout.addWidget(self.chk_fuselage)

        self.chk_vlm = QCheckBox("Panels", self)
        self.chk_vlm.setChecked(self._show_vlm_panels)
        self.chk_vlm.setToolTip("Toggle VLM Camber Panels")
        self.chk_vlm.toggled.connect(self._on_vlm_toggled)
        tb_layout.addWidget(self.chk_vlm)

        self.chk_wake = QCheckBox("Wake", self)
        self.chk_wake.setChecked(self._show_wake)
        self.chk_wake.setToolTip("Toggle Trailing Edge Wake Streamlines")
        self.chk_wake.toggled.connect(self._on_wake_toggled)
        tb_layout.addWidget(self.chk_wake)

        self.chk_freestream = QCheckBox("Flow", self)
        self.chk_freestream.setChecked(self._show_freestream)
        self.chk_freestream.setToolTip("Toggle Approaching Freestream Streamlines")
        self.chk_freestream.toggled.connect(self._on_freestream_toggled)
        tb_layout.addWidget(self.chk_freestream)

        # Scalar Colormap Selector
        lbl_color = QLabel("Color:", self)
        tb_layout.addWidget(lbl_color)

        self.combo_scalar = QComboBox(self)
        self.combo_scalar.addItem("Pressure (Cp)", "cp")
        self.combo_scalar.addItem("Vortex Strength (Γ)", "vortex_strength")
        self.combo_scalar.addItem("Local Lift (L')", "local_lift")
        self.combo_scalar.addItem("Panel Area", "area")
        self.combo_scalar.currentIndexChanged.connect(self._on_scalar_changed)
        tb_layout.addWidget(self.combo_scalar)

        # Live Alpha Slider
        lbl_alpha_prefix = QLabel("α:", self)
        tb_layout.addWidget(lbl_alpha_prefix)

        self.lbl_alpha_val = QLabel("4.0°", self)
        tb_layout.addWidget(self.lbl_alpha_val)

        self.slider_alpha = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_alpha.setRange(-40, 200)  # -4.0 to 20.0 deg
        self.slider_alpha.setValue(40)
        self.slider_alpha.setFixedWidth(100)
        self.slider_alpha.setToolTip("Live Angle of Attack Adjustment (α)")
        self.slider_alpha.valueChanged.connect(self._on_alpha_slider_changed)
        self.slider_alpha.sliderReleased.connect(self._on_alpha_slider_released)
        tb_layout.addWidget(self.slider_alpha)

        tb_layout.addStretch()

        # Camera preset buttons
        self.btn_iso = self._create_cam_button("fa6s.cube", "Isometric View (Perspective)", lambda: self._set_camera_view("iso"))
        self.btn_top = self._create_cam_button("fa6s.arrow-down", "Top View (XY Plane)", lambda: self._set_camera_view("top"))
        self.btn_side = self._create_cam_button("fa6s.arrow-right", "Side View (XZ Plane)", lambda: self._set_camera_view("side"))
        self.btn_front = self._create_cam_button("fa6s.arrow-left", "Front View (YZ Plane)", lambda: self._set_camera_view("front"))

        tb_layout.addWidget(self.btn_iso)
        tb_layout.addWidget(self.btn_top)
        tb_layout.addWidget(self.btn_side)
        tb_layout.addWidget(self.btn_front)

        self.main_layout.addWidget(toolbar)

        # 2. Placeholder initially (Lazy load PyVista on showEvent)
        self._placeholder = QLabel("Aero 3D View Ready", self)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self._placeholder, 1)

    def _create_cam_button(self, icon_name: str, tooltip: str, callback: Any) -> QToolButton:
        btn = QToolButton(self)
        btn.setIcon(get_icon(icon_name))
        btn.setToolTip(tooltip)
        btn.setAutoRaise(True)
        btn.clicked.connect(callback)
        return btn

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self._ensure_plotter()

    def _ensure_plotter(self) -> None:
        if self.plotter is not None or not PYVISTA_AVAILABLE:
            return

        try:
            tok = tokens()
            bg_color = tok.get("surface", "#181818")
            text_color = tok.get("text", "#cccccc")

            pv.global_theme.background = bg_color
            pv.global_theme.font.color = text_color

            self.plotter = QtInteractor(self)
            self.plotter.set_background(bg_color)
            self.plotter.add_axes(
                color=tok.get("border_strong", "#444444"),
                line_width=2,
                labels_off=False,
            )
            if self._placeholder is not None:
                self.main_layout.removeWidget(self._placeholder)
                self._placeholder.deleteLater()
                self._placeholder = None
            self.main_layout.addWidget(self.plotter.interactor, 1)
            self._update_display()
            self._set_camera_view("iso")
        except Exception as err:
            print(f"[Aero3DDock] Lazy plotter init error: {err}")

    def set_airplane_context(self, airplane: Any, velocity: float = 20.0, alpha: float = 4.0) -> None:
        """Set airplane geometry and trigger initial VLM snapshot."""
        if airplane is None:
            return

        self._airplane = airplane
        self._velocity = velocity
        self._current_alpha = alpha
        self._recompute_vlm(alpha)

    def _recompute_vlm(self, alpha: float) -> None:
        """Run single on-demand VLM solution for 3D scalar visualization."""
        if self._airplane is None:
            return

        try:
            import aerosandbox as asb

            op_point = asb.OperatingPoint(
                velocity=self._velocity,
                alpha=alpha,
                beta=0.0,
            )
            vlm = asb.VortexLatticeMethod(
                airplane=self._airplane,
                op_point=op_point,
                spanwise_resolution=12,
                chordwise_resolution=6,
            )
            vlm_res = vlm.run()
            self._vlm_instance = vlm
            self._current_alpha = alpha
            self.lbl_alpha_val.setText(f"{alpha:.1f}°")

            cl = float(np.ravel(vlm_res.get("CL", 0.0))[0]) if "CL" in vlm_res else 0.0
            cd = float(np.ravel(vlm_res.get("CD", 0.0))[0]) if "CD" in vlm_res else 0.0
            cm = float(np.ravel(vlm_res.get("Cm", 0.0))[0]) if "Cm" in vlm_res else 0.0
            ld = cl / cd if abs(cd) > 1e-7 else 0.0

            self._vlm_summary = {
                "cl": cl,
                "cd": cd,
                "cm": cm,
                "ld": ld,
                "alpha": alpha,
                "velocity": self._velocity,
            }

            if PYVISTA_AVAILABLE and self.plotter is not None:
                self._build_vlm_mesh()
                self._build_surface_meshes()
                self._build_fuselage_meshes()
                self._calculate_streamlines()
                self._update_display()

        except Exception as err:
            print(f"[Aero3DDock] VLM calculation failed: {err}")

    def _build_vlm_mesh(self) -> None:
        """Extract panel vertices and scalar distributions from VLM instance."""
        if self._vlm_instance is None or not PYVISTA_AVAILABLE:
            return

        vlm = self._vlm_instance
        front_left = vlm.front_left_vertices
        back_left = vlm.back_left_vertices
        back_right = vlm.back_right_vertices
        front_right = vlm.front_right_vertices
        n_panels = len(front_left)

        points = np.concatenate([front_left, back_left, back_right, front_right])
        faces = []
        for i in range(n_panels):
            faces.extend([4, i, i + n_panels, i + 2 * n_panels, i + 3 * n_panels])

        self._vlm_mesh = pv.PolyData(points, np.array(faces))

        # Scalar quantities
        self._scalar_data["vortex_strength"] = vlm.vortex_strengths
        self._scalar_data["area"] = vlm.areas

        gamma_max = np.max(np.abs(vlm.vortex_strengths)) + 1e-10
        self._scalar_data["cp"] = -vlm.vortex_strengths / gamma_max

        span_vectors = vlm.right_vortex_vertices - vlm.left_vortex_vertices
        local_spans = np.linalg.norm(span_vectors, axis=1)
        self._scalar_data["local_lift"] = vlm.vortex_strengths * local_spans

    def _build_surface_meshes(self) -> None:
        """Generate actual 3D wing surface (outer mold line) meshes."""
        self._surface_meshes = []
        if self._airplane is None or not PYVISTA_AVAILABLE:
            return

        try:
            for wing in self._airplane.wings:
                points, faces = wing.mesh_body(
                    method="quad",
                    chordwise_resolution=24,
                    mesh_surface=True,
                    mesh_tips=True,
                    mesh_trailing_edge=True,
                    mesh_symmetric=True,
                )
                pv_faces = []
                for face in faces:
                    pv_faces.extend([len(face)] + list(face))
                mesh = pv.PolyData(points, np.array(pv_faces))
                self._surface_meshes.append(mesh)
        except Exception:
            try:
                for wing in self._airplane.wings:
                    points, faces = wing.mesh_thin_surface(method="quad", chordwise_resolution=16, add_camber=True)
                    pv_faces = []
                    for face in faces:
                        pv_faces.extend([len(face)] + list(face))
                    self._surface_meshes.append(pv.PolyData(points, np.array(pv_faces)))
            except Exception:
                pass

    def _build_fuselage_meshes(self) -> None:
        """Generate actual 3D fuselage surface meshes."""
        self._fuselage_meshes = []
        if self._airplane is None or not hasattr(self._airplane, "fuselages") or not PYVISTA_AVAILABLE:
            return

        try:
            for fuselage in self._airplane.fuselages:
                try:
                    points, faces = fuselage.mesh_body(
                        method="quad",
                        tangential_resolution=24,
                    )
                except TypeError:
                    points, faces = fuselage.mesh_body(method="quad")

                pv_faces = []
                for face in faces:
                    pv_faces.extend([len(face)] + list(face))
                mesh = pv.PolyData(points, np.array(pv_faces))
                self._fuselage_meshes.append(mesh)
        except Exception as err:
            print(f"[Aero3DDock] Fuselage mesh generation skipped: {err}")

    def _calculate_streamlines(self) -> None:
        """Pre-calculate wake and flow streamlines."""
        if self._vlm_instance is None:
            return
        try:
            if not hasattr(self._vlm_instance, "streamlines"):
                self._vlm_instance.calculate_streamlines(n_steps=120)
        except Exception:
            pass

    def _update_display(self) -> None:
        """Render composite 3D scene (wings, fuselage, panels, streamlines)."""
        if not PYVISTA_AVAILABLE or self.plotter is None:
            return

        # Clean up existing props & scalar bar before adding fresh elements
        try:
            self.plotter.remove_scalar_bar()
        except Exception:
            pass
        self.plotter.renderer.RemoveAllViewProps()

        # 1. Wing Surfaces (OML)
        if self._show_surface and self._surface_meshes:
            for mesh in self._surface_meshes:
                self.plotter.add_mesh(
                    mesh,
                    color="#4a7090",
                    opacity=0.65,
                    show_edges=True,
                    edge_color="#2b4860",
                    line_width=0.4,
                    lighting=True,
                    smooth_shading=True,
                )

        # 2. Fuselage Solid Mesh
        if self._show_fuselage and self._fuselage_meshes:
            for f_mesh in self._fuselage_meshes:
                self.plotter.add_mesh(
                    f_mesh,
                    color="#555866",
                    opacity=0.85,
                    show_edges=True,
                    edge_color="#363842",
                    line_width=0.4,
                    lighting=True,
                    smooth_shading=True,
                )

        # 3. VLM Camber Panels with Scalar Colormap
        if self._show_vlm_panels and self._vlm_mesh is not None:
            scalar_key = self.combo_scalar.currentData()
            scalars = self._scalar_data.get(scalar_key, None)

            if scalar_key == "cp":
                cmap = "RdBu_r"
                title_str = "Pressure Cp"
            elif scalar_key == "vortex_strength":
                cmap = "viridis"
                title_str = "Vortex Γ [m²/s]"
            elif scalar_key == "local_lift":
                cmap = "plasma"
                title_str = "Local Lift L'"
            else:
                cmap = "plasma"
                title_str = "Panel Area [m²]"

            self.plotter.add_mesh(
                self._vlm_mesh,
                scalars=scalars,
                cmap=cmap,
                show_edges=True,
                edge_color="#ffffff",
                line_width=0.8,
                opacity=0.85 if not self._show_surface else 0.55,
                scalar_bar_args={
                    "title": "",
                    "color": "#b0b0b8",
                    "label_font_size": 8,
                    "n_labels": 5,
                    "fmt": "%.3g",
                    "shadow": False,
                    "bold": False,
                    "italic": False,
                    "position_x": 0.25,
                    "position_y": 0.02,
                    "width": 0.50,
                    "height": 0.05,
                    "vertical": False,
                },
            )

        # 4. Wake Streamlines
        if self._show_wake:
            self._add_wake_streamlines()

        # 5. Freestream Streamlines
        if self._show_freestream:
            self._add_freestream_streamlines()

        # 6. Upper-Left HUD Analysis Summary (Soft gray compact text overlay)
        if self._vlm_summary:
            cl = self._vlm_summary.get("cl", 0.0)
            cd = self._vlm_summary.get("cd", 0.0)
            cm = self._vlm_summary.get("cm", 0.0)
            ld = self._vlm_summary.get("ld", 0.0)
            alpha = self._vlm_summary.get("alpha", self._current_alpha)
            vel = self._vlm_summary.get("velocity", self._velocity)

            hud_text = (
                f"α = {alpha:.1f}°   |   V = {vel:.1f} m/s\n"
                f"CL = {cl:.3f}   |   CD = {cd:.4f}\n"
                f"L/D = {ld:.1f}   |   Cm = {cm:.3f}"
            )
            try:
                self.plotter.add_text(
                    hud_text,
                    position="upper_left",
                    font_size=8,
                    color="#9c9ca6",
                    shadow=False,
                    name="aero_3d_hud_summary",
                )
            except Exception:
                pass

    def _get_fuselage_envelope(self) -> list[tuple[float, float, float, float]]:
        """Return list of (x, z_center, radius_y, radius_z) along fuselage length."""
        envelopes = []
        if self._airplane and hasattr(self._airplane, "fuselages"):
            for f in self._airplane.fuselages:
                for sec in f.xsecs:
                    x = float(sec.xyz_c[0])
                    z = float(sec.xyz_c[2])
                    ry = float(sec.width) / 2.0 if hasattr(sec, "width") else (float(sec.radius) if hasattr(sec, "radius") else 0.06)
                    rz = float(sec.height) / 2.0 if hasattr(sec, "height") else (float(sec.radius) if hasattr(sec, "radius") else 0.06)
                    envelopes.append((x, z, max(ry, 0.01), max(rz, 0.01)))
        return envelopes

    @staticmethod
    def _is_inside_fuselage(pt: np.ndarray, envelopes: list[tuple[float, float, float, float]]) -> bool:
        if not envelopes:
            return False
        x, y, z = pt[0], pt[1], pt[2]
        best_env = None
        min_dx = float("inf")
        for env in envelopes:
            dx = abs(x - env[0])
            if dx < min_dx:
                min_dx = dx
                best_env = env
        if best_env is not None and min_dx < 0.35:
            _, z_c, ry, rz = best_env
            if (y / ry) ** 2 + ((z - z_c) / rz) ** 2 <= 1.05:
                return True
        return False

    def _add_wake_streamlines(self) -> None:
        if self._vlm_instance is None or not hasattr(self._vlm_instance, "streamlines") or not PYVISTA_AVAILABLE:
            return

        try:
            streamlines = self._vlm_instance.streamlines
            if streamlines is None or len(streamlines) == 0:
                return

            envelopes = self._get_fuselage_envelope()
            n_lines = streamlines.shape[0]
            step = max(1, n_lines // 80)
            lines_list = []

            for i in range(0, n_lines, step):
                pts = streamlines[i, :, :].T
                if len(pts) < 3:
                    continue

                # Exclude wake streamlines originating or passing inside fuselage volume
                if envelopes:
                    if self._is_inside_fuselage(pts[0], envelopes) or self._is_inside_fuselage(pts[1], envelopes):
                        continue

                try:
                    lines_list.append(pv.lines_from_points(pts))
                except Exception:
                    pass

            if lines_list and self.plotter is not None:
                combined = pv.MultiBlock(lines_list).combine()
                self.plotter.add_mesh(
                    combined,
                    color="#b388ff",
                    opacity=0.75,
                    line_width=1.8,
                )
        except Exception:
            pass

    def _add_freestream_streamlines(self) -> None:
        if self._vlm_instance is None or self._airplane is None or not PYVISTA_AVAILABLE:
            return

        try:
            vlm = self._vlm_instance
            all_pts = np.concatenate([vlm.front_left_vertices, vlm.front_right_vertices])
            x_min, x_max = np.min(all_pts[:, 0]), np.max(all_pts[:, 0])
            y_min, y_max = np.min(all_pts[:, 1]), np.max(all_pts[:, 1])
            z_min, z_max = np.min(all_pts[:, 2]), np.max(all_pts[:, 2])

            envelopes = self._get_fuselage_envelope()

            chord = x_max - x_min
            x_start = x_min - min(0.12 * chord, 0.06)

            y_seeds = np.linspace(y_min * 0.9, y_max * 0.9, 12)
            z_center = (z_min + z_max) / 2
            z_seeds = np.linspace(z_center - chord * 0.25, z_center + chord * 0.25, 8)

            lines_list = []
            n_steps = 50
            length = 2.5 * chord

            for y in y_seeds:
                for z in z_seeds:
                    # Skip seeds directly inside fuselage projected upstream
                    if envelopes and self._is_inside_fuselage(np.array([x_min, y, z]), envelopes):
                        continue

                    cur = np.array([x_start, y, z])
                    pts = [cur.copy()]
                    for _ in range(n_steps):
                        try:
                            # Stop streamline if it enters the fuselage solid boundary
                            if envelopes and self._is_inside_fuselage(cur, envelopes):
                                break

                            V = vlm.get_velocity_at_points(cur.reshape(1, -1))[0]
                            V_norm = np.linalg.norm(V)
                            if V_norm < 1e-5:
                                break
                            step = (length / n_steps) * V / V_norm
                            cur = cur + step
                            pts.append(cur.copy())
                            if cur[0] > x_max + chord:
                                break
                        except Exception:
                            break
                    if len(pts) >= 3:
                        try:
                            lines_list.append(pv.lines_from_points(np.array(pts)))
                        except Exception:
                            pass

            if lines_list and self.plotter is not None:
                combined = pv.MultiBlock(lines_list).combine()
                self.plotter.add_mesh(
                    combined,
                    color="#40c4ff",
                    opacity=0.65,
                    line_width=1.4,
                )
        except Exception:
            pass

    def _set_camera_view(self, view_type: str) -> None:
        if not PYVISTA_AVAILABLE or self.plotter is None:
            return

        if view_type == "top":
            self.plotter.view_xy()
        elif view_type == "side":
            self.plotter.view_xz()
        elif view_type == "front":
            self.plotter.view_yz(negative=True)
        elif view_type == "iso":
            # Aviation 3D Isometric View: looking from front-left/front-right top
            self.plotter.view_vector([-1.2, -1.4, 0.9], viewup=[0, 0, 1])

        self.plotter.reset_camera()

    def _on_surface_toggled(self, checked: bool) -> None:
        self._show_surface = checked
        self._update_display()

    def _on_fuselage_toggled(self, checked: bool) -> None:
        self._show_fuselage = checked
        self._update_display()

    def _on_vlm_toggled(self, checked: bool) -> None:
        self._show_vlm_panels = checked
        self._update_display()

    def _on_wake_toggled(self, checked: bool) -> None:
        self._show_wake = checked
        self._update_display()

    def _on_freestream_toggled(self, checked: bool) -> None:
        self._show_freestream = checked
        self._update_display()

    def _on_scalar_changed(self) -> None:
        self._update_display()

    def _on_alpha_slider_changed(self, value: int) -> None:
        alpha = value / 10.0
        self.lbl_alpha_val.setText(f"{alpha:.1f}°")

    def _on_alpha_slider_released(self) -> None:
        alpha = self.slider_alpha.value() / 10.0
        self._recompute_vlm(alpha)

    def closeEvent(self, event: Any) -> None:
        if self.plotter is not None:
            try:
                self.plotter.close()
            except Exception:
                pass
            self.plotter = None
        super().closeEvent(event)
