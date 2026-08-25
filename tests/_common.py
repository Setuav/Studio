"""Shared test helpers for setuav-studio tests."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

TEST_PROJECT_PATH = Path(__file__).parent / "fixtures" / "fixed-wing"


def get_qapp() -> QApplication:
    """Return the singleton QApplication, creating it if needed."""
    return QApplication.instance() or QApplication([])
