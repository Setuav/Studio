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
    resolver = ParameterResolver()
    cfg_mgr = ConfigurationManager(project_data, resolver=resolver)

    context: dict[str, Any] = {}

    # 1. Project Parameters & Constants
    resolved_params = cfg_mgr.get_effective_project_parameters(config_id)
    for k, v in resolved_params.items():
        context[k] = v

    # 2. Live Component Models
    components = cfg_mgr.get_materialized_components(config_id)
    total_mass = 0.0

    if isinstance(components, list):
        models_list: list[Any] = []
        for comp in components:
            if not isinstance(comp, dict):
                continue
            raw_cid = str(comp.get("id") or "")
            if not raw_cid:
                continue

            resolved_comp = cfg_mgr.get_resolved_component(comp, config_id)
            model = create_model_for_component(resolved_comp, api)
            models_list.append(model)

            clean_cid = raw_cid.replace("-", "_")
            context[clean_cid] = model
            if raw_cid != clean_cid:
                context[raw_cid] = model

            total_mass += model.mass

        # Link children to parent models
        model_by_id = {getattr(m, "id", ""): m for m in models_list if getattr(m, "id", "")}
        for model in models_list:
            parent_id = getattr(model, "parent_id", None) or (
                model.raw_data.get("attach_to") or model.raw_data.get("parent")
                if hasattr(model, "raw_data") and isinstance(model.raw_data, dict)
                else None
            )
            if parent_id and parent_id in model_by_id:
                parent_model = model_by_id[parent_id]
                if hasattr(model, "set_parent_model"):
                    model.set_parent_model(parent_model)
                if hasattr(parent_model, "add_child_model"):
                    parent_model.add_child_model(model)

        for model in models_list:
            clean_cid = model.id.replace("-", "_")
            if hasattr(model, "get_exposed_properties"):
                for prop_name, prop_val in model.get_exposed_properties().items():
                    if isinstance(prop_val, (int, float, bool, str)):
                        context[f"{clean_cid}_{prop_name}"] = prop_val

            if hasattr(model, "children") and isinstance(model.children, dict):
                for child_name, child_model in model.children.items():
                    if hasattr(child_model, "get_exposed_properties"):
                        for cp_name, cp_val in child_model.get_exposed_properties().items():
                            if isinstance(cp_val, (int, float, bool, str)):
                                context[f"{clean_cid}_{child_name}_{cp_name}"] = cp_val

    context["total_mass"] = total_mass
    context["mtow"] = resolved_params.get("mtow", total_mass)

    return context


def get_available_symbols_metadata(
    project_data: dict[str, Any],
    api: Any | None = None,
) -> dict[str, Any]:
    """Return categorized symbols with documentation and current evaluated values for UI assistance."""
    context = build_evaluation_context(project_data, api)

    constants_list: list[dict[str, Any]] = []
    components_list: list[dict[str, Any]] = []

    raw_params = project_data.get("parameters", {})
    for k, v in raw_params.items():
        curr_val = context.get(k, v)
        unit = v.get("unit", "") if isinstance(v, dict) else ""
        constants_list.append(
            {
                "key": k,
                "value": curr_val,
                "unit": unit,
                "expression": f"{k}",
            }
        )

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
            model = context.get(cid)

            props: list[dict[str, Any]] = []
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

    return {
        "constants": constants_list,
        "components": components_list,
        "context": context,
    }
