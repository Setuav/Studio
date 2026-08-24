"""Tests for the standalone native AeroSandbox snapshot tool."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import open_project
from setuav_studio.plugins.aerodynamics.aero_3d_tool import (
    Aero3DToolWindow,
    render_native_snapshot,
)
from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import HAS_AEROSANDBOX
from tests._common import TEST_PROJECT_PATH, get_qapp


@unittest.skipUnless(HAS_AEROSANDBOX, "AeroSandbox not installed")
class Aero3DToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def test_tool_launches_detached_process_with_selected_state(self) -> None:
        api = StudioAPI()
        api.set_project(open_project(TEST_PROJECT_PATH))
        window = Aero3DToolWindow(api)
        window.alpha_spin.setValue(5.0)
        window.beta_spin.setValue(2.0)
        window.elevator_spin.setValue(-3.0)

        with patch(
            "setuav_studio.plugins.aerodynamics.aero_3d_tool.QProcess.startDetached",
            return_value=(True, 123),
        ) as start_detached:
            window._launch_viewer()

        _program, arguments, _working_directory = start_detached.call_args.args
        payload_path = Path(arguments[-1])
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        finally:
            payload_path.unlink(missing_ok=True)

        self.assertEqual(payload["condition"]["alpha"], 5.0)
        self.assertEqual(payload["condition"]["beta"], 2.0)
        self.assertEqual(payload["condition"]["control_deflections"]["elevator"], -3.0)
        window.close()

    def test_native_snapshot_uses_public_pypi_draw_api(self) -> None:
        project = json.loads((TEST_PROJECT_PATH / "project.json").read_text(encoding="utf-8"))
        payload = {
            "components": project["components"],
            "condition": {
                "velocity": 25.0,
                "altitude": 100.0,
                "alpha": 4.0,
                "beta": 2.0,
                "control_deflections": {"elevator": -3.0},
            },
            "mesh": {"spanwise_resolution": 4, "chordwise_resolution": 2},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as stream:
            json.dump(payload, stream)
            payload_path = Path(stream.name)

        import aerosandbox as asb

        with patch.object(asb.VortexLatticeMethod, "draw") as draw:
            render_native_snapshot(payload_path)

        draw.assert_called_once_with(backend="pyvista", show=True)
        self.assertFalse(payload_path.exists())
