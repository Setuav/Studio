"""MkDocs build hooks for the unified documentation site."""

from __future__ import annotations

from pathlib import Path
from subprocess import run


def on_startup(command: str, dirty: bool) -> None:
    """Generate the SDK Doxygen site before MkDocs indexes documentation files."""
    del dirty
    repository = Path.cwd()
    doxyfile = repository / "Doxyfile"
    if not doxyfile.is_file():
        return

    # ``mkdocs serve`` may invoke the startup hook again for live rebuilds.
    # Avoid rewriting the generated tree on every rebuild: those writes are
    # themselves watched by MkDocs and otherwise cause an endless reload loop.
    output_index = repository / "docs" / "developer" / "sdk-api" / "index.html"
    if command == "serve" and output_index.is_file():
        return

    result = run(["doxygen", str(doxyfile)], cwd=repository, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Doxygen failed with exit code {result.returncode}")
