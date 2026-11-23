"""Values shown outside property cells keep their precision in the active display unit."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from setuav_studio.api import ParameterField, StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.units import get_unit_manager
from tests._common import get_qapp


def _fuselage() -> dict[str, Any]:
    return {
        "id": "fuselage-1",
        "name": "Fuselage",
        "type": "org.setuav.core:fuselage",
        "parameters": {
            "geometry": {
                "segments": [
                    {
                        "id": "seg_1",
                        "sections": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "circle", "diameter": 80.0},
                            },
                            {
                                "position": {"x": 255.0, "y": 0.0, "z": 0.0},
                                "profile": {"type": "ellipse", "width": 125.0, "height": 60.0},
                            },
                        ],
                    }
                ]
            }
        },
    }


class UnitDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def setUp(self) -> None:
        get_unit_manager().set_display_unit("length", "m")

    def test_fuselage_profile_size(self) -> None:
        from plugins.geometry.editors.fuselage.profile_editor import format_profile_size

        profile = {"type": "ellipse", "width": 125.0, "height": 60.0}
        self.assertEqual(format_profile_size(profile), "0.125 × 0.06 m")

    def test_fuselage_section_list_and_dialog(self) -> None:
        from plugins.geometry.editors.fuselage import FuselageEditor, FuselageSectionDialog

        api = StudioAPI()
        fuselage = _fuselage()
        api._host.set_project(
            ProjectDocument(Path("test.json"), "json", {"components": [fuselage]})
        )

        editor = FuselageEditor(api, fuselage)
        self.addCleanup(editor.deleteLater)
        texts = [
            item.text()
            for column in range(editor.sections_table.columnCount())
            if (item := editor.sections_table.item(1, column)) is not None
        ]
        self.assertIn("0.255 m", texts)

        dialog = FuselageSectionDialog(api, fuselage)
        self.addCleanup(dialog.deleteLater)
        dialog._on_next_section()
        self.assertIn("(X = 0.255 m)", dialog.section_label.text())

    def test_envelope_section_table(self) -> None:
        from setuav_studio.ui.editor.envelope import EnvelopeEditor

        api = StudioAPI()
        component = {
            "id": "box",
            "type": "org.setuav.core:battery",
            "envelope": {
                "shape": "box",
                "size_mm": {"x": 100.0, "y": 45.0, "z": 30.0},
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
                "sections": [
                    {"station_x_mm": 255.0, "width_mm": 45.0, "height_mm": 30.0},
                    {"station_x_mm": 355.0, "width_mm": 45.0, "height_mm": 30.0},
                ],
            },
        }
        api._host.set_project(
            ProjectDocument(Path("test.json"), "json", {"components": [component]})
        )
        editor = EnvelopeEditor(api, component)
        self.addCleanup(editor.deleteLater)
        item = editor.sections_table.item(0, 0)
        assert item is not None
        self.assertEqual(item.text(), "0.255 m")

    def test_control_surface_list_deflection(self) -> None:
        from plugins.geometry.editors.lifting_surface.control_surfaces_section import (
            ControlSurfacesSectionMixin,
        )

        get_unit_manager().set_display_unit("angle", "rad")
        host = SimpleNamespace(_cs_geom=lambda cs: cs["parameters"]["geometry"])
        cs = {"name": "Aileron", "parameters": {"geometry": {"deflection": 12.5}}}
        _, _, deflection = ControlSurfacesSectionMixin._cs_table_row_values(host, 0, cs)  # type: ignore[arg-type]
        self.assertEqual(deflection, "+0.218 rad")
        get_unit_manager().set_display_unit("angle", "deg")
        for value, expected in ((0.5, "+0.5 °"), (0.0, "0.0 °"), (-3.0, "-3.0 °")):
            cs["parameters"]["geometry"]["deflection"] = value
            _, _, deflection = ControlSurfacesSectionMixin._cs_table_row_values(host, 0, cs)  # type: ignore[arg-type]
            self.assertEqual(deflection, expected)

    def test_table_parameter_cells(self) -> None:
        from setuav_studio.ui.editor.component import _format_table_cell_value

        column = ParameterField(key="x", unit="mm", decimals=1)
        self.assertEqual(_format_table_cell_value(255.0, column), "0.255")

    def test_geometry_editors_subscribe_and_clean_up_units_event(self) -> None:
        from PySide6.QtWidgets import QApplication

        from plugins.geometry.editors.control_surface import ControlSurfaceEditor
        from plugins.geometry.editors.fuselage import FuselageEditor
        from plugins.geometry.editors.lifting_surface import LiftingSurfaceEditor
        from setuav_studio.api import StudioEvents
        from setuav_studio.project import open_project
        from tests._common import TEST_PROJECT_PATH

        project = open_project(TEST_PROJECT_PATH)
        fuselage = _fuselage()
        wing = project.get_component("main-wing")
        assert wing is not None
        cs: dict[str, Any] = {
            "id": "cs-1",
            "name": "Aileron",
            "type": "org.setuav.core:control-surface",
            "attach_to": "main-wing",
            "parameters": {
                "geometry": {
                    "type": "aileron",
                    "sizing_mode": "ratio",
                    "eta_start": 0.5,
                    "eta_end": 0.9,
                    "chord_fraction": 0.25,
                }
            },
        }
        api = StudioAPI()
        api._host.set_project(
            ProjectDocument(Path("test.json"), "json", {"components": [fuselage, wing, cs]})
        )

        before = len(api._event_subscribers.get(StudioEvents.UNITS_CHANGED, []))
        fus_editor = FuselageEditor(api, fuselage)
        wing_editor = LiftingSurfaceEditor(api, wing)
        cs_editor = ControlSurfaceEditor(api, cs)

        # FuselageEditor, LiftingSurfaceEditor, DriverPlanformTable, ControlSurfaceEditor.
        during = len(api._event_subscribers.get(StudioEvents.UNITS_CHANGED, []))
        self.assertEqual(during - before, 4)

        # Live unit switch updates displayed units via StudioEvents.UNITS_CHANGED.
        get_unit_manager().set_display_unit("length", "mm")
        get_unit_manager().units_changed.emit()
        texts = [
            item.text()
            for column in range(fus_editor.sections_table.columnCount())
            if (item := fus_editor.sections_table.item(1, column)) is not None
        ]
        self.assertIn("255.0 mm", texts)

        # Destroying editors automatically unsubscribes all unit listeners.
        from PySide6.QtCore import QCoreApplication, QEvent

        fus_editor.deleteLater()
        wing_editor.deleteLater()
        cs_editor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
        after = len(api._event_subscribers.get(StudioEvents.UNITS_CHANGED, []))
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
