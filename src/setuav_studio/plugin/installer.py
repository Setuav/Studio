"""Plugin archive extraction and user plugins directory management."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtCore import QStandardPaths

logger = logging.getLogger(__name__)

SUPPORTED_ARCHIVE_EXTENSIONS: tuple[str, ...] = (
    ".zip",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
    ".tar",
    ".rar",
)


def get_user_plugins_dir(custom_base: Path | str | None = None) -> Path:
    """Return the cross-platform user plugins directory, creating it if needed.

    Order of precedence:
    1. Explicit custom_base argument (used in tests or custom configuration)
    2. SETUAV_STUDIO_PLUGINS_DIR environment variable
    3. OS standard user data directory (QStandardPaths.AppDataLocation / "plugins")
    4. Fallback to ~/.setuav-studio/plugins
    """
    if custom_base is not None:
        plugins_dir = Path(custom_base)
    elif env_dir := os.environ.get("SETUAV_STUDIO_PLUGINS_DIR"):
        plugins_dir = Path(env_dir)
    else:
        app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        base = Path(app_data) if app_data else Path.home() / ".setuav-studio"
        plugins_dir = base / "plugins"

    plugins_dir.mkdir(parents=True, exist_ok=True)
    return plugins_dir


def _archive_stem(filename: str) -> str:
    """Return archive filename without archive extensions."""
    name = Path(filename).name
    for ext in SUPPORTED_ARCHIVE_EXTENSIONS:
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return Path(name).stem


def _validate_safe_path(target_dir: Path, relative_name: str) -> Path:
    """Ensure relative_name resolves strictly within target_dir (prevent Zip Slip)."""
    dest_path = (target_dir / relative_name).resolve()
    target_resolved = target_dir.resolve()
    if not (
        str(dest_path) == str(target_resolved)
        or str(dest_path).startswith(str(target_resolved) + os.sep)
    ):
        raise ValueError(f"Path traversal detected in archive entry: {relative_name}")
    return dest_path


def _extract_zip(archive_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            _validate_safe_path(dest_dir, member.filename)
        zf.extractall(dest_dir)


def _extract_tar(archive_path: Path, dest_dir: Path) -> None:
    with tarfile.open(archive_path, "r:*") as tf:
        for member in tf.getmembers():
            _validate_safe_path(dest_dir, member.name)
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest_dir, filter="data")
        else:
            tf.extractall(dest_dir)


def _extract_rar(archive_path: Path, dest_dir: Path) -> None:
    # 1. Try python rarfile module if available
    try:
        import rarfile  # type: ignore

        with rarfile.RarFile(archive_path, "r") as rf:
            for member in rf.infolist():
                _validate_safe_path(dest_dir, member.filename)
            rf.extractall(dest_dir)
            return
    except ImportError:
        pass

    # 2. Try external CLI extractors
    for tool in ("unrar", "rar", "7z", "bsdtar"):
        cmd = shutil.which(tool)
        if not cmd:
            continue
        if tool in ("unrar", "rar"):
            args = [cmd, "x", "-y", str(archive_path), f"{dest_dir}{os.sep}"]
        elif tool == "7z":
            args = [cmd, "x", f"-o{dest_dir}", "-y", str(archive_path)]
        elif tool == "bsdtar":
            args = [cmd, "-xf", str(archive_path), "-C", str(dest_dir)]
        else:
            continue

        res = subprocess.run(args, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return
        logger.warning("CLI tool %s failed to extract RAR archive: %s", tool, res.stderr)

    raise ValueError(
        "RAR archive extraction requires 'unrar', '7z', or the 'rarfile' Python package installed."
    )


def _extract_archive(archive_path: Path, dest_dir: Path) -> None:
    lower_name = archive_path.name.lower()
    if lower_name.endswith(".zip"):
        _extract_zip(archive_path, dest_dir)
    elif any(
        lower_name.endswith(ext)
        for ext in (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")
    ):
        _extract_tar(archive_path, dest_dir)
    elif lower_name.endswith(".rar"):
        _extract_rar(archive_path, dest_dir)
    else:
        supported = ", ".join(SUPPORTED_ARCHIVE_EXTENSIONS)
        raise ValueError(
            f"Unsupported archive format: {archive_path.name}. Supported formats: {supported}"
        )


def install_plugin_archive(
    archive_path: Path | str,
    target_plugins_dir: Path | str | None = None,
) -> Path:
    """Safely extract and install a plugin archive into the user plugins directory.

    Supports .zip, .tar.gz, .tgz, .tar.bz2, .tar.xz, .tar, and .rar formats.
    Returns the path to the newly installed plugin directory.
    """
    archive_file = Path(archive_path).resolve()
    if not archive_file.is_file():
        raise FileNotFoundError(f"Plugin archive not found: {archive_file}")

    target_dir = (
        Path(target_plugins_dir).resolve()
        if target_plugins_dir is not None
        else get_user_plugins_dir()
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="setuav_plugin_extract_") as temp_dir:
        staging_dir = Path(temp_dir)
        _extract_archive(archive_file, staging_dir)

        # Inspect extracted items, ignoring OS-generated metadata like __MACOSX
        valid_items = [
            p for p in staging_dir.iterdir() if p.name != "__MACOSX" and not p.name.startswith(".")
        ]
        if not valid_items:
            raise ValueError(f"Archive {archive_file.name} contains no valid files or folders.")

        # If archive contains a single top-level directory, use that as plugin root
        if len(valid_items) == 1 and valid_items[0].is_dir():
            plugin_source = valid_items[0]
            plugin_name = plugin_source.name
        else:
            plugin_source = staging_dir
            plugin_name = _archive_stem(archive_file.name)

        final_dest = target_dir / plugin_name
        if final_dest.exists():
            if final_dest.is_dir():
                shutil.rmtree(final_dest)
            else:
                final_dest.unlink()

        if plugin_source == staging_dir:
            shutil.copytree(
                staging_dir,
                final_dest,
                ignore=shutil.ignore_patterns("__MACOSX", ".*"),
            )
        else:
            shutil.copytree(plugin_source, final_dest)

        logger.info("Installed plugin archive %s to %s", archive_file.name, final_dest)
        return final_dest
