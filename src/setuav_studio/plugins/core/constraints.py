"""Constraint evaluation engine for project design rules and limits."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from setuav_studio.plugins.core.configurations import ConfigurationManager, get_by_path
from setuav_studio.plugins.core.expressions import ExpressionEvaluator
from setuav_studio.plugins.core.parameters import ParameterResolver


@dataclass
class ConstraintResult:
    """Outcome of evaluating a single constraint rule."""

    id: str
    name: str
    expression: str
    passed: bool
    severity: str = "warning"  # "warning" | "error" | "info"
    message: str = ""
    description: str = ""
    enabled: bool = True
    error: str | None = None
    resolved_values: dict[str, Any] = field(default_factory=dict)


class ConstraintChecker:
    """Evaluates mathematical design constraints against project state."""

    def __init__(
        self,
        evaluator: ExpressionEvaluator | None = None,
        resolver: ParameterResolver | None = None,
    ) -> None:
        self.evaluator = evaluator or ExpressionEvaluator()
        self.resolver = resolver or ParameterResolver(self.evaluator)

    def extract_context(
        self,
        project_data: dict[str, Any],
        config_id: str | None = None,
    ) -> dict[str, Any]:
        """Build evaluation context containing resolved parameters and component values."""
        cfg_mgr = ConfigurationManager(project_data, resolver=self.resolver)
        context: dict[str, Any] = cfg_mgr.get_effective_project_parameters(config_id)

        # Include basic component properties in context if available
        components = project_data.get("components", [])
        if isinstance(components, list):
            for comp in components:
                if not isinstance(comp, dict):
                    continue
                cid = str(comp.get("id") or "").replace("-", "_")
                if not cid:
                    continue

                # Add component mass
                if "mass" in comp:
                    context[f"{cid}_mass"] = comp["mass"]

                # Add flattened component parameters
                params = comp.get("parameters")
                if isinstance(params, dict):
                    resolved_comp = cfg_mgr.get_resolved_component(comp, config_id)
                    res_params = resolved_comp.get("parameters", {})
                    self._flatten_params(res_params, prefix=cid, out=context)

        return context

    def _flatten_params(self, params: Any, prefix: str, out: dict[str, Any]) -> None:
        """Helper to expose nested component parameters as flat variable names."""
        if isinstance(params, dict):
            for k, v in params.items():
                sanitized_k = str(k).replace("-", "_")
                new_prefix = f"{prefix}_{sanitized_k}"
                if isinstance(v, (int, float)):
                    out[new_prefix] = v
                elif isinstance(v, dict):
                    self._flatten_params(v, new_prefix, out)
                elif isinstance(v, list) and v and isinstance(v[0], dict):
                    for idx, item in enumerate(v):
                        self._flatten_params(item, f"{new_prefix}_{idx}", out)

    def check_constraint(
        self,
        constraint: dict[str, Any],
        project_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ConstraintResult:
        """Evaluate a single constraint against the project context."""
        cid = str(constraint.get("id") or "")
        name = str(constraint.get("name") or cid)
        expr = str(constraint.get("expression") or "").strip()
        severity = str(constraint.get("severity") or "warning")
        description = str(constraint.get("description") or "")
        message = str(constraint.get("message") or "")
        enabled = bool(constraint.get("enabled", True))

        if not enabled:
            return ConstraintResult(
                id=cid,
                name=name,
                expression=expr,
                passed=True,
                severity=severity,
                message=message or "Disabled",
                description=description,
                enabled=False,
            )

        if not expr:
            return ConstraintResult(
                id=cid,
                name=name,
                expression=expr,
                passed=True,
                severity=severity,
                message="Empty expression",
                description=description,
            )

        eval_ctx = dict(context if context is not None else self.extract_context(project_data))

        # Apply explicit variable mappings if specified in constraint
        var_mappings = constraint.get("variables")
        resolved_values: dict[str, Any] = {}
        if isinstance(var_mappings, dict):
            for var_name, path in var_mappings.items():
                with contextlib.suppress(Exception):
                    val = get_by_path(project_data, str(path))
                    if isinstance(val, (int, float)):
                        eval_ctx[var_name] = val

        # Evaluate boolean expression
        try:
            val = self.evaluator.evaluate(expr, eval_ctx)
            # Find symbols used in expression for reporting
            used_symbols = self.evaluator.extract_symbols(expr)
            for sym in used_symbols:
                if sym in eval_ctx:
                    resolved_values[sym] = eval_ctx[sym]

            passed = bool(val)
            res_msg = "" if passed else (message or f"Constraint violated: {expr}")
            return ConstraintResult(
                id=cid,
                name=name,
                expression=expr,
                passed=passed,
                severity=severity,
                message=res_msg,
                description=description,
                enabled=True,
                resolved_values=resolved_values,
            )
        except Exception as exc:
            return ConstraintResult(
                id=cid,
                name=name,
                expression=expr,
                passed=False,
                severity=severity,
                message=message or f"Evaluation error: {exc}",
                description=description,
                enabled=True,
                error=str(exc),
                resolved_values=resolved_values,
            )

    def check_all(
        self,
        project_data: dict[str, Any],
        config_id: str | None = None,
    ) -> list[ConstraintResult]:
        """Evaluate all constraints defined in project."""
        constraints = project_data.get("constraints", [])
        if not isinstance(constraints, list):
            return []

        context = self.extract_context(project_data, config_id)
        results: list[ConstraintResult] = []
        for c in constraints:
            if isinstance(c, dict):
                results.append(self.check_constraint(c, project_data, context))
        return results
