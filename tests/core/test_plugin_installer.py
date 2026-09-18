import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from setuav_studio.api import PluginManager, StudioAPI
from setuav_studio.api.installer import (
    get_user_plugins_dir,
    install_plugin_archive,
)
from setuav_studio.ui.dialog.plugin_manager import PluginManagerDialog


class TestPluginInstaller(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from PySide6.QtCore import QSettings

        QSettings().setValue("plugins/disabled", [])
        self.temp_dir = tempfile.TemporaryDirectory()
        self.user_dir = Path(self.temp_dir.name) / "plugins"
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.api = StudioAPI()
        self.manager = PluginManager(self.api)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_get_user_plugins_dir_precedence(self) -> None:
        custom_base = Path(self.temp_dir.name) / "custom_base"
        dir1 = get_user_plugins_dir(custom_base)
        self.assertEqual(dir1, custom_base)
        self.assertTrue(dir1.is_dir())

        with patch.dict(os.environ, {"SETUAV_STUDIO_PLUGINS_DIR": str(self.user_dir)}):
            dir2 = get_user_plugins_dir()
            self.assertEqual(dir2, self.user_dir)

    def test_install_zip_archive_with_top_level_dir(self) -> None:
        archive_path = Path(self.temp_dir.name) / "sample_plugin.zip"
        plugin_code = """
class SamplePlugin:
    id = "org.sample.plugin"
    priority = 200

    def activate(self, api) -> None:
        api.show_status("Sample plugin active", "info")

    def deactivate(self, api) -> None:
        pass
"""
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("sample_plugin/plugin.py", plugin_code)

        installed_dir = install_plugin_archive(archive_path, self.user_dir)
        self.assertEqual(installed_dir.name, "sample_plugin")
        self.assertTrue((installed_dir / "plugin.py").is_file())

        with patch.dict(os.environ, {"SETUAV_STUDIO_PLUGINS_DIR": str(self.user_dir)}):
            issues = self.manager.discover()
            self.assertEqual(issues, [])
            self.assertTrue(self.manager.is_active("org.sample.plugin"))
            self.manager.deactivate("org.sample.plugin")
            self.assertFalse(self.manager.is_active("org.sample.plugin"))

    def test_install_tar_gz_archive_root_files(self) -> None:
        archive_path = Path(self.temp_dir.name) / "root_plugin.tar.gz"
        plugin_code = """
class RootPlugin:
    id = "org.root.plugin"

    def activate(self, api) -> None:
        pass

    def deactivate(self, api) -> None:
        pass

PLUGIN = RootPlugin()
"""
        py_file = Path(self.temp_dir.name) / "plugin.py"
        py_file.write_text(plugin_code, encoding="utf-8")

        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(py_file, arcname="plugin.py")

        installed_dir = install_plugin_archive(archive_path, self.user_dir)
        self.assertEqual(installed_dir.name, "root_plugin")
        self.assertTrue((installed_dir / "plugin.py").is_file())

        with patch.dict(os.environ, {"SETUAV_STUDIO_PLUGINS_DIR": str(self.user_dir)}):
            issues = self.manager.discover()
            self.assertEqual(issues, [])
            self.assertTrue(self.manager.is_active("org.root.plugin"))

    def test_path_traversal_detection(self) -> None:
        malicious_zip = Path(self.temp_dir.name) / "evil.zip"
        with zipfile.ZipFile(malicious_zip, "w") as zf:
            zf.writestr("../../evil.txt", "evil content")

        with self.assertRaises(ValueError):
            install_plugin_archive(malicious_zip, self.user_dir)

    def test_unsupported_archive_format(self) -> None:
        bad_file = Path(self.temp_dir.name) / "fake.txt"
        bad_file.write_text("not an archive", encoding="utf-8")

        with self.assertRaises(ValueError):
            install_plugin_archive(bad_file, self.user_dir)

    def test_install_archive_via_manager_and_dialog(self) -> None:
        archive_path = Path(self.temp_dir.name) / "dialog_plugin.zip"
        plugin_code = """
class DialogPlugin:
    id = "org.dialog.plugin"

    def activate(self, api) -> None:
        pass

    def deactivate(self, api) -> None:
        pass
"""
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("dialog_plugin/plugin.py", plugin_code)

        with patch.dict(os.environ, {"SETUAV_STUDIO_PLUGINS_DIR": str(self.user_dir)}):
            installed = self.manager.install_archive(archive_path)
            self.assertEqual(installed.name, "dialog_plugin")
            self.assertTrue(self.manager.is_active("org.dialog.plugin"))

            dialog = PluginManagerDialog(self.manager)
            self.assertIsNotNone(dialog._install)
            self.assertIsNotNone(dialog._open_folder)

            # Check that org.dialog.plugin appears in tree
            plugin_ids = [
                dialog._plugins.topLevelItem(i).data(1, 0)
                for i in range(dialog._plugins.topLevelItemCount())
            ]
            self.assertIn("org.dialog.plugin", plugin_ids)

    def test_custom_plugin_folder_management(self) -> None:
        custom_dir = Path(self.temp_dir.name) / "external_plugins"
        custom_dir.mkdir(parents=True, exist_ok=True)
        plugin_file = custom_dir / "custom_test_plugin.py"
        plugin_file.write_text(
            """
class CustomTestPlugin:
    id = "org.custom.test.plugin"
    def activate(self, api) -> None:
        pass
    def deactivate(self, api) -> None:
        pass
""",
            encoding="utf-8",
        )

        self.assertTrue(self.manager.add_custom_folder(custom_dir))
        self.assertIn(custom_dir.resolve(), self.manager.custom_folders)

        issues = self.manager.discover()
        self.assertEqual(issues, [])
        self.assertTrue(self.manager.is_active("org.custom.test.plugin"))

        dialog = PluginManagerDialog(self.manager)
        self.assertEqual(dialog._custom_folders_table.rowCount(), 1)
        self.assertEqual(dialog._custom_folders_table.item(0, 0).text(), str(custom_dir.resolve()))
        self.assertEqual(dialog._custom_folders_table.item(0, 1).text(), "Found")

        self.assertTrue(self.manager.remove_custom_folder(custom_dir))
        self.assertNotIn(custom_dir.resolve(), self.manager.custom_folders)


if __name__ == "__main__":
    unittest.main()
