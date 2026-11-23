from collections.abc import Collection, Sequence
from dataclasses import dataclass

from packaging.version import InvalidVersion, Version

from .plugin import StudioPlugin


@dataclass(frozen=True)
class PluginLoadIssue:
    source: str
    message: str


def _plugin_sort_key(plugin: StudioPlugin) -> str:
    return plugin.id


def _plugin_requires(plugin: object) -> tuple[str, ...]:
    raw = getattr(plugin, "requires", ())
    if isinstance(raw, str):
        return (raw,) if raw.strip() else ()
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return ()
    seen: set[str] = set()
    ordered: list[str] = []
    for item in raw:
        dep = str(item).strip()
        if dep and dep not in seen:
            seen.add(dep)
            ordered.append(dep)
    return tuple(ordered)


def _resolve_plugin_dependencies(
    plugins: Sequence[StudioPlugin],
    by_id: dict[str, StudioPlugin],
    active_set: set[str],
    disabled_set: set[str],
) -> tuple[dict[str, set[str]], dict[str, str]]:
    provider_to_plugin: dict[str, str] = {}
    for plugin in plugins:
        provides = getattr(plugin, "provides", {})
        if isinstance(provides, dict):
            for capability_id in provides:
                provider_to_plugin.setdefault(str(capability_id), plugin.id)

    errors: dict[str, str] = {}
    deps_by_id: dict[str, set[str]] = {}
    for plugin in plugins:
        resolved_deps: set[str] = set()
        for dep in _plugin_requires(plugin):
            if dep in active_set:
                continue
            target_id = dep if dep in by_id else provider_to_plugin.get(dep)
            if target_id is None:
                reason = (
                    "Requires disabled plugin" if dep in disabled_set else "Missing required plugin"
                )
                errors.setdefault(plugin.id, f"{reason}: {dep}")
                continue
            if target_id == plugin.id:
                errors.setdefault(plugin.id, f"Circular plugin dependency: {plugin.id}")
                continue
            resolved_deps.add(target_id)
        deps_by_id[plugin.id] = resolved_deps

    changed = True
    while changed:
        changed = False
        for pid, deps in deps_by_id.items():
            if pid in errors:
                continue
            bad_dep = next((dep for dep in sorted(deps) if dep in errors), None)
            if bad_dep is not None:
                errors[pid] = f"Depends on unavailable plugin: {bad_dep}"
                changed = True

    return deps_by_id, errors


def _kahn_order(valid_ids: set[str], deps_by_id: dict[str, set[str]]) -> list[str]:
    adj: dict[str, set[str]] = {pid: set() for pid in valid_ids}
    in_deg: dict[str, int] = dict.fromkeys(valid_ids, 0)
    for pid in valid_ids:
        for dep in deps_by_id[pid]:
            if dep in valid_ids:
                adj[dep].add(pid)
                in_deg[pid] += 1

    queue = sorted(pid for pid, deg in in_deg.items() if deg == 0)
    ordered_ids: list[str] = []
    while queue:
        curr = queue.pop(0)
        ordered_ids.append(curr)
        for neighbor in sorted(adj[curr]):
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)
                queue.sort()
    return ordered_ids


def _order_plugins_by_dependencies(
    plugins: Sequence[StudioPlugin],
    *,
    already_active: Collection[str] = (),
    disabled_ids: Collection[str] = (),
) -> tuple[list[StudioPlugin], dict[str, str]]:
    """Topologically order plugins by ``requires`` with alphabetical ID tie-breaking.

    Returns ``(ordered_plugins, errors_by_plugin_id)`` where plugins with missing,
    disabled, or cyclic dependencies are omitted from ``ordered_plugins`` and
    explained in ``errors_by_plugin_id``.
    """
    by_id: dict[str, StudioPlugin] = {plugin.id: plugin for plugin in plugins}
    deps_by_id, errors = _resolve_plugin_dependencies(
        plugins, by_id, set(already_active), set(disabled_ids)
    )
    valid_ids = {pid for pid in by_id if pid not in errors}
    ordered_ids = _kahn_order(valid_ids, deps_by_id)
    for pid in sorted(valid_ids - set(ordered_ids)):
        errors[pid] = f"Circular plugin dependency involving '{pid}'"
    return [by_id[pid] for pid in ordered_ids], errors


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
    "_order_plugins_by_dependencies",
    "_parse_version",
    "_plugin_requires",
    "_plugin_sort_key",
    "_version_satisfies",
]
