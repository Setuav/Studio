from dataclasses import dataclass

from packaging.version import InvalidVersion, Version

from setuav_studio_sdk.plugin import StudioPlugin


@dataclass(frozen=True)
class PluginLoadIssue:
    source: str
    message: str


def _candidate_sort_key(candidate: object, source: str) -> tuple[int, str, object]:
    priority = getattr(candidate, "priority", 100)
    if not isinstance(priority, int):
        priority = 100
    plugin_id = getattr(candidate, "id", source)
    return priority, str(plugin_id), candidate


def _plugin_sort_key(plugin: StudioPlugin) -> tuple[int, str]:
    priority = getattr(plugin, "priority", 100)
    if not isinstance(priority, int):
        priority = 100
    return priority, plugin.id


def _version_satisfies(installed: str, requirement: str) -> bool:
    installed_version = _parse_version(installed)
    if installed_version is None:
        return False
    if requirement in {"", "*"}:
        return True
    if requirement.startswith("^"):
        minimum = _parse_version(requirement[1:])
        if minimum is None or installed_version < minimum:
            return False
        major, minor, patch = [*minimum.release, 0, 0, 0][:3]
        if major > 0:
            maximum = f"{major + 1}.0.0"
        elif minor > 0:
            maximum = f"0.{minor + 1}.0"
        else:
            maximum = f"0.0.{patch + 1}"
        max_v = _parse_version(maximum)
        return max_v is not None and installed_version < max_v
    expected = _parse_version(requirement)
    return expected is not None and expected == installed_version


def _parse_version(value: str) -> Version | None:
    try:
        return Version(value)
    except InvalidVersion:
        return None


__all__ = [
    "PluginLoadIssue",
    "_candidate_sort_key",
    "_parse_version",
    "_plugin_sort_key",
    "_version_satisfies",
]
