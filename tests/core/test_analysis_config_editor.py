import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from setuav_studio.api import StudioAPI
from setuav_studio.model.analysis_config import AnalysisConfig
from setuav_studio.project import create_project
from setuav_studio.ui.editor.analysis_config import AnalysisConfigPropertyEditor
from setuav_studio.ui.panels.properties import PropertiesPanel


class TestAnalysisConfigEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project.suav"
        self.api = StudioAPI()
        self.api.current_project = create_project(self.project_path)
        self.config = AnalysisConfig(
            solver_id="aero_solver",
            name="VLM Aero Case",
            parameters={"speed": 25.0, "angle_of_attack": 5.0},
            options={"mesh_resolution": "fine", "max_iterations": 100},
        )
        self.api.add_analysis_config(self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_editor_loads_config_data(self) -> None:
        selection = {
            "kind": "analysis_config",
            "id": self.config.config_id,
            "config_id": self.config.config_id,
        }
        editor = AnalysisConfigPropertyEditor(self.api, selection)

        self.assertEqual(editor._property_text(editor.general_table, 0), "VLM Aero Case")
        self.assertEqual(editor._property_text(editor.general_table, 1), "aero_solver")
        self.assertEqual(editor._property_text(editor.general_table, 2), self.config.config_id)

        self.assertEqual(editor._property_text(editor.parameters_table, 0), "25.0")
        self.assertEqual(editor._property_text(editor.parameters_table, 1), "5.0")

    def test_editor_updates_name_and_parameters(self) -> None:
        selection = {
            "kind": "analysis_config",
            "id": self.config.config_id,
            "config_id": self.config.config_id,
        }
        editor = AnalysisConfigPropertyEditor(self.api, selection)

        # Simulate editing name
        editor._set_property_value(editor.general_table, "name", "Renamed Aero Run")

        # Simulate editing parameter
        editor._set_property_value(editor.parameters_table, "speed", "30.5")

        # Verify AnalysisConfig in project was updated
        updated_config = self.api.get_current_analysis_config()
        self.assertIsNotNone(updated_config)
        self.assertEqual(updated_config.name, "Renamed Aero Run")
        self.assertEqual(updated_config.parameters["speed"], 30.5)

    def test_properties_panel_displays_analysis_config_editor(self) -> None:
        panel = PropertiesPanel(self.api)
        selection = {
            "kind": "analysis_config",
            "id": self.config.config_id,
            "config_id": self.config.config_id,
        }
        self.api.set_selection(selection)

        self.assertIsInstance(panel._current_widget, AnalysisConfigPropertyEditor)


if __name__ == "__main__":
    unittest.main()
