import unittest
from importlib import resources

from PySide6.QtGui import QPalette

from setuav_studio.ui.settings.settings_pages import StudioSettings
from setuav_studio.ui.style.icons import application_icon
from setuav_studio.ui.style.theme import (
    ACCENT_COLOR,
    DEFAULT_FONT_SIZE,
    FONT_FAMILY,
)
from tests._common import get_qapp


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def test_inter_font_is_applied_globally(self) -> None:
        self.assertEqual(FONT_FAMILY, "Inter")
        self.assertEqual(DEFAULT_FONT_SIZE, 10)

    def test_accent_color_is_defined(self) -> None:
        self.assertEqual(ACCENT_COLOR, "#c5a9eb")

    def test_settings_have_theme_mode_selection(self) -> None:
        settings = StudioSettings()
        self.assertEqual(settings.reopen_last_project, False)
        self.assertEqual(settings.recent_project_limit, 10)
        self.assertEqual(settings.theme_mode, "native")

    def test_inter_font_files_are_bundled(self) -> None:
        font_root = resources.files("setuav_studio").joinpath("assets", "fonts", "Inter")

        self.assertTrue(font_root.joinpath("Inter-VariableFont_opsz,wght.ttf").is_file())
        self.assertTrue(font_root.joinpath("Inter-Italic-VariableFont_opsz,wght.ttf").is_file())
        self.assertTrue(font_root.joinpath("OFL.txt").is_file())

    def test_application_icon_is_available(self) -> None:
        self.assertFalse(application_icon().isNull())

    def test_theme_mode_switching_and_tokens(self) -> None:
        from setuav_studio.ui.style.theme import (
            BLENDER_TOKENS,
            DARK_TOKENS,
            accent_color,
            current_theme_mode,
            set_theme_mode,
            tokens,
        )

        set_theme_mode("native")
        self.assertEqual(current_theme_mode(), "native")
        self.assertEqual(tokens()["window"], DARK_TOKENS["window"])
        self.assertEqual(accent_color(), DARK_TOKENS["accent"])

        set_theme_mode("blender")
        self.assertEqual(current_theme_mode(), "blender")
        self.assertEqual(tokens()["window"], BLENDER_TOKENS["window"])
        self.assertEqual(accent_color(), BLENDER_TOKENS["accent"])

        for mode in ("github", "monokai", "nord"):
            set_theme_mode(mode)
            self.assertEqual(current_theme_mode(), mode)
            self.assertTrue(tokens()["window"].startswith("#"))
            self.assertTrue(accent_color().startswith("#"))

        # Reset back to native
        set_theme_mode("native")

    def test_application_palette_and_existing_icons_follow_theme(self) -> None:
        from setuav_studio.ui.style.theme import apply_theme, tokens

        app = get_qapp()

        apply_theme(app, "native")
        self.assertEqual(
            app.palette().color(QPalette.ColorRole.Window).name(),
            tokens()["window"],
        )

        apply_theme(app, "nord")
        self.assertEqual(
            app.palette().color(QPalette.ColorRole.Window).name(),
            tokens()["window"],
        )

        apply_theme(app, "native")

    def test_chart_series_and_axes_are_rethemed(self) -> None:
        from PySide6.QtCore import Qt

        from setuav_studio.ui.style.theme import apply_theme, chart_color, tokens
        from setuav_studio.ui.widget.chart import StudioChartWidget

        app = get_qapp()
        apply_theme(app, "native")
        widget = StudioChartWidget("Theme test")
        axis_x = widget.create_axis("X")
        axis_y = widget.create_axis("Y")
        widget.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        widget.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series = widget.create_line_series("CL", "blue")
        widget.add_line_series(series, axis_x, axis_y)
        self.assertEqual(series.pen().color().name(), chart_color("blue"))

        apply_theme(app, "nord")
        widget.update_theme_style()
        self.assertEqual(series.pen().color().name(), chart_color("blue"))
        self.assertEqual(widget.axes()[0].linePenColor().name(), tokens()["text_dim"])

        widget.deleteLater()
        apply_theme(app, "native")


if __name__ == "__main__":
    unittest.main()
