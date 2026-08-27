"""Launch a native AeroSandbox VLM snapshot in a separate process/window."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from setuav_studio_sdk import StudioAPI

from setuav_studio.ui.buttons import set_native_button
from setuav_studio.ui.numeric_spinbox import NumericSpinBox

from .engine.aerosandbox_engine import HAS_AEROSANDBOX, AeroSandboxEngine
from .engine.base import AeroResult, FlightCondition, SweepType


def viewer_process_command(payload_path: str | Path) -> tuple[str, list[str]]:
    """Return the viewer command for source and frozen application modes."""
    payload = str(payload_path)
    if getattr(sys, "frozen", False):
        return sys.executable, ["--render-aero-3d", payload]
    return sys.executable, ["-m", __name__, "--render", payload]


class Aero3DToolWindow(QDialog):
    """Collect a flight state and launch AeroSandbox's own PyVista viewer."""

    def __init__(
        self,
        api: StudioAPI,
        defaults: AeroResult | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("aerodynamics.aerosandbox_3d_tool")
        self.setWindowTitle("AeroSandbox 3D Snapshot")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(460, 520)
        self._api = api
        self._build_ui(defaults)

    @staticmethod
    def _angle_spin(value: float = 0.0) -> NumericSpinBox:
        spin = NumericSpinBox()
        spin.setRange(-90.0, 90.0)
        spin.setDecimals(2)
        spin.setValue(value)
        spin.setSuffix(" °")
        return spin

    def _build_ui(self, defaults: AeroResult | None) -> None:
        condition = defaults.condition if defaults is not None else FlightCondition()
        controls = condition.control_deflections

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        condition_group = QGroupBox("Flight Condition", self)
        condition_form = QFormLayout(condition_group)
        self.velocity_spin = NumericSpinBox(parent=condition_group)
        self.velocity_spin.setRange(1.0, 300.0)
        self.velocity_spin.setDecimals(2)
        self.velocity_spin.setValue(condition.velocity)
        self.velocity_spin.setSuffix(" m/s")
        condition_form.addRow("Airspeed", self.velocity_spin)

        self.altitude_spin = NumericSpinBox(parent=condition_group)
        self.altitude_spin.setRange(-500.0, 20000.0)
        self.altitude_spin.setDecimals(1)
        self.altitude_spin.setValue(condition.altitude)
        self.altitude_spin.setSuffix(" m")
        condition_form.addRow("Altitude", self.altitude_spin)

        self.alpha_spin = self._angle_spin(condition.alpha)
        self.beta_spin = self._angle_spin(condition.beta)
        condition_form.addRow("Angle of attack (α)", self.alpha_spin)
        condition_form.addRow("Sideslip (β)", self.beta_spin)
        layout.addWidget(condition_group)

        control_group = QGroupBox("Control Deflections", self)
        control_form = QFormLayout(control_group)
        self.elevator_spin = self._angle_spin(float(controls.get("elevator", 0.0)))
        self.aileron_spin = self._angle_spin(float(controls.get("aileron", 0.0)))
        self.rudder_spin = self._angle_spin(float(controls.get("rudder", 0.0)))
        self.flap_spin = self._angle_spin(float(controls.get("flap", 0.0)))
        control_form.addRow("Elevator", self.elevator_spin)
        control_form.addRow("Aileron", self.aileron_spin)
        control_form.addRow("Rudder", self.rudder_spin)
        control_form.addRow("Flap", self.flap_spin)
        layout.addWidget(control_group)

        mesh_group = QGroupBox("VLM Mesh", self)
        mesh_form = QFormLayout(mesh_group)
        self.spanwise_spin = QSpinBox(mesh_group)
        self.spanwise_spin.setRange(4, 50)
        self.spanwise_spin.setValue(12)
        self.chordwise_spin = QSpinBox(mesh_group)
        self.chordwise_spin.setRange(2, 30)
        self.chordwise_spin.setValue(10)
        mesh_form.addRow("Spanwise panels", self.spanwise_spin)
        mesh_form.addRow("Chordwise panels", self.chordwise_spin)
        layout.addWidget(mesh_group)

        self.status_label = QLabel(
            "The native AeroSandbox viewer opens in a separate process.",
            self,
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        button_row.addWidget(close_button)
        launch_button = QPushButton("Open AeroSandbox View", self)
        set_native_button(launch_button, "fa6s.up-right-from-square")
        launch_button.clicked.connect(self._launch_viewer)
        button_row.addWidget(launch_button)
        layout.addLayout(button_row)

    def _launch_viewer(self) -> None:
        project = self._api.current_project
        if project is None:
            QMessageBox.warning(
                self, "No Project", "Open a project before launching AeroSandbox 3D."
            )
            return
        if not HAS_AEROSANDBOX:
            QMessageBox.warning(
                self,
                "AeroSandbox Missing",
                "Install the aerodynamics extra: pip install 'setuav-studio[aerodynamics]'",
            )
            return

        components = project.data.get("components")
        if not isinstance(components, list) or not any(
            isinstance(component, dict)
            and component.get("type") == "org.setuav.core:lifting-surface"
            for component in components
        ):
            QMessageBox.warning(
                self,
                "Missing Lifting Surface",
                "The current project does not contain a lifting surface.",
            )
            return

        payload = {
            "components": components,
            "condition": {
                "velocity": float(self.velocity_spin.value()),
                "altitude": float(self.altitude_spin.value()),
                "alpha": float(self.alpha_spin.value()),
                "beta": float(self.beta_spin.value()),
                "control_deflections": {
                    "elevator": float(self.elevator_spin.value()),
                    "aileron": float(self.aileron_spin.value()),
                    "rudder": float(self.rudder_spin.value()),
                    "flap": float(self.flap_spin.value()),
                },
            },
            "mesh": {
                "spanwise_resolution": int(self.spanwise_spin.value()),
                "chordwise_resolution": int(self.chordwise_spin.value()),
            },
        }

        descriptor, payload_path = tempfile.mkstemp(
            prefix="setuav-aerosandbox-",
            suffix=".json",
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
            program, arguments = viewer_process_command(payload_path)
            launch_result = QProcess.startDetached(
                program,
                arguments,
                str(project.location),
            )
            started = launch_result[0] if isinstance(launch_result, tuple) else bool(launch_result)
            if not started:
                raise RuntimeError("The viewer process could not be started")
        except Exception as error:
            Path(payload_path).unlink(missing_ok=True)
            QMessageBox.critical(self, "AeroSandbox 3D", str(error))
            return

        self.status_label.setText("AeroSandbox viewer launched in a separate process.")
        self._api.show_status("AeroSandbox 3D viewer launched", "success")


def render_native_snapshot(payload_path: str | Path, *, show: bool = True) -> None:
    """Build and show one native AeroSandbox VLM scene."""
    path = Path(payload_path)
    try:
        with path.open("r", encoding="utf-8") as stream:
            payload: dict[str, Any] = json.load(stream)
    finally:
        path.unlink(missing_ok=True)

    condition_data = payload.get("condition") or {}
    condition = FlightCondition(
        velocity=float(condition_data.get("velocity", 25.0)),
        altitude=float(condition_data.get("altitude", 0.0)),
        alpha=float(condition_data.get("alpha", 2.0)),
        beta=float(condition_data.get("beta", 0.0)),
        control_deflections={
            str(name): float(value)
            for name, value in (condition_data.get("control_deflections") or {}).items()
        },
        sweep_type=SweepType.ALPHA,
        sweep_variable="alpha",
        sweep_steps=1,
        alpha_steps=1,
    )

    engine = AeroSandboxEngine()
    components = payload.get("components") or []
    mass_cg, _source = engine._resolve_mass_cg(components)
    airplane = engine._build_airplane(
        components,
        condition=condition,
        xyz_ref=mass_cg,
        control_encoding="airfoil",
    )
    if not airplane.wings:
        raise ValueError("No valid lifting surface was converted to AeroSandbox.")

    import aerosandbox as asb

    mesh = payload.get("mesh") or {}
    operating_point = asb.OperatingPoint(
        atmosphere=asb.Atmosphere(altitude=max(condition.altitude, 0.0)),
        velocity=condition.velocity,
        alpha=condition.alpha,
        beta=condition.beta,
    )
    analysis = asb.VortexLatticeMethod(
        airplane=airplane,
        op_point=operating_point,
        spanwise_resolution=int(mesh.get("spanwise_resolution", 12)),
        chordwise_resolution=int(mesh.get("chordwise_resolution", 10)),
    )
    analysis.run()
    # Deliberately use the public PyPI API with no Setuav plotter adapter.
    # AeroSandbox creates and owns its native PyVista window.
    plotter = analysis.draw(backend="pyvista", show=show)
    if not show:
        plotter.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Setuav AeroSandbox 3D snapshot")
    parser.add_argument("--render", required=True, help="Temporary snapshot payload")
    args = parser.parse_args(argv)
    render_native_snapshot(args.render)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
