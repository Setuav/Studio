"""Project-wide Parametric Expression Evaluator for Setuav Studio.

Re-evaluates mathematical expressions across project components, transforms,
and extension data whenever global parameters or configurations change.
"""

from __future__ import annotations

from typing import Any

from setuav_studio.model.expression import (
    ExpressionEvaluationError,
    ExpressionEvaluator,
    get_expression,
)


def recompute_project_expressions(project: Any, api: Any | None = None) -> list[dict[str, str]]:
    """Re-evaluate all mathematical formulas across project components and extensions.

    Evaluates against the project's current parameter and component scope.
    Directly updates the evaluated numeric values while preserving the original
    expression definitions and leaving failed fields at their last valid value.

    Returns:
        List of diagnostic dicts for any failed expressions.
    """
    from setuav_studio.project.document import ProjectDocument

    if project is None:
        return []

    evaluator = ExpressionEvaluator()
    components = project.data.get("components", [])
    extensions = project.data.get("extensions", {})
    max_passes = len(components) + 1 if isinstance(components, list) else 1

    diagnostics: list[dict[str, str]] = []
    for _ in range(max_passes):
        scope = project.get_scope(api=api)
        changed = False
        diagnostics = []

        if isinstance(components, list):
            for comp in components:
                if isinstance(comp, dict) and _recompute_component(
                    comp, evaluator, scope, diagnostics
                ):
                    changed = True

        if isinstance(extensions, dict):
            for ext_name, ext_val in extensions.items():
                if isinstance(ext_val, dict) and _recompute_generic_dict(
                    ext_val,
                    evaluator,
                    scope,
                    component_id="",
                    path_prefix=f"extensions.{ext_name}",
                    diagnostics=diagnostics,
                ):
                    changed = True

        if not changed:
            break

    if isinstance(project, ProjectDocument):
        project.expression_diagnostics = list(diagnostics)

    return diagnostics


def _evaluate_numeric_expression(
    evaluator: ExpressionEvaluator,
    expr_str: str,
    scope: dict[str, Any],
) -> float:
    """Evaluate a stored formula and require a finite numeric result."""
    res = evaluator.evaluate(expr_str, scope)
    if isinstance(res, bool) or not isinstance(res, (int, float)):
        raise ExpressionEvaluationError(
            f"Expression '{expr_str}' did not evaluate to a numeric value"
        )
    return float(res)


def _recompute_node_expressions(
    node: Any,
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
    *,
    component_id: str,
    path_prefix: str,
    diagnostics: list[dict[str, str]],
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
        if expr is None:
            continue
        field_path = f"{path_prefix}.{key}" if path_prefix else key
        try:
            val = _evaluate_numeric_expression(evaluator, expr, scope)
        except ExpressionEvaluationError as exc:
            diagnostics.append(
                {
                    "component_id": component_id,
                    "path": field_path,
                    "expression": expr,
                    "message": str(exc),
                }
            )
            continue
        if node.get(key) != val:
            node[key] = val
            changed = True
    return changed


def _recompute_component(
    comp: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
    diagnostics: list[dict[str, str]],
) -> bool:
    """Recompute expressions for a single component (mass, transform, parameters)."""
    component_id = str(comp.get("id") or "")
    changed = _recompute_node_expressions(
        comp,
        evaluator,
        scope,
        component_id=component_id,
        path_prefix="",
        diagnostics=diagnostics,
    )

    # Transform position and rotation expressions
    tf = comp.get("transform")
    if isinstance(tf, dict):
        if _recompute_node_expressions(
            tf.get("position"),
            evaluator,
            scope,
            component_id=component_id,
            path_prefix="transform.position",
            diagnostics=diagnostics,
            keys=("x", "y", "z"),
        ):
            changed = True
        if _recompute_node_expressions(
            tf.get("rotation"),
            evaluator,
            scope,
            component_id=component_id,
            path_prefix="transform.rotation",
            diagnostics=diagnostics,
            keys=("roll", "pitch", "yaw"),
        ):
            changed = True

    # Parameters (and all nested structures under parameters)
    params = comp.get("parameters")
    if isinstance(params, dict) and _recompute_generic_dict(
        params,
        evaluator,
        scope,
        component_id=component_id,
        path_prefix="parameters",
        diagnostics=diagnostics,
    ):
        changed = True

    return changed


def _recompute_generic_dict(
    d: dict[str, Any],
    evaluator: ExpressionEvaluator,
    scope: dict[str, Any],
    *,
    component_id: str,
    path_prefix: str,
    diagnostics: list[dict[str, str]],
) -> bool:
    """Recursively recompute expressions in arbitrary nested dictionary or list structures."""
    changed = _recompute_node_expressions(
        d,
        evaluator,
        scope,
        component_id=component_id,
        path_prefix=path_prefix,
        diagnostics=diagnostics,
    )

    for k, v in list(d.items()):
        if k == "_expressions":
            continue
        nested_prefix = f"{path_prefix}.{k}" if path_prefix else str(k)
        if isinstance(v, dict):
            if _recompute_generic_dict(
                v,
                evaluator,
                scope,
                component_id=component_id,
                path_prefix=nested_prefix,
                diagnostics=diagnostics,
            ):
                changed = True
        elif isinstance(v, list):
            for idx, item in enumerate(v):
                if isinstance(item, dict) and _recompute_generic_dict(
                    item,
                    evaluator,
                    scope,
                    component_id=component_id,
                    path_prefix=f"{nested_prefix}[{idx}]",
                    diagnostics=diagnostics,
                ):
                    changed = True

    return changed


__all__ = [
    "recompute_project_expressions",
]
