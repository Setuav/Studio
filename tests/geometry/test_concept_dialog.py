"""Unit tests for the Vehicle Concept Generator Dialog."""

from __future__ import annotations

import unittest
from pathlib import Path

from plugins.geometry.dialogs.concept_dialog import (
    PRESETS,
    ConceptGeneratorDialog,
)
from setuav_studio.api import StudioAPI
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


class ConceptGeneratorDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def setUp(self) -> None:
        self.api = StudioAPI()
        self.project = ProjectDocument(
            Path("test-concept.json"),
            "json",
            {"components": []},
        )
        self.api._host.set_project(self.project)
        self.dialog = ConceptGeneratorDialog(api=self.api)

    def tearDown(self) -> None:
        self.dialog.close()

    def test_presets_loaded(self) -> None:
        expected_presets = {"talon_pusher", "conventional_tractor", "twin_boom_pusher", "flying_wing"}
        self.assertEqual(set(PRESETS.keys()), expected_presets)
        self.assertEqual(len(self.dialog._cards), 4)

    def test_default_selection_is_talon_pusher(self) -> None:
        self.assertEqual(self.dialog._selected_id, "talon_pusher")
        self.assertEqual(self.dialog.params["concept_id"], "talon_pusher")
        self.assertEqual(self.dialog.params["propulsion_layout"], "Pusher")
        self.assertEqual(self.dialog.params["tail_type"], "V-Tail")

    def test_switching_presets(self) -> None:
        self.dialog.select_preset("conventional_tractor")
        self.assertEqual(self.dialog._selected_id, "conventional_tractor")
        self.assertEqual(self.dialog.params["wingspan_mm"], 1600.0)
        self.assertEqual(self.dialog.params["propulsion_layout"], "Tractor")
        self.assertEqual(self.dialog.params["tail_type"], "Conventional")

        self.dialog.select_preset("flying_wing")
        self.assertEqual(self.dialog._selected_id, "flying_wing")
        self.assertEqual(self.dialog.params["wingspan_mm"], 1200.0)
        self.assertEqual(self.dialog.params["wing_sweep_deg"], 18.0)

    def test_derived_metrics_calculation(self) -> None:
        self.dialog.select_preset("talon_pusher")
        # Wingspan 1.4m, root 0.21m, tip 0.13m -> S = 1.4 * (0.21 + 0.13) / 2 = 0.238 m2
        # AR = 1.4^2 / 0.238 = 8.235
        config = self.dialog.get_configuration()
        b = config["wingspan_mm"] / 1000.0
        cr = config["wing_root_chord_mm"] / 1000.0
        ct = config["wing_tip_chord_mm"] / 1000.0
        s_expected = b * (cr + ct) / 2.0
        ar_expected = (b ** 2) / s_expected

        self.assertAlmostEqual(s_expected, 0.238, places=3)
        self.assertAlmostEqual(ar_expected, 8.235, places=2)

    def test_generate_signal_emitted(self) -> None:
        emitted_payload = []
        self.dialog.concept_generated.connect(lambda payload: emitted_payload.append(payload))

        self.dialog._on_generate_clicked()

        self.assertEqual(len(emitted_payload), 1)
        self.assertEqual(emitted_payload[0]["concept_id"], "talon_pusher")
        self.assertEqual(emitted_payload[0]["wingspan_mm"], 1400.0)

    def test_reset_to_defaults(self) -> None:
        self.dialog.select_preset("talon_pusher")
        self.dialog.params["wingspan_mm"] = 2200.0
        self.dialog._on_reset_clicked()
        self.assertEqual(self.dialog.params["wingspan_mm"], 1400.0)
