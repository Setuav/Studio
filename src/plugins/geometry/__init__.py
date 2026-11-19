"""Airframe Design Plugin package."""

from . import editors, engine
from .plugin import AirframeDesignPlugin
from .scene_controller import AirframeSceneController

PLUGIN = AirframeDesignPlugin()


__all__ = [
    "PLUGIN",
    "AirframeDesignPlugin",
    "AirframeSceneController",
    "editors",
    "engine",
]
