from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtWidgets import QDockWidget, QMainWindow

from setuav_studio.plugin_system import PanelContribution, PluginManager, StudioAPI, WorkspaceContribution
from setuav_studio.plugins.core.properties import PropertiesPanel
from setuav_studio.plugins.core.ui.project_explorer import (
    ProjectExplorer,
    ProjectExplorerPanel,
)
from setuav_studio.plugins.weight_balance import WeightBalancePlugin
from setuav_studio.plugins.weight_balance.engine.base import WeightBalanceError
from setuav_studio.plugins.weight_balance.engine.solver import EXTENSION_ID, WeightBalanceSolver
from setuav_studio.plugins.core.derived_geometry import derive_project_component_geometry
from setuav_studio.plugins.weight_balance.mass_definition_dock import MassPropertiesEditor
from setuav_studio.project import ProjectDocument, open_project
from setuav_studio.schema_validation import get_catalog

from tests._common import TEST_PROJECT_PATH, get_qapp


def _project(data: dict) -> ProjectDocument:
    return ProjectDocument(Path("project.json"), "json", data)


class WeightBalanceSolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.solver = WeightBalanceSolver()

    def test_geometry_derived_control_surface_properties_without_mass_deduction(self) -> None:
        wing = {
            "id": "wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {"geometry": {"mirror": True, "profiles": [
                {"position": {"x": 0, "y": 0, "z": 0}, "chord": 100, "airfoil": "0012"},
                {"position": {"x": 0, "y": 500, "z": 0}, "chord": 80, "airfoil": "0012"},
            ]}},
        }
        aileron = {
            "id": "aileron",
            "type": "org.setuav.core:control-surface",
            "parent": "wing",
            "attach_to": "wing",
            "parameters": {"geometry": {"type": "aileron", "span_mode": "ratio",
                                          "eta_start": 0.5, "eta_end": 1.0,
                                          "chord_fraction": 0.25}},
        }
        derived = derive_project_component_geometry([wing, aileron])
        self.assertGreater(derived["aileron"].mass_g or 0, 0)
        self.assertEqual(derived["aileron"].envelope["size_mm"]["y"], 500.0)
        self.assertAlmostEqual(derived["wing"].mass_g or 0, 77.76, places=2)

    def test_two_point_masses_have_expected_cg_and_parallel_axis_inertia(self) -> None:
        project = _project({
            "components": [
                {
                    "id": "front",
                    "name": "Front",
                    "mass": 1000,
                    "transform": {"position": {"x": 0, "y": 0, "z": 0}},
                },
                {
                    "id": "rear",
                    "name": "Rear",
                    "mass": 3000,
                    "transform": {"position": {"x": 1000, "y": 0, "z": 0}},
                },
            ]
        })

        result = self.solver.evaluate(project)

        self.assertAlmostEqual(result.total.mass_kg, 4.0)
        self.assertEqual(result.total.cg_body_m, (0.75, 0.0, 0.0))
        self.assertAlmostEqual(result.total.inertia_cg_kg_m2.ixx, 0.0)
        self.assertAlmostEqual(result.total.inertia_cg_kg_m2.iyy, 0.75)
        self.assertAlmostEqual(result.total.inertia_cg_kg_m2.izz, 0.75)

    def test_parent_transform_and_local_cg_are_composed(self) -> None:
        project = _project({
            "components": [
                {
                    "id": "body",
                    "name": "Body",
                    "mass": 1000,
                    "transform": {"position": {"x": 100, "y": 20, "z": 30}},
                },
                {
                    "id": "payload",
                    "name": "Payload",
                    "mass": 1000,
                    "attach_to": "body",
                    "transform": {"position": {"x": 200, "y": 0, "z": 0}},
                    "extensions": {
                        EXTENSION_ID: {"local_cg_mm": {"x": 50, "y": 0, "z": 0}}
                    },
                },
            ]
        })

        result = self.solver.evaluate(project)
        payload = next(item for item in result.components if item.component_id == "payload")

        self.assertEqual(payload.cg_body_m, (0.35, 0.02, 0.03))
        self.assertAlmostEqual(result.total.cg_body_m[0], 0.225)
        self.assertAlmostEqual(result.total.cg_body_m[1], 0.02)
        self.assertAlmostEqual(result.total.cg_body_m[2], 0.03)

    def test_declared_inertia_is_rotated_to_body_axes(self) -> None:
        project = _project({
            "components": [
                {
                    "id": "box",
                    "name": "Box",
                    "mass": 1000,
                    "transform": {"rotation": {"yaw": 90}},
                    "extensions": {
                        EXTENSION_ID: {
                            "local_cg_mm": {"x": 0, "y": 0, "z": 0},
                            "inertia_kg_m2": {"ixx": 1, "iyy": 2, "izz": 3}
                        }
                    },
                }
            ]
        })

        inertia = self.solver.evaluate(project).total.inertia_cg_kg_m2

        self.assertAlmostEqual(inertia.ixx, 2.0)
        self.assertAlmostEqual(inertia.iyy, 1.0)
        self.assertAlmostEqual(inertia.izz, 3.0)

    def test_root_mass_wins_over_parameter_mass_with_warning(self) -> None:
        project = _project({
            "components": [
                {
                    "id": "battery",
                    "name": "Battery",
                    "mass": 800,
                    "parameters": {"mass": 750},
                    "transform": {},
                }
            ]
        })

        result = self.solver.evaluate(project)

        self.assertAlmostEqual(result.total.mass_kg, 0.8)
        self.assertTrue(any("overrides parameters.mass" in warning for warning in result.warnings))

    def test_mirrored_surface_defaults_to_body_symmetry_plane(self) -> None:
        project = _project({
            "components": [
                {
                    "id": "wing",
                    "name": "Wing",
                    "mass": 1000,
                    "transform": {"position": {"y": 120}},
                    "parameters": {"geometry": {"mirror": True}},
                }
            ]
        })

        result = self.solver.evaluate(project)

        self.assertEqual(result.total.cg_body_m[1], 0.0)

    def test_zero_mass_is_rejected(self) -> None:
        project = _project({"components": [{"id": "empty", "name": "Empty", "mass": 0}]})
        with self.assertRaises(WeightBalanceError):
            self.solver.evaluate(project)

    def test_fixed_wing_fixture_produces_mass_properties(self) -> None:
        result = self.solver.evaluate(open_project(TEST_PROJECT_PATH))
        self.assertGreater(result.total.mass_kg, 0.0)
        self.assertGreater(len(result.components), 5)


class WeightBalancePluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def test_plugin_registers_workspace_panels_and_provider(self) -> None:
        api = StudioAPI()
        panels: list[PanelContribution] = []
        workspaces: list[WorkspaceContribution] = []
        api.set_panel_handler(panels.append)
        api.set_workspace_handler(workspaces.append)
        manager = PluginManager(api)

        manager.activate(WeightBalancePlugin())

        self.assertEqual([workspace.id for workspace in workspaces], ["studio.workspace.weight_balance"])
        self.assertEqual(workspaces[0].title, "Weight-Balance")
        self.assertIsNone(workspaces[0].icon)
        self.assertEqual(len(panels), 2)
        self.assertIsNotNone(api.get_mass_properties_provider(EXTENSION_ID))

        manager.deactivate("org.setuav.studio.weight_balance")
        self.assertIsNone(api.get_mass_properties_provider(EXTENSION_ID))
        self.assertEqual(api.component_tree_nodes({"id": "item"}), ())

    def test_plugin_publishes_analysis_result(self) -> None:
        api = StudioAPI()
        api.set_panel_handler(lambda _panel: None)
        api.set_workspace_handler(lambda _workspace: None)
        plugin = WeightBalancePlugin()
        plugin.activate(api)
        api.set_project(_project({"components": [{"id": "item", "name": "Item", "mass": 1250}]}))
        received = []
        api.subscribe("weight_balance.analysis_completed", received.append)

        plugin.run_analysis()

        self.assertEqual(len(received), 1)
        self.assertAlmostEqual(received[0].total.mass_kg, 1.25)

    def test_panel_factories_display_analysis_result(self) -> None:
        api = StudioAPI()
        panels: list[PanelContribution] = []
        api.set_panel_handler(panels.append)
        api.set_workspace_handler(lambda _workspace: None)
        plugin = WeightBalancePlugin()
        plugin.activate(api)
        api.set_project(_project({
            "components": [
                {"id": "airframe", "name": "Airframe", "mass": 1000, "transform": {}},
                {
                    "id": "payload",
                    "name": "Payload",
                    "mass": 500,
                    "transform": {"position": {"x": 200}},
                },
            ]
        }))
        by_id = {panel.id: panel for panel in panels}
        view = by_id["weight_balance.view_dock"].factory()
        results = by_id["weight_balance.results_dock"].factory()

        self.assertIsInstance(view, QMainWindow)
        self.assertEqual(view.top_dock.windowTitle(), "Top View · X / Y")
        self.assertEqual(view.side_dock.windowTitle(), "Side View · X / Z")
        for projection_dock in (view.top_dock, view.side_dock):
            self.assertTrue(
                projection_dock.features()
                & QDockWidget.DockWidgetFeature.DockWidgetMovable
            )
            self.assertTrue(
                projection_dock.features()
                & QDockWidget.DockWidgetFeature.DockWidgetFloatable
            )
            self.assertFalse(
                projection_dock.features()
                & QDockWidget.DockWidgetFeature.DockWidgetClosable
            )

        plugin.run_analysis()

        self.assertIsNotNone(view.canvas.result)
        self.assertEqual(results.component_table.rowCount(), 2)
        self.assertEqual(results.summary_table.rowCount(), 2)
        self.assertEqual(results.cg_table.columnCount(), 3)
        self.assertEqual(results.inertia_table.rowCount(), 2)
        self.assertEqual(results.component_table.horizontalHeaderItem(2).text(), "CG-X (mm)")
        self.assertEqual(results.component_table.horizontalHeaderItem(7).text(), "Notes")
        self.assertRegex(results.warning_label.text(), r"^\d+ warning\(s\)$")
        self.assertFalse(results.warning_icon.pixmap().isNull())
        self.assertIn("Warnings", results.warning_label.toolTip())
        notes_cell = results.component_table.item(0, 7)
        self.assertIsNotNone(notes_cell)
        self.assertIn("warning(s)", notes_cell.text())
        self.assertFalse(notes_cell.icon().isNull())
        self.assertIn("Warnings", notes_cell.toolTip())
        self.assertGreaterEqual(results.component_table.font().pointSizeF(), 9.5)

    def test_mass_definition_editor_updates_component_with_undo(self) -> None:
        api = StudioAPI()
        api.set_panel_handler(lambda _panel: None)
        api.set_workspace_handler(lambda _workspace: None)
        plugin = WeightBalancePlugin()
        plugin.activate(api)
        component = {
            "id": "payload",
            "name": "Payload",
            "parameters": {"mass": 500},
            "transform": {},
        }
        project = _project({"components": [component]})
        api.set_project(project)
        contribution = api.component_tree_nodes(component)[0]
        self.assertEqual(contribution.icon, "fa6s.cubes-stacked")
        definition = api.create_component_editor(contribution.selection)
        self.assertIsInstance(definition, MassPropertiesEditor)
        self.assertEqual(definition.mass_table.rowCount(), 2)
        self.assertEqual(definition.cg_table.rowCount(), 1)
        self.assertEqual(definition.cg_table.columnCount(), 3)
        self.assertEqual(
            [definition.cg_table.horizontalHeaderItem(column).text() for column in range(3)],
            ["X", "Y", "Z"],
        )
        self.assertEqual(definition.inertia_moments_table.rowCount(), 1)
        self.assertEqual(definition.inertia_moments_table.columnCount(), 3)
        self.assertEqual(definition.inertia_products_table.rowCount(), 1)
        self.assertEqual(definition.inertia_products_table.columnCount(), 3)
        self.assertEqual(
            [
                definition.inertia_moments_table.horizontalHeaderItem(column).text()
                for column in range(3)
            ],
            ["IXX", "IYY", "IZZ"],
        )
        self.assertEqual(
            [
                definition.inertia_products_table.horizontalHeaderItem(column).text()
                for column in range(3)
            ],
            ["IXY", "IXZ", "IYZ"],
        )
        self.assertEqual(len(definition._section_icons), 3)
        self.assertEqual(definition._section_icons[0][1], "fa6s.cubes-stacked")
        self.assertFalse(definition.apply_button.icon().isNull())

        definition.mass_g.setValue(750)
        definition.cg_spins["x"].setValue(120)
        definition.inertia_spins["ixx"].setValue(0.02)
        definition.apply_button.click()

        self.assertEqual(component["mass"], 750)
        self.assertEqual(component["parameters"]["mass"], 750)
        self.assertEqual(
            component["extensions"][EXTENSION_ID]["local_cg_mm"]["x"],
            120,
        )
        result = WeightBalanceSolver().evaluate(project)
        self.assertAlmostEqual(result.total.cg_body_m[0], 0.12)
        self.assertAlmostEqual(result.total.inertia_cg_kg_m2.ixx, 0.02)

        api.undo()
        self.assertNotIn("mass", component)
        self.assertEqual(component["parameters"]["mass"], 500)

    def test_project_tree_child_opens_mass_properties_in_properties_panel(self) -> None:
        api = StudioAPI()
        api.set_panel_handler(lambda _panel: None)
        api.set_workspace_handler(lambda _workspace: None)
        plugin = WeightBalancePlugin()
        plugin.activate(api)
        component = {"id": "payload", "name": "Payload", "mass": 500}
        project = _project({"name": "Test", "components": [component]})
        explorer = ProjectExplorer(api)
        properties = PropertiesPanel(api)
        api.set_project(project)

        mass_item = explorer._item_map["payload:mass-properties"]
        self.assertEqual(mass_item.parent(), explorer._item_map["payload"])
        self.assertEqual(mass_item.text(0), "Mass")

        explorer.setCurrentItem(mass_item)
        get_qapp().processEvents()

        self.assertEqual(api.current_selection["kind"], "mass-properties")
        self.assertIsInstance(properties._current_widget, MassPropertiesEditor)

    def test_project_explorer_expand_and_collapse_buttons_control_tree(self) -> None:
        api = StudioAPI()
        panel = ProjectExplorerPanel(api)
        api.set_project(
            _project(
                {
                    "name": "Test",
                    "components": [
                        {
                            "id": "parent",
                            "name": "Parent",
                            "components": [],
                        },
                        {
                            "id": "child",
                            "name": "Child",
                            "parent": "parent",
                        },
                    ],
                }
            )
        )

        self.assertEqual(panel.expand_all_button.toolTip(), "Expand All")
        self.assertEqual(panel.collapse_all_button.toolTip(), "Collapse All")
        self.assertFalse(panel.expand_all_button.icon().isNull())
        self.assertFalse(panel.collapse_all_button.icon().isNull())

        panel.collapse_all_button.click()
        root = panel.explorer.topLevelItem(0)
        self.assertIsNotNone(root)
        self.assertFalse(root.isExpanded())

        panel.expand_all_button.click()
        self.assertTrue(root.isExpanded())

    def test_cg_view_marker_click_selects_mass_properties(self) -> None:
        from setuav_studio.plugins.weight_balance.balance_view_dock import WeightBalanceViewDock
        from setuav_studio.plugins.weight_balance.models import (
            ComponentMassProperties,
            InertiaTensor,
            MassProperties,
            WeightBalanceResult,
        )

        api = StudioAPI()
        api.set_panel_handler(lambda _panel: None)
        api.set_workspace_handler(lambda _workspace: None)
        plugin = WeightBalancePlugin()
        plugin.activate(api)
        component = {"id": "battery_1", "name": "Main Battery", "mass": 450}
        project = _project({"name": "Test", "components": [component]})
        api.set_project(project)

        properties = PropertiesPanel(api)
        view_dock = WeightBalanceViewDock(api)

        # Dispatch weight balance result
        result = WeightBalanceResult(
            total=MassProperties(mass_kg=0.45, cg_body_m=(0.1, 0.0, -0.02), inertia_cg_kg_m2=InertiaTensor()),
            components=[
                ComponentMassProperties(
                    component_id="battery_1",
                    component_name="Main Battery",
                    component_type="org.setuav.core:battery",
                    mass_kg=0.45,
                    cg_local_m=(0.0, 0.0, 0.0),
                    cg_body_m=(0.1, 0.0, -0.02),
                    inertia_local_kg_m2=InertiaTensor(),
                    source="declared",
                    quality="good",
                )
            ],
        )
        view_dock._set_result(result)
        get_qapp().processEvents()

        # Simulate clicking the marker in top canvas
        view_dock.top_canvas.itemClicked.emit("battery_1")
        get_qapp().processEvents()

        self.assertIsNotNone(api.current_selection)
        self.assertEqual(api.current_selection.get("kind"), "mass-properties")
        self.assertEqual(api.current_selection.get("component_id"), "battery_1")
        self.assertIsInstance(properties._current_widget, MassPropertiesEditor)


if __name__ == "__main__":
    unittest.main()
