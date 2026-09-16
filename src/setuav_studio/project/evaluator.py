"""Project-wide Parametric Expression Evaluator for Setuav Studio.

Re-evaluates mathematical expressions across all project components and plugin
extensions whenever global parameters or configurations change.
"""

from __future__ import annotations

import logging
from typing import Any

from setuav_studio.model.expression import ExpressionEvaluator

logger = logging.getLogger(__name__)


def recompute_project_expressions(project: Any, api: Any | None = None) -> bool:
    """Re-evaluate all mathematical formulas across project components and plugin extensions.

    Evaluates against the project's current parameter and component scope.
    Directly updates the evaluated numeric values in the component and extension
    dictionaries so that plugins and viewers automatically read fresh values.

    Returns:
        bool: True if any values or geometries were updated, False otherwise.
    """
    if project is None or not hasattr(project, "data") or not isinstance(project.data, dict):
        return False

    try:
        scope = project.get_scope(api=api) if hasattr(project, "get_scope") else {}
    except Exception:
        logger.debug("Could not resolve project scope for parametric recompute", exc_info=True)
        scope = {}

    evaluator = ExpressionEvaluator()
    updated = False

    # 1. Recompute Components
    components = project.data.get("components", [])
    if isinstance(components, list):
        for comp in components:
            if not isinstance(comp, dict):
                continue
            if _recompute_component(comp, evaluator, scope):
                updated = True

    # 2. Recompute Plugin Extensions (e.g. Manufacturing)
    extensions = project.data.get("extensions", {})
    if isinstance(extensions, dict):
        for ext_val in extensions.values():
            if not isinstance(ext_val, dict):
                continue
            if _recompute_extension(ext_val, evaluator, scope):
                updated = True

    return updated


