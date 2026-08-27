"""Start a PyInstaller desktop bundle and require a clean automatic exit."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_PROJECT = PROJECT_ROOT / "tests" / "fixtures" / "fixed-wing" / "project.json"


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
        timeout=60,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Desktop command failed: {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def _viewer_payload_path() -> Path:
    project = json.loads(TEST_PROJECT.read_text(encoding="utf-8"))
    payload = {
        "components": project["components"],
        "condition": {
            "velocity": 25.0,
            "altitude": 100.0,
            "alpha": 4.0,
            "beta": 0.0,
            "control_deflections": {},
        },
        "mesh": {"spanwise_resolution": 4, "chordwise_resolution": 2},
    }
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix="setuav-viewer-smoke-",
        suffix=".json",
        delete=False,
    ) as stream:
        json.dump(payload, stream)
        return Path(stream.name)


def main() -> int:
    bundle = _parse_arguments().bundle.resolve()
    executable = _executable_path(bundle)
    if not executable.is_file():
        raise RuntimeError(f"Desktop executable is missing: {executable}")

    with tempfile.TemporaryDirectory(prefix="setuav-desktop-smoke-") as temporary_directory:
        environment = os.environ.copy()
        environment.update(
            {
                "MPLCONFIGDIR": str(Path(temporary_directory) / "matplotlib"),
                "PYVISTA_OFF_SCREEN": "true",
                "QT_QPA_PLATFORM": "offscreen",
                "XDG_CACHE_HOME": str(Path(temporary_directory) / "cache"),
                "XDG_CONFIG_HOME": str(Path(temporary_directory) / "config"),
                "XDG_DATA_HOME": str(Path(temporary_directory) / "data"),
            }
        )
        _run_command(executable, ["--smoke-test"], environment)
        viewer_payload = _viewer_payload_path()
        try:
            _run_command(
                executable,
                ["--smoke-test-aero-3d", str(viewer_payload)],
                environment,
            )
        finally:
            viewer_payload.unlink(missing_ok=True)

    print(f"Desktop startup and VLM viewer smoke tests passed: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
