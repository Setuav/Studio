"""Universal Component Symbol Extractor and Live Domain Scope Context Builder.

Exposes live component models and calculated geometric properties (e.g. main_wing.planform_area)
for equations, expressions, and constraints evaluation.
"""

from __future__ import annotations

import keyword
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from setuav_studio.model.component import Component, GenericComponent
from setuav_studio.model.expression import STANDARD_SYMBOLS, rewrite_root_identifiers
from setuav_studio.model.scope import extension_features

_TURKISH_ASCII = str.maketrans(
    {
        "\u0131": "i",
        "\u0130": "i",
        "I": "i",
        "\u011f": "g",
        "\u011e": "g",
        "\u015f": "s",
        "\u015e": "s",
        "\u00e7": "c",
        "\u00c7": "c",
        "\u00f6": "o",
        "\u00d6": "o",
        "\u00fc": "u",
        "\u00dc": "u",
    }
)


def slugify_identifier(name: str, fallback: str = "component") -> str:
    """Convert a human-readable component name into a valid ASCII Python identifier."""
    folded = name.translate(_TURKISH_ASCII)
    ascii_text = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "_", fallback.lower()).strip("_") or "component"
    if slug[0].isdigit() or keyword.iskeyword(slug):
        slug = f"c_{slug}"
    return slug


@dataclass(frozen=True)
class ComponentSymbolMap:
    """Bijective mapping between canonical stored component IDs and user-facing name symbols."""

    id_to_symbol: dict[str, str]
    symbol_to_id: dict[str, str]

    def to_display(self, expression: str) -> str:
        """Translate stored component IDs in ``expression`` to current display symbols."""
        return rewrite_root_identifiers(expression, self.id_to_symbol)

    def to_storage(self, expression: str) -> str:
        """Translate display symbols in ``expression`` back to canonical stored component IDs."""
        return rewrite_root_identifiers(expression, self.symbol_to_id)


def build_component_symbol_map(project_data: dict[str, Any] | Any) -> ComponentSymbolMap:
    """Build deterministic canonical-id <-> display-symbol map from a project's components."""
    from setuav_studio.project.document import ProjectDocument

    raw_data = project_data.data if isinstance(project_data, ProjectDocument) else project_data
    p_dict: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}

    reserved: set[str] = set(STANDARD_SYMBOLS.keys()) | {"total_mass", "mtow"}
    raw_params = p_dict.get("parameters", {})
    if isinstance(raw_params, dict):
        for k in raw_params:
            reserved.add(str(k))
            reserved.add(str(k).replace("-", "_"))
    raw_exts = p_dict.get("extensions", {})
    if isinstance(raw_exts, dict):
        for k in raw_exts:
            reserved.add(str(k))
            reserved.add(str(k).replace("-", "_"))
    components = p_dict.get("components", [])
    for _cid, feature in extension_features(components):
        fid = str(feature["id"])
        reserved.add(fid)
        reserved.add(fid.replace("-", "_"))

    id_to_symbol: dict[str, str] = {}
    symbol_to_id: dict[str, str] = {}
    used: set[str] = set(reserved)

    if isinstance(components, list):
        for comp in components:
            if not isinstance(comp, dict):
                continue
            raw_id = str(comp.get("id") or "")
            if not raw_id:
                continue
            clean_id = raw_id.replace("-", "_")
            raw_name = str(comp.get("name") or "").strip()
            base = slugify_identifier(raw_name, fallback=clean_id) if raw_name else clean_id
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            id_to_symbol[clean_id] = candidate
            symbol_to_id[candidate] = clean_id
            used.add(candidate)

    return ComponentSymbolMap(id_to_symbol=id_to_symbol, symbol_to_id=symbol_to_id)


def create_model_for_component(
    component: dict[str, Any],
    api: Any | None = None,
) -> Component:
    """Instantiate the registered domain model for a component."""
    if api is not None:
        return api.create_component_model(component)
    return GenericComponent(component)


def build_component_models(components: Any, api: Any | None = None) -> list[Component]:
    """Instantiate a domain model for each component and link each to the one it attaches to."""
    if not isinstance(components, list):
        return []
    models = [
        create_model_for_component(deepcopy(comp), api)
        for comp in components
        if isinstance(comp, dict)
    ]
    model_by_id = {model.id: model for model in models if model.id}
    for model in models:
        target_model = model_by_id.get(model.attach_to or "")
        if target_model is not None:
            model.set_attach_target_model(target_model)
            target_model.add_child_model(model)
    return models


def build_evaluation_context(
    project_data: dict[str, Any],
    api: Any | None = None,
) -> dict[str, Any]:
    """Build complete evaluation context containing resolved parameters and live domain model objects."""
    from setuav_studio.model.scope import build_universal_scope

    return build_universal_scope(project_data, api=api)


