"""Project-wide Parametric Expression Evaluator for Setuav Studio.

Re-evaluates mathematical expressions across project components, transforms,
and extension data whenever global parameters or configurations change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from setuav_studio.model.expression import (
    ExpressionEvaluationError,
    ExpressionEvaluator,
    get_expression,
)
from setuav_studio.model.parameter import ParameterResolver

if TYPE_CHECKING:
    from setuav_studio.project.document import ProjectDocument

CIRCULAR_DEPENDENCY_MESSAGE = "Circular dependency: expression value does not converge"

_MISSING = object()


def recompute_project_expressions(
    project: ProjectDocument | None, api: Any | None = None
) -> list[dict[str, str]]:
    """Re-evaluate all mathematical formulas across project components and extensions.

    Evaluates against the project's current parameter and component scope and
    stores the results in the value fields. Fields whose expression fails keep
    their last valid value; fields on a non-converging dependency cycle are
    restored to their value before this recompute. Both are reported as
    diagnostics, which are also stored on ``project.expression_diagnostics``.
    """
    if project is None:
        return []

    evaluator = ExpressionEvaluator()
    raw_params = project.data.get("parameters", {})
    parameter_diagnostics = (
        ParameterResolver(evaluator).resolve_all(raw_params).diagnostics
        if isinstance(raw_params, dict)
        else []
    )

    originals: dict[tuple[int, str], Any] = {}
    passes = 0
    while True:
        current = _Pass(
            evaluator=evaluator,
            scope=project.get_scope(api=api),
            diagnostics=list(parameter_diagnostics),
            originals=originals,
        )
        current.visit_project(project.data)
        passes += 1
        # A dependency chain over N expression fields settles within N passes.
        if not current.changed or passes > current.evaluated:
            break

    for changed in current.changed:
        original = originals[(id(changed.node), changed.key)]
        if original is _MISSING:
            changed.node.pop(changed.key, None)
        else:
            changed.node[changed.key] = original
        current.diagnostics.append(changed.diagnostic(CIRCULAR_DEPENDENCY_MESSAGE))

    project.expression_diagnostics = list(current.diagnostics)
    return current.diagnostics


@dataclass
class _Field:
    node: dict[str, Any]
    key: str
    component_id: str
    path: str
    expression: str

    def diagnostic(self, message: str) -> dict[str, str]:
        return {
            "component_id": self.component_id,
            "path": self.path,
            "expression": self.expression,
            "message": message,
        }


@dataclass
class _Pass:
    """One evaluation sweep over every stored expression in the project."""

    evaluator: ExpressionEvaluator
    scope: dict[str, Any]
    diagnostics: list[dict[str, str]]
    originals: dict[tuple[int, str], Any]
    evaluated: int = 0
    changed: list[_Field] = field(default_factory=list)

    def visit_project(self, data: dict[str, Any]) -> None:
        components = data.get("components", [])
        if isinstance(components, list):
            for comp in components:
                if isinstance(comp, dict):
                    self.visit_component(comp)

        extensions = data.get("extensions", {})
        if isinstance(extensions, dict):
            for ext_name, ext_val in extensions.items():
                if isinstance(ext_val, dict):
                    self.visit_tree(ext_val, "", f"extensions.{ext_name}")

    def visit_component(self, comp: dict[str, Any]) -> None:
        component_id = str(comp.get("id") or "")
        self.visit_node(comp, component_id, "")

        tf = comp.get("transform")
        if isinstance(tf, dict):
            self.visit_node(tf.get("position"), component_id, "transform.position", ("x", "y", "z"))
            self.visit_node(
                tf.get("rotation"), component_id, "transform.rotation", ("roll", "pitch", "yaw")
            )

        params = comp.get("parameters")
        if isinstance(params, dict):
            self.visit_tree(params, component_id, "parameters")

    def visit_tree(self, node: dict[str, Any], component_id: str, path_prefix: str) -> None:
        self.visit_node(node, component_id, path_prefix)
        for key, value in list(node.items()):
            if key == "_expressions":
                continue
            nested_prefix = f"{path_prefix}.{key}" if path_prefix else str(key)
            if isinstance(value, dict):
                self.visit_tree(value, component_id, nested_prefix)
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    if isinstance(item, dict):
                        self.visit_tree(item, component_id, f"{nested_prefix}[{idx}]")

    def visit_node(
        self,
        node: Any,
        component_id: str,
        path_prefix: str,
        keys: tuple[str, ...] | None = None,
    ) -> None:
        if not isinstance(node, dict):
            return
        if keys is None:
            raw_exprs = node.get("_expressions")
            if not isinstance(raw_exprs, dict):
                return
            keys = tuple(str(k) for k in raw_exprs)

        for key in keys:
            expr = get_expression(node, key)
            if expr is None:
                continue
            self.evaluated += 1
            entry = _Field(
                node=node,
                key=key,
                component_id=component_id,
                path=f"{path_prefix}.{key}" if path_prefix else key,
                expression=expr,
            )
            try:
                value = _evaluate_numeric_expression(self.evaluator, expr, self.scope)
            except ExpressionEvaluationError as exc:
                self.diagnostics.append(entry.diagnostic(str(exc)))
                continue
            if node.get(key) != value:
                self.originals.setdefault((id(node), key), node.get(key, _MISSING))
                node[key] = value
                self.changed.append(entry)


def _evaluate_numeric_expression(
    evaluator: ExpressionEvaluator,
    expr_str: str,
    scope: dict[str, Any],
) -> float:
    """Evaluate a stored formula and require a numeric result."""
    res = evaluator.evaluate(expr_str, scope)
    if isinstance(res, bool) or not isinstance(res, (int, float)):
        raise ExpressionEvaluationError(
            f"Expression '{expr_str}' did not evaluate to a numeric value"
        )
    return float(res)


__all__ = [
    "CIRCULAR_DEPENDENCY_MESSAGE",
    "recompute_project_expressions",
]
