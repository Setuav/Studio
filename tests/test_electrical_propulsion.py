"""Unit tests for the Electrical Propulsion plugin and component property editors."""

from __future__ import annotations

import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication

from setuav_studio.plugin_system import PluginManager, StudioAPI
from setuav_studio.plugins.core import CorePlugin
from setuav_studio.plugins.electrical_propulsion.editors import (
    BatteryEditor,
    ElectricPropulsionSystemEditor,
    EscEditor,
    MotorEditor,
    PropellerEditor,
)
from setuav_studio.project import open_project


class TestElectricalPropulsion(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_plugin_discovery_and_registration(self) -> None:
        from setuav_studio.shell import MainWindow

        api = StudioAPI()
        win = MainWindow(api)
        pm = PluginManager(api)
        pm.activate(CorePlugin())
        issues = pm.discover()
        self.assertEqual(len(issues), 0)
        self.assertIn("org.setuav.studio.electrical_propulsion", pm._plugins)

        # Check registered editors
        self.assertIn("org.setuav.core:motor", api._component_editors)
        self.assertIn("org.setuav.core:propeller", api._component_editors)
        self.assertIn("org.setuav.core:esc", api._component_editors)
        self.assertIn("org.setuav.core:battery", api._component_editors)
        self.assertIn("org.setuav.core:electric-propulsion-system", api._component_editors)

    def test_motor_editor(self) -> None:
        api = StudioAPI()
        doc = open_project("/home/huseyin/dev/setware/setuav-specification/examples/fixed-wing")
        api.set_project(doc)

        motor_comp = next(c for c in doc.data["components"] if c.get("type") == "org.setuav.core:motor")
        editor = MotorEditor(api, motor_comp)

        self.assertEqual(editor._property_text(editor.general_table, 0), motor_comp.get("name"))
        self.assertEqual(editor._property_text(editor.parameters_table, 0), "900")

        # Edit KV (row 0 in parameters_table)
        editor.parameters_table.item(0, 1).setText("1050")
        self.assertEqual(motor_comp["parameters"]["kv"], 1050.0)

        # Undo
        api.undo()
        self.assertEqual(motor_comp["parameters"]["kv"], 900.0)

    def test_battery_editor(self) -> None:
        api = StudioAPI()
        doc = open_project("/home/huseyin/dev/setware/setuav-specification/examples/fixed-wing")
        api.set_project(doc)

        battery_comp = next(c for c in doc.data["components"] if c.get("type") == "org.setuav.core:battery")
        editor = BatteryEditor(api, battery_comp)

        self.assertEqual(editor._property_text(editor.pack_table, 0), "6")
        self.assertEqual(editor._property_text(editor.pack_table, 2), "6000")
        self.assertEqual(editor._property_text(editor.cell_table, 0), "LiPo")
        self.assertEqual(editor._property_text(editor.general_table, 2), "820.0")

        # Change Series Count to 4S -> calculated mass becomes 4*130 + 40 = 560.0g
        editor.pack_table.item(0, 1).setText("4")
        self.assertEqual(battery_comp["mass"], 560.0)
        self.assertEqual(editor._property_text(editor.general_table, 2), "560.0")

    def test_esc_editor(self) -> None:
        api = StudioAPI()
        doc = open_project("/home/huseyin/dev/setware/setuav-specification/examples/fixed-wing")
        api.set_project(doc)

        esc_comp = next(c for c in doc.data["components"] if c.get("type") == "org.setuav.core:esc")
        editor = EscEditor(api, esc_comp)

        self.assertEqual(editor._property_text(editor.parameters_table, 0), "50.0")

    def test_propeller_editor(self) -> None:
        api = StudioAPI()
        doc = open_project("/home/huseyin/dev/setware/setuav-specification/examples/fixed-wing")
        api.set_project(doc)

        prop_comp = next(c for c in doc.data["components"] if c.get("type") == "org.setuav.core:propeller")
        editor = PropellerEditor(api, prop_comp)

        self.assertEqual(editor._property_text(editor.parameters_table, 0), "330.2")
        self.assertEqual(editor._property_text(editor.parameters_table, 1), "165.1")
        self.assertEqual(editor._property_text(editor.parameters_table, 2), "2")

    def test_assembly_editor(self) -> None:
        api = StudioAPI()
        doc = open_project("/home/huseyin/dev/setware/setuav-specification/examples/fixed-wing")
        api.set_project(doc)

        asm = doc.data["assemblies"][0]
        editor = ElectricPropulsionSystemEditor(api, asm)

        self.assertEqual(editor._property_text(editor.general_table, 0), "Main Propulsion")
        self.assertEqual(editor._property_text(editor.members_table, 0), "battery-main")
        self.assertEqual(editor._property_text(editor.members_table, 2), "motor-cruise")
        self.assertEqual(editor._property_text(editor.members_table, 3), "propeller-cruise")

    def test_catalog_database_and_dialog(self) -> None:
        from setuav_studio.plugins.electrical_propulsion.database import get_motor_database, get_propeller_database
        from setuav_studio.plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog

        mot_db = get_motor_database()
        self.assertGreater(mot_db.motor_count, 100)

        prop_db = get_propeller_database()
        self.assertGreater(prop_db.propeller_count, 100)

        dialog = ComponentCatalogDialog(component_type="all")
        self.assertIsNotNone(dialog)
        dialog.motor_search.setText("Tiger")
        self.assertLessEqual(dialog.motor_table.rowCount(), 400)



if __name__ == "__main__":
    unittest.main()
