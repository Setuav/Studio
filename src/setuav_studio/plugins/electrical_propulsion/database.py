"""Propulsion component database loader bridging PyThrust datasets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pythrust.motors.database import MotorDatabase, MotorEntry
from pythrust.propellers.database import PropellerDatabase, PropellerEntry


def _find_pythrust_data_dir() -> Path:
    env_dir = os.environ.get("PYTHRUST_DATA_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)

    # Standard relative locations
    candidates = [
        Path("/home/huseyin/dev/setware/PyThrust/data"),
        Path(__file__).resolve().parents[5] / "PyThrust" / "data",
        Path.cwd().parent / "PyThrust" / "data",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


_MOTOR_DB: MotorDatabase | None = None
_PROP_DB: PropellerDatabase | None = None


def get_motor_database() -> MotorDatabase:
    global _MOTOR_DB
    if _MOTOR_DB is None:
        _MOTOR_DB = MotorDatabase()
        data_dir = _find_pythrust_data_dir() / "motors"
        if data_dir.exists():
            _MOTOR_DB.load(data_dir)
    return _MOTOR_DB


def get_propeller_database() -> PropellerDatabase:
    global _PROP_DB
    if _PROP_DB is None:
        _PROP_DB = PropellerDatabase()
        prop_dir = _find_pythrust_data_dir() / "propellers"
        apc_dir = prop_dir / "apc_202602"
        if apc_dir.exists():
            _PROP_DB.load(apc_dir)
        elif prop_dir.exists():
            _PROP_DB.load(prop_dir)
    return _PROP_DB
