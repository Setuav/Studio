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
    with open(path, "r", encoding="utf-8") as f:
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

    def validate_schema(
        self, instance: dict[str, Any], schema_id: str
    ) -> list[Issue]:
        schema = self.schemas.get(schema_id)
        if schema is None:
            return [Issue("error", f"Schema '{schema_id}' not found in catalog", "$")]
        cls = validator_for(schema)
        validator = cls(schema, registry=self.registry, format_checker=FormatChecker())
        issues = []
        for err in validator.iter_errors(instance):
            path_str = "$" + "".join(
                f"[{repr(p)}]" if isinstance(p, str) else f"[{p}]" for p in err.path
            )
            issues.append(Issue("error", err.message, path_str))
        return issues


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
    """Validate a project document against the spec schema catalog.

    Returns a list of :class:`Issue` entries; empty list means valid.
    """
    catalog = catalog or get_catalog()
    issues: list[Issue] = []

    # 1. Root Schema Validation
    root_schema = catalog.schemas.get(SCHEMA_IDS["project"])
    if root_schema is None:
        return [Issue("error", "Core project schema not found in catalog", "$")]

    cls = validator_for(root_schema)
    validator = cls(root_schema, registry=catalog.registry, format_checker=FormatChecker())
    for err in sorted(validator.iter_errors(project), key=lambda e: str(e.path)):
        path_str = "$" + "".join(
            f"[{repr(p)}]" if isinstance(p, str) else f"[{p}]" for p in err.path
        )
        issues.append(Issue("error", err.message, path_str))

    components = project.get("components", [])
    assemblies = project.get("assemblies", [])

    # 2. Check unique IDs
    comp_ids: set[str] = set()
    comp_by_id: dict[str, dict[str, Any]] = {}
    for idx, comp in enumerate(components):
        cid = comp.get("id")
        if not cid:
            continue
        if cid in comp_ids:
            issues.append(
                Issue("error", f"Duplicate component ID '{cid}'", f"$.components[{idx}].id")
            )
        comp_ids.add(cid)
        comp_by_id[cid] = comp

    # 3. Check parent / attach_to references & DAG cycles
    def _validate_link_field(field: str) -> dict[str, str | None]:
        link_map: dict[str, str | None] = {}
        for idx, comp in enumerate(components):
            cid = comp.get("id")
            if not cid:
                continue
            link = comp.get(field)
            if link:
                if link not in comp_ids:
                    issues.append(
                        Issue("error", f"Unknown {field} '{link}'", f"$.components[{idx}].{field}")
                    )
                elif link == cid:
                    issues.append(
                        Issue("error", f"Component '{cid}' cannot be its own {field}", f"$.components[{idx}].{field}")
                    )
            link_map[cid] = link
        return link_map

    for field, label in (("parent", "Parent"), ("attach_to", "attach_to")):
        link_map = _validate_link_field(field)
        for cid in comp_ids:
            visited: set[str] = set()
            curr = link_map.get(cid)
            while curr:
                if curr in visited:
                    issues.append(
                        Issue("error", f"{label} cycle involving '{cid}'", "$.components")
                    )
                    break
                visited.add(curr)
                curr = link_map.get(curr)

    # 4. Component Parameter Validation against Plugin Schemas
    for idx, comp in enumerate(components):
        ctype = comp.get("type", "")
        params = comp.get("parameters")
        if not ctype or params is None:
            continue

        plugin_id = ctype.split(":")[0] if ":" in ctype else ""
        plugin = catalog.plugins.get(plugin_id)
        if not plugin or ctype not in plugin.component_types:
            continue

        schema_info = plugin.component_types[ctype]
        c_schema = schema_info["schema"]
        c_validator = validator_for(c_schema)(
            c_schema, registry=catalog.registry, format_checker=FormatChecker()
        )
        for err in c_validator.iter_errors(params):
            param_path = "".join(
                f"[{repr(p)}]" if isinstance(p, str) else f"[{p}]" for p in err.path
            )
            issues.append(
                Issue("error", err.message, f"$.components[{idx}].parameters{param_path}")
            )

    # 5. Assembly Member Validation
    asm_ids: set[str] = set()
    for idx, asm in enumerate(assemblies):
        aid = asm.get("id")
        if aid:
            if aid in asm_ids or aid in comp_ids:
                issues.append(
                    Issue("error", f"Duplicate assembly ID '{aid}'", f"$.assemblies[{idx}].id")
                )
            asm_ids.add(aid)

        atype = asm.get("type", "")
        members = asm.get("members", {})
        plugin_id = atype.split(":")[0] if ":" in atype else ""
        plugin = catalog.plugins.get(plugin_id)
        if not plugin or atype not in plugin.assembly_types:
            continue

        allowed_members = plugin.assembly_types[atype].get("member_types", {})
        for role, ref_val in members.items():
            ref_list = ref_val if isinstance(ref_val, list) else [ref_val]
            expected_types = allowed_members.get(role, [])
            for ref_id in ref_list:
                if not ref_id:
                    continue
                if ref_id not in comp_by_id:
                    issues.append(
                        Issue(
                            "error",
                            f"Assembly member '{ref_id}' for role '{role}' does not exist",
                            f"$.assemblies[{idx}].members.{role}",
                        )
                    )
                elif expected_types:
                    c = comp_by_id[ref_id]
                    actual_type = c.get("type")
                    if actual_type and actual_type not in expected_types:
                        issues.append(
                            Issue(
                                "error",
                                f"Component '{ref_id}' of type '{actual_type}' is not allowed for role '{role}' in '{atype}'",
                                f"$.assemblies[{idx}].members.{role}",
                            )
                        )

    return issues
