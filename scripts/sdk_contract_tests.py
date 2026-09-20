"""Run SDK contract tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SDK_SOURCE = PROJECT_ROOT / "packages" / "setuav-studio-sdk" / "src"
SRC_SOURCE = PROJECT_ROOT / "src"
TEST_DIRECTORY = PROJECT_ROOT / "packages" / "setuav-studio-sdk" / "tests"


def _add_source_paths() -> None:
    """Make the packages importable."""
    sys.path[:0] = [str(SDK_SOURCE), str(SRC_SOURCE)]


def _load_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    return loader.discover(str(TEST_DIRECTORY))


def main() -> int:
    _add_source_paths()
    result = unittest.TextTestRunner(verbosity=2).run(_load_suite())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
