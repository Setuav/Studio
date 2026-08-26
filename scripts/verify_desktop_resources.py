"""Verify resources bundled in a PyInstaller one-folder build."""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PACKAGE_ROOT = PROJECT_ROOT / "src" / "setuav_studio"
RESOURCE_DIRECTORIES = ("assets", "schemas", "data")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path, help="PyInstaller one-folder bundle")
    return parser.parse_args()


def main() -> int:
    bundle = _parse_arguments().bundle.resolve()
    package_root = bundle / "_internal" / "setuav_studio"
    expected_resources = {
        path.relative_to(SOURCE_PACKAGE_ROOT)
        for directory in RESOURCE_DIRECTORIES
        for path in (SOURCE_PACKAGE_ROOT / directory).rglob("*")
        if path.is_file()
    }
    missing = sorted(
        str(resource) for resource in expected_resources if not (package_root / resource).is_file()
    )
    if not (bundle / "_internal" / "LICENSE").is_file():
        missing.append("LICENSE")
    metadata_files = list((bundle / "_internal").glob("setuav_studio-*.dist-info/METADATA"))
    if not metadata_files:
        missing.append("setuav_studio distribution metadata")
    if missing:
        formatted = "\n  - ".join(missing)
        raise RuntimeError(f"Desktop bundle resources are missing:\n  - {formatted}")

    print(f"Desktop resources verified: {len(expected_resources)} files in {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
