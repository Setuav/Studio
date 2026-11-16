"""Propulsion component database loader bridging PyThrust datasets."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QSettings
from pythrust.motors.database import MotorDatabase
from pythrust.propellers.database import PropellerDatabase, PropellerEntry

logger = logging.getLogger(__name__)

_PYTHRUST_SETTINGS_KEY = "propulsion/pythrust_data_dir"


def _bundled_dataset_dir() -> Path | None:
    """Dataset shipped inside the pythrust package (>= 0.3.0), if present."""
    try:
        from pythrust import dataset_dir

        return dataset_dir()
    except ImportError:
        return None


def _resolve_pythrust_data_dir() -> Path | None:
    env_dir = os.environ.get("PYTHRUST_DATA_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)

    settings_dir = str(QSettings().value(_PYTHRUST_SETTINGS_KEY, "", type=str) or "")
    if settings_dir and Path(settings_dir).exists():
        return Path(settings_dir)

    bundled_dir = _bundled_dataset_dir()
    if bundled_dir is not None and bundled_dir.exists():
        return bundled_dir

    # Fallback: sibling checkout of the PyThrust repo in a source tree.
    for candidate in (
        Path(__file__).resolve().parents[5] / "PyThrust" / "pythrust" / "data",
        Path.cwd().parent / "PyThrust" / "pythrust" / "data",
    ):
        if candidate.exists():
            return candidate

    logger.warning(
        "PyThrust dataset directory not found. Set PYTHRUST_DATA_DIR or "
        "configure the 'PyThrust data directory' in Settings."
    )
    return None


_MOTOR_DB: MotorDatabase | None = None
_PROP_DB: PropellerDatabase | None = None
_PROP_ENTRIES: dict[str, PropellerEntry] = {}


def get_motor_database() -> MotorDatabase:
    global _MOTOR_DB
    if _MOTOR_DB is None:
        _MOTOR_DB = MotorDatabase()
        data_dir = _resolve_pythrust_data_dir()
        if data_dir is not None:
            motor_dir = data_dir / "motors"
            if motor_dir.exists():
                _MOTOR_DB.load(motor_dir)
            else:
                logger.warning("PyThrust motors subdirectory not found at %s", motor_dir)
    return _MOTOR_DB


def _propeller_dir() -> Path | None:
    data_dir = _resolve_pythrust_data_dir()
    if data_dir is None:
        return None
    prop_dir = data_dir / "propellers"
    apc_dir = prop_dir / "apc_202602"
    if apc_dir.exists():
        return apc_dir
    if prop_dir.exists():
        return prop_dir
    logger.warning("PyThrust propellers subdirectory not found at %s", prop_dir)
    return None


def get_propeller_database() -> PropellerDatabase:
    global _PROP_DB
    if _PROP_DB is None:
        _PROP_DB = PropellerDatabase()
        prop_dir = _propeller_dir()
        if prop_dir is not None:
            _PROP_DB.load(prop_dir)
    return _PROP_DB


def get_propeller_entry(prop_id: str) -> PropellerEntry | None:
    """Return one propeller's data, loading only its own files.

    The dataset stores each propeller as ``<id>.json`` with its CSV; the whole
    database is read only when it is already loaded for the catalog.
    """
    if _PROP_DB is not None:
        return _PROP_DB.get(prop_id)
    if prop_id not in _PROP_ENTRIES:
        prop_dir = _propeller_dir()
        json_path = prop_dir / f"{prop_id}.json" if prop_dir is not None else None
        if json_path is None or not json_path.exists():
            return None
        entry = PropellerDatabase().load_entry(json_path, prop_dir)
        if entry is None:
            return None
        if entry.metadata.id != prop_id:
            raise ValueError(f"Propeller file {json_path.name} holds '{entry.metadata.id}'.")
        _PROP_ENTRIES[prop_id] = entry
    return _PROP_ENTRIES[prop_id]
