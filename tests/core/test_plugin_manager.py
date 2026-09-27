"""Unit tests for core PluginManager lifecycle, sorting, activation, and archive installation."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QSettings

from setuav_studio.api import StudioAPI
from setuav_studio.plugin import PluginManager
from setuav_studio.plugin.installer import install_plugin_archive
from tests._common import get_qapp


@pytest.fixture(autouse=True)
def qapp() -> Any:
    return get_qapp()


@pytest.fixture(autouse=True)
def clean_qsettings() -> Any:
    settings = QSettings()
    old_disabled = settings.value("plugins/disabled", [])
    old_folders = settings.value("plugins/custom_folders", [])
    settings.setValue("plugins/disabled", [])
    settings.setValue("plugins/custom_folders", [])
    yield
    settings.setValue("plugins/disabled", old_disabled)
    settings.setValue("plugins/custom_folders", old_folders)


class DummyMockPlugin:
    def __init__(
        self, plugin_id: str, priority: int = 100, provides: dict[str, str] | None = None
    ) -> None:
        self.id = plugin_id
        self.priority = priority
        self.provides = provides or {}
        self.activated = False
        self.deactivated = False

    def activate(self, api: StudioAPI) -> None:
        self.activated = True

    def deactivate(self, api: StudioAPI) -> None:
        self.deactivated = True


class FailingMockPlugin:
    def __init__(self, plugin_id: str = "org.test.failing") -> None:
        self.id = plugin_id
        self.priority = 100

    def activate(self, api: StudioAPI) -> None:
        raise RuntimeError("Crash on activation")

    def deactivate(self, api: StudioAPI) -> None:
        pass


# ==============================================================================
# 1. Plugin Constants & Entry Point Group
# ==============================================================================


def test_plugin_entry_point_group_is_stable() -> None:
    from setuav_studio.plugin import PLUGIN_ENTRY_POINT_GROUP

    assert PLUGIN_ENTRY_POINT_GROUP == "setuav_studio.plugins"


# ==============================================================================
# 2. Plugin Activation & Deactivation Lifecycle
# ==============================================================================


def test_plugin_activation_and_deactivation() -> None:
    api = StudioAPI()
    manager = PluginManager(api)
    plugin = DummyMockPlugin("org.test.dummy", priority=50)

    # 1. Activate
    manager.activate(plugin)  # type: ignore[arg-type]
    assert manager.is_active("org.test.dummy")
    assert plugin.activated
    assert plugin in manager.active_plugins

    # 2. Duplicate activation rejects
    with pytest.raises(ValueError, match="already active"):
        manager.activate(plugin)  # type: ignore[arg-type]

    # 3. Deactivate
    manager.deactivate("org.test.dummy")
    assert not manager.is_active("org.test.dummy")
    assert plugin.deactivated
    assert plugin not in manager.active_plugins
    assert manager.is_disabled("org.test.dummy")

    # 4. Deactivating inactive plugin rejects
    with pytest.raises(ValueError, match="not active"):
        manager.deactivate("org.test.dummy")


def test_plugin_activation_failure_rollback() -> None:
    api = StudioAPI()
    manager = PluginManager(api)
    failing = FailingMockPlugin()

    with pytest.raises(RuntimeError, match="Crash on activation"):
        manager.activate(failing)  # type: ignore[arg-type]

    assert not manager.is_active(failing.id)
    assert failing not in manager.active_plugins


def test_active_plugins_ordering_by_priority() -> None:
    api = StudioAPI()
    manager = PluginManager(api)

    p1 = DummyMockPlugin("org.test.low_priority", priority=200)
    p2 = DummyMockPlugin("org.test.high_priority", priority=10)
    p3 = DummyMockPlugin("org.test.medium_priority", priority=50)

    manager.activate(p1)  # type: ignore[arg-type]
    manager.activate(p2)  # type: ignore[arg-type]
    manager.activate(p3)  # type: ignore[arg-type]

    active_ids = [p.id for p in manager.active_plugins]
    assert active_ids == [
        "org.test.high_priority",
        "org.test.medium_priority",
        "org.test.low_priority",
    ]


# ==============================================================================
# 2. Capabilities & Project Requirement Checking
# ==============================================================================


def test_plugin_provides_and_requirement_checking() -> None:
    api = StudioAPI()
    manager = PluginManager(api)
    plugin = DummyMockPlugin("org.test.aero", provides={"org.setuav.aero": "2.1.0"})

    manager.activate(plugin)  # type: ignore[arg-type]

    # Satisfied requirement
    project_data = {
        "plugins": [
            {"id": "org.setuav.aero", "version": "2.1.0"},
        ]
    }
    issues = manager.check_project_requirements(project_data)
    assert issues == []

    # Unsatisfied missing requirement
    missing_data = {
        "plugins": [
            {"id": "org.setuav.propulsion", "version": "1.0.0"},
        ]
    }
    missing_issues = manager.check_project_requirements(missing_data)
    assert len(missing_issues) == 1
    assert "org.setuav.propulsion" in missing_issues[0]


# ==============================================================================
# 3. Custom Search Folders
# ==============================================================================


def test_custom_plugin_folders(tmp_path: Path) -> None:
    api = StudioAPI()
    manager = PluginManager(api)

    folder1 = tmp_path / "extra_plugins"
    folder1.mkdir()

    # Add folder
    assert manager.add_custom_folder(folder1)
    assert folder1.resolve() in manager.custom_folders

    # Adding again returns False
    assert not manager.add_custom_folder(folder1)

    # Remove folder
    assert manager.remove_custom_folder(folder1)
    assert folder1.resolve() not in manager.custom_folders
    assert not manager.remove_custom_folder(folder1)


# ==============================================================================
# 4. Plugin Archive Installer
# ==============================================================================


def test_install_zip_archive_with_folder(tmp_path: Path) -> None:
    archive_path = tmp_path / "addon.zip"
    plugin_code = (
        "class AddonPlugin:\n"
        "    id = 'org.test.addon'\n"
        "    def activate(self, api):\n"
        "        pass\n"
    )
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("addon_pkg/plugin.py", plugin_code)

    dest_dir = tmp_path / "installed_plugins"
    dest_dir.mkdir()

    installed = install_plugin_archive(archive_path, dest_dir)
    assert installed.is_dir()
    assert (installed / "plugin.py").is_file()
    assert "class AddonPlugin" in (installed / "plugin.py").read_text(encoding="utf-8")


def test_install_tar_gz_archive_root_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "root_addon.tar.gz"
    py_file = tmp_path / "plugin.py"
    py_file.write_text("id = 'org.test.tar_addon'", encoding="utf-8")

    with tarfile.open(archive_path, "w:gz") as tf:
        tf.add(py_file, arcname="plugin.py")

    dest_dir = tmp_path / "installed_plugins"
    dest_dir.mkdir(exist_ok=True)

    installed = install_plugin_archive(archive_path, dest_dir)
    assert installed.is_dir()
    assert (installed / "plugin.py").is_file()
