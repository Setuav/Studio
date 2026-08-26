import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from PySide6.QtWidgets import QLabel

from setuav_studio.ui.about_dialog import AboutDialog, application_version
from tests._common import get_qapp


class AboutDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapp()

    def test_displays_logo_version_and_license_notice(self) -> None:
        with patch(
            "setuav_studio.ui.about_dialog.distribution_version",
            return_value="1.2.3",
        ):
            dialog = AboutDialog()
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.windowTitle(), "About")
        self.assertEqual(dialog.findChild(QLabel, "aboutTitle").text(), "Setuav Studio")
        self.assertEqual(dialog.findChild(QLabel, "aboutVersion").text(), "Version 1.2.3")
        self.assertIn("MIT License", dialog.findChild(QLabel, "aboutLicense").text())
        self.assertFalse(dialog.findChild(QLabel, "aboutLogo").pixmap().isNull())

    def test_version_falls_back_outside_an_installed_package(self) -> None:
        with patch(
            "setuav_studio.ui.about_dialog.distribution_version",
            side_effect=PackageNotFoundError,
        ):
            self.assertEqual(application_version(), "development")


if __name__ == "__main__":
    unittest.main()