def get_available_symbols_metadata(  # noqa: C901
    project_data: dict[str, Any] | Any,
    api: Any | None = None,
) -> dict[str, Any]:
    """Return categorized symbols with documentation and current evaluated values for UI assistance."""
    from setuav_studio.project.document import ProjectDocument

    raw_data = project_data.data if isinstance(project_data, ProjectDocument) else project_data
    p_dict: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}

    context = build_evaluation_context(p_dict, api)

    constants_list: list[dict[str, Any]] = []
    components_list: list[dict[str, Any]] = []

    # 1. Global Project Parameters
    from setuav_studio.units import QUANTITIES, get_quantity_for_unit

    raw_params = p_dict.get("parameters", {})
    for k, v in raw_params.items():
        curr_val = context.get(k, v)
        if hasattr(curr_val, "unwrap"):
            curr_val = curr_val.unwrap()
        quantity = ""
        unit = ""
        if isinstance(v, dict):
            quantity = str(v.get("quantity") or "")
            legacy_unit = str(v.get("unit") or "")
            if not quantity and legacy_unit:
                quantity = get_quantity_for_unit(legacy_unit) or ""
            qty_def = QUANTITIES.get(quantity)
            if qty_def is not None:
                unit = qty_def.units[qty_def.base_unit_id].symbol
            else:
                unit = legacy_unit
        constants_list.append(
            {
                "key": k,
                "value": curr_val,
                "quantity": quantity,
                "unit": unit,
                "expression": f"{k}",
            }
        )

    # 2. Components and their properties
    symbol_map = build_component_symbol_map(p_dict)
    components = p_dict.get("components", [])
    if isinstance(components, list):
        for comp in components:
            if not isinstance(comp, dict):
                continue
            raw_id = str(comp.get("id") or "")
            cid = raw_id.replace("-", "_")
            symbol = symbol_map.id_to_symbol.get(cid, cid)
            cname = str(comp.get("name") or cid)
            # Subparts are listed under the component they are part of.
            target_raw = str(comp.get("attach_to") or "")
            is_subpart = api is not None and comp.get("type") in api.subpart_types
            parent_id = target_raw.replace("-", "_") if target_raw and is_subpart else None
            proxy_or_model = context.get(cid)
            model = getattr(proxy_or_model, "_target", proxy_or_model)

            props: list[dict[str, Any]] = []
            seen_props: set[str] = set()

            # A) Exposed properties
            if model is not None and hasattr(model, "get_exposed_properties"):
                for pkey, pval in model.get_exposed_properties().items():
                    if isinstance(pval, (int, float, str, bool)):
                        props.append(
                            {
                                "key": pkey,
                                "value": pval,
                                "expression": f"{symbol}.{pkey}",
                            }
                        )
                        seen_props.add(pkey)

            # B) Parameters dictionary properties (e.g. motor KV, battery cell count)
            comp_params = comp.get("parameters", {})
            if isinstance(comp_params, dict):
                for pkey, pval in comp_params.items():
                    if pkey not in seen_props and isinstance(pval, (int, float, str, bool)):
                        props.append(
                            {
                                "key": pkey,
                                "value": pval,
                                "expression": f"{symbol}.{pkey}",
                            }
                        )
                        seen_props.add(pkey)

            # C) Transform position and rotation
            tf = comp.get("transform", {})
            if isinstance(tf, dict):
                pos = tf.get("position", {})
                if isinstance(pos, dict):
                    for axis in ("x", "y", "z"):
                        if axis not in seen_props and axis in pos:
                            props.append(
                                {
                                    "key": axis,
                                    "value": pos[axis],
                                    "expression": f"{symbol}.{axis}",
                                }
                            )
                            seen_props.add(axis)

            components_list.append(
                {
                    "id": cid,
                    "symbol": symbol,
                    "raw_id": raw_id,
                    "name": cname,
                    "type": comp.get("type", ""),
                    "parent_id": parent_id,
                    "properties": props,
                }
            )

    # 3. Plugin features stored on components, listed under their component
    for component_id, feature in extension_features(components):
        feature_id = str(feature["id"]).replace("-", "_")
        components_list.append(
            {
                "id": feature_id,
                "raw_id": str(feature["id"]),
                "name": str(feature.get("name") or feature_id),
                "type": str(feature.get("type") or ""),
                "parent_id": component_id.replace("-", "_"),
                "properties": [
                    {"key": key, "value": value, "expression": f"{feature_id}.{key}"}
                    for key, value in feature["parameters"].items()
                    if isinstance(value, (int, float, str, bool)) and not key.startswith("_")
                ],
            }
        )

    return {
        "constants": constants_list,
        "components": components_list,
        "context": context,
    }
