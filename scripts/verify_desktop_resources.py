"""Verify resources bundled in a PyInstaller desktop build."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PACKAGE_ROOT = PROJECT_ROOT / "src" / "setuav_studio"
RESOURCE_DIRECTORIES = ("assets", "data")
# Source-only folders inside the resource directories: the icon generator.
SOURCE_ONLY = (Path("assets") / "icons" / "tools",)
# Packages the plugins import on first use, so startup never touches them.
FIRST_USE_MODULES = ("aerosandbox", "aerosandbox.numpy", "neuralfoil", "casadi")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path, help="PyInstaller desktop bundle")
    return parser.parse_args()


def _internal_roots(bundle: Path) -> tuple[Path, ...]:
    if bundle.suffix == ".app":
        contents = bundle / "Contents"
        return contents / "Frameworks", contents / "Resources"
    return (bundle / "_internal",)


def _executable_path(bundle: Path) -> Path:
    if bundle.suffix == ".app":
        return bundle / "Contents" / "MacOS" / "setuav-studio"
    suffix = ".exe" if os.name == "nt" else ""
    return bundle / f"setuav-studio{suffix}"


def _bundled_modules(bundle: Path) -> set[str]:
    archive = CArchiveReader(str(_executable_path(bundle)))
    return set(archive.open_embedded_archive("PYZ.pyz").toc)


def main() -> int:
    bundle = _parse_arguments().bundle.resolve()
    internal_roots = _internal_roots(bundle)
    expected_resources = {
        path.relative_to(SOURCE_PACKAGE_ROOT)
        for directory in RESOURCE_DIRECTORIES
        for path in (SOURCE_PACKAGE_ROOT / directory).rglob("*")
        if path.is_file()
        and not any(path.relative_to(SOURCE_PACKAGE_ROOT).is_relative_to(s) for s in SOURCE_ONLY)
    }
    missing = sorted(
        str(resource)
        for resource in expected_resources
        if not any((root / "setuav_studio" / resource).is_file() for root in internal_roots)
    )
    if not any((root / "LICENSE").is_file() for root in internal_roots):
        missing.append("LICENSE")
    metadata_files = [
        metadata
        for root in internal_roots
        for metadata in root.glob("setuav_studio-*.dist-info/METADATA")
    ]
    if not metadata_files:
        missing.append("setuav_studio distribution metadata")
    plugin_package_root = PROJECT_ROOT / "src" / "plugins"
    expected_plugin_resources = {
        path.relative_to(plugin_package_root)
        for path in plugin_package_root.rglob("*")
        if path.is_file() and path.suffix not in (".py", ".pyc") and "__pycache__" not in path.parts
    }
    missing.extend(
        f"plugins/{resource}"
        for resource in sorted(expected_plugin_resources)
        if not any((root / "plugins" / resource).is_file() for root in internal_roots)
    )
    bundled_modules = _bundled_modules(bundle)
    missing.extend(
        f"module {module}" for module in FIRST_USE_MODULES if module not in bundled_modules
    )
    if missing:
        formatted = "\n  - ".join(missing)
        raise RuntimeError(f"Desktop bundle resources are missing:\n  - {formatted}")

    total_count = len(expected_resources) + len(expected_plugin_resources)
    print(f"Desktop resources verified: {total_count} files in {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
