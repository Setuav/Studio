"""Plugin management and lifecycle system for Setuav Studio."""

from __future__ import annotations

from .installer import get_user_plugins_dir, install_plugin_archive
from .manager import PluginManager
from .plugin import PLUGIN_ENTRY_POINT_GROUP, StudioPlugin
from .requirements import (
    PluginLoadIssue,
    _candidate_sort_key,
    _plugin_sort_key,
    _version_satisfies,
)

__all__ = [
    "PLUGIN_ENTRY_POINT_GROUP",
    "PluginLoadIssue",
    "PluginManager",
    "StudioPlugin",
    "_candidate_sort_key",
    "_plugin_sort_key",
    "_version_satisfies",
    "get_user_plugins_dir",
    "install_plugin_archive",
]
