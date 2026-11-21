"""Propulsion component database loader bridging PyThrust datasets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pythrust.motors.database import MotorDatabase
    from pythrust.propellers.database import PropellerDatabase, PropellerEntry


def _resolve_pythrust_data_dir() -> Path:
    """The PyThrust dataset folder: ``PYTHRUST_DATA_DIR`` if set, else the bundled one."""
    env_dir = os.environ.get("PYTHRUST_DATA_DIR")
    if env_dir:
        path = Path(env_dir)
        if not path.is_dir():
            raise FileNotFoundError(f"PYTHRUST_DATA_DIR is not a folder: {path}")
        return path
    from pythrust import dataset_dir

    return dataset_dir()


_MOTOR_DB: MotorDatabase | None = None
_PROP_DB: PropellerDatabase | None = None
_PROP_ENTRIES: dict[str, PropellerEntry] = {}


def get_motor_database() -> MotorDatabase:
    global _MOTOR_DB
    if _MOTOR_DB is None:
        # pythrust's motor database imports scipy, which slows Studio's start.
        from pythrust.motors.database import MotorDatabase

        _MOTOR_DB = MotorDatabase()
        motor_dir = _resolve_pythrust_data_dir() / "motors"
        if not motor_dir.is_dir():
            raise FileNotFoundError(f"The PyThrust dataset has no motors folder: {motor_dir}")
        _MOTOR_DB.load(motor_dir)
    return _MOTOR_DB


def _propeller_dir() -> Path:
    prop_dir = _resolve_pythrust_data_dir() / "propellers"
    apc_dir = prop_dir / "apc_202602"
    if apc_dir.is_dir():
        return apc_dir
    if prop_dir.is_dir():
        return prop_dir
    raise FileNotFoundError(f"The PyThrust dataset has no propellers folder: {prop_dir}")


def get_propeller_database() -> PropellerDatabase:
    global _PROP_DB
    if _PROP_DB is None:
        from pythrust.propellers.database import PropellerDatabase

        _PROP_DB = PropellerDatabase()
        _PROP_DB.load(_propeller_dir())
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
        json_path = prop_dir / f"{prop_id}.json"
        if not json_path.exists():
            return None
        from pythrust.propellers.database import PropellerDatabase

        entry = PropellerDatabase().load_entry(json_path, prop_dir)
        if entry is None:
            return None
        if entry.metadata.id != prop_id:
            raise ValueError(f"Propeller file {json_path.name} holds '{entry.metadata.id}'.")
        _PROP_ENTRIES[prop_id] = entry
    return _PROP_ENTRIES[prop_id]
