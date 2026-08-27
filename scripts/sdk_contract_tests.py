"""Run standalone SDK and example-plugin contract tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SDK_SOURCE = PROJECT_ROOT / "packages" / "setuav-studio-sdk" / "src"
EXAMPLE_SOURCE = PROJECT_ROOT / "packages" / "example-plugin" / "src"
TEST_DIRECTORIES = (
    PROJECT_ROOT / "packages" / "setuav-studio-sdk" / "tests",
    PROJECT_ROOT / "packages" / "example-plugin" / "tests",
)


def _add_source_paths() -> None:
    """Make the standalone packages importable without installing the project."""
    sys.path[:0] = [str(SDK_SOURCE), str(EXAMPLE_SOURCE)]


def _load_suite() -> unittest.TestSuite:
    # ``TestLoader`` keeps the inferred top-level directory between discover
    # calls. The SDK and example plugin live in separate package trees, so a
    # shared loader triggers Python 3.11's "Path must be within the project"
    # assertion on the second directory.
    suites = []
    for directory in TEST_DIRECTORIES:
        loader = unittest.TestLoader()
        suites.append(loader.discover(str(directory)))
    return unittest.TestSuite(suites)


def main() -> int:
    _add_source_paths()
    result = unittest.TextTestRunner(verbosity=2).run(_load_suite())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