def _recompute_component(  # noqa: C901
    comp: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
) -> bool:
    changed = False

    # Component mass formula
    mass_expr = comp.get("mass_expression")
    if isinstance(mass_expr, str) and mass_expr.strip():
        val = _safe_eval(evaluator, mass_expr, scope)
        if val is not None and comp.get("mass") != val:
            comp["mass"] = val
            changed = True

    # Transform position and rotation expressions
    tf = comp.get("transform")
    if isinstance(tf, dict):
        pos = tf.get("position")
        if isinstance(pos, dict):
            pos_exprs = pos.get("_expressions")
            if isinstance(pos_exprs, dict):
                for axis, expr in pos_exprs.items():
                    if isinstance(expr, str) and expr.strip():
                        val = _safe_eval(evaluator, expr, scope)
                        if val is not None and pos.get(axis) != val:
                            pos[axis] = val
                            changed = True
            for axis in ("x", "y", "z"):
                ax_expr = pos.get(f"{axis}_expression")
                if isinstance(ax_expr, str) and ax_expr.strip():
                    val = _safe_eval(evaluator, ax_expr, scope)
                    if val is not None and pos.get(axis) != val:
                        pos[axis] = val
                        changed = True

        rot = tf.get("rotation")
        if isinstance(rot, dict):
            rot_exprs = rot.get("_expressions")
            if isinstance(rot_exprs, dict):
                for axis, expr in rot_exprs.items():
                    if isinstance(expr, str) and expr.strip():
                        val = _safe_eval(evaluator, expr, scope)
                        if val is not None and rot.get(axis) != val:
                            rot[axis] = val
                            changed = True
            for axis in ("roll", "pitch", "yaw"):
                ax_expr = rot.get(f"{axis}_expression")
                if isinstance(ax_expr, str) and ax_expr.strip():
                    val = _safe_eval(evaluator, ax_expr, scope)
                    if val is not None and rot.get(axis) != val:
                        rot[axis] = val
                        changed = True

    params = comp.get("parameters")
    if not isinstance(params, dict):
        return changed

    param_mass_expr = params.get("mass_expression")
    if isinstance(param_mass_expr, str) and param_mass_expr.strip():
        val = _safe_eval(evaluator, param_mass_expr, scope)
        if val is not None:
            if comp.get("mass") != val:
                comp["mass"] = val
                changed = True
            if params.get("mass") != val:
                params["mass"] = val
                changed = True

    comp_type = str(comp.get("type", "")).lower()
    if "battery" in comp_type or "battery" in str(comp.get("id", "")).lower():
        s = int(params.get("cell_count", 6))
        par = int(params.get("parallel_count", 1))
        cell_m = float(params.get("cell_mass", 130.0))
        pkg_m = float(params.get("packaging_mass", 40.0))
        total_m = (s * par * cell_m) + pkg_m
        if comp.get("mass") != total_m:
            comp["mass"] = total_m
            params["mass"] = total_m
            changed = True

    # Generic component parameter expressions
    param_exprs = params.get("_expressions")
    if isinstance(param_exprs, dict):
        for k, expr in param_exprs.items():
            if isinstance(expr, str) and expr.strip():
                val = _safe_eval(evaluator, expr, scope)
                if val is not None and params.get(k) != val:
                    params[k] = val
                    changed = True

    geom = params.get("geometry")
    if not isinstance(geom, dict):
        return changed

    # Generic geometry expressions
    geom_exprs = geom.get("_expressions")
    if isinstance(geom_exprs, dict):
        for k, expr in geom_exprs.items():
            if isinstance(expr, str) and expr.strip():
                val = _safe_eval(evaluator, expr, scope)
                if val is not None and geom.get(k) != val:
                    geom[k] = val
                    changed = True

    # Wing Planform Driver Expressions
    driver_exprs = geom.get("driver_expressions")
    if isinstance(driver_exprs, dict) and driver_exprs:
        active_drivers = geom.get("active_drivers", ["span", "root_chord", "tip_chord"])
        solved_inputs: dict[str, float] = {}
        for d in active_drivers:
            expr = driver_exprs.get(d)
            if isinstance(expr, str) and expr.strip():
                val = _safe_eval(evaluator, expr, scope)
                if val is not None:
                    solved_inputs[d] = val

        if solved_inputs:
            profiles = geom.get("profiles")
            if isinstance(profiles, list) and len(profiles) >= 2:
                try:
                    from plugins.geometry.engine.wing_driver_solver import (
                        compute_all_8_parameters,
                        solve_8_parameter_driver,
                    )
                    from plugins.geometry.engine.wing_planform_engine import (
                        compute_planform_metrics,
                        solve_wing_planform,
                    )

                    sw_loc = float(geom.get("sweep_location", 0.25))
                    is_sym = bool(geom.get("symmetric", True))
                    y_off = 0.0
                    tf = comp.get("transform")
                    if isinstance(tf, dict) and isinstance(tf.get("position"), dict):
                        y_off = float(tf["position"].get("y", 0.0))

                    metrics = compute_planform_metrics(
                        profiles, sw_loc, symmetric=is_sym, y_offset=y_off
                    )
                    p8 = compute_all_8_parameters(
                        metrics["span"],
                        metrics["root_chord"],
                        metrics["tip_chord"],
                        is_symmetric=is_sym,
                        y_offset=y_off,
                    )
                    solved = solve_8_parameter_driver(
                        active_drivers, solved_inputs, p8, is_symmetric=is_sym, y_offset=y_off
                    )
                    new_profiles, _ = solve_wing_planform(
                        "span_root_tip",
                        {
                            "span": solved["span"],
                            "root_chord": solved["root_chord"],
                            "tip_chord": solved["tip_chord"],
                            "sweep": 0.0,
                        },
                        profiles,
                        sw_loc,
                        symmetric=is_sym,
                        y_offset=y_off,
                    )
                    if new_profiles != profiles:
                        profiles.clear()
                        profiles.extend(new_profiles)
                        changed = True
                except Exception:
                    logger.debug(
                        "Failed wing planform recompute for %s", comp.get("id"), exc_info=True
                    )

    # Fuselage Sections Profile Expressions
    segments = geom.get("segments")
    if isinstance(segments, list):
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            sections = seg.get("sections")
            if isinstance(sections, list):
                for sec in sections:
                    if not isinstance(sec, dict):
                        continue
                    prof = sec.get("profile")
                    if isinstance(prof, dict):
                        for k, v in list(prof.items()):
                            if k.endswith("_expression") and isinstance(v, str):
                                base_k = k[:-11]
                                val = _safe_eval(evaluator, v, scope)
                                if val is not None and prof.get(base_k) != val:
                                    prof[base_k] = val
                                    changed = True

    # Control Surfaces / Wing Angles Expressions
    for k, v in list(geom.items()):
        if k.endswith("_expression") and isinstance(v, str):
            base_k = k[:-11]
            val = _safe_eval(evaluator, v, scope)
            if val is not None and geom.get(base_k) != val:
                geom[base_k] = val
                changed = True

    return changed


def _recompute_extension(
    ext: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
) -> bool:
    """Generic recursive expression recomputation across plugin extensions without hardcoding."""
    return _recompute_generic_dict(ext, evaluator, scope)


def _recompute_generic_dict(
    d: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
) -> bool:
    changed = False

    # 1. Check '_expressions' sub-dictionary
    exprs = d.get("_expressions")
    if isinstance(exprs, dict):
        for k, expr in exprs.items():
            if isinstance(expr, str) and expr.strip():
                val = _safe_eval(evaluator, expr, scope)
                if val is not None and d.get(k) != val:
                    d[k] = val
                    changed = True

    # 2. Check '{k}_expression' and nested dicts/lists
    for k, v in list(d.items()):
        if k == "_expressions":
            continue
        if k.endswith("_expression") and isinstance(v, str) and v.strip():
            base_k = k[:-11]
            val = _safe_eval(evaluator, v, scope)
            if val is not None and d.get(base_k) != val:
                d[base_k] = val
                changed = True
        elif isinstance(v, dict):
            if _recompute_generic_dict(v, evaluator, scope):
                changed = True
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and _recompute_generic_dict(item, evaluator, scope):
                    changed = True

    return changed


def _safe_eval(
    evaluator: ExpressionEvaluator,
    expr_str: str,
    scope: dict[str, Any],
) -> float | None:
    clean = expr_str.lstrip("=").strip()
    if not clean:
        return None
    try:
        res = evaluator.evaluate(clean, scope)
        if isinstance(res, (int, float)):
            return float(res)
    except Exception:
        pass
    return None
