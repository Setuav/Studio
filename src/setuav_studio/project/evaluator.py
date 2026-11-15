"""Project-wide Parametric Expression Evaluator for Setuav Studio.

Re-evaluates mathematical expressions across project components, transforms,
and extension data whenever global parameters or configurations change.
"""

from __future__ import annotations

import logging
from typing import Any

from setuav_studio.model.expression import ExpressionEvaluator, get_expression

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


def _recompute_node_expressions(
    node: Any,
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
    keys: tuple[str, ...] | None = None,
) -> bool:
    """Recompute evaluated values for stored expressions on a mapping node."""
    if not isinstance(node, dict):
        return False
    if keys is None:
        raw_exprs = node.get("_expressions")
        if not isinstance(raw_exprs, dict):
            return False
        target_keys = tuple(str(k) for k in raw_exprs)
    else:
        target_keys = keys

    changed = False
    for key in target_keys:
        expr = get_expression(node, key)
        if expr is not None:
            val = _safe_eval(evaluator, expr, scope)
            if val is not None and node.get(key) != val:
                node[key] = val
                changed = True
    return changed


def _recompute_component(
    comp: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
) -> bool:
    """Recompute expressions for a single component (mass, transform, parameters)."""
    changed = _recompute_node_expressions(comp, evaluator, scope)

    # 2. Transform position and rotation expressions
    tf = comp.get("transform")
    if isinstance(tf, dict):
        if _recompute_node_expressions(tf.get("position"), evaluator, scope, ("x", "y", "z")):
            changed = True
        if _recompute_node_expressions(
            tf.get("rotation"), evaluator, scope, ("roll", "pitch", "yaw")
        ):
            changed = True

    # 3. Parameters (and all nested structures under parameters)
    params = comp.get("parameters")
    if isinstance(params, dict) and _recompute_generic_dict(params, evaluator, scope):
        changed = True

    return changed


def _recompute_generic_dict(
    d: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
) -> bool:
    """Recursively recompute expressions in arbitrary nested dictionary or list structures."""
    changed = _recompute_node_expressions(d, evaluator, scope)

    for k, v in list(d.items()):
        if k == "_expressions":
            continue

        if isinstance(v, dict):
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
