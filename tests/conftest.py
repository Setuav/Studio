"""Global pytest fixtures and environment setup for Setuav Studio tests."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from collections.abc import Generator

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

# Ensure headless environment variables are set before any Qt or Matplotlib imports
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QSG_RHI_BACKEND", "software")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault(
    "MPLCONFIGDIR",
    os.path.join(tempfile.gettempdir(), "setuav-studio-matplotlib"),
)

# Keep settings written by tests (units, recent projects, layouts) out of the user's
# configuration and independent between test runs.
_SETTINGS_DIR = tempfile.mkdtemp(prefix="setuav-studio-test-settings-")
atexit.register(shutil.rmtree, _SETTINGS_DIR, ignore_errors=True)
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)


@pytest.fixture(autouse=True)
def si_display_units() -> None:
    """Start every test with SI display units."""
    from setuav_studio.units import get_unit_manager

    get_unit_manager().set_active_preset("si")


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """Ensure a singleton QApplication instance exists for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    yield app
