"""Unit tests for Debug Plugin Inspector and Status Panel."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from plugins.debug import DebugPlugin
from plugins.debug.panel import DebugPanel
from setuav_studio.api import StudioAPI
from setuav_studio.project import create_project


class TestDebugPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_debug_panel.suav"
        self.api = StudioAPI()
        self.api._host.set_project(create_project(self.project_path))
        self.plugin = DebugPlugin()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_debug_plugin_registers_panel_hidden_by_default(self) -> None:
        registered_panels = []
        self.api._register_panel = lambda p: registered_panels.append(p)

        self.plugin.activate(self.api)
        debug_panels = [p for p in registered_panels if p.id == "debug:panel"]
        self.assertEqual(len(debug_panels), 1)

        panel_contrib = debug_panels[0]
        self.assertEqual(panel_contrib.title, "Debug")
        self.assertFalse(panel_contrib.default_visible)

        # Test deactivate unregisters
        unregistered = []
        self.api._unregister_panel = lambda pid: unregistered.append(pid)
        self.plugin.deactivate(self.api)
        self.assertIn("debug:panel", unregistered)

    def test_debug_panel_tabs_and_structure(self) -> None:
        panel = DebugPanel(self.api)
        self.assertEqual(panel._tabs.count(), 2)
        self.assertEqual(panel._tabs.tabText(0), "Inspector")
        self.assertEqual(panel._tabs.tabText(1), "Status")

    def test_inspector_with_component_selection(self) -> None:
        panel = DebugPanel(self.api)

        comp_data = {
            "id": "box_test_1",
            "name": "Test Box",
            "type": "debug:box",
            "attach_to": "fuselage_root",
            "position": [1.5, 0.0, 0.5],
            "rotation": [0.0, 15.0, 0.0],
            "parameters": {"width": 2.0, "height": 1.0, "depth": 0.5},
        }

        # Simulate selection changed
        self.api.set_selection(comp_data)

        # Check selection table
        self.assertEqual(panel._property_value(panel.selection_table, "kind"), "Component")
        self.assertIn("Test Box", panel._property_value(panel.selection_table, "target"))

        # Check component table
        self.assertEqual(panel._property_value(panel.component_table, "name"), "Test Box")
        self.assertEqual(panel._property_value(panel.component_table, "id"), "box_test_1")
        self.assertEqual(panel._property_value(panel.component_table, "attach_to"), "fuselage_root")
        self.assertIn("1.500", panel._property_value(panel.component_table, "position"))

        # Check parameters table
        self.assertEqual(panel.params_table.rowCount(), 3)
        self.assertEqual(panel._property_value(panel.params_table, "width"), "2.0")

    def test_inspector_with_empty_selection(self) -> None:
        panel = DebugPanel(self.api)
        self.api.set_selection(None)

        self.assertEqual(panel._property_value(panel.selection_table, "kind"), "-")
        self.assertEqual(panel._property_value(panel.component_table, "name"), "-")

    def test_status_tab_metrics_and_events(self) -> None:
        panel = DebugPanel(self.api)
        panel._refresh_status()

        uptime_val = panel._property_value(panel.system_table, "uptime")
        self.assertTrue(len(uptime_val) >= 5)  # HH:MM:SS

        ram_val = panel._property_value(panel.system_table, "ram_rss")
        self.assertIn("MB", ram_val)

        python_val = panel._property_value(panel.system_table, "python")
        self.assertTrue(python_val.startswith("3."))

        # Trigger events and verify event stream
        panel._log_event("TEST_EVENT", {"id": "obj_123"})
        self.assertEqual(panel.events_table.rowCount(), 1)
        event_name = panel.events_table.item(0, 1)
        event_details = panel.events_table.item(0, 2)
        assert event_name is not None
        assert event_details is not None
        self.assertEqual(event_name.text(), "TEST_EVENT")
        self.assertIn("id=obj_123", event_details.text())

        # Test clear button
        panel._clear_events()
        self.assertEqual(panel.events_table.rowCount(), 0)
        self.assertEqual(len(panel._events_history), 0)
