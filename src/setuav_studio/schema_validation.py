"""Setuav Specification schema validation (vendored).

Adapted from the ``setuav-specification`` repository's ``setuav_validator.py``.
Schemas are packaged with the application under
:mod:`setuav_studio/schemas` and loaded locally via the ``referencing``
registry (schema ``$id`` values are identifiers, never fetched remotely).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import FormatChecker
from jsonschema.validators import validator_for
from referencing import Registry, Resource

SCHEMAS_ROOT = Path(__file__).parent / "schemas"

SCHEMA_IDS = {
    "project": "https://schemas.setuav.org/core/project.schema.json",
    "plugin": "https://schemas.setuav.org/core/plugin-manifest.schema.json",
}


def load_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@dataclass(frozen=True)
class Issue:
    severity: str
    message: str
    path: str = "$"

    def __str__(self) -> str:
        return f"{self.severity.upper()}: {self.path}: {self.message}"


@dataclass
class PluginInfo:
    manifest_path: Path
    manifest: dict[str, Any]
    component_types: dict[str, dict[str, Any]]
    assembly_types: dict[str, dict[str, Any]]


class SchemaCatalog:
    def __init__(self, schemas_root: Path | None = None):
        self.schemas_root = (schemas_root or SCHEMAS_ROOT).resolve()
        self.schemas: dict[str, dict[str, Any]] = {}
        self.schema_paths: dict[str, Path] = {}
        self.plugins: dict[str, PluginInfo] = {}
        self._load_schemas()
        resources = [
            (schema_id, Resource.from_contents(schema))
            for schema_id, schema in self.schemas.items()
        ]
        self.registry = Registry().with_resources(resources)
        self._load_plugins()

    def _load_schemas(self) -> None:
        for path in sorted(self.schemas_root.rglob("*.schema.json")):
            schema = load_json(path)
            schema_id = schema.get("$id")
            if not schema_id:
                raise ValueError(f"Schema has no $id: {path}")
            if schema_id in self.schemas:
                raise ValueError(f"Duplicate schema $id {schema_id}: {path}")
            self.schemas[schema_id] = schema
            self.schema_paths[schema_id] = path.resolve()

    def _load_plugins(self) -> None:
        for path in sorted(self.schemas_root.glob("plugins/*/plugin.json")):
            manifest = load_json(path)
            plugin_id = manifest.get("id")
            if not plugin_id:
                continue

            comp_types = {}
            for comp_type, info in manifest.get("component_types", {}).items():
                schema_rel = info.get("schema")
                if schema_rel:
                    schema_path = (path.parent / schema_rel).resolve()
                    comp_types[comp_type] = {
                        "path": schema_path,
                        "schema": load_json(schema_path),
                    }

            asm_types = {}
            for asm_type, info in manifest.get("assembly_types", {}).items():
                schema_rel = info.get("schema")
                asm_entry: dict[str, Any] = {
                    "member_types": info.get("member_types", {}),
                }
                if schema_rel:
                    schema_path = (path.parent / schema_rel).resolve()
                    asm_entry["path"] = schema_path
                    asm_entry["schema"] = load_json(schema_path)
                asm_types[asm_type] = asm_entry

            self.plugins[plugin_id] = PluginInfo(
                manifest_path=path,
                manifest=manifest,
                component_types=comp_types,
                assembly_types=asm_types,
            )

    def validate_schema(self, instance: dict[str, Any], schema_id: str) -> list[Issue]:
        schema = self.schemas.get(schema_id)
        if schema is None:
            return [Issue("error", f"Schema '{schema_id}' not found in catalog", "$")]
        cls = validator_for(schema)
        validator = cls(schema, registry=self.registry, format_checker=FormatChecker())
        issues = []
        for err in validator.iter_errors(instance):
            path_str = "$" + "".join(
                f"[{p!r}]" if isinstance(p, str) else f"[{p}]" for p in err.path
            )
            issues.append(Issue("error", err.message, path_str))
        return issues

    def register_schema(self, schema: dict[str, Any], schema_id: str | None = None) -> str:
        """Register a dynamic JSON Schema into the catalog."""
        sid = schema_id or schema.get("$id")
        if not sid:
            raise ValueError("Schema must provide an '$id' field or schema_id parameter")
        self.schemas[sid] = schema
        self.registry = self.registry.with_resource(sid, Resource.from_contents(schema))
        return sid

    def register_component_type_schema(
        self,
        component_type: str,
        schema: dict[str, Any],
        plugin_id: str | None = None,
    ) -> None:
        """Register a dynamic component type schema under a plugin."""
        pid = plugin_id or (component_type.split(":")[0] if ":" in component_type else "custom")
        sid = (
            schema.get("$id")
            or f"https://schemas.setuav.org/plugins/{pid}/{component_type.replace(':', '_')}.schema.json"
        )
        schema["$id"] = sid
        self.register_schema(schema, sid)
        if pid not in self.plugins:
            self.plugins[pid] = PluginInfo(
                manifest_path=Path("dynamic"),
                manifest={"id": pid},
                component_types={},
                assembly_types={},
            )
        self.plugins[pid].component_types[component_type] = {
            "path": Path("dynamic"),
            "schema": schema,
        }


_default_catalog: SchemaCatalog | None = None


def get_catalog() -> SchemaCatalog:
    """Return the shared catalog built from the packaged schemas."""
    global _default_catalog
    if _default_catalog is None:
        _default_catalog = SchemaCatalog()
    return _default_catalog


def validate_project(
    project: dict[str, Any],
    catalog: SchemaCatalog | None = None,
) -> list[Issue]:
    """Validate a project document against the spec schema catalog."""
    catalog = catalog or get_catalog()
    root_issues, schema_available = _validate_project_schema(project, catalog)
    if not schema_available:
        return root_issues

    components = project.get("components", [])
    assemblies = project.get("assemblies", [])
    component_issues, component_ids, components_by_id = _index_components(components)
    return [
        *root_issues,
        *component_issues,
        *_validate_component_links(components, component_ids),
        *_validate_component_parameters(components, catalog),
        *_validate_assemblies(assemblies, component_ids, components_by_id, catalog),
    ]


def _validate_project_schema(
    project: dict[str, Any],
    catalog: SchemaCatalog,
) -> tuple[list[Issue], bool]:
    root_schema = catalog.schemas.get(SCHEMA_IDS["project"])
    if root_schema is None:
        return [Issue("error", "Core project schema not found in catalog", "$")], False
    validator_class = validator_for(root_schema)
    validator = validator_class(
        root_schema,
        registry=catalog.registry,
        format_checker=FormatChecker(),
    )
    issues = [
        Issue("error", error.message, _json_path(error.path))
        for error in sorted(validator.iter_errors(project), key=lambda error: str(error.path))
    ]
    return issues, True


def _json_path(path: Any, prefix: str = "$") -> str:
    suffix = "".join(f"[{part!r}]" if isinstance(part, str) else f"[{part}]" for part in path)
    return f"{prefix}{suffix}"


def _index_components(
    components: list[dict[str, Any]],
) -> tuple[list[Issue], set[str], dict[str, dict[str, Any]]]:
    issues: list[Issue] = []
    component_ids: set[str] = set()
    components_by_id: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        component_id = component.get("id")
        if not component_id:
            continue
        if component_id in component_ids:
            issues.append(
                Issue(
                    "error",
                    f"Duplicate component ID '{component_id}'",
                    f"$.components[{index}].id",
                )
            )
        component_ids.add(component_id)
        components_by_id[component_id] = component
    return issues, component_ids, components_by_id


def _validate_component_links(
    components: list[dict[str, Any]],
    component_ids: set[str],
) -> list[Issue]:
    issues: list[Issue] = []
    for field, label in (("parent", "Parent"), ("attach_to", "attach_to")):
        link_map, field_issues = _component_link_map(components, component_ids, field)
        issues.extend(field_issues)
        issues.extend(_component_cycle_issues(component_ids, link_map, label))
    return issues


def _component_link_map(
    components: list[dict[str, Any]],
    component_ids: set[str],
    field: str,
) -> tuple[dict[str, str | None], list[Issue]]:
    links: dict[str, str | None] = {}
    issues: list[Issue] = []
    for index, component in enumerate(components):
        component_id = component.get("id")
        if not component_id:
            continue
        link = component.get(field)
        if link and link not in component_ids:
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
    catalog: SchemaCatalog,
) -> list[Issue]:
    issues: list[Issue] = []
    for index, component in enumerate(components):
        component_type = component.get("type", "")
        parameters = component.get("parameters")
        schema = _component_schema(catalog, component_type)
        if parameters is None or schema is None:
            continue
        validator = validator_for(schema)(
            schema,
            registry=catalog.registry,
            format_checker=FormatChecker(),
        )
        for error in validator.iter_errors(parameters):
            path = _json_path(error.path, f"$.components[{index}].parameters")
            issues.append(Issue("error", error.message, path))
    return issues


def _component_schema(
    catalog: SchemaCatalog,
    component_type: str,
) -> dict[str, Any] | None:
    if not component_type:
        return None
    plugin_id = component_type.split(":")[0] if ":" in component_type else ""
    plugin = catalog.plugins.get(plugin_id)
    if not plugin or component_type not in plugin.component_types:
        return None
    return plugin.component_types[component_type]["schema"]


def _validate_assemblies(
    assemblies: list[dict[str, Any]],
    component_ids: set[str],
    components_by_id: dict[str, dict[str, Any]],
    catalog: SchemaCatalog,
) -> list[Issue]:
    issues: list[Issue] = []
    assembly_ids: set[str] = set()
    for index, assembly in enumerate(assemblies):
        issues.extend(_assembly_id_issues(assembly, index, assembly_ids, component_ids))
        issues.extend(_assembly_member_issues(assembly, index, components_by_id, catalog))
    return issues


def _assembly_id_issues(
    assembly: dict[str, Any],
    index: int,
    assembly_ids: set[str],
    component_ids: set[str],
) -> list[Issue]:
    assembly_id = assembly.get("id")
    if not assembly_id:
        return []
    issues = []
    if assembly_id in assembly_ids or assembly_id in component_ids:
        issues.append(
            Issue(
                "error",
                f"Duplicate assembly ID '{assembly_id}'",
                f"$.assemblies[{index}].id",
            )
        )
    assembly_ids.add(assembly_id)
    return issues


def _assembly_member_issues(
    assembly: dict[str, Any],
    index: int,
    components_by_id: dict[str, dict[str, Any]],
    catalog: SchemaCatalog,
) -> list[Issue]:
    assembly_type = assembly.get("type", "")
    plugin_id = assembly_type.split(":")[0] if ":" in assembly_type else ""
    plugin = catalog.plugins.get(plugin_id)
    if not plugin or assembly_type not in plugin.assembly_types:
        return []
    allowed_members = plugin.assembly_types[assembly_type].get("member_types", {})
    members = assembly.get("members", {})
    issues: list[Issue] = []
    for role, value in members.items():
        references = value if isinstance(value, list) else [value]
        for reference in references:
            issues.extend(
                _assembly_reference_issues(
                    reference,
                    role,
                    index,
                    assembly_type,
                    allowed_members.get(role, []),
                    components_by_id,
                )
            )
    return issues


def _assembly_reference_issues(
    reference: Any,
    role: str,
    assembly_index: int,
    assembly_type: str,
    expected_types: list[str],
    components_by_id: dict[str, dict[str, Any]],
) -> list[Issue]:
    if not reference:
        return []
    path = f"$.assemblies[{assembly_index}].members.{role}"
    if reference not in components_by_id:
        return [
            Issue(
                "error",
                f"Assembly member '{reference}' for role '{role}' does not exist",
                path,
            )
        ]
    actual_type = components_by_id[reference].get("type")
    if expected_types and actual_type and actual_type not in expected_types:
        return [
            Issue(
                "error",
                f"Component '{reference}' of type '{actual_type}' is not allowed for role '{role}' in '{assembly_type}'",
                path,
            )
        ]
    return []
