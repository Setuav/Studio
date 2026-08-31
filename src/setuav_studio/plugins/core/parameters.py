"""Project parameters resolver with dependency DAG and expression support."""

from __future__ import annotations

import copy
from typing import Any

from setuav_studio.plugins.core.expressions import ExpressionEvaluationError, ExpressionEvaluator


class ParameterResolutionError(Exception):
    """Raised when parameter resolution fails."""


class CircularDependencyError(ParameterResolutionError):
    """Raised when a cycle is detected among parameters."""

    def __init__(self, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        super().__init__(f"Circular dependency detected: {' -> '.join(cycle_path)}")


def _topological_sort(graph: dict[str, set[str]]) -> list[str]:
    """Sort dependency DAG in topological order using Kahn's algorithm."""
    adj: dict[str, set[str]] = {k: set() for k in graph}
    in_deg: dict[str, int] = dict.fromkeys(graph, 0)
    for node, deps in graph.items():
        in_deg[node] = len(deps)
        for dep in deps:
            adj[dep].add(node)

    queue = [k for k, deg in in_deg.items() if deg == 0]
    queue.sort()
    order: list[str] = []

    while queue:
        curr = queue.pop(0)
        order.append(curr)
        for neighbor in sorted(adj[curr]):
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)
                queue.sort()

    if len(order) != len(graph):
        remaining = [k for k in graph if k not in order]
        raise ParameterResolutionError(
            f"Could not determine evaluation order for parameters: {remaining}"
        )

    return order


class ParameterResolver:
    """Resolves project parameters with support for formulas and dependency DAG."""

    def __init__(self, evaluator: ExpressionEvaluator | None = None) -> None:
        self.evaluator = evaluator or ExpressionEvaluator()

    def build_dependency_graph(self, parameters: dict[str, Any]) -> dict[str, set[str]]:
        """Build dependency graph mapping each parameter to set of parameters it depends on."""
        graph: dict[str, set[str]] = {}
        for key, val in parameters.items():
            raw_val = val.get("value") if isinstance(val, dict) and "value" in val else val
            if self.evaluator.is_expression(raw_val):
                symbols = self.evaluator.extract_symbols(str(raw_val))
                # Only keep symbols (or root identifiers) that exist in parameters
                dep_set: set[str] = set()
                for sym in symbols:
                    root_sym = sym.split(".")[0]
                    if sym in parameters:
                        dep_set.add(sym)
                    elif root_sym in parameters:
                        dep_set.add(root_sym)
                graph[key] = dep_set
            else:
                graph[key] = set()
        return graph

    def detect_cycles(self, parameters: dict[str, Any]) -> list[list[str]]:
        """Detect circular dependencies among parameters using DFS."""
        graph = self.build_dependency_graph(parameters)
        visited: set[str] = set()
        rec_stack: list[str] = []
        cycles: list[list[str]] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)
            for neighbor in sorted(graph.get(node, set())):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    idx = rec_stack.index(neighbor)
                    cycles.append([*rec_stack[idx:], neighbor])
            rec_stack.pop()

        for key in sorted(graph.keys()):
            if key not in visited:
                dfs(key)

        return cycles

    def get_evaluation_order(self, parameters: dict[str, Any]) -> list[str]:
        """Compute topological sort of parameters for evaluation.

        Raises:
            CircularDependencyError: If a cycle is detected.
        """
        cycles = self.detect_cycles(parameters)
        if cycles:
            raise CircularDependencyError(cycles[0])

        graph = self.build_dependency_graph(parameters)
        return _topological_sort(graph)

    def resolve_all(
        self,
        parameters: dict[str, Any],
        extra_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve all parameters into concrete scalar/string values.

        Raises:
            ParameterResolutionError: If an expression fails or cannot be resolved.
        """
        order = self.get_evaluation_order(parameters)
        resolved: dict[str, Any] = dict(extra_context or {})

        for key in order:
            val = parameters[key]
            raw_val = val.get("value") if isinstance(val, dict) and "value" in val else val
            if self.evaluator.is_expression(raw_val):
                try:
                    res = self.evaluator.evaluate(str(raw_val), resolved)
                    resolved[key] = res
                except ExpressionEvaluationError as exc:
                    raise ParameterResolutionError(
                        f"Failed to evaluate parameter '{key}': {exc}"
                    ) from exc
            else:
                resolved[key] = raw_val

        return {k: resolved[k] for k in parameters}

    def resolve_single(self, key: str, parameters: dict[str, Any]) -> Any:
        """Resolve a single parameter, evaluating dependencies as needed."""
        if key not in parameters:
            raise KeyError(f"Parameter '{key}' not found.")
        resolved = self.resolve_all(parameters)
        return resolved[key]

    def get_dependents(self, parameters: dict[str, Any], key: str) -> set[str]:
        """Find all parameters in the dictionary that directly or indirectly depend on key."""
        graph = self.build_dependency_graph(parameters)
        # Reverse edges: dep -> dependent
        adj: dict[str, set[str]] = {k: set() for k in graph}
        for node, deps in graph.items():
            for dep in deps:
                if dep in adj:
                    adj[dep].add(node)

        dependents: set[str] = set()
        queue = list(adj.get(key, set()))
        while queue:
            curr = queue.pop(0)
            if curr not in dependents:
                dependents.add(curr)
                queue.extend(adj.get(curr, set()))
        return dependents

    def evaluate_component_value(self, value: Any, resolved_parameters: dict[str, Any]) -> Any:
        """Evaluate an arbitrary component parameter value (scalar, formula, dict, or list)."""
        if self.evaluator.is_expression(value):
            try:
                return self.evaluator.evaluate(str(value), resolved_parameters)
            except ExpressionEvaluationError as exc:
                raise ParameterResolutionError(
                    f"Failed to evaluate expression '{value}': {exc}"
                ) from exc

        if isinstance(value, dict):
            res_dict = {
                k: self.evaluate_component_value(v, resolved_parameters) for k, v in value.items()
            }
            # When resolving a *_expression entry, also assign its evaluated value to the base key
            for k, evaluated_val in list(res_dict.items()):
                if k.endswith("_expression"):
                    base_key = k[:-11]  # len("_expression") == 11
                    if base_key:
                        res_dict[base_key] = evaluated_val
            return res_dict

        if isinstance(value, list):
            return [self.evaluate_component_value(elem, resolved_parameters) for elem in value]

        return value

    def evaluate_component_parameters(
        self, component_params: dict[str, Any], resolved_parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep copy and resolve all expressions in a component's parameters dictionary."""
        params_copy = copy.deepcopy(component_params)
        return self.evaluate_component_value(params_copy, resolved_parameters)
