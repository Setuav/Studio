"""Run the debug plugin tests without a display, with throwaway settings and SI units."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

import pytest
from PySide6.QtCore import QSettings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")

_SETTINGS_DIR = tempfile.mkdtemp(prefix="setuav-debug-test-settings-")
atexit.register(shutil.rmtree, _SETTINGS_DIR, ignore_errors=True)
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)


@pytest.fixture(autouse=True)
def si_display_units() -> None:
    """Start every test with SI display units."""
    from setuav_studio.units import get_unit_manager

    get_unit_manager().set_active_preset("si")
