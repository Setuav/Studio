"""Project parameters resolver with dependency DAG and expression support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from setuav_studio.model.expression import ExpressionEvaluationError, ExpressionEvaluator


@dataclass
class ParameterResolution:
    """Resolved parameter values and diagnostics for parameters that failed."""

    values: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, str]] = field(default_factory=list)


def _raw_value(entry: Any) -> Any:
    return entry.get("value") if isinstance(entry, dict) and "value" in entry else entry


def _topological_order(graph: dict[str, set[str]]) -> list[str]:
    """Return the nodes reachable in topological order (Kahn); nodes on or behind a cycle are left out."""
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

    return order


class ParameterResolver:
    """Resolves project parameters with support for formulas and dependency DAG."""

    def __init__(self, evaluator: ExpressionEvaluator | None = None) -> None:
        self.evaluator = evaluator or ExpressionEvaluator()

    def build_dependency_graph(self, parameters: dict[str, Any]) -> dict[str, set[str]]:
        """Build dependency graph mapping each parameter to set of parameters it depends on."""
        alias_to_key: dict[str, str] = {}
        for key in parameters:
            clean = key.replace("-", "_")
            alias_to_key.setdefault(clean, key)
        for key in parameters:
            alias_to_key[key] = key

        graph: dict[str, set[str]] = {}
        for key, val in parameters.items():
            raw_val = _raw_value(val)
            if self.evaluator.is_expression(raw_val):
                symbols = self.evaluator.extract_symbols(str(raw_val))
                # Only keep symbols (or root identifiers) that exist in parameters
                dep_set: set[str] = set()
                for sym in symbols:
                    root_sym = sym.split(".")[0]
                    if sym in alias_to_key:
                        dep_set.add(alias_to_key[sym])
                    elif root_sym in alias_to_key:
                        dep_set.add(alias_to_key[root_sym])
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

    def resolve_all(
        self,
        parameters: dict[str, Any],
        base_scope: dict[str, Any] | None = None,
    ) -> ParameterResolution:
        """Resolve every parameter that can be evaluated.

        When ``base_scope`` is provided, parameter expressions may also read symbols
        from that scope (such as component models, ``total_mass``, and extensions).
        A parameter whose expression fails, that lies on a dependency cycle, or that
        depends on such a parameter is left out of ``values`` and reported in
        ``diagnostics``.
        """
        graph = self.build_dependency_graph(parameters)
        errors: dict[str, str] = {}
        for cycle in self.detect_cycles(parameters):
            message = f"Circular dependency: {' -> '.join(cycle)}"
            for node in cycle[:-1]:
                errors.setdefault(node, message)

        order = _topological_order(graph)
        ordered = set(order)
        values: dict[str, Any] = {}
        eval_scope: dict[str, Any] = dict(base_scope) if base_scope else {}
        for key in parameters:
            eval_scope.pop(key, None)
            eval_scope.pop(key.replace("-", "_"), None)

        for key in [*order, *(k for k in parameters if k not in ordered)]:
            if key in errors:
                continue
            invalid_dep = next((dep for dep in sorted(graph[key]) if dep not in values), None)
            if invalid_dep is not None:
                errors[key] = f"Depends on invalid parameter '{invalid_dep}'"
                continue
            raw_val = _raw_value(parameters[key])
            if not self.evaluator.is_expression(raw_val):
                resolved_val = raw_val
            else:
                try:
                    resolved_val = self.evaluator.evaluate(str(raw_val), eval_scope)
                except ExpressionEvaluationError as exc:
                    errors[key] = str(exc)
                    continue
            values[key] = resolved_val
            eval_scope[key] = resolved_val
            clean_key = key.replace("-", "_")
            if clean_key != key:
                eval_scope[clean_key] = resolved_val

        diagnostics = [
            {
                "component_id": "",
                "path": f"parameters.{key}",
                "expression": str(_raw_value(parameters[key])),
                "message": errors[key],
            }
            for key in parameters
            if key in errors
        ]
        return ParameterResolution(
            values={k: values[k] for k in parameters if k in values},
            diagnostics=diagnostics,
        )
