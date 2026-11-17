"""Core project document schema and relational integrity validation engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning" | "info"
    message: str
    path: str = "$"

    def __str__(self) -> str:
        return f"{self.severity.upper()}: {self.path}: {self.message}"


def validate_project(
    project: dict[str, Any],
    **_kwargs: Any,
) -> list[Issue]:
    """Validate core project document schema and relational integrity."""
    if not isinstance(project, dict):
        return [Issue("error", "Project root must be a dictionary", "$")]

    issues: list[Issue] = []

    # 1. Root fields validation
    units = project.get("units")
    if units is not None and not isinstance(units, dict):
        issues.append(Issue("error", "Project units must be an object", "$.units"))

    # 2. Components validation
    components = project.get("components", [])
    if not isinstance(components, list):
        issues.append(Issue("error", "'components' field must be an array", "$.components"))
        components = []

    component_issues, component_ids, _ = _index_components(components)
    issues.extend(component_issues)
    issues.extend(_validate_component_links(components, component_ids))
    issues.extend(_validate_component_parameters(components))

    return issues


def _index_components(
    components: list[dict[str, Any]],
) -> tuple[list[Issue], set[str], dict[str, dict[str, Any]]]:
    issues: list[Issue] = []
    component_ids: set[str] = set()
    components_by_id: dict[str, dict[str, Any]] = {}

    for index, component in enumerate(components):
        if not isinstance(component, dict):
            issues.append(
                Issue("error", "Component entry must be an object", f"$.components[{index}]")
            )
            continue

        cid = component.get("id")
        if not cid or not isinstance(cid, str) or not cid.strip():
            issues.append(
                Issue(
                    "error",
                    "Component ID is required and must be a non-empty string",
                    f"$.components[{index}].id",
                )
            )
            continue

        if cid in component_ids:
            issues.append(
                Issue("error", f"Duplicate component ID '{cid}'", f"$.components[{index}].id")
            )
        component_ids.add(cid)
        components_by_id[cid] = component

        ctype = component.get("type")
        if not ctype or not isinstance(ctype, str) or not ctype.strip():
            issues.append(
                Issue(
                    "error",
                    "Component type is required and must be a non-empty string",
                    f"$.components[{index}].type",
                )
            )

    return issues, component_ids, components_by_id


def _validate_component_links(
    components: list[dict[str, Any]],
    component_ids: set[str],
) -> list[Issue]:
    issues: list[Issue] = []
    link_map, field_issues = _component_link_map(components, component_ids, "attach_to")
    issues.extend(field_issues)
    issues.extend(_component_cycle_issues(component_ids, link_map, "Attachment"))
    return issues


def _component_link_map(
    components: list[dict[str, Any]],
    component_ids: set[str],
    field: str,
) -> tuple[dict[str, str | None], list[Issue]]:
    links: dict[str, str | None] = {}
    issues: list[Issue] = []
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            continue
        component_id = component.get("id")
        if not component_id or not isinstance(component_id, str):
            continue
        link = component.get(field)
        if link and isinstance(link, str):
            if link not in component_ids:
                issues.append(
                    Issue(
                        "error",
                        f"Unknown {field} '{link}'",
                        f"$.components[{index}].{field}",
                    )
                )
            elif link == component_id:
                issues.append(
                    Issue(
                        "error",
                        f"Component '{component_id}' cannot be its own {field}",
                        f"$.components[{index}].{field}",
                    )
                )
            links[component_id] = link
        else:
            links[component_id] = None
    return links, issues


def _component_cycle_issues(
    component_ids: set[str],
    links: dict[str, str | None],
    label: str,
) -> list[Issue]:
    issues: list[Issue] = []
    for component_id in component_ids:
        visited: set[str] = set()
        current = links.get(component_id)
        while current:
            if current in visited:
                issues.append(
                    Issue(
                        "error",
                        f"{label} cycle involving '{component_id}'",
                        "$.components",
                    )
                )
                break
            visited.add(current)
            current = links.get(current)
    return issues


def _validate_component_parameters(
    components: list[dict[str, Any]],
) -> list[Issue]:
    issues: list[Issue] = []
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            continue
        parameters = component.get("parameters")
        if parameters is not None and not isinstance(parameters, dict):
            issues.append(
                Issue(
                    "error",
                    "Component parameters must be an object",
                    f"$.components[{index}].parameters",
                )
            )
    return issues


__all__ = [
    "Issue",
    "validate_project",
]
