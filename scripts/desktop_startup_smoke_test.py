"""Start a PyInstaller desktop bundle and require a clean automatic exit."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_PROJECT = PROJECT_ROOT / "tests" / "fixtures" / "fixed-wing" / "project.json"
SMOKE_TEST_TIMEOUT_SECONDS = int(os.environ.get("SETUAV_DESKTOP_SMOKE_TIMEOUT", "60"))


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path, help="PyInstaller desktop bundle")
    return parser.parse_args()


def _executable_path(bundle: Path) -> Path:
    if bundle.suffix == ".app":
        return bundle / "Contents" / "MacOS" / "setuav-studio"
    suffix = ".exe" if os.name == "nt" else ""
    return bundle / f"setuav-studio{suffix}"


def _run_command(executable: Path, arguments: list[str], environment: dict[str, str]) -> None:
    result = subprocess.run(
        [str(executable), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=SMOKE_TEST_TIMEOUT_SECONDS,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Desktop command failed: {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def main() -> int:
    arguments = _parse_arguments()
    bundle = arguments.bundle.resolve()
    executable = _executable_path(bundle)
    if not executable.is_file():
        raise RuntimeError(f"Desktop executable is missing: {executable}")

    with tempfile.TemporaryDirectory(prefix="setuav-desktop-smoke-") as temporary_directory:
        environment = os.environ.copy()
        environment.update(
            {
                "MPLCONFIGDIR": str(Path(temporary_directory) / "matplotlib"),
                "QT_QPA_PLATFORM": "offscreen",
                "XDG_CACHE_HOME": str(Path(temporary_directory) / "cache"),
                "XDG_CONFIG_HOME": str(Path(temporary_directory) / "config"),
                "XDG_DATA_HOME": str(Path(temporary_directory) / "data"),
            }
        )
        _run_command(executable, ["--smoke-test"], environment)

    print(f"Desktop startup smoke test passed: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
