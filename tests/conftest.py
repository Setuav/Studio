"""Global pytest fixtures and environment setup for Setuav Studio tests."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest
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


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """Ensure a singleton QApplication instance exists for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    yield app
