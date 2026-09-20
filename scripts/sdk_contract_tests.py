"""Run API contract tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_SOURCE = PROJECT_ROOT / "src"


def _add_source_paths() -> None:
    """Make the packages importable."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    if str(SRC_SOURCE) not in sys.path:
        sys.path.insert(0, str(SRC_SOURCE))


def main() -> int:
    _add_source_paths()
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.core.test_sdk")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
