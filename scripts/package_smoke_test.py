"""Verify an installed Setuav Studio wheel and its bundled resources."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

import setuav_studio

EXPECTED_FILES = (
    "setuav_studio/assets/icons/manifest.toml",
    "setuav_studio/assets/icons/project-open-file.png",
    "setuav_studio/assets/icons/studio.icns",
    "setuav_studio/assets/icons/studio.ico",
    "setuav_studio/assets/icons/studio.png",
    "setuav_studio/assets/fonts/Inter/Inter-VariableFont_opsz,wght.ttf",
    "setuav_studio/assets/fonts/Inter/OFL.txt",
    "setuav_studio/schemas/core/project.schema.json",
    "setuav_studio/schemas/plugins/org.setuav.core/plugin.json",
    "setuav_studio/data/airfoils/clarky.dat",
)


def _console_script_path() -> Path:
    # Keep the virtual-environment path: resolving the Python symlink would
    # incorrectly point at the system interpreter's bin directory.
    scripts_dir = Path(sys.executable).parent
    suffix = ".exe" if os.name == "nt" else ""
    return scripts_dir / f"setuav-studio{suffix}"


def main() -> int:
    distribution = importlib.metadata.distribution("setuav-studio")
    installed_files = {str(path) for path in distribution.files or ()}
    missing_files = sorted(set(EXPECTED_FILES) - installed_files)
    if missing_files:
        missing = "\n  - ".join(missing_files)
        raise RuntimeError(f"Wheel resources are missing:\n  - {missing}")

    package_file = Path(setuav_studio.__file__).resolve()
    if not package_file.is_file():
        raise RuntimeError(f"Package import path does not exist: {package_file}")

    entry_points = {
        entry_point.name
        for entry_point in distribution.entry_points
        if entry_point.group == "console_scripts"
    }
    if "setuav-studio" not in entry_points:
        raise RuntimeError("setuav-studio console entry point is missing")

    console_script = _console_script_path()
    if not console_script.is_file():
        raise RuntimeError(f"Console script does not exist: {console_script}")

    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    help_result = subprocess.run(
        [str(console_script), "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if help_result.returncode != 0 or "usage: setuav-studio" not in help_result.stdout:
        raise RuntimeError(
            "setuav-studio --help failed:\n"
            f"stdout:\n{help_result.stdout}\n"
            f"stderr:\n{help_result.stderr}"
        )

    print(
        f"Package smoke test passed: setuav-studio {distribution.version}, "
        f"{len(EXPECTED_FILES)} resources"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
