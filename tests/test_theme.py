import unittest
from importlib import resources

from setuav_studio.plugins.core.settings import StudioSettings
from setuav_studio.ui.theme import (
    ACCENT_COLOR,
    DEFAULT_FONT_SIZE,
    FONT_FAMILY,
    INACTIVE_SELECTION_COLOR,
    build_stylesheet,
)


class ThemeTests(unittest.TestCase):
    def test_inter_font_is_applied_globally(self) -> None:
        stylesheet = build_stylesheet(DEFAULT_FONT_SIZE)

        self.assertEqual(FONT_FAMILY, "Inter")
        self.assertEqual(DEFAULT_FONT_SIZE, 10)
        self.assertIn('font-family: "Inter"', stylesheet)
        self.assertIn("font-size: 10pt", stylesheet)
        self.assertIn("QDockWidget", stylesheet)
        self.assertIn("QComboBox QAbstractItemView", stylesheet)
        self.assertIn('QAbstractItemView[tableComboPopup="true"]', stylesheet)

    def test_accent_color_is_defined(self) -> None:
        self.assertEqual(ACCENT_COLOR, "#c5a9eb")

    def test_tables_are_compact_and_use_alternating_palette_rows(self) -> None:
        stylesheet = build_stylesheet(DEFAULT_FONT_SIZE)

        self.assertIn("alternate-background-color: palette(alternate-base)", stylesheet)
        self.assertIn("QTableView:!focus", stylesheet)
        self.assertIn(
            f"selection-background-color: {INACTIVE_SELECTION_COLOR}",
            stylesheet,
        )
        self.assertIn("padding: 0 4px", stylesheet)
        self.assertIn("padding: 1px 4px", stylesheet)
        self.assertIn("width: 8px", stylesheet)
        self.assertIn("height: 8px", stylesheet)

    def test_settings_have_no_theme_or_font_selection(self) -> None:
        self.assertEqual(StudioSettings().reopen_last_project, False)
        self.assertEqual(StudioSettings().recent_project_limit, 10)

    def test_inter_font_files_are_bundled(self) -> None:
        font_root = resources.files("setuav_studio").joinpath(
            "assets", "fonts", "Inter"
        )

        self.assertTrue(font_root.joinpath("Inter-VariableFont_opsz,wght.ttf").is_file())
        self.assertTrue(
            font_root.joinpath("Inter-Italic-VariableFont_opsz,wght.ttf").is_file()
        )
        self.assertTrue(font_root.joinpath("OFL.txt").is_file())


if __name__ == "__main__":
    unittest.main()
