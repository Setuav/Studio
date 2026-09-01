import unittest
from importlib import resources

from PySide6.QtGui import QPalette

from setuav_studio.ui.settings.settings_pages import StudioSettings
from setuav_studio.ui.icons import application_icon, get_icon
from setuav_studio.ui.theme import (
    ACCENT_COLOR,
    DEFAULT_FONT_SIZE,
    FONT_FAMILY,
)
from tests._common import get_qapp


class ThemeTests(unittest.TestCase):
    def test_inter_font_is_applied_globally(self) -> None:
        self.assertEqual(FONT_FAMILY, "Inter")
        self.assertEqual(DEFAULT_FONT_SIZE, 10)

    def test_accent_color_is_defined(self) -> None:
        self.assertEqual(ACCENT_COLOR, "#c5a9eb")

    def test_settings_have_theme_mode_selection(self) -> None:
        settings = StudioSettings()
        self.assertEqual(settings.reopen_last_project, False)
        self.assertEqual(settings.recent_project_limit, 10)
        self.assertEqual(settings.theme_mode, "blender")

    def test_inter_font_files_are_bundled(self) -> None:
        font_root = resources.files("setuav_studio").joinpath("assets", "fonts", "Inter")

        self.assertTrue(font_root.joinpath("Inter-VariableFont_opsz,wght.ttf").is_file())
        self.assertTrue(font_root.joinpath("Inter-Italic-VariableFont_opsz,wght.ttf").is_file())
        self.assertTrue(font_root.joinpath("OFL.txt").is_file())

    def test_application_icon_is_available(self) -> None:
        self.assertFalse(application_icon().isNull())

    def test_theme_mode_switching_and_tokens(self) -> None:
        from setuav_studio.ui.theme import (
            BLENDER_TOKENS,
            DARK_TOKENS,
            LIGHT_TOKENS,
            accent_color,
            current_theme_mode,
            is_light_theme,
            set_theme_mode,
            tokens,
        )

        set_theme_mode("dark")
        self.assertEqual(current_theme_mode(), "dark")
        self.assertEqual(tokens()["window"], DARK_TOKENS["window"])
        self.assertEqual(accent_color(), DARK_TOKENS["accent"])

        set_theme_mode("light")
        self.assertEqual(current_theme_mode(), "light")
        self.assertEqual(tokens()["window"], LIGHT_TOKENS["window"])
        self.assertEqual(accent_color(), LIGHT_TOKENS["accent"])

        set_theme_mode("blender")
        self.assertEqual(current_theme_mode(), "blender")
        self.assertEqual(tokens()["window"], BLENDER_TOKENS["window"])
        self.assertEqual(accent_color(), BLENDER_TOKENS["accent"])

        for mode in ("github_dark", "github_light", "monokai", "nord"):
            set_theme_mode(mode)
            self.assertEqual(current_theme_mode(), mode)
            self.assertTrue(tokens()["window"].startswith("#"))
            self.assertTrue(accent_color().startswith("#"))

        set_theme_mode("github_light")
        self.assertTrue(is_light_theme())
        set_theme_mode("github_dark")
        self.assertFalse(is_light_theme())

        # Reset back to dark
        set_theme_mode("dark")

    def test_application_palette_and_existing_icons_follow_theme(self) -> None:
        from setuav_studio.ui.theme import apply_theme, tokens

        app = get_qapp()

        apply_theme(app, "dark")
        icon_dark = get_icon("fa6s.floppy-disk")
        dark_icon = icon_dark.pixmap(24, 24).toImage().pixelColor(12, 12)
        self.assertEqual(
            app.palette().color(QPalette.ColorRole.Window).name(),
            tokens()["window"],
        )

        apply_theme(app, "light")
        icon_light = get_icon("fa6s.floppy-disk")
        light_icon = icon_light.pixmap(24, 24).toImage().pixelColor(12, 12)
        self.assertEqual(
            app.palette().color(QPalette.ColorRole.Window).name(),
            tokens()["window"],
        )
        self.assertGreater(dark_icon.lightness(), light_icon.lightness())

        apply_theme(app, "dark")

    def test_chart_series_and_axes_are_rethemed(self) -> None:
        from plugins.aerodynamics.charts_dock import SingleChartWidget
        from setuav_studio.ui.theme import apply_theme, chart_color, tokens

        app = get_qapp()
        apply_theme(app, "dark")
        widget = SingleChartWidget("Theme test")
        widget.plot_single([0.0, 1.0], [0.0, 1.0], "CL", "blue")
        series = widget.series()[0]
        self.assertEqual(series.pen().color().name(), chart_color("blue"))

        apply_theme(app, "light")
        widget.update_theme_style()
        self.assertEqual(series.pen().color().name(), chart_color("blue"))
        self.assertEqual(widget.axes()[0].linePenColor().name(), tokens()["text_dim"])

        widget.deleteLater()
        apply_theme(app, "dark")


if __name__ == "__main__":
    unittest.main()
