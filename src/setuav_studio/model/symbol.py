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
        for comp in components:
            if not isinstance(comp, dict):
                continue
            raw_cid = str(comp.get("id") or "")
            if not raw_cid:
                continue

            resolved_comp = cfg_mgr.get_resolved_component(comp, config_id)
            model = create_model_for_component(resolved_comp, api)

            clean_cid = raw_cid.replace("-", "_")
            context[clean_cid] = model
            if raw_cid != clean_cid:
                context[raw_cid] = model

            # Also provide flat aliases: main_wing_planform_area, etc.
            if hasattr(model, "get_exposed_properties"):
                for prop_name, prop_val in model.get_exposed_properties().items():
                    if isinstance(prop_val, (int, float, bool, str)):
                        context[f"{clean_cid}_{prop_name}"] = prop_val

            total_mass += model.mass

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
            cid = str(comp.get("id") or "").replace("-", "_")
            cname = str(comp.get("name") or cid)
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
                    "name": cname,
                    "type": comp.get("type", ""),
                    "properties": props,
                }
            )

    return {
        "constants": constants_list,
        "components": components_list,
        "context": context,
    }
