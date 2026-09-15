"""Universal Component Symbol Extractor and Live Domain Scope Context Builder.

Exposes live component models and calculated geometric properties (e.g. main_wing.planform_area)
for equations, expressions, and constraints evaluation.
"""

from __future__ import annotations

from typing import Any

from setuav_studio.model.component import Component, GenericComponent
from setuav_studio.model.configuration import ConfigurationManager
from setuav_studio.model.parameter import ParameterResolver


def create_model_for_component(
    component: dict[str, Any],
    api: Any | None = None,
) -> Component:
    """Instantiate the registered domain model for a component."""
    if api is not None and hasattr(api, "create_component_model"):
        return api.create_component_model(component)
    return GenericComponent(component)


def build_evaluation_context(
    project_data: dict[str, Any],
    api: Any | None = None,
    config_id: str | None = None,
) -> dict[str, Any]:
    """Build complete evaluation context containing resolved parameters and live domain model objects."""
    from setuav_studio.model.scope import build_universal_scope

    return build_universal_scope(project_data, api=api, config_id=config_id)


def get_available_symbols_metadata(
    project_data: dict[str, Any],
    api: Any | None = None,
) -> dict[str, Any]:
    """Return categorized symbols with documentation and current evaluated values for UI assistance."""
    context = build_evaluation_context(project_data, api)

    constants_list: list[dict[str, Any]] = []
    components_list: list[dict[str, Any]] = []

    # 1. Global Project Parameters
    raw_params = project_data.get("parameters", {})
    for k, v in raw_params.items():
        curr_val = context.get(k, v)
        if hasattr(curr_val, "unwrap"):
            curr_val = curr_val.unwrap()
        unit = v.get("unit", "") if isinstance(v, dict) else ""
        constants_list.append(
            {
                "key": k,
                "value": curr_val,
                "unit": unit,
                "expression": f"{k}",
            }
        )

    # 2. Components and their properties
    components = project_data.get("components", [])
    if isinstance(components, list):
        for comp in components:
            if not isinstance(comp, dict):
                continue
            raw_id = str(comp.get("id") or "")
            cid = raw_id.replace("-", "_")
            cname = str(comp.get("name") or cid)
            parent_raw = str(comp.get("parent") or comp.get("attach_to") or "")
            parent_id = parent_raw.replace("-", "_") if parent_raw else None
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
                                "expression": f"{cid}.{pkey}",
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
                                "expression": f"{cid}.{pkey}",
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
                                    "expression": f"{cid}.{axis}",
                                }
                            )
                            seen_props.add(axis)

            components_list.append(
                {
                    "id": cid,
                    "raw_id": raw_id,
                    "name": cname,
                    "type": comp.get("type", ""),
                    "parent_id": parent_id,
                    "properties": props,
                }
            )

    # 3. Extension Features (e.g. Manufacturing spars, ribs, covers)
    extensions = project_data.get("extensions", {})
    if isinstance(extensions, dict):
        for ext_key, ext_val in extensions.items():
            if not isinstance(ext_val, dict):
                continue
            clean_ext_key = str(ext_key).replace("-", "_")
            features = ext_val.get("features", {})
            if isinstance(features, dict):
                for fid, feat in features.items():
                    if not isinstance(feat, dict) or feat.get("deleted") is True:
                        continue
                    clean_fid = str(feat.get("id") or fid).replace("-", "_")
                    fname = str(feat.get("name") or clean_fid)
                    ftype = str(feat.get("type") or ext_key)

                    fprops: list[dict[str, Any]] = []
                    for k, v in feat.items():
                        if isinstance(v, (int, float, str, bool)) and not k.startswith("_") and k not in ("id", "name", "type", "deleted"):
                            fprops.append(
                                {
                                    "key": k,
                                    "value": v,
                                    "expression": f"{clean_fid}.{k}",
                                }
                            )

                    components_list.append(
                        {
                            "id": clean_fid,
                            "raw_id": fid,
                            "name": fname,
                            "type": ftype,
                            "parent_id": clean_ext_key,
                            "properties": fprops,
                        }
                    )

    return {
        "constants": constants_list,
        "components": components_list,
        "context": context,
    }
