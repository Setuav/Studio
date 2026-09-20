"""Project-wide Parametric Expression Evaluator for Setuav Studio.

Re-evaluates mathematical expressions across project components, transforms,
and extension data whenever global parameters or configurations change.
"""

from __future__ import annotations

import logging
from typing import Any

from setuav_studio.model.expression import ExpressionEvaluator

logger = logging.getLogger(__name__)


def recompute_project_expressions(project: Any, api: Any | None = None) -> bool:
    """Re-evaluate all mathematical formulas across project components and extensions.

    Evaluates against the project's current parameter and component scope.
    Directly updates the evaluated numeric values while preserving the original
    expression definitions.

    Returns:
        bool: True if any values were updated, False otherwise.
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
            if isinstance(comp, dict) and _recompute_component(comp, evaluator, scope):
                updated = True

    # 2. Recompute Plugin Extensions
    extensions = project.data.get("extensions", {})
    if isinstance(extensions, dict):
        for ext_val in extensions.values():
            if isinstance(ext_val, dict) and _recompute_generic_dict(ext_val, evaluator, scope):
                updated = True

    return updated


def _recompute_component(
    comp: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
) -> bool:
    """Recompute expressions for a single component (mass, transform, parameters)."""
    changed = False

    # 1. Component mass expression (top-level)
    mass_expr = comp.get("mass_expression")
    if isinstance(mass_expr, str) and mass_expr.strip():
        val = _safe_eval(evaluator, mass_expr, scope)
        if val is not None and comp.get("mass") != val:
            comp["mass"] = val
            changed = True

    # 2. Transform position and rotation expressions
    tf = comp.get("transform")
    if isinstance(tf, dict):
        if _recompute_transform_node(tf.get("position"), evaluator, scope, ("x", "y", "z")):
            changed = True
        if _recompute_transform_node(
            tf.get("rotation"), evaluator, scope, ("roll", "pitch", "yaw")
        ):
            changed = True

    # 3. Parameters (and all nested structures under parameters)
    params = comp.get("parameters")
    if isinstance(params, dict):
        # Parameters-level mass_expression
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

        # Generic parameter expressions (handles _expressions dict, *_expression fields, nested dicts/lists)
        if _recompute_generic_dict(params, evaluator, scope):
            changed = True

    return changed


def _recompute_transform_node(
    node: Any,
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
    axes: tuple[str, ...],
) -> bool:
    """Recompute position or rotation transform dictionary."""
    if not isinstance(node, dict):
        return False

    changed = False
    # Check _expressions dictionary on transform node
    exprs = node.get("_expressions")
    if isinstance(exprs, dict):
        for axis in axes:
            expr = exprs.get(axis)
            if isinstance(expr, str) and expr.strip():
                val = _safe_eval(evaluator, expr, scope)
                if val is not None and node.get(axis) != val:
                    node[axis] = val
                    changed = True

    # Check {axis}_expression fields on transform node
    for axis in axes:
        expr = node.get(f"{axis}_expression")
        if isinstance(expr, str) and expr.strip():
            val = _safe_eval(evaluator, expr, scope)
            if val is not None and node.get(axis) != val:
                node[axis] = val
                changed = True

    return changed


def _recompute_generic_dict(
    d: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
) -> bool:
    """Recursively recompute expressions in arbitrary nested dictionary or list structures."""
    changed = False

    # 1. Evaluate _expressions mapping if present
    exprs = d.get("_expressions")
    if isinstance(exprs, dict):
        for k, expr in exprs.items():
            if isinstance(expr, str) and expr.strip():
                val = _safe_eval(evaluator, expr, scope)
                if val is not None and d.get(k) != val:
                    d[k] = val
                    changed = True

    # 2. Evaluate {key}_expression fields and recurse into nested dicts / lists
    for k, v in list(d.items()):
        if k == "_expressions":
            continue

        if k.endswith("_expression") and isinstance(v, str) and v.strip():
            target_key = k[:-11]
            val = _safe_eval(evaluator, v, scope)
            if val is not None and d.get(target_key) != val:
                d[target_key] = val
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
    """Safely evaluate a mathematical expression string within a given scope."""
    clean = expr_str.lstrip("=").strip()
    if not clean:
        return None
    try:
        res = evaluator.evaluate(clean, scope)
        if isinstance(res, (int, float)):
            return float(res)
    except Exception as exc:
        logger.debug("Failed evaluating expression '%s': %s", expr_str, exc)
    return None


__all__ = [
    "recompute_project_expressions",
]
