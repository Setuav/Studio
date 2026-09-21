import tempfile
import unittest
from pathlib import Path

from setuav_studio.api import StudioAPI
from setuav_studio.project import create_project, open_project, save_project
from setuav_studio.solver import SolverConfig


class TestSolverConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project.suav"
        self.api = StudioAPI()
        self.api.current_project = create_project(self.project_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_solver_config_model_and_serialization(self) -> None:
        config = SolverConfig(
            solver_id="org.setuav.vlm",
            name="VLM Config Alpha",
            parameters={"alpha": 3.0, "velocity": 25.0},
            options={"mesh": "fine"},
        )
        self.assertEqual(config.solver_id, "org.setuav.vlm")
        self.assertEqual(config.name, "VLM Config Alpha")

        dict_data = config.to_dict()
        self.assertEqual(dict_data["solver_id"], "org.setuav.vlm")
        self.assertEqual(dict_data["parameters"]["alpha"], 3.0)

        deserialized = SolverConfig.from_dict(dict_data)
        self.assertEqual(deserialized.config_id, config.config_id)
        self.assertEqual(deserialized.name, config.name)
        self.assertEqual(deserialized.solver_id, config.solver_id)
        self.assertEqual(deserialized.parameters["alpha"], 3.0)
        self.assertEqual(deserialized.options["mesh"], "fine")

    def test_project_document_solver_configs(self) -> None:
        config = SolverConfig(solver_id="org.setuav.motor", name="Motor Sweep")
        doc = self.api.current_project
        self.assertIsNotNone(doc)
        assert doc is not None

        self.assertEqual(len(doc.solver_configs), 0)
        doc.add_solver_config(config)
        self.assertEqual(len(doc.solver_configs), 1)

        fetched = doc.get_solver_config(config.config_id)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.name, "Motor Sweep")

        removed = doc.remove_solver_config(config.config_id)
        self.assertTrue(removed)
        self.assertEqual(len(doc.solver_configs), 0)

    def test_studio_api_solver_config_selection(self) -> None:
        config1 = SolverConfig(solver_id="s1", name="Config 1")
        config2 = SolverConfig(solver_id="s2", name="Config 2")

        selected_configs: list[SolverConfig | None] = []

        def _on_selection(cfg: SolverConfig | None) -> None:
            selected_configs.append(cfg)

        self.api.on_solver_config_selection_changed(_on_selection)

        self.api.add_solver_config(config1)
        self.assertEqual(self.api.current_solver_config_id, config1.config_id)
        self.assertIsNotNone(self.api.get_current_solver_config())
        current_cfg = self.api.get_current_solver_config()
        assert current_cfg is not None
        self.assertEqual(current_cfg.name, "Config 1")

        self.api.add_solver_config(config2)
        current_cfg2 = self.api.get_current_solver_config()
        assert current_cfg2 is not None
        self.assertEqual(current_cfg2.name, "Config 2")
        self.assertIn(config2, selected_configs)

        # Remove active selection
        self.api.remove_solver_config(config2.config_id)
        self.assertIsNone(self.api.get_current_solver_config())

    def test_persistence_across_save_and_open(self) -> None:
        doc = self.api.current_project
        assert doc is not None

        config = SolverConfig(
            solver_id="org.setuav.aero",
            name="Aero Run 1",
            parameters={"mach": 0.15},
        )
        self.api.add_solver_config(config)

        save_project(doc)
        reopened = open_project(self.project_path)

        self.assertEqual(len(reopened.solver_configs), 1)
        reopened_cfg = reopened.get_solver_config(config.config_id)
        self.assertIsNotNone(reopened_cfg)
        assert reopened_cfg is not None
        self.assertEqual(reopened_cfg.name, "Aero Run 1")
        self.assertEqual(reopened_cfg.parameters["mach"], 0.15)


if __name__ == "__main__":
    unittest.main()
